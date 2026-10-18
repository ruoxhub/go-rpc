"""Serial batch orchestration for video analysis jobs."""

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Literal, Protocol

from models.results import AnalysisRequest, AnalysisResult
from common.errors import format_error, redact_secrets

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchSummary:
    claimed: int
    succeeded: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class ModelSnapshot:
    id: int | None
    name: str


class AsyncAnalysisService(Protocol):
    def run(self, request: AnalysisRequest) -> Awaitable[AnalysisResult]: ...


def _redact_secrets(message: str) -> str:
    """Compatibility wrapper for existing imports."""
    return redact_secrets(message)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _drain_analysis_task(task: asyncio.Task) -> None:
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    try:
        task.result()
    except BaseException:
        pass


async def _restore_cancelled_jobs(repository, jobs, finished_at: datetime) -> None:
    restore_task = asyncio.create_task(
        repository.mark_cancelled(jobs, finished_at=finished_at)
    )
    while not restore_task.done():
        try:
            await asyncio.shield(restore_task)
        except asyncio.CancelledError:
            continue
    await restore_task


async def run_analysis_batch(
    *,
    repository,
    source,
    analysis_service: AsyncAnalysisService,
    model: ModelSnapshot | str,
    request_path: str = "chat",
    review_route: Literal["R", "G"] | None = None,
    batch_size: int,
    max_attempts: int,
    stale_timeout_seconds: float,
    now: datetime,
    clock: Callable[[], datetime] | None = None,
) -> BatchSummary:
    """Reap stale work, claim a batch, and process each job serially."""
    model_snapshot = (
        model if isinstance(model, ModelSnapshot) else ModelSnapshot(None, model)
    )
    finished_clock = clock or _utcnow_naive
    await repository.reap_stale(
        cutoff=now - timedelta(seconds=stale_timeout_seconds),
        finished_at=now,
    )
    jobs = await repository.claim_batch(
        batch_size=batch_size,
        bucket=source.bucket,
        model=model_snapshot,
        max_attempts=max_attempts,
        now=now,
    )

    succeeded = 0
    failed = 0
    pending_jobs = list(jobs)
    try:
        for job in jobs:
            object_name = None
            object_bucket = None
            temp_dir = None
            result_json = None
            primary_error: BaseException | None = None
            try:
                temp_dir = tempfile.TemporaryDirectory()
                downloaded = await source.download(
                    platform=job.platform,
                    content_id=job.content_id,
                    target_dir=Path(temp_dir.name),
                )
                object_name = downloaded.object_name
                object_bucket = downloaded.bucket

                async def run_analysis():
                    request = AnalysisRequest(
                        source=downloaded.local_path,
                        model=model_snapshot.name,
                        request_path=request_path,
                        review_route=review_route,
                        cleanup=True,
                    )
                    return await analysis_service.run(request)

                analysis_task = asyncio.create_task(run_analysis())
                try:
                    result = await asyncio.shield(analysis_task)
                except asyncio.CancelledError:
                    await _drain_analysis_task(analysis_task)
                    raise
                result_json = result.model_dump(mode="json")
            except BaseException as exc:
                primary_error = exc
            finally:
                if temp_dir is not None:
                    try:
                        temp_dir.cleanup()
                    except Exception as cleanup_error:
                        if primary_error is None:
                            primary_error = cleanup_error
                        else:
                            primary_error.add_note(
                                f"Temporary directory cleanup failed: "
                                f"{format_error(cleanup_error)}"
                            )

            if isinstance(primary_error, asyncio.CancelledError):
                raise primary_error
            if isinstance(primary_error, Exception):
                await repository.mark_failed(
                    job=job,
                    bucket=object_bucket,
                    object_name=object_name,
                    error_message=format_error(primary_error),
                    finished_at=finished_clock(),
                )
                failed += 1
                pending_jobs.pop(0)
                continue
            if primary_error is not None:
                raise primary_error

            await repository.mark_succeeded(
                job=job,
                bucket=object_bucket,
                object_name=object_name,
                result=result_json,
                finished_at=finished_clock(),
            )
            succeeded += 1
            pending_jobs.pop(0)
    except asyncio.CancelledError as cancelled:
        try:
            await _restore_cancelled_jobs(
                repository, pending_jobs, finished_clock()
            )
        except BaseException as recovery_error:
            cancelled.add_note(
                f"Video analysis cancellation recovery failed: "
                f"{format_error(recovery_error)}"
            )
            logger.warning(
                "Video analysis cancellation recovery failed: %s",
                type(recovery_error).__name__,
            )
        raise cancelled

    return BatchSummary(
        claimed=len(jobs),
        succeeded=succeeded,
        failed=failed,
        skipped=0,
    )
