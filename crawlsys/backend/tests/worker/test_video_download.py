import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cleaner.download_repository import DownloadCandidate, DownloadJob, VideoDownloadRepository
from worker.video_clean import VideoCleanWorker
from worker.video_download import VideoDownloadWorker
from models import BusTask
from models.task_config import VideoDownloadTaskConfig


def row(index=1, pic_url=None, page_url=None):
    return DownloadCandidate(
        index, "tiktok", str(index), index, f"https://cdn/{index}.mp4",
        pic_url, page_url,
    )


def make_worker(repo, service):
    return VideoDownloadWorker("download", None, None, SimpleNamespace(),
                               download_repo=repo, download_service=service)


FIXED_NOW = datetime(2026, 8, 9, 12, 0)


def download_job(*, content_id="1", token="batch-1", attempt=1, input_error=None):
    candidate = None if input_error else DownloadCandidate(
        int(content_id), "tiktok", content_id, None,
        f"https://cdn/{content_id}.mp4", f"https://cdn/{content_id}.jpg",
        music_url=f"https://cdn/{content_id}.mp3",
    )
    return DownloadJob(
        candidate=candidate,
        material_id=int(content_id),
        platform="tiktok",
        content_id=content_id,
        claim_token=token,
        attempt_count=attempt,
        input_error=input_error,
    )


def claimed(*candidates):
    return [
        DownloadJob(
            candidate=candidate,
            material_id=candidate.material_id,
            platform=candidate.platform,
            content_id=candidate.content_id,
            claim_token=f"claim-{candidate.content_id}",
            attempt_count=1,
        )
        for candidate in candidates
    ]
def lease_repo(*jobs):
    return SimpleNamespace(
        claim_batch=AsyncMock(return_value=list(jobs)),
        mark_succeeded=AsyncMock(return_value=True),
        mark_failed=AsyncMock(return_value=True),
        release_claim=AsyncMock(return_value=True),
    )


def lease_worker(repo, service, **kwargs):
    return VideoDownloadWorker(
        "download", None, None, SimpleNamespace(concurrency=2),
        download_repo=repo, download_service=service,
        utcnow=lambda: FIXED_NOW, **kwargs,
    )


@pytest.mark.asyncio
async def test_success_marks_downloaded_with_same_claim():
    job = download_job(token="batch-1", attempt=1)
    repo = lease_repo(job)
    service = SimpleNamespace(download_media=AsyncMock())

    result = await lease_worker(repo, service).run_batch(
        VideoDownloadTaskConfig(), task_id=41
    )

    service.download_media.assert_awaited_once()
    repo.mark_succeeded.assert_awaited_once_with(job)
    assert result.succeeded == 1
    assert repo.claim_batch.await_args.kwargs["stale_before"] == (
        FIXED_NOW - timedelta(seconds=1800)
    )
    assert repo.claim_batch.await_args.kwargs["now"].tzinfo is None
    assert repo.claim_batch.await_args.kwargs["stale_before"].tzinfo is None


@pytest.mark.asyncio
async def test_transient_failure_sets_exponential_retry(caplog):
    job = download_job(token="batch-1", attempt=3)
    repo = lease_repo(job)
    service = SimpleNamespace(download_media=AsyncMock(
        side_effect=TimeoutError("upstream timeout")
    ))

    with caplog.at_level("INFO"):
        result = await lease_worker(repo, service).run_batch(
            VideoDownloadTaskConfig(
                retry_base_seconds=60, retry_max_seconds=3600
            ),
            task_id=41,
        )

    retry_at = repo.mark_failed.await_args.args[2]
    assert retry_at == FIXED_NOW + timedelta(seconds=240)
    assert repo.mark_failed.await_args.kwargs == {
        "permanent": False,
        "max_attempts": 5,
    }
    assert result.failed == 1
    record = next(
        record for record in caplog.records
        if getattr(record, "outcome", None) == "failed"
    )
    assert record.task_id == 41
    assert record.consumer_key == "task:41"
    assert record.platform == job.platform
    assert record.content_id == job.content_id
    assert record.batch_id is not None
    assert record.claim_token_prefix == job.claim_token[:8]
    assert record.attempt_count == 3
    assert record.exception_type == "TimeoutError"


