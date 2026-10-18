"""抓取 Kalodata AI 视频榜单，并通过 TikTok videoDetail 入库。

示例:
    python scripts/crawl_kalodata_query_list.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "app"))

from go_rpc import RpcClient

from scripts._ai_video_rank_common import extract_video_ids, run_rank_video_details


async def fetch_kalodata_video_pages(
    rpc: RpcClient,
    *,
    country: str,
    start_date: str,
    end_date: str,
    cate_ids: list[str],
    page_count: int,
    page_size: int,
) -> AsyncIterator[tuple[int, list[str]]]:
    """按指定日期区间逐页抓取，每页返回后立即交给调用方保存。"""
    if date.fromisoformat(start_date) != date.fromisoformat(end_date):
        raise ValueError("start_date must be equal to end_date")
    if page_count <= 0:
        raise ValueError("page_count must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    seen: set[str] = set()
    for page_no in range(1, page_count + 1):
        response = await rpc.invoke(
            "kalodata",
            "queryList",
            {
                "country": country,
                "startDate": start_date,
                "endDate": end_date,
                "cateIds": cate_ids,
                "showCateIds": cate_ids,
                "pageNo": page_no,
                "pageSize": page_size,
            },
        )
        if isinstance(response, dict):
            response_data = response.get("data")
            if response_data is None or response_data == []:
                break
        page_ids = extract_video_ids(response, "kalodata")
        new_ids = [video_id for video_id in page_ids if video_id not in seen]
        seen.update(new_ids)
        yield page_no, new_ids


async def run(args: argparse.Namespace) -> None:
    def fetch_pages(rpc: RpcClient) -> AsyncIterator[tuple[int, list[str]]]:
        return fetch_kalodata_video_pages(
            rpc,
            country=args.country,
            start_date=args.start_date,
            end_date=args.end_date,
            cate_ids=args.cate_ids,
            page_count=args.page_count,
            page_size=args.page_size,
        )

    await run_rank_video_details(
        label="kalodata/queryList",
        fetch_video_pages=fetch_pages,
        config_path=args.config,
        dry_run=args.dry_run,
    )


def main() -> None:
    end_date = date.today() - timedelta(days=1)
    start_date = end_date
    parser = argparse.ArgumentParser(
        description="抓取 Kalodata AI 视频榜单并通过 videoDetail 入库"
    )
    parser.add_argument("--country", default="US", help="国家或地区，默认 US")
    parser.add_argument(
        "--start-date",
        default=start_date.isoformat(),
        help="开始日期，必须与结束日期一致，默认昨天",
    )
    parser.add_argument(
        "--end-date", default=end_date.isoformat(), help="结束日期，默认昨天"
    )
    parser.add_argument("--page-count", type=int, default=10, help="抓取页数，默认 10")
    parser.add_argument(
        "--cate-ids",
        nargs="+",
        default=["840072", "839944"],
        help="分类 ID，默认 840072 839944",
    )
    parser.add_argument("--page-size", type=int, default=10, help="每页数量，默认 10")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只请求和解析，不入库")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
