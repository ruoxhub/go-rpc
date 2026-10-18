"""单独跑 SearchVideo 任务：遍历搜索关键词，分页抓取视频列表。

与常驻 Worker 不同，本脚本是一次性任务：
  1. 查询 t_busi_search_keyword 中指定平台的关键词；
  2. 从每条记录的 keyword 构造 RPC 参数；
  3. 对每个关键词调用 SearchVideo，按 cursor 翻页直到 hasMore=false 或游标不再推进；
  4. 解析结果（产出 content / media）经标准 Pipeline（Bloom 去重 + upsert）入库。

依赖外部 go-rpc 服务（config.toml 中的 rpc_base_url）在线，与 Worker 共用同一端点。

用法:
    python scripts/crawl_search_video.py --platform tiktok
    python scripts/crawl_search_video.py --platform tiktok --limit 50 --offset 0
    python scripts/crawl_search_video.py --platform tiktok --max-pages 10 --concurrency 2
    python scripts/crawl_search_video.py --platform tiktok --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from hashlib import sha256
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
for _path in (_BACKEND_DIR / "app", _BACKEND_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from common.errors import format_error
from common.logging import get_logger
from core.config import PlatformQuota, SchedulerConfig
from core.sink_handlers import ResultSinkRouter
from filter import Bloom
from go_rpc import RpcClient
from models import BusTask
from models.keyword import BusiSearchKeyword
from models.task_config import PaginationConfig, SinkConfig, TaskConfig
from parser import (
    general_parser,  # compatibility hook; Worker uses this shared registry
)
from pipeline import CrawlerPipeline
from sqlalchemy import select
from storage import SQLAlchemyDB
from worker.crawler import CrawlerWorker
from worker.work_item import ItemDisposition, SourceBatch, WorkItem

logger = get_logger(__file__)


class _KeywordSource:
    """将单个关键词适配为 CrawlerWorker 的一次性输入批次。"""

    def __init__(self, keyword: str) -> None:
        self._item = WorkItem({"keyword": keyword}, entity_id=keyword)

    async def fetch(self) -> SourceBatch:
        return SourceBatch(items=[self._item], read=1)

    async def complete(self, item: WorkItem) -> ItemDisposition:
        return ItemDisposition.SUCCEEDED

    async def fail(
        self,
        item: WorkItem,
        error: Exception,
        *,
        deterministic: bool,
    ) -> ItemDisposition:
        return ItemDisposition.FAILED


def _safe_identifier(value: str) -> str:
    return f"sha256:{sha256(value.encode()).hexdigest()[:12]}"


def _log_failure(keyword: str, exc: BaseException) -> None:
    logger.error(
        "关键词 %s 抓取失败: %s",
        _safe_identifier(keyword),
        format_error(exc, max_length=500),
    )


async def crawl_search_video(
    rpc: RpcClient,
    pipeline: CrawlerPipeline,
    platform: str,
    keyword: str,
    *,
    rps: float,
    max_pages: int,
    dry_run: bool,
) -> tuple[int, int]:
    """通过共享 WorkItemProcessor 抓取单个关键词。"""
    cfg = TaskConfig(
        pagination=PaginationConfig(
            max_pages=max_pages,
            response_cursor_keys=["cursor", "maxCursor", "nextCursor", "next_cursor"],
        ),
        sink=SinkConfig(mode="standard"),
    )
    task = BusTask(platform=platform, action="SearchVideo", config=cfg)
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

    worker = CrawlerWorker(
        platform=platform,
        rpc=rpc,
        default_quota=PlatformQuota(platform=platform, rps=max(0, rps)),
        db=None,
        pipeline=pipeline,
        sink_router=CountingRouter(),
        source_factory=lambda _config, _task: _KeywordSource(keyword),
    )
    result = await worker.execute_business(task)
    if result.failed:
        raise RuntimeError(
            f"CrawlerWorker failed {result.failed}/{result.total} work item(s)"
        )
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
) -> None:
    config = SchedulerConfig.from_toml(config_path)
    pg = config.postgresql
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
        base_url=config.rpc_base_url,
        token=config.rpc_token,
        timeout=config.rpc_timeout,
    )

    sem = asyncio.Semaphore(max(1, concurrency))
    total_keywords = total_pages = total_items = errors = 0

    async def _worker(row: BusiSearchKeyword) -> None:
        nonlocal total_pages, total_items, errors
        try:
            pages, items = await crawl_search_video(
                rpc,
                pipeline,
                platform,
                row.keyword,
                rps=rps,
                max_pages=max_pages,
                dry_run=dry_run,
            )
            total_pages += pages
            total_items += items
            logger.info(
                "关键词 %s 抓取完成: pages=%d items=%d",
                _safe_identifier(row.keyword),
                pages,
                items,
            )
        except Exception as exc:  # noqa: BLE001 - batch script isolates keyword failures
            errors += 1
            _log_failure(row.keyword, exc)

    try:
        async with db.asession_scope() as session:
            stmt = (
                select(BusiSearchKeyword)
                .where(BusiSearchKeyword.platform == platform)
                .order_by(BusiSearchKeyword.id.asc())
            )
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()

        total_keywords = len(rows)
        logger.info("查询到 %d 条 %s 搜索关键词", total_keywords, platform)
        if not rows:
            logger.info("无关键词可抓取，退出")
            return

        async def _guarded(row: BusiSearchKeyword) -> None:
            async with sem:
                await _worker(row)

        await asyncio.gather(*(_guarded(row) for row in rows))
    finally:
        logger.info(
            "汇总: keywords=%d pages=%d items=%d errors=%d (dry_run=%s)",
            total_keywords,
            total_pages,
            total_items,
            errors,
            dry_run,
        )
        await rpc.close()
        await pipeline.close()
        await bloom.aclose()
        await db.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="遍历 t_busi_search_keyword 分页搜索视频 (SearchVideo)"
    )
    ap.add_argument("--platform", default="tiktok", help="平台标识，默认 tiktok")
    ap.add_argument("--config", default="config.toml", help="配置文件路径")
    ap.add_argument("--limit", type=int, default=0, help="最多处理关键词数，0=全部")
    ap.add_argument(
        "--offset", type=int, default=0, help="关键词列表偏移量（用于分批）"
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="单关键词最大翻页数，0=不限（依赖 hasMore）",
    )
    ap.add_argument("--concurrency", type=int, default=1, help="并发关键词数")
    ap.add_argument(
        "--rps",
        type=float,
        default=0.0,
        help="每关键词 RPC 速率上限，0=默认 1.0",
    )
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
        )
    )


if __name__ == "__main__":
    main()