@pytest.mark.asyncio
async def test_invalid_claim_payload_is_permanent_failure():
    job = download_job(input_error="missing music_url")
    repo = lease_repo(job)
    service = SimpleNamespace(download_media=AsyncMock())

    result = await lease_worker(repo, service).run_batch(
        VideoDownloadTaskConfig(max_attempts=5), task_id=41
    )

    service.download_media.assert_not_awaited()
    assert repo.mark_failed.await_args.kwargs == {
        "permanent": True,
        "max_attempts": 5,
    }
    assert result.failed == 1


@pytest.mark.asyncio
async def test_download_terminal_write_failure_logs_then_propagates(caplog):
    job = download_job(token="full-secret-claim-token", attempt=1)
    repo = lease_repo(job)
    repo.mark_succeeded.side_effect = RuntimeError(
        "url=https://db.invalid token=database-secret"
    )
    service = SimpleNamespace(download_media=AsyncMock())

    with caplog.at_level("INFO"), pytest.raises(RuntimeError, match="database-secret"):
        await lease_worker(repo, service).run_batch(
            VideoDownloadTaskConfig(), task_id=41
        )

    record = next(
        record for record in caplog.records
        if getattr(record, "outcome", None) == "failed"
    )
    assert record.claim_token_prefix == job.claim_token[:8]
    assert "full-secret-claim-token" not in caplog.text
    assert "https://" not in caplog.text
    repo.release_claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_releases_unfinished_claims():
    first = download_job(content_id="1")
    second = download_job(content_id="2")
    repo = lease_repo(first, second)
    service = SimpleNamespace(download_media=AsyncMock(
        side_effect=asyncio.CancelledError
    ))

    with pytest.raises(asyncio.CancelledError):
        await lease_worker(repo, service).run_batch(
            VideoDownloadTaskConfig(), task_id=41
        )

    released = {
        call.args[0].content_id for call in repo.release_claim.await_args_list
    }
    assert released == {"1", "2"}


@pytest.mark.asyncio
async def test_lost_claim_is_skipped_not_reported_success():
    repo = lease_repo(download_job())
    repo.mark_succeeded.return_value = False

    result = await lease_worker(
        repo, SimpleNamespace(download_media=AsyncMock())
    ).run_batch(VideoDownloadTaskConfig(), task_id=41)

    assert (result.succeeded, result.failed, result.skipped) == (0, 0, 1)


@pytest.mark.asyncio
async def test_download_filters_query_and_continues_after_failure(caplog):
    jobs = claimed(row(1), row(2))
    repo = SimpleNamespace(claim_batch=AsyncMock(return_value=jobs),
                           mark_succeeded=AsyncMock(return_value=True),
                           mark_failed=AsyncMock(return_value=True),
                           release_claim=AsyncMock(return_value=True))
    service = SimpleNamespace(download=AsyncMock(side_effect=[RuntimeError("HTTP failed"), None]))
    result = await make_worker(repo, service).execute_business(BusTask(task_id=42, platform="tiktok", action="download", config={
        "executor": "video_download", "download": {"batch_size": 2, "min_grade": 2}
    }))
    assert (result.total, result.succeeded, result.failed) == (2, 1, 1)
    assert repo.claim_batch.await_args.kwargs["min_grade"] == 2
    assert repo.claim_batch.await_args.kwargs["platform"] == "tiktok"
    repo.mark_succeeded.assert_awaited_once_with(jobs[1])
    assert any(record.task_id == 42 for record in caplog.records if hasattr(record, "task_id"))


@pytest.mark.asyncio
async def test_upload_failure_does_not_mark_and_mark_failure_is_failed():
    repo = lease_repo(*claimed(row()))
    result = await make_worker(repo, SimpleNamespace(download=AsyncMock(side_effect=RuntimeError("upload")))).run_batch()
    assert result.failed == 1
    repo.mark_succeeded.assert_not_awaited()

    repo.mark_succeeded.side_effect = RuntimeError("db")
    with pytest.raises(RuntimeError, match="db"):
        await make_worker(repo, SimpleNamespace(download=AsyncMock())).run_batch()


