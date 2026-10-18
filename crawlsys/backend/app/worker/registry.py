"""Worker 注册表与调度进程依赖构造。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import httpx
from cleaner.download_repository import VideoDownloadRepository
from cleaner.repository import CleanerRepository
from core.config import PlatformQuota, SchedulerConfig
from core.repository import PlatformRepo, TaskRepo
from core.sink_handlers import ResultSinkRouter
from core.stream_queue import StreamQueue
from filter import Bloom
from go_rpc import RpcClient
from llm.catalog import LlmCatalog
from llm.migration import RuntimeConfigReferenceChecker, migrate_legacy_llm_settings
from llm.model_factory import LitellmModelFactory
from llm.transcription import LiteLlmTranscriber
from models import SiteSource
from parser import general_parser
from pipeline import CrawlerPipeline
from runtime_config.defaults import build_runtime_config_defaults
from runtime_config.store import RuntimeConfigStore
from services.video_analysis.minio_source import MinioVideoSource
from services.video_analysis.repository import VideoAnalysisRepository
from services.video_download import VideoDownloadService
from storage import MinioDB, RedisDB, SQLAlchemyDB
from tools.ytdlp import YtDlpClient

from .crawler import CrawlerWorker
from .video_analysis import VideoAnalysisWorker, build_analysis_service
from .video_clean import VideoCleanWorker
from .video_download import VideoDownloadWorker

WORKER_TYPES = {
    "rpc_crawl": CrawlerWorker,
    "video_clean": VideoCleanWorker,
    "video_download": VideoDownloadWorker,
    "video_analysis": VideoAnalysisWorker,
}

logger = logging.getLogger(__name__)


def create_workers(dependencies: Mapping[str, Mapping[str, Any]]) -> list[Any]:
    """按 executor 各构造一个 Worker。"""
    missing = set(WORKER_TYPES) - set(dependencies)
    if missing:
        raise ValueError(f"缺少 Worker 依赖: {sorted(missing)}")
    workers = []
    try:
        for executor, worker_type in WORKER_TYPES.items():
            workers.append(worker_type(**dependencies[executor]))
    except BaseException:
        for worker in reversed(workers):
            try:
                worker.stop()
            except Exception as stop_error:
                logger.warning("Worker 构造回滚停止失败: %s", type(stop_error).__name__)
        raise
    return workers


@dataclass
class WorkerRuntime:
    workers: list[Any]
    _stack: AsyncExitStack
    active_quota_count: int = 0
    _stop_requested: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False)
    _close_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _close_task: asyncio.Task[None] | None = field(default=None, init=False)

    def request_stop(self) -> None:
        if self._stop_requested:
            return
        self._stop_requested = True
        for worker in reversed(self.workers):
            try:
                worker.stop()
            except Exception as stop_error:
                logger.warning("Worker 停止失败: %s", type(stop_error).__name__)

    async def close(self) -> None:
        self.request_stop()
        async with self._close_lock:
            if self._closed:
                return
            if self._close_task is None:
                self._close_task = asyncio.create_task(self._stack.aclose())
            close_task = self._close_task
        await asyncio.shield(close_task)
        self._closed = True


def _http_client(proxy: str | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        proxy=proxy,
        trust_env=False,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
        headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"},
    )


async def build_runtime(config: SchedulerConfig, config_path: str) -> WorkerRuntime:
    """构造四类全局 Worker；任何阶段失败都会回收已创建资源。"""
    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
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
        stack.push_async_callback(db.aclose)
        await db.aconnect()
        await db.ainit_db()
        await db.amigrate_db()

        config_redis = RedisDB(config.redis.url, amode=True)
        stack.push_async_callback(config_redis.aclose)
        await config_redis.aconnect()
        stream_queue = StreamQueue(config_redis.get_redis_obj())
        defaults = build_runtime_config_defaults(config, config_path)
        config_store = RuntimeConfigStore(config_redis, defaults)
        await migrate_legacy_llm_settings(db, config_redis, defaults.legacy_llm)
        llm_catalog = LlmCatalog(
            db,
            reference_checker=RuntimeConfigReferenceChecker(db, config_redis),
        )

        bloom = Bloom(redis_url=config.redis.url, amode=True)
        stack.push_async_callback(bloom.aclose)
        pipeline = CrawlerPipeline(filter=bloom, store=db)
        stack.push_async_callback(pipeline.close)
        rpc = RpcClient(token=config.rpc_token, config_store=config_store)
        stack.push_async_callback(rpc.close)
        sink_router = ResultSinkRouter(
            db=db,
            pipeline=pipeline,
            parser=general_parser,
            stream_queue=stream_queue,
            persist_results=True,
        )

        minio_config = config.minio
        minio = MinioDB(
            endpoint=f"{minio_config.host}:{minio_config.port}",
            access_key=minio_config.username,
            secret_key=minio_config.password,
            secure=minio_config.secure,
            amode=True,
        )
        stack.push_async_callback(minio.aclose)
        bucket = "videos"
        audio_bucket = bucket
        cover_bucket = bucket

        direct_client = _http_client()
        stack.push_async_callback(direct_client.aclose)
        quotas_list = await SiteSource.load_active_quotas(db)
        quotas = {quota.platform: quota for quota in quotas_list}
        default_quota = PlatformQuota(platform="default")
        shared = dict(
            repo=TaskRepo(db=db),
            db=db,
            poll_interval=config.poll_interval,
            default_loop_interval_seconds=config.default_loop_interval_seconds,
            zombie_reap_after_seconds=config.zombie_reap_after_seconds,
            config_store=config_store,
        )

        def proxy_service_factory(url: str):
            client = _http_client(url)
            return client, VideoDownloadService(
                client,
                minio,
                bucket,
                audio_bucket=audio_bucket,
                cover_bucket=cover_bucket,
                ytdlp_client=YtDlpClient(proxy_url=url),
                proxy_url=url,
            )

        dependencies = {
            "rpc_crawl": dict(
                **shared,
                platform=None,
                rpc=rpc,
                pipeline=pipeline,
                stream_queue=stream_queue,
                sink_router=sink_router,
                quotas=quotas,
                default_quota=default_quota,
            ),
            "video_clean": dict(
                **shared,
                platform="video-clean",
                quota=default_quota,
                cleaner_repo=CleanerRepository(db),
                platform_provider=PlatformRepo(db),
            ),
            "video_download": dict(
                **shared,
                platform="video-download",
                quota=default_quota,
                download_repo=VideoDownloadRepository(db),
                download_services={
                    False: VideoDownloadService(
                        direct_client,
                        minio,
                        bucket,
                        audio_bucket=audio_bucket,
                        cover_bucket=cover_bucket,
                    )
                },
                proxy_service_factory=proxy_service_factory,
            ),
            "video_analysis": dict(
                **shared,
                platform="video-analysis",
                quota=default_quota,
                source=MinioVideoSource(minio, bucket),
                analysis_service_factory=build_analysis_service,
                catalog=llm_catalog,
                model_factory=LitellmModelFactory(llm_catalog),
                transcriber=LiteLlmTranscriber(),
                analysis_repo=VideoAnalysisRepository(db),
            ),
        }
        return WorkerRuntime(create_workers(dependencies), stack, len(quotas))
    except BaseException as primary_error:
        try:
            await stack.aclose()
        except BaseException as cleanup_error:
            primary_error.add_note(
                f"Worker 资源清理失败: {type(cleanup_error).__name__}"
            )
        raise
