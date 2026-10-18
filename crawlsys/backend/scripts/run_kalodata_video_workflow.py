"""抓取 Kalodata 榜单、清洗分级并下载视频的完整工作流。

示例:
    python scripts/run_kalodata_video_workflow.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "app"))

from scripts.clean_and_download_videos import run as run_clean_and_download
from scripts.crawl_kalodata_query_list import run as run_kalodata_crawl


async def run(args: argparse.Namespace) -> None:
    """依次执行抓取入库、清洗分级和视频下载。"""
    crawl_args = argparse.Namespace(
        country=args.country,
        start_date=args.start_date,
        end_date=args.end_date,
        cate_ids=args.cate_ids,
        page_count=args.page_count,
        page_size=args.page_size,
        config=args.config,
        dry_run=args.dry_run,
    )
    await run_kalodata_crawl(crawl_args)

    if args.dry_run:
        print("抓取 dry-run 已完成，跳过清洗和下载。")
        return

    await run_clean_and_download(
        config_path=args.config,
        platform="tiktok",
        only_clean=False,
        skip_clean=False,
        source=args.source,
        min_grade=args.min_grade,
        bucket=args.bucket,
        limit=args.limit,
        offset=args.offset,
        concurrency=args.concurrency,
        rps=args.rps,
        no_proxy=args.no_proxy,
    )


def build_parser() -> argparse.ArgumentParser:
    end_date = date.today() - timedelta(days=1)
    start_date = end_date
    parser = argparse.ArgumentParser(
        description="抓取 Kalodata AI 视频榜单，清洗分级后下载视频"
    )
    parser.add_argument(
        "--config",
        default=str(_BACKEND_DIR / "config.toml"),
        help="配置文件路径，默认使用 backend/config.toml",
    )

    crawl = parser.add_argument_group("抓取参数")
    crawl.add_argument("--country", default="US", help="国家或地区，默认 US")
    crawl.add_argument("--start-date", default=start_date.isoformat())
    crawl.add_argument("--end-date", default=end_date.isoformat())
    crawl.add_argument("--page-count", type=int, default=1)
    crawl.add_argument(
        "--cate-ids", nargs="+", default=["840072", "839944"]
    )
    crawl.add_argument("--page-size", type=int, default=50)
    crawl.add_argument(
        "--dry-run",
        action="store_true",
        help="只抓取和解析，不入库，并跳过清洗与下载",
    )

    download = parser.add_argument_group("清洗与下载参数")
    download.add_argument(
        "--source", default="media", choices=["media", "material"]
    )
    download.add_argument("--min-grade", type=int, default=3)
    download.add_argument("--bucket", default="videos")
    download.add_argument("--limit", type=int, default=0)
    download.add_argument("--offset", type=int, default=0)
    download.add_argument("--concurrency", type=int, default=4)
    download.add_argument("--rps", type=float, default=2.0)
    download.add_argument("--no-proxy", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