@pytest.mark.asyncio
async def test_downloads_cover_before_marking_downloaded():
    candidate = row(pic_url="https://cdn/cover.jpg")
    job = claimed(candidate)[0]
    repo = lease_repo(job)
    service = SimpleNamespace(download=AsyncMock(), download_cover=AsyncMock())

    result = await make_worker(repo, service).run_batch()

    assert result.succeeded == 1
    service.download.assert_awaited_once_with(
        candidate.media_url, "tiktok", candidate.content_id
    )
    service.download_cover.assert_awaited_once_with(
        candidate.pic_url, "tiktok", candidate.content_id
    )
    repo.mark_succeeded.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_uses_ytdlp_for_page_url():
    candidate = row(page_url="https://www.tiktok.com/@user/video/1")
    repo = lease_repo(*claimed(candidate))
    service = SimpleNamespace(
        download=AsyncMock(), download_cover=AsyncMock(),
        download_with_ytdlp=AsyncMock(),
    )

    result = await make_worker(repo, service).run_batch()

    assert result.succeeded == 1
    service.download_with_ytdlp.assert_awaited_once_with(
        candidate.page_url, "tiktok", "1"
    )
    service.download.assert_not_awaited()
    service.download_cover.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefers_download_media_for_all_direct_resources():
    candidate = row(
        pic_url="https://cdn/cover.jpg",
        page_url="https://www.tiktok.com/@user/video/1",
    )
    candidate = type(candidate)(
        **{**candidate.__dict__, "music_url": "https://cdn/audio.mp3"}
    )
    repo = lease_repo(*claimed(candidate))
    service = SimpleNamespace(
        download_media=AsyncMock(),
        download_with_ytdlp=AsyncMock(),
        download=AsyncMock(),
        download_cover=AsyncMock(),
    )

    result = await make_worker(repo, service).run_batch()

    assert result.succeeded == 1
    service.download_media.assert_awaited_once_with(
        candidate.media_url,
        candidate.music_url,
        candidate.pic_url,
        "tiktok",
        "1",
    )
    service.download_with_ytdlp.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_log_does_not_leak_url_or_exception_message(caplog):
    secret = "https://cdn/video.mp4?signature=TOP_SECRET"
    candidate = DownloadCandidate(1, "tiktok", "safe-id", 1, secret)
    repo = lease_repo(*claimed(candidate))
    service = SimpleNamespace(download=AsyncMock(side_effect=RuntimeError(secret)))
    result = await make_worker(repo, service).run_batch()
    assert result.failed == 1
    records = [record for record in caplog.records if getattr(record, "outcome", None)]
    assert records[-1].platform == "tiktok"
    assert records[-1].content_id == "safe-id"
    assert records[-1].exception_type == "RuntimeError"
    batch_ids = {record.batch_id for record in records}
    assert len(batch_ids) == 1
    assert "TOP_SECRET" not in caplog.text
    assert "https://" not in caplog.text
    repo.mark_succeeded.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_mark_is_skipped_and_cancel_is_propagated():
    repo = lease_repo(*claimed(row()))
    repo.mark_succeeded.return_value = False
    result = await make_worker(repo, SimpleNamespace(download=AsyncMock())).run_batch()
    assert (result.succeeded, result.skipped) == (0, 1)

    service = SimpleNamespace(download=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await make_worker(repo, service).run_batch()


@pytest.mark.asyncio
async def test_rps_spaces_record_starts_and_zero_does_not_sleep():
    repo = lease_repo(*claimed(row(1), row(2), row(3)))
    now = [10.0]
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=3),
                                 download_repo=repo, download_service=SimpleNamespace(download=AsyncMock()),
                                 sleep=sleep, clock=lambda: now[0])
    await worker.run_batch(VideoDownloadTaskConfig(rps=2))
    assert sleeps == [0.5, 0.5]
    sleeps.clear()
    await worker.run_batch(VideoDownloadTaskConfig(rps=0))
    assert sleeps == []


@pytest.mark.asyncio
async def test_cancelling_rate_limited_batch_cancels_started_and_waiting_children():
    repo = lease_repo(*claimed(row(1), row(2)))
    download_started = asyncio.Event()
    release_download = asyncio.Event()
    sleep_started = asyncio.Event()

    async def download(*args):
        download_started.set()
        await release_download.wait()

    async def sleep(delay):
        sleep_started.set()
        await asyncio.Event().wait()

    service = SimpleNamespace(download=AsyncMock(side_effect=download))
    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=2),
                                 download_repo=repo, download_service=service,
                                 sleep=sleep, clock=lambda: 0.0)
    task = asyncio.create_task(worker.run_batch(VideoDownloadTaskConfig(rps=1)))
    await download_started.wait()
    await sleep_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    repo.mark_succeeded.assert_not_awaited()
    assert service.download.await_count == 1


