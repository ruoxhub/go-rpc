import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel

from common.errors import register_secret
from services.video_analysis.minio_source import DownloadedMinioVideo
from services.video_analysis.batch import (
    BatchSummary,
    ModelSnapshot,
    format_error,
    run_analysis_batch,
)
from services.video_analysis.repository import AnalysisJob


NOW = datetime(2026, 1, 2, 3, 4, 5)
FINISHED = datetime(2026, 1, 2, 3, 4, 6)


def test_registered_secret_is_redacted_without_a_field_name():
    secret = "runtime-provider-secret-123"
    register_secret(secret)

    rendered = format_error(RuntimeError(f"remote rejected {secret}"))

    assert secret not in rendered
    assert "remote rejected ***" in rendered


class Result(BaseModel):
    value: str
    details: dict[str, object]


class FakeRepository:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []
        self.succeeded = []
        self.failed = []
        self.cancelled = []
        self.succeed_error = None
        self.fail_error = None
        self.cancel_error = None

    async def reap_stale(self, **kwargs):
        self.calls.append(("reap", kwargs))

    async def claim_batch(self, **kwargs):
        self.calls.append(("claim", kwargs))
        return self.jobs

    async def mark_succeeded(self, **kwargs):
        if self.succeed_error:
            raise self.succeed_error
        self.succeeded.append(kwargs)

    async def mark_failed(self, **kwargs):
        if self.fail_error:
            raise self.fail_error
        self.failed.append(kwargs)

    async def mark_cancelled(self, jobs, **kwargs):
        if self.cancel_error:
            raise self.cancel_error
        self.cancelled.append((list(jobs), kwargs))
        return len(jobs)


class FakeSource:
    bucket = "videos"

    def __init__(self, failures=()):
        self.failures = set(failures)
        self.paths = []

    async def download(self, *, platform, content_id, target_dir):
        self.paths.append(Path(target_dir))
        if content_id in self.failures:
            raise RuntimeError(f"download failed: {content_id}")
        path = Path(target_dir) / f"{content_id}.mp4"
        path.write_bytes(b"video")
        return DownloadedMinioVideo(
            f"{content_id}/video", path, platform
        )


class FakeAnalysisService:
    def __init__(self, failure=None):
        self.failure = failure
        self.requests = []
        self.active = 0
        self.max_active = 0

    async def run(self, request):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self.requests.append(request)
            if self.failure:
                raise self.failure
            return Result(value="ok", details={"items": [1], "none": None})
        finally:
            self.active -= 1


