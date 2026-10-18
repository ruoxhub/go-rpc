"""用 TikTok videoDetail 刷新 CDN 地址并重试下载失败的视频。

候选记录来自 t_material_clean、t_busi_content 与 t_busi_media 的联查，仅处理
仍处于 graded 且内容尚未下载的 TikTok 素材。每条记录先调用 videoDetail
获取新地址，再下载并上传 MinIO；成功后同步更新内容与素材状态。

用法:
    python scripts/retry_failed_video_downloads.py
    python scripts/retry_failed_video_downloads.py --limit 100 --concurrency 4
    python scripts/retry_failed_video_downloads.py --no-proxy
"""

from __future__ import annotations

import argparse
import asyncio
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
from parser.tiktok._common import get_video_url
from services.video_download import VideoDownloadService
from sqlalchemy import text
from storage import MinioDB, SQLAlchemyDB

logger = get_logger(__file__)


SELECT_FAILED_SQL = text(
    """
    SELECT mc.id AS mc_id,
           mc.content_id
    FROM t_material_clean mc
    INNER JOIN t_busi_content c
      ON c.platform = mc.platform
     AND c.content_id = mc.content_id
    WHERE mc.platform = 'tiktok'
      AND mc.clean_status = 'graded'
      AND mc.is_delete = 0
      AND mc.grade_rank BETWEEN 1 AND :min_grade
    ORDER BY mc.grade_rank ASC, mc.id ASC
    LIMIT :limit OFFSET :offset
    """
)


def extract_media_urls(detail: dict, content_id: str) -> tuple[str, str, str]:
    """从 videoDetail 响应中提取视频、音频和封面地址。"""
    item_info = detail.get("itemInfo")
    item = item_info.get("itemStruct") if isinstance(item_info, dict) else None
    if not isinstance(item, dict):
        item_list = detail.get("itemList")
        item = item_list[0] if isinstance(item_list, list) and item_list else detail
    if isinstance(item, dict) and str(item.get("id")) == str(content_id):
        video = item.get("video") or {}
        music = item.get("music") or {}
        video_url = get_video_url(video) if isinstance(video, dict) else None
        music_url = music.get("playUrl") if isinstance(music, dict) else None
        pic_url = video.get("cover") or video.get("dynamicCover")
        if video_url and music_url and pic_url:
            return str(video_url), str(music_url), str(pic_url)
    raise ValueError("videoDetail 响应缺少视频、音频或封面地址")


def extract_video_url(detail: dict, content_id: str) -> str:
    """兼容旧调用，仅返回刷新后的视频地址。"""
    item_info = detail.get("itemInfo")
    item = item_info.get("itemStruct") if isinstance(item_info, dict) else None
    if isinstance(item, dict) and str(item.get("id")) == str(content_id):
        video = item.get("video") or {}
        video_url = get_video_url(video) if isinstance(video, dict) else None
        if video_url:
            return str(video_url)
    raise ValueError("videoDetail 响应中没有目标视频的 CDN 地址")


def _derive_ext(url: str) -> str:
    """兼容旧调用；新下载路径固定由 download_media 管理。"""
    suffix = Path(url.split("?", 1)[0]).suffix
    return suffix if 2 <= len(suffix) <= 5 else ".mp4"


async def fetch_failed_rows(
    db: SQLAlchemyDB,
    *,
    min_grade: int,
    limit: int,
    offset: int,
) -> list[dict]:
    async with db.asession_scope() as session:
        result = await session.execute(
            SELECT_FAILED_SQL,
            {"min_grade": min_grade, "limit": limit, "offset": offset},
        )
        return [dict(row) for row in result.mappings().all()]


async def mark_downloaded(
    db: SQLAlchemyDB,
    *,
    mc_id: int,
    content_id: str,
    video_url: str,
    music_url: str,
    pic_url: str,
) -> None:
    async with db.asession_scope() as session:
        await session.execute(
            text(
                "UPDATE t_busi_content "
                "SET is_download = true, updated_time = now(), "
                "extend = jsonb_set(jsonb_set(jsonb_set(COALESCE(NULLIF(extend, ''), '{}')::jsonb, "
                "'{video_url}', to_jsonb(CAST(:video_url AS text))), "
                "'{music_url}', to_jsonb(CAST(:music_url AS text))), "
                "'{pic_url}', to_jsonb(CAST(:pic_url AS text)))::text "
                "WHERE platform = 'tiktok' AND content_id = :content_id"
            ),
            {
                "content_id": content_id,
                "video_url": video_url,
                "music_url": music_url,
                "pic_url": pic_url,
            },
        )
        await session.execute(
            text(
                "UPDATE t_material_clean "
                "SET clean_status = 'downloaded', updated_time = now() "
                "WHERE id = :mc_id"
            ),
            {"mc_id": mc_id},
        )


