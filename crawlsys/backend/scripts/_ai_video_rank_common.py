"""AI 视频榜单脚本共享的 videoDetail 入库流程。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from common.logging import get_logger
from core.config import SchedulerConfig
from core.constants import DATATYPE_TO_MODEL
from filter import Bloom
from go_rpc import RpcClient
from parser.tiktok.videoDetail import parse_video_detail
from pipeline import CrawlerPipeline
from storage import SQLAlchemyDB

logger = get_logger(__file__)


def extract_video_ids(response: dict, platform: str) -> list[str]:
    values = response.get("data") if isinstance(response, dict) else None
    if not isinstance(values, list):
        raise ValueError(f"{platform} response.data must be a video ID list")
    return list(dict.fromkeys(str(value) for value in values if value))


async def crawl_rank_video_details(
    rpc: RpcClient,
    pipeline: CrawlerPipeline,
    *,
    video_ids: list[str],
    dry_run: bool,
) -> tuple[int, int, int]:
    """抓取视频详情；返回（视频数、成功详情数、失败数）。"""
    if not video_ids:
        raise RuntimeError("榜单未返回可用视频 ID")

    succeeded = errors = 0
    for video_id in video_ids:
        try:
            detail = await rpc.invoke("tiktok", "videoDetail", {"itemId": video_id})
            parsed = list(parse_video_detail(detail))
            if not parsed:
                raise ValueError("videoDetail parser returned 0 items")
            if not dry_run:
                models = [
                    DATATYPE_TO_MODEL[item["datatype"]](**item) for item in parsed
                ]
                await pipeline.process_items(models)
            succeeded += 1
        except Exception as exc:
            errors += 1
            logger.error("videoDetail 抓取失败 itemId=%s: %s", video_id, exc)

    return len(video_ids), succeeded, errors


async def run_rank_video_details(
    *,
    label: str,
    fetch_video_ids: Callable[[RpcClient], Awaitable[list[str]]] | None = None,
    fetch_video_pages: Callable[[RpcClient], AsyncIterator[tuple[int, list[str]]]]
    | None = None,
    config_path: str,
    dry_run: bool,
) -> None:
    if (fetch_video_ids is None) == (fetch_video_pages is None):
        raise ValueError(
            "fetch_video_ids and fetch_video_pages must provide exactly one"
        )

    config = SchedulerConfig.from_toml(config_path)
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
    await db.aconnect()
    await db.ainit_db()
    bloom = Bloom(redis_url=config.redis.url, amode=True)
    pipeline = CrawlerPipeline(filter=bloom, store=db)
    rpc = RpcClient(
        base_url=config.rpc_base_url,
        token=config.rpc_token,
        timeout=config.rpc_timeout,
    )

    try:
        total = succeeded = errors = 0
        if fetch_video_pages is not None:
            async for page_no, video_ids in fetch_video_pages(rpc):
                if video_ids:
                    (
                        page_total,
                        page_succeeded,
                        page_errors,
                    ) = await crawl_rank_video_details(
                        rpc,
                        pipeline,
                        video_ids=video_ids,
                        dry_run=dry_run,
                    )
                else:
                    page_total = page_succeeded = page_errors = 0
                total += page_total
                succeeded += page_succeeded
                errors += page_errors
                logger.info(
                    "%s 第 %d 页保存完成: videos=%d succeeded=%d errors=%d",
                    label,
                    page_no,
                    page_total,
                    page_succeeded,
                    page_errors,
                )
        else:
            assert fetch_video_ids is not None
            video_ids = await fetch_video_ids(rpc)
            total, succeeded, errors = await crawl_rank_video_details(
                rpc,
                pipeline,
                video_ids=video_ids,
                dry_run=dry_run,
            )
        if total == 0:
            raise RuntimeError("榜单未返回可用视频 ID")
        logger.info(
            "%s 抓取完成: videos=%d succeeded=%d errors=%d dry_run=%s",
            label,
            total,
            succeeded,
            errors,
            dry_run,
        )
    finally:
        await rpc.close()
        await pipeline.close()
        await bloom.aclose()
        await db.aclose()