def jobs(count=2):
    return [
        AnalysisJob(index, "tiktok", str(index), 1)
        for index in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_reaps_then_claims_with_expected_arguments():
    repository = FakeRepository([])
    summary = await run_analysis_batch(
        repository=repository,
        source=FakeSource(),
        analysis_service=FakeAnalysisService(),
        model=ModelSnapshot(id=7, name="provider/model-x"),
        request_path="chat",
        batch_size=7,
        max_attempts=4,
        stale_timeout_seconds=90,
        now=NOW,
    )

    assert repository.calls == [
        ("reap", {"cutoff": NOW - timedelta(seconds=90), "finished_at": NOW}),
        (
            "claim",
            {
                "batch_size": 7,
                "bucket": "videos",
                "model": ModelSnapshot(id=7, name="provider/model-x"),
                "max_attempts": 4,
                "now": NOW,
            },
        ),
    ]
    assert summary == BatchSummary(claimed=0, succeeded=0, failed=0, skipped=0)


@pytest.mark.asyncio
async def test_download_failure_does_not_stop_next_job_and_temp_dirs_are_removed():
    repository = FakeRepository(jobs())
    source = FakeSource(failures={"1"})
    service = FakeAnalysisService()

    summary = await run_analysis_batch(
        repository=repository,
        source=source,
        analysis_service=service,
        model="model-x",
        request_path="responses",
        batch_size=2,
        max_attempts=3,
        stale_timeout_seconds=60,
        now=NOW,
        clock=lambda: FINISHED,
    )

    assert summary == BatchSummary(2, 1, 1, 0)
    assert repository.failed[0]["object_name"] is None
    assert repository.succeeded[0]["object_name"] == "2/video"
    assert repository.succeeded[0]["bucket"] == "tiktok"
    assert repository.succeeded[0]["result"] == {
        "value": "ok",
        "details": {"items": [1], "none": None},
    }
    assert all(call["finished_at"] == FINISHED for call in repository.failed + repository.succeeded)
    assert service.max_active == 1
    assert all(not path.exists() for path in source.paths)


@pytest.mark.asyncio
async def test_analysis_failure_preserves_object_name():
    repository = FakeRepository(jobs(1))
    source = FakeSource()
    service = FakeAnalysisService(ValueError("bad analysis"))
    summary = await run_analysis_batch(
        repository=repository,
        source=source,
        analysis_service=service,
        model="model-x",
        request_path="responses",
        batch_size=1,
        max_attempts=3,
        stale_timeout_seconds=60,
        now=NOW,
    )

    assert summary == BatchSummary(1, 0, 1, 0)
    request = service.requests[0]
    assert request.model == "model-x"
    assert request.request_path == "responses"
    assert request.cleanup is True
    assert repository.failed[0]["object_name"] == "1/video"
    assert repository.failed[0]["bucket"] == "tiktok"
    assert all(not path.exists() for path in source.paths)


@pytest.mark.asyncio
async def test_request_path_defaults_to_chat_for_legacy_callers():
    repository = FakeRepository(jobs(1))
    service = FakeAnalysisService()

    await run_analysis_batch(
        repository=repository,
        source=FakeSource(),
        analysis_service=service,
        model="model-x",
        batch_size=1,
        max_attempts=3,
        stale_timeout_seconds=60,
        now=NOW,
    )

    assert service.requests[0].request_path == "chat"


@pytest.mark.asyncio
@pytest.mark.parametrize("review_route", ["R", "G", None])
async def test_analysis_request_receives_explicit_review_route(review_route):
    repository = FakeRepository(jobs(1))
    service = FakeAnalysisService()

    await run_analysis_batch(
        repository=repository,
        source=FakeSource(),
        analysis_service=service,
        model="model-x",
        review_route=review_route,
        batch_size=1,
        max_attempts=3,
        stale_timeout_seconds=60,
        now=NOW,
    )

    assert service.requests[0].review_route == review_route


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["success", "failure"])
async def test_repository_finish_errors_propagate(operation):
    repository = FakeRepository(jobs(1))
    source = FakeSource(failures={"1"} if operation == "failure" else ())
    error = RuntimeError("database unavailable")
    if operation == "success":
        repository.succeed_error = error
    else:
        repository.fail_error = error

    with pytest.raises(RuntimeError, match="database unavailable"):
        await run_analysis_batch(
            repository=repository,
            source=source,
            analysis_service=FakeAnalysisService(),
            model="model-x",
            request_path="chat",
            batch_size=1,
            max_attempts=3,
            stale_timeout_seconds=60,
            now=NOW,
        )


def test_format_error_uses_only_exception_type_and_message_and_truncates():
    try:
        try:
            raise RuntimeError("secret context")
        except RuntimeError as cause:
            raise ValueError("x" * 3000) from cause
    except ValueError as exc:
        rendered = format_error(exc)

    assert rendered.startswith("ValueError: ")
    assert len(rendered) == 2000
    assert "secret context" not in rendered


def test_format_error_redacts_credentials_before_truncating():
    rendered = format_error(
        RuntimeError(
            "diagnosis api_key=abc password:xyz access_key='minio' "
            "Bearer tok postgres://user:pass@host remains"
        )
    )

    assert "diagnosis" in rendered
    assert "remains" in rendered
    assert "api_key=***" in rendered
    assert "password:***" in rendered
    assert "access_key='***'" in rendered
    assert "Bearer ***" in rendered
    assert "[REDACTED_URL]" in rendered
    for secret in ("abc", "xyz", "minio", "tok"):
        assert secret not in rendered
    assert "postgres://user:pass@" not in rendered


def test_format_error_redacts_complete_urls():
    rendered = format_error(RuntimeError(
        "download failed for https://private.invalid/video?id=41&token=visible "
        "through socks5://proxy-user:proxy-pass@proxy.invalid:1080"
    ))

    assert rendered == (
        "RuntimeError: download failed for [REDACTED_URL] through [REDACTED_URL]"
    )
    for leaked in (
        "private.invalid",
        "video?id=41",
        "visible",
        "proxy-user",
        "proxy-pass",
        "proxy.invalid",
    ):
        assert leaked not in rendered


