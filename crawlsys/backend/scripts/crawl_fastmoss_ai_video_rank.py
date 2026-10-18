"""抓取 FastMoss AI 视频榜单，并通过 TikTok videoDetail 入库。

示例:
    python scripts/crawl_fastmoss_ai_video_rank.py --date-value 2026-08-01
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "app"))

from go_rpc import RpcClient

from scripts._ai_video_rank_common import extract_video_ids, run_rank_video_details


async def fetch_fastmoss_video_ids(
    rpc: RpcClient,
    *,
    region: str,
    date_value: str,
) -> list[str]:
    """从第 1 页开始抓取，直到空页或上游重复最后一页。"""
    collected: dict[str, None] = {}
    page = 1
    while True:
        response = await rpc.invoke(
            "fastmoss",
            "aiVideoRank",
            {"region": region, "date_value": date_value, "page": page},
        )
        page_ids = extract_video_ids(response, "fastmoss")
        if not page_ids:
            break
        new_ids = [video_id for video_id in page_ids if video_id not in collected]
        if not new_ids:
            break
        collected.update(dict.fromkeys(new_ids))
        page += 1
    return list(collected)


async def run(args: argparse.Namespace) -> None:
    async def fetch(rpc: RpcClient) -> list[str]:
        return await fetch_fastmoss_video_ids(
            rpc,
            region=args.region,
            date_value=args.date_value,
        )

    await run_rank_video_details(
        label="fastmoss/aiVideoRank",
        fetch_video_ids=fetch,
        config_path=args.config,
        dry_run=args.dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="抓取 FastMoss AI 视频榜单并通过 videoDetail 入库"
    )
    parser.add_argument("--region", default="US", help="榜单地区，默认 US")
    parser.add_argument("--date-value", required=True, help="榜单日期，格式 YYYY-MM-DD")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只请求和解析，不入库")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
