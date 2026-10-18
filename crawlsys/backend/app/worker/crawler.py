"""Config-driven crawler orchestrating work item sources and processors."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from common.errors import format_error
from common.logging import get_logger
from core.config import PlatformQuota
from core.repository import TaskRepo
from core.sink_handlers import ResultSinkRouter
from models import BusTask
from models.task_config import (
    DatabaseSourceConfig,
    RedisStreamSourceConfig,
    TaskConfig,
)
from pipeline import CrawlerPipeline
from services.parser_configuration.repository import (
    ActionParserRepository,
    ActionRuntimeDefinition,
)

from .base import BaseWorker
from .processors import (
    InvokeActionProcessor,
    PublishSourceProcessor,
    WorkItemProcessor,
    WorkItemValidationError,
)
from .rate_limit import PlatformLimiter
from .result import WorkerResult
from .sources import (
    DatabaseWorkItemSource,
    RedisStreamWorkItemSource,
    WorkItemSource,
)
from .work_item import (
    CrawlerRoundStats,
    ItemDisposition,
    ItemResult,
    SourceBatch,
    WorkItem,
)

logger = get_logger(__file__)
_ALLOWED_LOG_FIELDS = frozenset(
    {
        "ba_id",
        "platform",
        "action",
        "parser_source",
        "parser_revision_id",
        "task_id",
        "priority",
        "stream",
        "group",
        "consumer",
        "message_id",
        "delivery_count",
        "outcome",
        "latency_ms",
        "acked",
        "retried",
        "dead_lettered",
        "attempt",
        "backoff_ms",
        "error_type",
        "error_message",
        "raw_payload_bytes",
    }
)


def _safe_log_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key in _ALLOWED_LOG_FIELDS}


def _log_event(level: str, message: str, fields: dict[str, Any]) -> None:
    safe_fields = _safe_log_fields(fields)
    target = logger.bind(**safe_fields) if hasattr(logger, "bind") else logger
    kwargs = {} if hasattr(logger, "bind") else {"extra": safe_fields}
    getattr(target, level)(message, **kwargs)


def build_consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


class CrawlerWorker(BaseWorker):
    executor = "rpc_crawl"

    @property
    def task_platform_scope(self) -> str | None:
        return self._legacy_platform

    @property
    def consumer_name(self) -> str:
        return self._consumer_name

    @property
    def stream_queue(self) -> Any:
        return self._stream_queue

    @property
    def sink_router(self) -> ResultSinkRouter:
        return self._sink_router

    def __init__(
        self,
        platform: str | None = None,
        rpc: Any = None,
        repo: TaskRepo | None = None,
        pipeline: CrawlerPipeline | None = None,
        db: Any = None,
        quota: PlatformQuota | None = None,
        poll_interval: float = 1.0,
        default_loop_interval_seconds: int = 3600,
        zombie_reap_after_seconds: int = 600,
        heartbeat_interval_seconds: float | None = None,
        *,
        quotas: dict[str, PlatformQuota] | None = None,
        default_quota: PlatformQuota | None = None,
        persist_results: bool = True,
        config_store: Any = None,
        stream_queue: Any = None,
        sink_router: ResultSinkRouter | None = None,
        consumer_name_factory: Callable[[], str] = build_consumer_name,
        source_factory: Callable[[TaskConfig, BusTask], WorkItemSource] | None = None,
        processor_factory: Callable[[TaskConfig], WorkItemProcessor] | None = None,
        runtime_repository: ActionParserRepository | None = None,
    ) -> None:
        fallback_quota = default_quota or quota or PlatformQuota(platform="default")
        super().__init__(
            platform or "all-platforms",
            repo,
            db,
            fallback_quota,
            poll_interval,
            default_loop_interval_seconds,
            zombie_reap_after_seconds,
            heartbeat_interval_seconds,
            config_store,
        )
        self._legacy_platform = platform if quotas is None else None
        self._quotas = dict(quotas or {})
        if platform is not None and quota is not None:
            self._quotas.setdefault(platform, quota)
        self._default_quota = fallback_quota
        self._limiters: dict[str, PlatformLimiter] = {}
        self.rpc = rpc
        self.pipeline = pipeline
        self.persist_results = persist_results
        self._stream_queue = stream_queue
        self._sink_router = sink_router or ResultSinkRouter(
            db=db,
            pipeline=pipeline,
            stream_queue=stream_queue,
            persist_results=persist_results,
        )
        self._consumer_name = consumer_name_factory()
        self._source_factory = source_factory
        self._processor_factory = processor_factory
        self._runtime_repository = runtime_repository or ActionParserRepository(db)
        self.last_round_stats = CrawlerRoundStats()

    async def run(self) -> None:
        logger.info("Worker[%s] started, poll_interval=%.1fs", self.platform, self.poll_interval)
        while self._running:
            try:
                settings = await self._scheduler_settings()
            except Exception as error:  # noqa: BLE001 - polling boundary must survive backend errors
                logger.warning(
                    "Worker[%s] runtime config read failed: %s",
                    self.platform,
                    format_error(error, max_length=500),
                )
                await asyncio.sleep(0.5)
                continue
            tasks = await self.repo.get_pending_tasks(
                platform=self.task_platform_scope,
                executor=self.executor,
                limit=settings.batch_size,
            )
            if tasks:
                await asyncio.gather(
                    *(self.execute(task, settings) for task in tasks if self._running)
                )
                continue
            try:
                await self.repo.reclaim_stuck_running(
                    executor=self.executor,
                    platform=self.task_platform_scope,
                    older_than=datetime.now()  # noqa: DTZ005 - task timestamps are DB-naive
                    - timedelta(seconds=settings.zombie_reap_after_seconds),
                )
            except Exception as error:  # noqa: BLE001 - polling boundary must survive backend errors
                logger.warning(
                    "Worker[%s] reclaim failed: %s",
                    self.platform,
                    format_error(error, max_length=500),
                )
            await asyncio.sleep(settings.poll_interval_ms / 1000)

    def _quota_for(self, platform: str) -> PlatformQuota:
        return self._quotas.get(platform, self._default_quota)

    def _limiter_for(self, platform: str) -> PlatformLimiter:
        limiter = self._limiters.get(platform)
        if limiter is None:
            limiter = PlatformLimiter(self._quota_for(platform))
            self._limiters[platform] = limiter
        return limiter

    async def execute_business(self, task: BusTask) -> WorkerResult:
        started = time.perf_counter()
        config = self._parse_config(task)
        runtime = (
            await self._runtime_repository.load_runtime(
                task.ba_id,
                include_parser=config.execution_mode != "publish_source",
            )
            if task.ba_id is not None
            else ActionRuntimeDefinition(None, None, None)
        )
        source = self._make_source(config, task)
        processor = self._make_processor(config)
        stats = CrawlerRoundStats()
        completed = False
        try:
            batch = await source.fetch()
            stats.read = batch.read
            stats.claimed = batch.claimed
            if not batch.items:
                completed = True
                return WorkerResult()
            succeeded, failed = await self._run_task_items(
                task,
                config,
                runtime,
                batch,
                source,
                processor,
                stats,
            )
            completed = True
            return WorkerResult(
                total=len(batch.items),
                succeeded=succeeded,
                failed=failed,
                skipped=stats.skipped,
            )
        finally:
            self.last_round_stats = replace(stats)
            if completed:
                self._log_round_complete(task, config, runtime, stats, started)

    def _log_round_complete(
        self,
        task: BusTask,
        config: TaskConfig,
        runtime: ActionRuntimeDefinition,
        stats: CrawlerRoundStats,
        started: float,
    ) -> None:
        stream_source = (
            config.source if isinstance(config.source, RedisStreamSourceConfig) else None
        )
        if stream_source is not None:
            priority_val = (
                task.priority.db_value
                if hasattr(task.priority, "db_value")
                else int(task.priority)
                if task.priority is not None
                else None
            )
            fields = {
                "task_id": task.task_id,
                "priority": priority_val,
                "platform": task.platform,
                "action": task.action,
                "stream": stream_source.stream,
                "group": stream_source.group,
                "consumer": self.consumer_name,
                "message_id": None,
                "delivery_count": None,
                "outcome": "round_complete",
                "latency_ms": (time.perf_counter() - started) * 1000,
                "acked": stats.acked,
                "retried": stats.retried,
                "dead_lettered": stats.dead_lettered,
            }
            safe_fields = _safe_log_fields(fields)
            rendered_fields = " ".join(
                f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
                for key, value in safe_fields.items()
            )
            self._write_action_log(f"Crawler action round complete {rendered_fields}", fields)
        else:
            fields = {
                "ba_id": task.ba_id,
                "platform": task.platform,
                "action": task.action,
                "parser_source": "dynamic" if runtime.parser_definition else "static",
                "parser_revision_id": runtime.parser_revision_id,
            }
            self._write_action_log("Crawler action round complete", fields)

    def _log_item_terminal(
        self,
        task: BusTask,
        item: WorkItem,
        runtime: ActionRuntimeDefinition,
        disposition: ItemDisposition,
        started: float,
    ) -> None:
        receipt = item.receipt
        if receipt is None:
            return
        fields = {
            "task_id": task.task_id,
            "platform": task.platform,
            "action": task.action,
            "stream": receipt.stream,
            "group": receipt.group,
            "consumer": self.consumer_name,
            "message_id": receipt.message_id,
            "delivery_count": receipt.delivery_count,
            "outcome": disposition.value,
            "latency_ms": (time.perf_counter() - started) * 1000,
        }
        safe_fields = _safe_log_fields(fields)
        rendered_fields = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
            for key, value in safe_fields.items()
        )
        self._write_action_log(
            f"Crawler action message complete {rendered_fields}",
            fields,
        )

    @staticmethod
    def _write_action_log(message: str, fields: dict[str, Any]) -> None:
        safe_fields = _safe_log_fields(fields)
        target = logger.bind(**safe_fields) if hasattr(logger, "bind") else logger
        kwargs = {} if hasattr(logger, "bind") else {"extra": safe_fields}
        target.info(message, **kwargs)

    async def _run_task_items(
        self,
        task: BusTask,
        config: TaskConfig,
        runtime: ActionRuntimeDefinition,
        batch: SourceBatch,
        source: WorkItemSource,
        processor: WorkItemProcessor,
        stats: CrawlerRoundStats,
    ) -> tuple[int, int]:
        succeeded = 0
        failed = 0
        worker_count = min(config.max_inflight_items, len(batch.items))
        queue: asyncio.Queue[tuple[int, WorkItem] | object] = asyncio.Queue(
            maxsize=worker_count
        )
        stop = object()

        async def process(item: WorkItem) -> None:
            nonlocal succeeded, failed
            started = time.perf_counter()
            result = ItemResult()
            if item.input_error is not None:
                disposition = await source.fail(
                    item,
                    WorkItemValidationError(item.input_error),
                    deterministic=True,
                )
            else:
                try:
                    result = await processor.process(task, item, runtime)
                except WorkItemValidationError as error:
                    disposition = await source.fail(item, error, deterministic=True)
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # noqa: BLE001 - source owns retry classification
                    disposition = await source.fail(item, error, deterministic=False)
                else:
                    sink = result.sink
                    stats.produced += sink.produced
                    stats.deduplicated += sink.deduplicated
                    stats.skipped += sink.skipped
                    disposition = await source.complete(item)

            if disposition is ItemDisposition.SUCCEEDED:
                succeeded += 1
                if item.receipt is not None:
                    stats.acked += 1
            elif disposition is ItemDisposition.FAILED:
                failed += 1
            elif disposition is ItemDisposition.RETRY:
                stats.retried += 1
            elif disposition is ItemDisposition.DEAD_LETTERED:
                stats.dead_lettered += 1
            self._log_item_terminal(task, item, runtime, disposition, started)

        async def consume() -> None:
            while True:
                queued = await queue.get()
                try:
                    if queued is stop:
                        return
                    _index, item = queued
                    await process(item)
                finally:
                    queue.task_done()

        consumers = [asyncio.create_task(consume()) for _ in range(worker_count)]

        async def produce() -> None:
            for entry in enumerate(batch.items, 1):
                await queue.put(entry)
            for _ in consumers:
                await queue.put(stop)

        producer = asyncio.create_task(produce())
        tasks = [producer, *consumers]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for running in tasks:
                running.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return succeeded, failed

    def _make_source(self, config: TaskConfig, task: BusTask) -> WorkItemSource:
        if self._source_factory is not None:
            return self._source_factory(config, task)
        if isinstance(config.source, RedisStreamSourceConfig):
            if self._stream_queue is None:
                raise ValueError("Redis Stream source requires a configured StreamQueue")
            return RedisStreamWorkItemSource(
                self._stream_queue,
                config.source,
                consumer=self._consumer_name,
                consumer_task_id=task.task_id,
            )
        return DatabaseWorkItemSource(
            self.db,
            config.source if isinstance(config.source, DatabaseSourceConfig) else None,
            platform=task.platform,
        )

    def _make_processor(self, config: TaskConfig) -> WorkItemProcessor:
        if self._processor_factory is not None:
            return self._processor_factory(config)
        if config.execution_mode == "publish_source":
            return PublishSourceProcessor(sink_router=self._sink_router)
        return InvokeActionProcessor(
            rpc=self.rpc,
            limiter_for=self._limiter_for,
            sink_router=self._sink_router,
        )

    @staticmethod
    def _parse_config(task: BusTask) -> TaskConfig:
        if task.config is None:
            return TaskConfig()
        if isinstance(task.config, TaskConfig):
            return task.config
        return TaskConfig.model_validate(task.config)

__all__ = ["CrawlerRoundStats", "CrawlerWorker", "WorkItem", "build_consumer_name"]