def test_format_error_redacts_quoted_spaces_and_preserves_boundaries():
    register_secret("secret")
    register_secret("access")
    rendered = format_error(RuntimeError(
        'token="abc def", password=\'hello world\'; '
        'api_key=third, secret:fourth; access_token=fifth; diagnosis'
    ))

    assert 'token="***",' in rendered
    assert "password='***';" in rendered
    assert "api_key=***," in rendered
    assert "secret:***;" in rendered
    assert "access_token=***;" in rendered
    assert "diagnosis" in rendered
    for secret in ("abc def", "hello world", "third", "fourth", "fifth"):
        assert secret not in rendered
    assert format_error(RuntimeError("remote access denied")).endswith(
        "remote *** denied"
    )


def test_format_error_redacts_escaped_quotes_and_backslashes():
    rendered = format_error(RuntimeError(
        r'''token="abc\" def" password='abc\' def' secret="one\\two\" three" '''
        r'''api_key=bare-value diagnosis remains'''
    ))

    assert 'token="***"' in rendered
    assert "password='***'" in rendered
    assert 'secret="***"' in rendered
    assert "api_key=***" in rendered
    assert "diagnosis remains" in rendered
    for secret in (
        r'abc\" def',
        r"abc\' def",
        r'one\\two\" three',
        "bare-value",
    ):
        assert secret not in rendered


@pytest.mark.parametrize(
    "message",
    [
        'token="unterminated secret diagnosis',
        "password='unterminated secret",
        r'token="unterminated\\path\" secret diagnosis',
        'token="abc def\\',
        "password='abc def\\",
    ],
)
def test_format_error_redacts_unterminated_quoted_value_to_end(message):
    rendered = format_error(RuntimeError(message))

    assert rendered.startswith("RuntimeError: ")
    assert "***" in rendered
    for leaked in ("unterminated", "secret", "diagnosis", "path"):
        assert leaked not in rendered
    assert message.split("=", 1)[1] not in rendered


@pytest.mark.parametrize(
    "key",
    [
        "OPENAI_API_KEY",
        "CRAWLER_PG_PASSWORD",
        "MINIO_SECRET_KEY",
        "MINIO_ACCESS_KEY",
        "openai-api-key",
        "crawler-pg-password",
    ],
)
def test_format_error_redacts_prefixed_sensitive_identifiers(key):
    rendered = format_error(RuntimeError(f"diagnosis {key}=credential remains"))

    assert f"{key}=***" in rendered
    assert "credential" not in rendered
    assert "diagnosis" in rendered
    assert "remains" in rendered


