"""通过 TikTok videoDetail 刷新素材封面并保存到 MinIO。"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path

import tomllib

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "app"))

import httpx
from common.logging import get_logger
from core.config import SchedulerConfig
from go_rpc import RpcClient
from parser.tiktok.videoDetail import parse_video_detail
from services.video_download.naming import cover_object_name
from sqlalchemy import text
from storage import MinioDB, SQLAlchemyDB

logger = get_logger(__file__)

SELECT_MATERIALS_SQL = text(
    """
    SELECT content_id
    FROM t_material_clean
    WHERE platform = 'tiktok' AND is_delete = 0
    ORDER BY id
    LIMIT :limit OFFSET :offset
    """
)


def extract_cover_url(detail: dict, content_id: str) -> str:
    for item in parse_video_detail(detail):
        if (
            item.get("datatype") == "content"
            and str(item.get("content_id")) == str(content_id)
            and item.get("pic")
        ):
            return str(item["pic"])
    raise ValueError("videoDetail 响应中没有目标视频封面")


async def fetch_material_ids(db: SQLAlchemyDB, *, limit: int, offset: int) -> list[str]:
    async with db.asession_scope() as session:
        rows = await session.scalars(
            SELECT_MATERIALS_SQL, {"limit": limit, "offset": offset}
        )
        return [str(value) for value in rows.all()]


async def run(
    config_path: str,
    *,
    bucket: str,
    limit: int,
    offset: int,
    concurrency: int,
    force: bool,
) -> int:
    config = SchedulerConfig.from_toml(config_path)
    with open(config_path, "rb") as file:
        raw = tomllib.load(file)
    minio_config = raw["minio"]
    proxy = raw.get("proxy", {}).get("url") or None
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    minio = MinioDB(
        endpoint=f"{minio_config['host']}:{minio_config['port']}",
        access_key=minio_config["username"],
        secret_key=minio_config["password"],
        secure=bool(minio_config.get("secure", False)),
        amode=True,
    )
    rpc = RpcClient(
        base_url=config.rpc_base_url, token=config.rpc_token, timeout=config.rpc_timeout
    )
    client = httpx.AsyncClient(
        proxy=proxy,
        trust_env=False,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10),
        headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"},
    )
    await db.aconnect()
    try:
        content_ids = await fetch_material_ids(db, limit=limit, offset=offset)
        await minio.amake_bucket(bucket)
        semaphore = asyncio.Semaphore(max(1, concurrency))
        succeeded = failed = skipped = 0

        async def worker(content_id: str) -> None:
            nonlocal succeeded, failed, skipped
            async with semaphore:
                object_name = cover_object_name(content_id)
                try:
                    if not force and await minio.aobject_exists(bucket, object_name):
                        skipped += 1
                        return
                    detail = await rpc.invoke(
                        "tiktok", "videoDetail", {"itemId": content_id}
                    )
                    cover_url = extract_cover_url(detail, content_id)
                    response = await client.get(cover_url)
                    response.raise_for_status()
                    if not response.content:
                        raise ValueError("下载到的封面为空")
                    content_type = response.headers.get(
                        "content-type", "image/jpeg"
                    ).split(";", 1)[0]
                    if not content_type.startswith("image/"):
                        raise ValueError(f"封面响应类型无效: {content_type}")
                    await minio.aput_object(
                        bucket,
                        object_name,
                        io.BytesIO(response.content),
                        len(response.content),
                        content_type=content_type,
                    )
                    succeeded += 1
                    logger.info(
                        "封面保存成功 [tiktok] %s -> %s/%s",
                        content_id,
                        bucket,
                        object_name,
                    )
                except Exception as error:
                    failed += 1
                    logger.error("封面刷新失败 [tiktok] %s: %s", content_id, error)

        await asyncio.gather(*(worker(content_id) for content_id in content_ids))
        logger.info("封面刷新汇总: 成功=%d 跳过=%d 失败=%d", succeeded, skipped, failed)
        return succeeded
    finally:
        await client.aclose()
        await rpc.close()
        await minio.aclose()
        await db.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 TikTok videoDetail 刷新素材封面")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--bucket", default="tiktok")
    parser.add_argument("--limit", type=int, default=0, help="最大处理数，0=不限制")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="覆盖已存在封面")
    args = parser.parse_args()
    asyncio.run(
        run(
            args.config,
            bucket=args.bucket,
            limit=args.limit if args.limit > 0 else 9_999_999,
            offset=args.offset,
            concurrency=args.concurrency,
            force=args.force,
        )
    )


if __name__ == "__main__":
    main()