@pytest.mark.asyncio
async def test_rate_limit_applies_at_download_start_when_concurrency_is_full():
    repo = lease_repo(*claimed(row(1), row(2), row(3)))
    now = [0.0]
    starts = []
    first_two_started = asyncio.Event()
    release = asyncio.Event()

    async def sleep(delay):
        now[0] += delay
        await asyncio.sleep(0)

    async def download(*args):
        starts.append(now[0])
        if len(starts) == 2:
            first_two_started.set()
        if len(starts) <= 2:
            await release.wait()

    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=2),
                                 download_repo=repo,
                                 download_service=SimpleNamespace(download=AsyncMock(side_effect=download)),
                                 sleep=sleep, clock=lambda: now[0])
    task = asyncio.create_task(worker.run_batch(VideoDownloadTaskConfig(rps=2)))
    await first_two_started.wait()
    release.set()
    await task
    assert starts == [0.0, 0.5, 1.0]


@pytest.mark.asyncio
@pytest.mark.parametrize("use_proxy", [True, False])
async def test_use_proxy_selects_prebuilt_service(use_proxy):
    repo = lease_repo(*claimed(row()))
    proxy = SimpleNamespace(download=AsyncMock())
    direct = SimpleNamespace(download=AsyncMock())
    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                 download_repo=repo, download_services={True: proxy, False: direct})
    await worker.run_batch(VideoDownloadTaskConfig(use_proxy=use_proxy))
    selected, other = (proxy, direct) if use_proxy else (direct, proxy)
    selected.download.assert_awaited_once()
    other.download.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_settings_refresh_per_batch_and_clients_are_closed():
    repo = lease_repo(*claimed(row()))
    store = SimpleNamespace(get_proxy=AsyncMock(side_effect=[
        SimpleNamespace(url="http://proxy-one"), SimpleNamespace(url="http://proxy-two")
    ]))
    clients = [SimpleNamespace(aclose=AsyncMock()), SimpleNamespace(aclose=AsyncMock())]
    services = [SimpleNamespace(download=AsyncMock()), SimpleNamespace(download=AsyncMock())]
    calls = []

    def factory(url):
        calls.append(url)
        index = len(calls) - 1
        return clients[index], services[index]

    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                 config_store=store, download_repo=repo,
                                 download_services={False: SimpleNamespace(download=AsyncMock())},
                                 proxy_service_factory=factory)
    await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))
    await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))
    assert calls == ["http://proxy-one", "http://proxy-two"]
    clients[0].aclose.assert_awaited_once()
    clients[1].aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_proxy_empty_url_and_read_error_do_not_create_client():
    repo = lease_repo(*claimed(row()))
    factory = Mock()
    store = SimpleNamespace(get_proxy=AsyncMock(return_value=SimpleNamespace(url="")))
    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                 config_store=store, download_repo=repo,
                                 download_services={False: object()}, proxy_service_factory=factory)
    with pytest.raises(ValueError, match="proxy URL"):
        await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))
    factory.assert_not_called()

    store.get_proxy.side_effect = RuntimeError("redis failed")
    with pytest.raises(RuntimeError, match="redis failed"):
        await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_proxy_client_closes_on_download_failure_and_cancellation():
    repo = lease_repo(*claimed(row()))
    store = SimpleNamespace(get_proxy=AsyncMock(return_value=SimpleNamespace(url="http://proxy")))

    for error, should_raise in ((RuntimeError("download failed"), False), (asyncio.CancelledError(), True)):
        client = SimpleNamespace(aclose=AsyncMock())
        service = SimpleNamespace(download=AsyncMock(side_effect=error))
        worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                     config_store=store, download_repo=repo,
                                     download_services={False: object()},
                                     proxy_service_factory=lambda url: (client, service))
        if should_raise:
            with pytest.raises(asyncio.CancelledError):
                await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))
        else:
            assert (await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))).failed == 1
        client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_download_does_not_read_proxy_settings():
    repo = lease_repo(*claimed(row()))
    store = SimpleNamespace(get_proxy=AsyncMock())
    direct = SimpleNamespace(download=AsyncMock())
    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                 config_store=store, download_repo=repo,
                                 download_services={False: direct},
                                 proxy_service_factory=Mock())
    await worker.run_batch(VideoDownloadTaskConfig(use_proxy=False))
    store.get_proxy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("primary", [RuntimeError("business failed"), asyncio.CancelledError()])