@pytest.mark.asyncio
async def test_cancellation_waits_for_analysis_before_temp_cleanup():
    started = asyncio.Event()
    release = asyncio.Event()
    observed = {}

    class BlockingAnalysisService:
        async def run(self, request):
            observed["path"] = Path(request.source)
            started.set()
            await release.wait()
            return Result(value="ok", details={})

    source = FakeSource()
    repository = FakeRepository(jobs(1))
    batch_task = asyncio.create_task(
        run_analysis_batch(
            repository=repository,
            source=source,
            analysis_service=BlockingAnalysisService(),
            model="model-x",
            request_path="chat",
            batch_size=1,
            max_attempts=3,
            stale_timeout_seconds=60,
            now=NOW,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    local_path = observed["path"]
    assert local_path.exists()

    batch_task.cancel()
    await asyncio.sleep(0)
    assert not batch_task.done()
    assert local_path.exists()

    batch_task.cancel()
    await asyncio.sleep(0)
    assert not batch_task.done()
    assert local_path.exists()

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await batch_task

    assert not local_path.exists()
    assert repository.failed == []
    assert len(repository.cancelled) == 1
    assert repository.cancelled[0][0] == jobs(1)
    assert isinstance(repository.cancelled[0][1]["finished_at"], datetime)


@pytest.mark.asyncio
async def test_cancellation_on_first_job_restores_current_and_remaining_jobs():
    started = asyncio.Event()

    class BlockingSource(FakeSource):
        async def download(self, **kwargs):
            started.set()
            await asyncio.Future()

    repository = FakeRepository(jobs(3))
    task = asyncio.create_task(run_analysis_batch(
        repository=repository, source=BlockingSource(),
        analysis_service=FakeAnalysisService(), model="model-x",
        batch_size=3, max_attempts=3, stale_timeout_seconds=60,
        now=NOW, clock=lambda: FINISHED,
    ))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert repository.cancelled == [
        (jobs(3), {"finished_at": FINISHED})
    ]


@pytest.mark.asyncio
async def test_cancellation_on_second_job_restores_only_unfinished_jobs():
    second_started = asyncio.Event()

    class BlockingSecondSource(FakeSource):
        async def download(self, *, content_id, **kwargs):
            if content_id == "2":
                second_started.set()
                await asyncio.Future()
            return await super().download(content_id=content_id, **kwargs)

    repository = FakeRepository(jobs(3))
    task = asyncio.create_task(run_analysis_batch(
        repository=repository, source=BlockingSecondSource(),
        analysis_service=FakeAnalysisService(), model="model-x",
        batch_size=3, max_attempts=3, stale_timeout_seconds=60,
        now=NOW, clock=lambda: FINISHED,
    ))
    await second_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert [call["job"] for call in repository.succeeded] == [jobs(3)[0]]
    assert repository.cancelled == [
        (jobs(3)[1:], {"finished_at": FINISHED})
    ]


@pytest.mark.asyncio
async def test_cancellation_recovery_failure_preserves_original_cancellation():
    started = asyncio.Event()

    class BlockingSource(FakeSource):
        async def download(self, **kwargs):
            started.set()
            await asyncio.Future()

    repository = FakeRepository(jobs(1))
    repository.cancel_error = RuntimeError("password=do-not-log")
    task = asyncio.create_task(run_analysis_batch(
        repository=repository, source=BlockingSource(),
        analysis_service=FakeAnalysisService(), model="model-x",
        batch_size=1, max_attempts=3, stale_timeout_seconds=60, now=NOW,
    ))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    assert exc_info.value.__notes__ == [
        "Video analysis cancellation recovery failed: RuntimeError: password=***"
    ]


@pytest.mark.asyncio
async def test_cleanup_failure_marks_job_failed_before_later_job_succeeds(
    monkeypatch,
):
    real_temporary_directory = tempfile.TemporaryDirectory
    created = 0

    class CleanupFailsFirst:
        def __init__(self):
            nonlocal created
            created += 1
            self._delegate = real_temporary_directory()
            self.name = self._delegate.name
            self._should_fail = created == 1

        def cleanup(self):
            self._delegate.cleanup()
            if self._should_fail:
                raise OSError("cleanup failed")

    monkeypatch.setattr(
        "services.video_analysis.batch.tempfile.TemporaryDirectory",
        CleanupFailsFirst,
    )
    repository = FakeRepository(jobs())

    summary = await run_analysis_batch(
        repository=repository,
        source=FakeSource(),
        analysis_service=FakeAnalysisService(),
        model="model-x",
        request_path="chat",
        batch_size=2,
        max_attempts=3,
        stale_timeout_seconds=60,
        now=NOW,
    )

    assert summary == BatchSummary(2, 1, 1, 0)
    assert repository.failed[0]["job"] == jobs()[0]
    assert repository.failed[0]["error_message"] == "OSError: cleanup failed"
    assert [call["job"] for call in repository.succeeded] == [jobs()[1]]


@pytest.mark.asyncio
async def test_processing_error_remains_primary_when_cleanup_also_fails(
    monkeypatch,
):
    real_temporary_directory = tempfile.TemporaryDirectory

    class CleanupFails:
        def __init__(self):
            self._delegate = real_temporary_directory()
            self.name = self._delegate.name

        def cleanup(self):
            self._delegate.cleanup()
            raise OSError("cleanup failed")

    monkeypatch.setattr(
        "services.video_analysis.batch.tempfile.TemporaryDirectory",
        CleanupFails,
    )
    repository = FakeRepository(jobs(1))

    summary = await run_analysis_batch(
        repository=repository,
        source=FakeSource(failures={"1"}),
        analysis_service=FakeAnalysisService(),
        model="model-x",
        request_path="chat",
        batch_size=1,
        max_attempts=3,
        stale_timeout_seconds=60,
        now=NOW,
    )

    assert summary == BatchSummary(1, 0, 1, 0)
    assert repository.failed[0]["error_message"] == (
        "RuntimeError: download failed: 1"
    )