def _load_runtime_options(config_path: str) -> tuple[dict, str | None]:
    with open(config_path, "rb") as file:
        raw = tomllib.load(file)
    if "minio" not in raw:
        raise ValueError(f"配置文件缺少 [minio]：{config_path}")
    return raw["minio"], raw.get("proxy", {}).get("url") or None


async def run(
    config_path: str,
    *,
    min_grade: int,
    bucket: str,
    limit: int,
    offset: int,
    concurrency: int,
    rps: float,
    no_proxy: bool,
) -> int:
    config = SchedulerConfig.from_toml(config_path)
    minio_config, configured_proxy = _load_runtime_options(config_path)
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
        base_url=config.rpc_base_url,
        token=config.rpc_token,
        timeout=config.rpc_timeout,
    )
    download_client = httpx.AsyncClient(
        proxy=None if no_proxy else configured_proxy,
        trust_env=False,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
        headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"},
    )
    download_service = VideoDownloadService(
        download_client,
        minio,
        bucket,
        cover_bucket="tiktok",
        audio_bucket="tiktok",
        proxy_url="" if no_proxy else configured_proxy or "",
    )

    await db.aconnect()
    try:
        rows = await fetch_failed_rows(
            db, min_grade=min_grade, limit=limit, offset=offset
        )
        if not rows:
            logger.info("无待重试的 TikTok 视频")
            return 0

        logger.info("待刷新地址并重试下载 %d 条", len(rows))
        await minio.amake_bucket("tiktok")
        semaphore = asyncio.Semaphore(max(1, concurrency))
        succeeded = 0
        failed = 0

        async def worker(row: dict) -> None:
            nonlocal succeeded, failed
            async with semaphore:
                content_id = str(row["content_id"])
                try:
                    detail = await rpc.invoke(
                        "tiktok", "videoDetail", {"itemId": content_id}
                    )
                    video_url, music_url, pic_url = extract_media_urls(
                        detail, content_id
                    )
                    await download_service.download_media(
                        video_url,
                        music_url,
                        pic_url,
                        "tiktok",
                        content_id,
                    )
                    await mark_downloaded(
                        db,
                        mc_id=row["mc_id"],
                        content_id=content_id,
                        video_url=video_url,
                        music_url=music_url,
                        pic_url=pic_url,
                    )
                    succeeded += 1
                    logger.info(
                        "刷新并下载成功 [tiktok] %s -> %s/%s",
                        content_id,
                        "tiktok",
                        f"{content_id}/video|audio|pic",
                    )
                except Exception as error:
                    failed += 1
                    logger.error("刷新或下载失败 [tiktok] %s: %s", content_id, error)
                if rps > 0:
                    await asyncio.sleep(1.0 / rps)

        await asyncio.gather(*(worker(row) for row in rows))

        logger.info("失败视频重试汇总: 成功=%d 失败=%d", succeeded, failed)
        return succeeded
    finally:
        await download_client.aclose()
        await rpc.close()
        await minio.aclose()
        await db.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="通过 TikTok videoDetail 刷新 CDN 地址并重试失败视频"
    )
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument(
        "--min-grade",
        type=int,
        default=3,
        help="最低分级 (1=P1, 2=P2, 3=P3)，默认 3",
    )
    parser.add_argument("--bucket", default="videos", help="MinIO bucket")
    parser.add_argument("--limit", type=int, default=0, help="最大处理数，0=不限制")
    parser.add_argument("--offset", type=int, default=0, help="结果偏移量")
    parser.add_argument("--concurrency", type=int, default=4, help="并发数")
    parser.add_argument("--rps", type=float, default=2.0, help="每任务速率，0=不限速")
    parser.add_argument("--no-proxy", action="store_true", help="下载时绕过代理")
    args = parser.parse_args()

    asyncio.run(
        run(
            args.config,
            min_grade=args.min_grade,
            bucket=args.bucket,
            limit=args.limit if args.limit > 0 else 9_999_999,
            offset=args.offset,
            concurrency=args.concurrency,
            rps=args.rps,
            no_proxy=args.no_proxy,
        )
    )


if __name__ == "__main__":
    main()