async def test_proxy_cleanup_failure_preserves_primary_error(primary):
    repo = lease_repo()
    repo.claim_batch.side_effect = primary
    client = SimpleNamespace(aclose=AsyncMock(side_effect=ValueError("close secret")))
    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                 config_store=SimpleNamespace(get_proxy=AsyncMock(
                                 return_value=SimpleNamespace(url="http://proxy"))),
                                 download_repo=repo, download_services={False: object()},
                                 proxy_service_factory=lambda url: (client, object()))
    with pytest.raises(type(primary)) as caught:
        await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))
    assert caught.value is primary
    assert caught.value.__notes__ == ["proxy client cleanup failed: ValueError"]


@pytest.mark.asyncio
async def test_proxy_success_propagates_cleanup_failure():
    repo = lease_repo()
    client = SimpleNamespace(aclose=AsyncMock(side_effect=ValueError("close failed")))
    worker = VideoDownloadWorker("download", None, None, SimpleNamespace(concurrency=1),
                                 config_store=SimpleNamespace(get_proxy=AsyncMock(
                                     return_value=SimpleNamespace(url="http://proxy"))),
                                 download_repo=repo, download_services={False: object()},
                                 proxy_service_factory=lambda url: (client, object()))
    with pytest.raises(ValueError, match="close failed"):
        await worker.run_batch(VideoDownloadTaskConfig(use_proxy=True))


def test_download_rejects_missing_or_conflicting_mode_dependencies():
    base = ("download", None, None, SimpleNamespace())
    with pytest.raises(ValueError, match="direct"):
        VideoDownloadWorker(*base, download_services={True: object()})
    with pytest.raises(ValueError, match="static download_services"):
        VideoDownloadWorker(*base, download_services={False: object()})
    with pytest.raises(ValueError, match="dynamic proxy"):
        VideoDownloadWorker(*base, download_services={False: object()}, proxy_service_factory=lambda url: None)
    with pytest.raises(ValueError, match="dynamic proxy"):
        VideoDownloadWorker(*base, config_store=object(), download_services={False: object(), True: object()},
                            proxy_service_factory=lambda url: None)


def test_script_reuses_workers_without_legacy_loops():
    from scripts import clean_and_download_videos as script

    assert script.VideoCleanWorker is VideoCleanWorker
    assert script.VideoDownloadWorker is VideoDownloadWorker
    assert not hasattr(script, "run_clean")
    assert not hasattr(script, "run_download")


def test_script_prints_stage_result(capsys):
    from app.worker.result import WorkerResult
    from scripts.clean_and_download_videos import _print_result

    _print_result("下载", WorkerResult(total=4, succeeded=2, failed=1, skipped=1))

    assert capsys.readouterr().out == "下载统计: 总数=4 成功=2 失败=1 跳过=1\n"


@pytest.mark.asyncio
async def test_cli_unlimited_downloads_in_500_batches_until_empty():
    from app.worker.result import WorkerResult
    from scripts.clean_and_download_videos import run_download_batches

    worker = SimpleNamespace(run_batch=AsyncMock(side_effect=[
        WorkerResult(total=500, succeeded=500), WorkerResult(total=2, succeeded=2)
    ]))
    result = await run_download_batches(worker, limit=0, min_grade=3, use_proxy=True,
                                        rps=0, platform=None, source="media", offset=0)
    assert result.total == 502
    assert [call.args[0].batch_size for call in worker.run_batch.await_args_list] == [500, 500]


