"""端到端跑通 Boss 直聘 (zhipin) search 抓取并入库。

用法（与现有 crawl_search_video 等一次性脚本同构）：
    uv run python scripts/crawl_zhipin_search.py --keywords "爬虫工程师,Python后端" --dry-run
    uv run python scripts/crawl_zhipin_search.py --keywords "爬虫工程师,Python后端"

流程：
  1. 查询 t_busi_search_keyword 中 platform='zhipin' 的关键词（或用 --keywords 直给）；
  2. 对每个关键词构造 zhipin search RPC 参数（keyword/city/page/size）；
  3. 调用 go-rpc /business/invoke (group=zhipin, action=search)；
  4. 经 zhipin parser（parse_zhipin_search）产出 datatype="job" 记录；
  5. 走通用 Pipeline（Bloom 去重 + 幂等 upsert）写入 t_busi_job。

风控说明：zhipin 搜索近期返回 code=37（"您的环境存在异常"），zpData 只有
name/seed/ts 而无 jobList。脚本会把此类响应记录为“风控/无数据”并继续，不报错，
确保流程可复现；待风控解除后相同命令即可真实入库。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
for _path in (_BACKEND_DIR / "app", _BACKEND_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from common.logging import get_logger
from core.config import PlatformQuota, SchedulerConfig
from core.sink_handlers import ResultSinkRouter
from filter import Bloom
from go_rpc import RpcClient
from models import BusiSearchKeyword, BusTask
from models.task_config import PaginationConfig, SinkConfig, TaskConfig
from parser import general_parser
from pipeline import CrawlerPipeline
from services.parser_configuration.repository import ActionRuntimeDefinition
from sqlalchemy import select
from storage import SQLAlchemyDB
from worker.processors import InvokeActionProcessor
from worker.rate_limit import PlatformLimiter
from worker.work_item import WorkItem

logger = get_logger(__file__)


def _search_params(keyword: str, city: str, page: int, size: int) -> dict:
    return {"keyword": keyword, "city": city, "page": page, "size": size}


async def crawl_keyword(
    rpc: RpcClient,
    pipeline: CrawlerPipeline,
    keyword: str,
    *,
    rps: float,
    max_pages: int,
    dry_run: bool,
    city: str,
) -> tuple[int, int, int]:
    """对单个关键词执行 zhipin search 分页并入库。返回 (pages, jobs, risk)."""
    cfg = TaskConfig(
        pagination=PaginationConfig(
            max_pages=max_pages,
            response_cursor_keys=[
                "page",
                "cursor",
                "maxCursor",
                "nextCursor",
                "next_cursor",
            ],
        ),
        sink=SinkConfig(mode="standard"),
    )
    task = BusTask(platform="zhipin", action="search", config=cfg)
    pages = jobs = 0
    router = ResultSinkRouter(
        db=None,
        pipeline=pipeline,
        parser=general_parser,
        stream_queue=None,
        persist_results=not dry_run,
    )

    class CountingRouter:
        async def persist(self, **kwargs):
            nonlocal pages, jobs
            pages += 1
            result = await router.persist(**kwargs)
            jobs += result.processed
            return result

    limiter = PlatformLimiter(PlatformQuota(platform="zhipin", rps=max(rps, 0.2)))
    processor = InvokeActionProcessor(
        rpc=rpc,
        limiter_for=lambda _p: limiter,
        sink_router=CountingRouter(),
    )
    params = _search_params(keyword, city, 1, 15)
    runtime = ActionRuntimeDefinition({"type": "object"}, None, None)
    await processor.process(task, WorkItem(params), runtime)
    return pages, jobs, 0


async def run(
    config_path: str,
    *,
    keywords: list[str] | None,
    limit: int,
    offset: int,
    max_pages: int,
    concurrency: int,
    rps: float,
    dry_run: bool,
    city: str,
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
        base_url=config.rpc_base_url, token=config.rpc_token, timeout=config.rpc_timeout
    )

    # 关键词来源：CLI 直给，否则查 t_busi_search_keyword 表
    if keywords:
        kw_rows = keywords
    else:
        async with db.asession_scope() as session:
            stmt = (
                select(BusiSearchKeyword)
                .where(BusiSearchKeyword.platform == "zhipin")
                .order_by(BusiSearchKeyword.id.asc())
            )
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)
            kw_rows = [r.keyword for r in (await session.execute(stmt)).scalars().all()]

    logger.info("查询到 %d 个 zhipin 搜索关键词", len(kw_rows))
    if not kw_rows:
        logger.info("无关键词可抓取，退出")
        await rpc.close()
        await pipeline.close()
        await bloom.aclose()
        await db.aclose()
        return

    sem = asyncio.Semaphore(max(1, concurrency))
    total_pages = total_jobs = total_risk = 0

    async def _worker(keyword: str) -> None:
        nonlocal total_pages, total_jobs, total_risk
        try:
            pages, jobs, risk = await crawl_keyword(
                rpc,
                pipeline,
                keyword,
                rps=rps,
                max_pages=max_pages,
                dry_run=dry_run,
                city=city,
            )
            total_pages += pages
            total_jobs += jobs
            total_risk += risk
            logger.info("关键词 %r 完成: pages=%d jobs=%d", keyword, pages, jobs)
        except Exception as exc:  # noqa: BLE001 - 隔离单关键词失败
            total_risk += 1
            logger.error("关键词 %r 失败: %s", keyword, exc)

    async def _guarded(kw: str) -> None:
        async with sem:
            await _worker(kw)

    await asyncio.gather(*(_guarded(kw) for kw in kw_rows))

    logger.info(
        "汇总: keywords=%d pages=%d jobs=%d risk_or_errors=%d (dry_run=%s)",
        len(kw_rows),
        total_pages,
        total_jobs,
        total_risk,
        dry_run,
    )
    await rpc.close()
    await pipeline.close()
    await bloom.aclose()
    await db.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(description="端到端抓取 Boss 直聘职位并入库")
    ap.add_argument("--config", default="config.toml", help="配置文件路径")
    ap.add_argument(
        "--keywords",
        default=None,
        help="逗号分隔关键词；缺省从 t_busi_search_keyword 读取",
    )
    ap.add_argument("--city", default="深圳", help="城市名称（默认深圳）")
    ap.add_argument("--limit", type=int, default=0, help="关键词上限，0=全部")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--max-pages", type=int, default=5, help="单关键词最大翻页数")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--rps", type=float, default=0.0)
    ap.add_argument("--dry-run", action="store_true", help="只解析不入库")
    args = ap.parse_args()

    keywords = None
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    asyncio.run(
        run(
            config_path=args.config,
            keywords=keywords,
            limit=args.limit,
            offset=args.offset,
            max_pages=args.max_pages,
            concurrency=args.concurrency,
            rps=args.rps,
            dry_run=args.dry_run,
            city=args.city,
        )
    )


if __name__ == "__main__":
    main()
