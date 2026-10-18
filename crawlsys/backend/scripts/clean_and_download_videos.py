"""清洗并下载视频的命令行入口；业务逻辑由 Worker 共享实现提供。"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import tomllib
from pathlib import Path
from typing import Optional

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "app"))

import httpx

from services.video_download import VideoDownloadService
from worker.video_clean import VideoCleanWorker
from worker.video_download import VideoDownloadWorker
from cleaner.config import CleanerConfig
from cleaner.repository import CleanerRepository
from core.config import PlatformQuota, SchedulerConfig
from models.task_config import VideoCleanTaskConfig, VideoDownloadTaskConfig
from storage import MinioDB, SQLAlchemyDB
from tools.ytdlp import YtDlpClient
from worker.result import WorkerResult

logger = logging.getLogger(__name__)


def _print_result(stage: str, result: WorkerResult) -> None:
    print(
        f"{stage}统计: 总数={result.total} 成功={result.succeeded} "
        f"失败={result.failed} 跳过={result.skipped}",
        flush=True,
    )


def _load_raw(config_path: str) -> dict:
    with open(config_path, "rb") as file:
        return tomllib.load(file)


def _load_proxy(config_path: str) -> Optional[str]:
    return _load_raw(config_path).get("proxy", {}).get("url") or None


def _load_minio_config(config_path: str) -> dict:
    raw = _load_raw(config_path)
    if "minio" not in raw:
        raise ValueError(f"配置文件缺少 [minio]：{config_path}")
    return raw["minio"]


async def run_download_batches(
    worker: VideoDownloadWorker, *, limit: int, min_grade: int, use_proxy: bool,
    rps: float, platform: str | None, source: str, offset: int,
) -> WorkerResult:
    total = succeeded = failed = skipped = 0
    query_offset = offset
    while limit == 0 or total < limit:
        batch_size = min(500, limit - total) if limit else 500
        result = await worker.run_batch(
            VideoDownloadTaskConfig(batch_size=batch_size, min_grade=min_grade,
                                    use_proxy=use_proxy, rps=rps),
            platform=platform, source=source, offset=query_offset,
            consumer_key=f"cli:clean-and-download:{source}",
        )
        query_offset = 0
        total += result.total
        succeeded += result.succeeded
        failed += result.failed
        skipped += result.skipped
        if result.total == 0:
            break
        if result.total < batch_size:
            break
    return WorkerResult(total=total, succeeded=succeeded, failed=failed, skipped=skipped)


async def run(
    config_path: str, *, platform: Optional[str], only_clean: bool, skip_clean: bool,
    source: str, min_grade: int, bucket: str, limit: int, offset: int,
    concurrency: int, rps: float, no_proxy: bool,
) -> None:
    config = SchedulerConfig.from_toml(config_path)
    pg = config.postgresql
    db = SQLAlchemyDB(username=pg.username, password=pg.password, host=pg.host,
                      port=pg.port, database=pg.database, amode=True, driver="postgresql")
    await db.aconnect()
    await db.ainit_db()
    quota = PlatformQuota(platform="video-batch", concurrency=concurrency, rps=rps)
    try:
        if not skip_clean:
            cleaner_cfg = CleanerConfig.from_toml(config_path)
            cleaner_cfg.validate()
            cleaner = VideoCleanWorker("video-clean", None, db, quota,
                                       cleaner_config=cleaner_cfg,
                                       cleaner_repo=CleanerRepository(db))
            clean_result = await cleaner.run_batch(
                VideoCleanTaskConfig(platforms=[platform] if platform else []),
                consumer_key=f"cli:clean-and-download:{source}",
            )
            _print_result("清洗", clean_result)
        if only_clean:
            return

        minio_cfg = _load_minio_config(config_path)
        minio = MinioDB(endpoint=f"{minio_cfg['host']}:{minio_cfg['port']}",
                        access_key=minio_cfg["username"], secret_key=minio_cfg["password"],
                        secure=bool(minio_cfg.get("secure", False)), amode=True)
        media_bucket = platform or "tiktok"
        await minio.amake_bucket(media_bucket)
        cover_bucket = media_bucket
        audio_bucket = media_bucket
        proxy = None if no_proxy else _load_proxy(config_path)
        client = httpx.AsyncClient(proxy=proxy, trust_env=False, follow_redirects=True,
                                   timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
                                   headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"})
        try:
            worker = VideoDownloadWorker("video-download", None, db, quota,
                                         download_service=VideoDownloadService(
                                             client, minio, bucket,
                                             cover_bucket=cover_bucket,
                                             audio_bucket=audio_bucket,
                                             ytdlp_client=YtDlpClient(proxy_url=proxy),
                                             proxy_url=proxy or "",
                                         ))
            download_result = await run_download_batches(
                worker, limit=limit, min_grade=min_grade,
                use_proxy=not no_proxy, rps=rps, platform=platform,
                source=source, offset=offset,
            )
            _print_result("下载", download_result)
        finally:
            await client.aclose()
            await minio.aclose()
    finally:
        await db.aclose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    parser = argparse.ArgumentParser(description="先分级清洗，再下载清洗后的视频")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--platform", default="tiktok")
    parser.add_argument("--only-clean", action="store_true")
    parser.add_argument("--skip-clean", action="store_true")
    parser.add_argument("--source", default="media", choices=["media", "material"])
    parser.add_argument("--min-grade", type=int, default=3)
    parser.add_argument("--bucket", default="videos")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--no-proxy", action="store_true")
    args = parser.parse_args()
    if args.only_clean and args.skip_clean:
        parser.error("--only-clean 与 --skip-clean 互斥")
    try:
        asyncio.run(run(config_path=args.config, platform=args.platform, only_clean=args.only_clean,
                        skip_clean=args.skip_clean, source=args.source, min_grade=args.min_grade,
                        bucket=args.bucket, limit=args.limit, offset=args.offset,
                        concurrency=args.concurrency, rps=args.rps, no_proxy=args.no_proxy))
    except Exception:
        logger.exception("清洗下载工作流执行失败")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