@pytest.mark.asyncio
async def test_cli_large_limit_chunks_without_exceeding_limit():
    from app.worker.result import WorkerResult
    from scripts.clean_and_download_videos import run_download_batches

    worker = SimpleNamespace(run_batch=AsyncMock(side_effect=[
        WorkerResult(total=500, succeeded=500), WorkerResult(total=250, succeeded=250)
    ]))
    result = await run_download_batches(worker, limit=750, min_grade=3, use_proxy=False,
                                        rps=1, platform=None, source="media", offset=0)
    assert result.total == 750
    assert [call.args[0].batch_size for call in worker.run_batch.await_args_list] == [500, 250]


@pytest.mark.asyncio
async def test_cli_uses_initial_offset_once_and_failed_claims_do_not_shift_tail():
    from app.worker.result import WorkerResult
    from scripts.clean_and_download_videos import run_download_batches

    worker = SimpleNamespace(run_batch=AsyncMock(side_effect=[
        WorkerResult(total=500, succeeded=498, failed=2),
        WorkerResult(total=100, succeeded=99, failed=1),
    ]))
    result = await run_download_batches(worker, limit=600, min_grade=3, use_proxy=True,
                                        rps=0, platform=None, source="media", offset=7)
    assert result.total == 600
    calls = worker.run_batch.await_args_list
    assert [call.args[0].batch_size for call in calls] == [500, 100]
    assert [call.kwargs["offset"] for call in calls] == [7, 0]
    assert all(
        call.kwargs["consumer_key"] == "cli:clean-and-download:media"
        for call in calls
    )


@pytest.mark.asyncio
async def test_cli_failure_only_batch_can_continue_with_newly_claimable_tail():
    from app.worker.result import WorkerResult
    from scripts.clean_and_download_videos import run_download_batches

    worker = SimpleNamespace(run_batch=AsyncMock(side_effect=[
        WorkerResult(total=500, failed=500), WorkerResult(total=3, succeeded=3)
    ]))
    result = await run_download_batches(worker, limit=0, min_grade=3, use_proxy=True,
                                        rps=0, platform=None, source="media", offset=4)
    assert result.total == 503
    assert [call.kwargs["offset"] for call in worker.run_batch.await_args_list] == [4, 0]


@pytest.mark.asyncio
async def test_cli_clean_uses_stable_source_consumer_key(monkeypatch):
    from scripts import clean_and_download_videos as script

    db = SimpleNamespace(aconnect=AsyncMock(), ainit_db=AsyncMock(), aclose=AsyncMock())
    cleaner = SimpleNamespace(run_batch=AsyncMock(return_value=SimpleNamespace(
        total=0, succeeded=0, failed=0, skipped=0
    )))
    monkeypatch.setattr(
        script.SchedulerConfig,
        "from_toml",
        lambda path: SimpleNamespace(postgresql=SimpleNamespace(
            username="u", password="p", host="h", port=5432, database="d"
        )),
    )
    monkeypatch.setattr(script, "SQLAlchemyDB", lambda **kwargs: db)
    monkeypatch.setattr(
        script.CleanerConfig,
        "from_toml",
        lambda path: SimpleNamespace(validate=lambda: None),
    )
    monkeypatch.setattr(script, "CleanerRepository", lambda db: object())
    monkeypatch.setattr(script, "VideoCleanWorker", lambda *args, **kwargs: cleaner)

    await script.run(
        "config.toml", platform="tiktok", only_clean=True, skip_clean=False,
        source="material", min_grade=3, bucket="videos", limit=0, offset=17,
        concurrency=1, rps=0, no_proxy=True,
    )

    cleaner.run_batch.assert_awaited_once()
    assert cleaner.run_batch.await_args.kwargs == {
        "consumer_key": "cli:clean-and-download:material"
    }


