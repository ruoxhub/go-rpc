"""清洗后视频下载 Worker。"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from cleaner.download_repository import DownloadJob, VideoDownloadRepository
from common.errors import format_error
from models import BusTask
from models.task_config import TaskConfig, VideoDownloadTaskConfig

from .base import BaseWorker
from .media_logging import log_media_event
from .result import WorkerResult

logger = logging.getLogger(__name__)


class VideoDownloadWorker(BaseWorker):
    executor = "video_download"

    def __init__(self, *args: Any, download_service: Any | None = None,
                 download_services: Mapping[bool, Any] | None = None,
                 download_repo: VideoDownloadRepository | None = None,
                 proxy_service_factory: Callable[[str], tuple[Any, Any]] | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic, **kwargs: Any):
        utcnow = kwargs.pop("utcnow", None)
        super().__init__(*args, **kwargs)
        if download_services is None:
            if download_service is None:
                raise ValueError("download_service or download_services is required")
            download_services = {True: download_service, False: download_service}
        self.download_services = dict(download_services)
        dynamic_proxy = proxy_service_factory is not None
        if False not in self.download_services:
            raise ValueError("direct download service is required")
        if dynamic_proxy and (self.config_store is None or True in self.download_services
                              or not callable(proxy_service_factory)):
            raise ValueError("dynamic proxy requires config_store and proxy_service_factory only")
        if not dynamic_proxy and set(self.download_services) != {False, True}:
            raise ValueError("static download_services must include direct and proxy services")
        self.download_repo = download_repo or VideoDownloadRepository(self.db)
        self._sleep = sleep
        self._clock = clock
        self._utcnow = utcnow or (
            lambda: datetime.now(timezone.utc).replace(tzinfo=None)
        )
        self._proxy_service_factory = proxy_service_factory

    async def execute_business(self, task: BusTask) -> WorkerResult:
        config = task.config if isinstance(task.config, TaskConfig) else TaskConfig.model_validate(task.config or {})
        return await self.run_batch(
            config.download,
            platform=task.platform or None,
            task_id=task.task_id,
            consumer_key=f"task:{task.task_id}",
        )

    async def run_batch(self, options: VideoDownloadTaskConfig | None = None, *, platform: str | None = None,
                        source: str = "media", offset: int = 0,
                        task_id: int | None = None,
                        consumer_key: str | None = None) -> WorkerResult:
        options = options or VideoDownloadTaskConfig()
        batch_id = uuid.uuid4().hex
        claim_token = uuid.uuid4().hex
        consumer_key = consumer_key or (
            f"task:{task_id}" if task_id is not None
            else f"cli:clean-and-download:{source}"
        )

        def db_now() -> datetime:
            now = self._utcnow()
            if now.tzinfo is not None:
                return now.astimezone(timezone.utc).replace(tzinfo=None)
            return now

        dynamic_proxy = options.use_proxy and self._proxy_service_factory is not None
        client = None
        if dynamic_proxy:
            proxy = await self.config_store.get_proxy()
            if not proxy.url.strip():
                raise ValueError("proxy URL is not configured")
            client, service = self._proxy_service_factory(proxy.url)
        else:
            service = self.download_services[options.use_proxy]

        async def close_client(primary_error: BaseException | None = None) -> None:
            if client is None:
                return
            try:
                result = client.aclose()
                if inspect.isawaitable(result):
                    await result
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    f"proxy client cleanup failed: {type(cleanup_error).__name__}"
                )

        jobs: list[DownloadJob] = []
        tasks: list[asyncio.Task[str]] = []
        terminal: set[tuple[int, str]] = set()
        preserve_claim: set[tuple[int, str]] = set()

        def job_key(job: DownloadJob) -> tuple[int, str]:
            return job.material_id, job.claim_token

        def latency_ms(started_at: float) -> int:
            return max(0, round((self._clock() - started_at) * 1000))

        def log_job(
            job: DownloadJob,
            outcome: str,
            started_at: float,
            error: BaseException | None = None,
        ) -> None:
            log_media_event(
                logger,
                logging.ERROR if error is not None else logging.INFO,
                task_id=task_id,
                consumer_key=consumer_key,
                platform=job.platform,
                content_id=job.content_id,
                batch_id=batch_id,
                claim_token_prefix=job.claim_token[:8],
                attempt_count=job.attempt_count,
                outcome=outcome,
                latency_ms=latency_ms(started_at),
                exception_type=type(error).__name__ if error is not None else None,
                error=error,
            )

        async def release_unfinished(primary_error: BaseException) -> None:
            for job in jobs:
                key = job_key(job)
                if key in terminal or key in preserve_claim:
                    continue
                try:
                    released = await self.download_repo.release_claim(job)
                    if not released:
                        raise RuntimeError("claim release rejected")
                except BaseException as release_error:
                    log_job(job, "failed", self._clock(), release_error)
                    primary_error.add_note(
                        f"claim release failed for material {job.material_id}: "
                        f"{type(release_error).__name__}"
                    )

        async def persist_failure(
            job: DownloadJob,
            error: BaseException,
            started_at: float,
            *,
            permanent: bool,
        ) -> str:
            retry_at = None
            if not permanent:
                delay = min(
                    options.retry_max_seconds,
                    options.retry_base_seconds * 2 ** (job.attempt_count - 1),
                )
                retry_at = db_now() + timedelta(seconds=delay)
            try:
                marked = await self.download_repo.mark_failed(
                    job,
                    format_error(error, max_length=500),
                    retry_at,
                    permanent=permanent,
                    max_attempts=options.max_attempts,
                )
            except BaseException as terminal_error:
                preserve_claim.add(job_key(job))
                log_job(job, "failed", started_at, terminal_error)
                raise
            terminal.add(job_key(job))
            if not marked:
                log_job(job, "skipped", started_at)
                return "skipped"
            log_job(job, "failed", started_at, error)
            return "failed"

        semaphore = asyncio.Semaphore(max(1, getattr(self.quota, "concurrency", 1)))
        rate_lock = asyncio.Lock()
        next_start = self._clock()
        interval = 1.0 / options.rps if options.rps > 0 else 0

        async def admit() -> None:
            nonlocal next_start
            if not interval:
                return
            async with rate_lock:
                delay = next_start - self._clock()
                if delay > 0:
                    await self._sleep(delay)
                next_start = max(next_start, self._clock()) + interval

        async def process(job: DownloadJob) -> str:
            started_at = self._clock()
            if job.input_error:
                return await persist_failure(
                    job, ValueError(job.input_error), started_at, permanent=True
                )
            candidate = job.candidate
            assert candidate is not None
            try:
                async with semaphore:
                    await admit()
                    download_media = getattr(service, "download_media", None)
                    if download_media is not None:
                        await download_media(
                            candidate.media_url,
                            candidate.music_url,
                            candidate.pic_url,
                            candidate.platform,
                            candidate.content_id,
                        )
                    else:
                        if candidate.page_url:
                            await service.download_with_ytdlp(
                                candidate.page_url,
                                candidate.platform,
                                candidate.content_id,
                            )
                        else:
                            await service.download(
                                candidate.media_url,
                                candidate.platform,
                                candidate.content_id,
                            )
                            if candidate.pic_url:
                                await service.download_cover(
                                    candidate.pic_url,
                                    candidate.platform,
                                    candidate.content_id,
                                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return await persist_failure(
                    job, exc, started_at, permanent=False
                )

            try:
                marked = await self.download_repo.mark_succeeded(job)
            except BaseException as terminal_error:
                preserve_claim.add(job_key(job))
                log_job(job, "failed", started_at, terminal_error)
                raise
            terminal.add(job_key(job))
            outcome = "succeeded" if marked else "skipped"
            log_job(job, "success" if marked else "skipped", started_at)
            return outcome

        try:
            now = db_now()
            jobs = await self.download_repo.claim_batch(
                min_grade=options.min_grade,
                batch_size=options.batch_size,
                platform=platform,
                offset=offset,
                claim_token=claim_token,
                now=now,
                stale_before=now - timedelta(seconds=options.claim_timeout_seconds),
                max_attempts=options.max_attempts,
            )
            logger.info(
                "视频下载批次开始 batch_id=%s task_id=%s total=%d",
                batch_id, task_id, len(jobs),
            )
            tasks = [asyncio.create_task(process(job)) for job in jobs]
            outcomes = await asyncio.gather(*tasks)
        except BaseException as primary_error:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await release_unfinished(primary_error)
            await close_client(primary_error)
            raise
        await close_client()
        result = WorkerResult(total=len(jobs), succeeded=outcomes.count("succeeded"),
                              failed=outcomes.count("failed"), skipped=outcomes.count("skipped"))
        logger.info(
            "视频下载批次结束 batch_id=%s task_id=%s succeeded=%d failed=%d skipped=%d",
            batch_id, task_id, result.succeeded, result.failed, result.skipped,
        )
        return result
