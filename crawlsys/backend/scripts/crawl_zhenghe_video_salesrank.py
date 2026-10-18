"""抓取 Zhenghe 视频销量榜单，并通过 TikTok videoDetail 入库。

示例:
    python scripts/crawl_zhenghe_video_salesrank.py \
        --start-date 2026-07-27 --end-date 2026-08-02 --page-count 5
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

from go_rpc import RpcClient

from scripts._ai_video_rank_common import extract_video_ids, run_rank_video_details


async def fetch_zhenghe_video_ids(
    rpc: RpcClient,
    *,
    start_date: str,
    end_date: str,
    page_count: int,
    page_size: int,
) -> list[str]:
    """按闭区间逐日抓取销量榜单的前若干页。"""
    current = date.fromisoformat(start_date)
    last = date.fromisoformat(end_date)
    if current > last:
        raise ValueError("start_date must be <= end_date")

    collected: dict[str, None] = {}
    while current <= last:
        for page_num in range(1, page_count + 1):
            response = await rpc.invoke(
                "zhenghe",
                "videoSalesRank",
                {
                    "recordDate": current.isoformat(),
                    "pageNum": page_num,
                    "pageSize": page_size,
                },
            )
            collected.update(dict.fromkeys(extract_video_ids(response, "zhenghe")))
        current += timedelta(days=1)
    return list(collected)


async def run(args: argparse.Namespace) -> None:
    async def fetch(rpc: RpcClient) -> list[str]:
        return await fetch_zhenghe_video_ids(
            rpc,
            start_date=args.start_date,
            end_date=args.end_date,
            page_count=args.page_count,
            page_size=args.page_size,
        )

    await run_rank_video_details(
        label="zhenghe/videoSalesRank",
        fetch_video_ids=fetch,
        config_path=args.config,
        dry_run=args.dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="抓取 Zhenghe 视频销量榜单并通过 videoDetail 入库"
    )
    parser.add_argument(
        "--start-date", default="2026-07-27", help="开始日期，默认 2026-07-27"
    )
    parser.add_argument(
        "--end-date", default="2026-08-02", help="结束日期，默认 2026-08-02"
    )
    parser.add_argument(
        "--page-count", type=int, default=5, help="抓取页数，默认前 5 页"
    )
    parser.add_argument("--page-size", type=int, default=20, help="每页数量，默认 20")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只请求和解析，不入库")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