@pytest.mark.asyncio
async def test_cli_clean_uses_stable_source_consumer_key(monkeypatch):
    from scripts import clean_and_download_videos as script

    db = SimpleNamespace(aconnect=AsyncMock(), ainit_db=AsyncMock(), aclose=AsyncMock())
    cleaner = SimpleNamespace(run_batch=AsyncMock(return_value=SimpleNamespace(
        total=0, succeeded=0, failed=0, skipped=0
    )))
    monkeypatch.setattr(
        script.SchedulerConfig,
        "from_toml",
        lambda path: SimpleNamespace(postgresql=SimpleNamespace(
            username="u", password="p", host="h", port=5432, database="d"
        )),
    )
    monkeypatch.setattr(script, "SQLAlchemyDB", lambda **kwargs: db)
    monkeypatch.setattr(
        script.CleanerConfig,
        "from_toml",
        lambda path: SimpleNamespace(validate=lambda: None),
    )
    monkeypatch.setattr(script, "CleanerRepository", lambda db: object())
    monkeypatch.setattr(script, "VideoCleanWorker", lambda *args, **kwargs: cleaner)

    await script.run(
        "config.toml", platform="tiktok", only_clean=True, skip_clean=False,
        source="material", min_grade=3, bucket="videos", limit=0, offset=17,
        concurrency=1, rps=0, no_proxy=True,
    )

    cleaner.run_batch.assert_awaited_once()
    assert cleaner.run_batch.await_args.kwargs == {
        "consumer_key": "cli:clean-and-download:material"
    }


@pytest.mark.asyncio
async def test_repository_query_requires_download_media_urls():
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    context = AsyncMock()
    context.__aenter__.return_value = session
    db = SimpleNamespace(asession_scope=lambda: context)
    await VideoDownloadRepository(db).fetch_batch(min_grade=2, batch_size=10, platform="tiktok")
    statement, params = session.execute.await_args.args
    sql = str(statement)
    assert "mc.clean_status = 'graded'" in sql
    assert "mc.grade_rank BETWEEN 1 AND :min_grade" in sql
    assert "COALESCE(c.is_download, false) = false" in sql
    assert "c.extend IS NOT NULL" in sql
    assert params["platform"] == "tiktok"


@pytest.mark.asyncio
async def test_repository_claims_invalid_input_instead_of_dropping_lease():
    claimed = {
        "material_id": 9,
        "platform": "tiktok",
        "content_id": "broken",
        "extend": "not-json",
        "content_pic_url": None,
        "claim_token": "owner",
        "attempt_count": 1,
    }
    result = SimpleNamespace(
        mappings=lambda: SimpleNamespace(all=lambda: [claimed])
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    context = AsyncMock()
    context.__aenter__.return_value = session
    repo = VideoDownloadRepository(SimpleNamespace(asession_scope=lambda: context))
    now = datetime(2026, 8, 9, 12, 0)

    jobs = await repo.claim_batch(
        min_grade=3,
        batch_size=1,
        platform="tiktok",
        offset=0,
        claim_token="owner",
        now=now,
        stale_before=now - timedelta(minutes=30),
        max_attempts=5,
    )

    statement, params = session.execute.await_args.args
    sql = str(statement)
    assert "FOR UPDATE OF mc SKIP LOCKED" in sql
    assert "download_attempt_count < :max_attempts" in sql
    assert "download_next_retry_at <= :now" in sql
    assert jobs[0].candidate is None
    assert jobs[0].input_error is not None
    assert jobs[0].claim_token == "owner"
    assert params["stale_before"] == now - timedelta(minutes=30)
    session.execute.assert_awaited_once()
    context.__aenter__.assert_awaited_once()


@pytest.mark.asyncio
async def test_repository_failure_write_is_token_fenced_and_redacted():
    result = SimpleNamespace(rowcount=1)
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    context = AsyncMock()
    context.__aenter__.return_value = session
    repo = VideoDownloadRepository(SimpleNamespace(asession_scope=lambda: context))
    job = SimpleNamespace(material_id=9, claim_token="owner")

    assert await repo.mark_failed(
        job,
        "api_key=super-secret " + "x" * 600,
        datetime(2026, 8, 9, 12, 5),
        max_attempts=5,
    ) is True

    statement, params = session.execute.await_args.args
    assert "download_claim_token = :claim_token" in str(statement)
    assert "super-secret" not in params["error"]
    assert len(params["error"]) <= 500


@pytest.mark.asyncio
async def test_repository_success_rolls_back_when_content_row_is_missing():
    material = SimpleNamespace(
        mappings=lambda: SimpleNamespace(
            first=lambda: {"platform": "tiktok", "content_id": "gone"}
        )
    )
    missing_content = SimpleNamespace(rowcount=0)
    session = SimpleNamespace(execute=AsyncMock(side_effect=[material, missing_content]))
    context = AsyncMock()
    context.__aenter__.return_value = session
    repo = VideoDownloadRepository(SimpleNamespace(asession_scope=lambda: context))

    assert await repo.mark_succeeded(SimpleNamespace(
        material_id=9, claim_token="owner"
    )) is False


@pytest.mark.asyncio
async def test_repository_duplicate_mark_returns_false():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=0)))
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    repo = VideoDownloadRepository(SimpleNamespace(asession_scope=lambda: context))
    assert await repo.mark_downloaded(row()) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["media", "material"])
