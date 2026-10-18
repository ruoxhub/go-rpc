"""单独跑 challengeItemList 任务：遍历 tk_challenge 已有话题，分页抓取其视频列表。

与常驻 Worker 不同，本脚本是一次性任务：
  1. 查询 tk_challenge 中已有的话题（task 配置 filter_by_platform=false，故不过滤平台）；
  2. 从每条话题记录的 challenge_id 构造 RPC 参数；
  3. 对每个话题调用 challengeItemList，按 cursor 翻页直到 hasMore=false 或游标不再推进；
  4. 解析结果（复用视频解析逻辑，产出 content / media）经标准 Pipeline（Bloom 去重 + upsert）入库。

依赖外部 go-rpc 服务（config.toml 中的 rpc_base_url）在线，与 Worker 共用同一端点。

用法:
    python scripts/crawl_challenge_item_list.py --platform tiktok
    python scripts/crawl_challenge_item_list.py --platform tiktok --limit 50 --offset 0
    python scripts/crawl_challenge_item_list.py --platform tiktok --max-pages 10 --concurrency 2
    python scripts/crawl_challenge_item_list.py --platform tiktok --count 30 --region TW
    python scripts/crawl_challenge_item_list.py --platform tiktok --dry-run        # 只解析不入库
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import format_error
from common.logging import get_logger
from core.config import PlatformQuota, SchedulerConfig
from core.sink_handlers import ResultSinkRouter
from filter import Bloom
from go_rpc import RpcClient
from models import BusTask
from models.task_config import PaginationConfig, SinkConfig, TaskConfig
from models.tiktok import TkChallenge
from parser import general_parser
from pipeline import CrawlerPipeline
from sqlalchemy import select
from storage import SQLAlchemyDB
from worker.processors import InvokeActionProcessor
from worker.rate_limit import PlatformLimiter
from worker.work_item import WorkItem

logger = get_logger(__file__)


def _safe_identifier(value: str) -> str:
    return f"sha256:{sha256(value.encode()).hexdigest()[:12]}"


def _log_failure(challenge_id: str, exc: BaseException) -> None:
    logger.error(
        "话题 %s 抓取失败: %s",
        _safe_identifier(challenge_id),
        format_error(exc, max_length=500),
    )


async def crawl_challenge_item_list(
    rpc: RpcClient,
    pipeline: CrawlerPipeline,
    platform: str,
    challenge_id: str,
    *,
    rps: float,
    max_pages: int,
    dry_run: bool,
    count: int,
    region: str,
    locale: str,
) -> tuple[int, int]:
    """通过共享 WorkItemProcessor 抓取单个话题。"""
    cfg = TaskConfig(
        pagination=PaginationConfig(
            max_pages=max_pages,
            response_cursor_keys=["maxCursor", "cursor", "nextCursor", "next_cursor"],
        ),
        sink=SinkConfig(mode="standard"),
    )
    task = BusTask(platform=platform, action="challengeItemList", config=cfg)
    pages = items = 0
    router = ResultSinkRouter(
        db=None,
        pipeline=pipeline,
        parser=general_parser,
        stream_queue=None,
        persist_results=not dry_run,
    )

    class CountingRouter:
        async def persist(self, **kwargs):
            nonlocal pages, items
            pages += 1
            result = await router.persist(**kwargs)
            items += result.processed
            return result

    params = {
        "challengeID": challenge_id,
        "count": count,
        "region": region,
        "locale": locale,
    }
    limiter = PlatformLimiter(PlatformQuota(platform=platform, rps=max(0, rps)))
    processor = InvokeActionProcessor(
        rpc=rpc,
        limiter_for=lambda _platform: limiter,
        sink_router=CountingRouter(),
    )
    await processor.process(task, WorkItem(params), None)
    return pages, items


async def run(
    platform: str,
    config_path: str,
    *,
    limit: int,
    offset: int,
    max_pages: int,
    concurrency: int,
    rps: float,
    dry_run: bool,
    count: int,
    region: str,
    locale: str,
) -> None:
    config = SchedulerConfig.from_toml(config_path)
    pg = config.postgresql

    # 脚本级速率上限；--rps 未指定时退化为固定 1.0。翻页与话题间均按此速率休眠。
    if rps <= 0:
        rps = 1.0

    db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    await db.aconnect()
    await db.ainit_db()

    bloom = Bloom(redis_url=config.redis.url, amode=True)
    pipeline = CrawlerPipeline(filter=bloom, store=db)
    rpc = RpcClient(
        base_url=config.rpc_base_url, token=config.rpc_token, timeout=config.rpc_timeout
    )

    sem = asyncio.Semaphore(max(1, concurrency))
    total_pages, total_items = 0, 0
    skipped, errors = 0, 0
    total_challenges = 0

    async def _worker(challenge: TkChallenge) -> None:
        nonlocal total_pages, total_items, skipped, errors
        challenge_id = challenge.challenge_id
        if not challenge_id:
            logger.warning("话题记录 id=%s 缺少 challenge_id，跳过", challenge.id)
            skipped += 1
            return
        try:
            pages, items = await crawl_challenge_item_list(
                rpc,
                pipeline,
                platform,
                challenge_id,
                rps=rps,
                max_pages=max_pages,
                dry_run=dry_run,
                count=count,
                region=region,
                locale=locale,
            )
            total_pages += pages
            total_items += items
            logger.info(
                "话题 %s 抓取完成: pages=%d items=%d",
                _safe_identifier(challenge_id),
                pages,
                items,
            )
        except Exception as exc:  # noqa: BLE001 - batch script isolates challenge failures
            errors += 1
            _log_failure(challenge_id, exc)

    try:
        async with db.asession_scope() as session:
            stmt = select(TkChallenge)
            if limit:
                stmt = stmt.limit(limit)
            if offset:
                stmt = stmt.offset(offset)
            stmt = stmt.order_by(TkChallenge.id.asc())
            rows = (await session.execute(stmt)).scalars().all()
        logger.info("查询到 %d 条 tk_challenge 话题", len(rows))
        total_challenges = len(rows)
        if not rows:
            logger.info("无话题可抓取，退出")
            return

        async def _guarded(c: TkChallenge) -> None:
            async with sem:
                await _worker(c)

        await asyncio.gather(*(_guarded(c) for c in rows))
    finally:
        logger.info(
            "汇总: challenges=%d pages=%d items=%d skipped=%d errors=%d (dry_run=%s)",
            total_challenges,
            total_pages,
            total_items,
            skipped,
            errors,
            dry_run,
        )
        await rpc.close()
        await pipeline.close()
        await bloom.aclose()
        await db.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="遍历 tk_challenge 分页抓取话题视频 (challengeItemList)"
    )
    ap.add_argument(
        "--platform", default="tiktok", help="平台标识（作为 RPC group），默认 tiktok"
    )
    ap.add_argument("--config", default="config.toml", help="配置文件路径")
    ap.add_argument("--limit", type=int, default=0, help="最多处理话题数，0=全部")
    ap.add_argument("--offset", type=int, default=0, help="话题列表偏移量（用于分批）")
    ap.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="单话题最大翻页数，0=不限（依赖 hasMore）",
    )
    ap.add_argument("--concurrency", type=int, default=1, help="并发话题数")
    ap.add_argument(
        "--rps", type=float, default=0.0, help="每话题 RPC 速率上限，0=默认 1.0"
    )
    ap.add_argument(
        "--count", type=int, default=30, help="每页数量（对应 action 的 count 参数）"
    )
    ap.add_argument("--region", default="TW", help="区域，默认 TW")
    ap.add_argument("--locale", default="zh-Hans", help="语言区域，默认 zh-Hans")
    ap.add_argument("--dry-run", action="store_true", help="只解析不入库")
    args = ap.parse_args()

    asyncio.run(
        run(
            platform=args.platform,
            config_path=args.config,
            limit=args.limit,
            offset=args.offset,
            max_pages=args.max_pages,
            concurrency=args.concurrency,
            rps=args.rps,
            dry_run=args.dry_run,
            count=args.count,
            region=args.region,
            locale=args.locale,
        )
    )


if __name__ == "__main__":
    main()