async def test_repository_reads_download_media_urls_and_marks_candidate(source):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    event.listen(engine.sync_engine, "connect",
                 lambda connection, record: connection.create_function("now", 0, lambda: "2026-01-01"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    class DB:
        @asynccontextmanager
        async def asession_scope(self):
            async with sessions() as session:
                async with session.begin():
                    yield session

    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE t_material_clean (id INTEGER PRIMARY KEY, platform TEXT, content_id TEXT, clean_status TEXT, grade_rank INTEGER, is_delete INTEGER, updated_time TEXT)"))
        await connection.execute(text("CREATE TABLE t_busi_media (id INTEGER PRIMARY KEY, platform TEXT, content_id TEXT, type INTEGER, url TEXT, updated_time TEXT)"))
        await connection.execute(text("CREATE TABLE t_busi_content (id INTEGER PRIMARY KEY, platform TEXT, content_id TEXT, url TEXT, pic TEXT, extend TEXT, is_download BOOLEAN, updated_time TEXT)"))
        await connection.execute(text("INSERT INTO t_material_clean VALUES (1, 'tiktok', 'x', 'graded', 1, 0, NULL)"))
        await connection.execute(text("INSERT INTO t_busi_media VALUES (2, 'tiktok', 'x', 1, 'second', NULL), (1, 'tiktok', 'x', 1, 'first', NULL)"))
        await connection.execute(
            text("INSERT INTO t_busi_content VALUES (1, 'tiktok', 'x', 'material-url', 'fallback-cover', :extend, false, NULL)"),
            {"extend": '{"video_url":"video-url","music_url":"music-url","pic_url":"pic-url"}'},
        )
    repo = VideoDownloadRepository(DB())
    rows = await repo.fetch_batch(min_grade=3, batch_size=10, source=source)
    assert len(rows) == 1
    assert rows[0].page_url is None
    assert rows[0].media_id is None
    assert rows[0].media_url == "video-url"
    assert rows[0].music_url == "music-url"
    assert rows[0].pic_url == "pic-url"
    assert await repo.mark_downloaded(rows[0]) is True
    assert await repo.fetch_batch(min_grade=3, batch_size=10, source=source) == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_skips_invalid_rows_before_filling_batch_and_uses_cover_fallback():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    class DB:
        @asynccontextmanager
        async def asession_scope(self):
            async with sessions() as session:
                yield session

    async with engine.begin() as connection:
        await connection.execute(text(
            "CREATE TABLE t_material_clean (id INTEGER PRIMARY KEY, platform TEXT, "
            "content_id TEXT, clean_status TEXT, grade_rank INTEGER, is_delete INTEGER)"
        ))
        await connection.execute(text(
            "CREATE TABLE t_busi_content (id INTEGER PRIMARY KEY, platform TEXT, "
            "content_id TEXT, pic TEXT, extend TEXT, is_download BOOLEAN)"
        ))
        await connection.execute(text(
            "INSERT INTO t_material_clean VALUES "
            "(1, 'tiktok', 'invalid', 'graded', 1, 0), "
            "(2, 'tiktok', 'valid', 'graded', 2, 0)"
        ))
        await connection.execute(text(
            "INSERT INTO t_busi_content VALUES "
            "(1, 'tiktok', 'invalid', 'old-cover', '{}', false), "
            "(2, 'tiktok', 'valid', 'fallback-cover', :extend, false)"
        ), {"extend": '{"video_url":"video-url","music_url":"music-url"}'})

    rows = await VideoDownloadRepository(DB()).fetch_batch(
        min_grade=3, batch_size=1, source="media"
    )

    assert len(rows) == 1
    assert rows[0].content_id == "valid"
    assert rows[0].pic_url == "fallback-cover"
    await engine.dispose()
