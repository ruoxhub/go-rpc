from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from worker.video_clean import VideoCleanWorker, clean_policy_hash
from cleaner.config import CleanerConfig
from cleaner.engine import GradeRule, PlatformThresholds
from cleaner.repository import CleanCursorPosition, ContentCandidate
from models import BusTask
from runtime_config.models import FilterRule


TIKTOK_AIGC_FILTER = FilterRule(
    field="extend_data.aigcLabelType", operator=">", value=0
)


def candidate(content_id="1", platform="tiktok", views=100):
    now = datetime.now(timezone.utc)
    return ContentCandidate(1, content_id, platform, now - timedelta(hours=25), views,
                            None, now, now)


def make_worker(repo):
    cfg = CleanerConfig(batch_size=10, max_batches_per_platform=1,
                        thresholds={"tiktok": PlatformThresholds([GradeRule(30, 10)], [], [])})
    return VideoCleanWorker("clean", None, None, SimpleNamespace(), cleaner_config=cfg,
                            cleaner_repo=repo)


def cursor(ts=datetime(1900, 1, 1), row_id=0):
    return CleanCursorPosition(ts, row_id)


def cursor_repo(**overrides):
    values = {
        "load_cursor": AsyncMock(return_value=cursor()),
        "scan_batch": AsyncMock(return_value=[]),
        "commit_batch": AsyncMock(side_effect=lambda *args: len(args[3])),
        "purge_expired": AsyncMock(return_value=0),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_clean_uses_task_options_and_reports_statistics():
    repo = cursor_repo(scan_batch=AsyncMock(return_value=[candidate(), candidate("2", views=0)]))
    result = await make_worker(repo).execute_business(BusTask(task_id=41, platform="ignored", action="clean", config={
        "executor": "video_clean", "clean": {"platforms": ["tiktok"], "batch_size": 2}
    }))
    assert (result.total, result.succeeded, result.skipped) == (2, 1, 1)
    assert repo.scan_batch.await_args.args[0] == "tiktok"
    assert repo.scan_batch.await_args.args[3] == 2
    assert repo.scan_batch.await_args.args[4] == [TIKTOK_AIGC_FILTER]
    assert repo.load_cursor.await_args.args[:2] == ("task:41", "tiktok")
    material = repo.commit_batch.await_args.args[3][0]
    assert material.snap_hours == pytest.approx(25, abs=0.01)
    assert material.expire_time - material.grade_time == timedelta(days=14)


@pytest.mark.asyncio
async def test_clean_defaults_to_config_platforms_and_skips_unknown_platform():
    repo = cursor_repo()
    worker = make_worker(repo)
    result = await worker.run_batch()
    assert repo.scan_batch.await_args.args[0] == "tiktok"
    result = await worker.run_batch(type("Options", (), {"platforms": ["unknown"], "batch_size": None})())
    assert result.skipped == 1


@pytest.mark.asyncio
async def test_clean_refreshes_runtime_snapshot_and_uses_enabled_platform_provider():
    filters = [FilterRule(field="view_count", operator=">", value=10)]
    next_filters = [FilterRule(field="view_count", operator=">", value=20)]
    policy = SimpleNamespace(p1=[SimpleNamespace(max_hours=30, min_views=10)], p2=[], p3=[], filters=filters)
    next_policy = SimpleNamespace(p1=[SimpleNamespace(max_hours=30, min_views=20)], p2=[], p3=[], filters=next_filters)
    settings = SimpleNamespace(enabled=True, batch_size=8, max_batches_per_platform=1,
                               ttl_days=2, suspect_seconds=30, thresholds={})
    store = SimpleNamespace(get_cleaner=AsyncMock(side_effect=[settings, SimpleNamespace(**{
        **vars(settings), "enabled": True
    })]), get_platform_policy=AsyncMock(side_effect=[policy, next_policy]))
    provider = SimpleNamespace(find_all_enabled=AsyncMock(return_value=[SimpleNamespace(bs_platform_code="tiktok")]))
    repo = cursor_repo(scan_batch=AsyncMock(side_effect=[[candidate(views=15)], [candidate(views=15)]]))
    worker = VideoCleanWorker("clean", None, None, SimpleNamespace(), config_store=store,
                              cleaner_repo=repo, platform_provider=provider)

    await worker.run_batch()
    await worker.run_batch()

    assert [item.args[4] for item in repo.scan_batch.await_args_list] == [
        [*filters, TIKTOK_AIGC_FILTER],
        [*next_filters, TIKTOK_AIGC_FILTER],
    ]
    assert provider.find_all_enabled.await_count == 2
    assert store.get_cleaner.await_count == 2
    assert store.get_platform_policy.await_count == 2
    assert [len(item.args[3]) for item in repo.commit_batch.await_args_list] == [1, 0]


@pytest.mark.asyncio
async def test_clean_keeps_one_policy_snapshot_across_pages():
    policy = SimpleNamespace(
        p1=[SimpleNamespace(max_hours=2, min_views=10)], p2=[], p3=[],
        filters=[FilterRule(field="view_count", operator=">", value=10)],
    )
    settings = SimpleNamespace(enabled=True, batch_size=1, max_batches_per_platform=2,
                               ttl_days=2, suspect_seconds=30, thresholds={})
    store = SimpleNamespace(get_cleaner=AsyncMock(return_value=settings),
                            get_platform_policy=AsyncMock(return_value=policy))
    repo = cursor_repo(scan_batch=AsyncMock(side_effect=[[candidate()], []]))
    worker = VideoCleanWorker("clean", None, None, SimpleNamespace(), config_store=store,
                              cleaner_repo=repo, platform_provider=SimpleNamespace(
                                  find_all_enabled=AsyncMock(return_value=[SimpleNamespace(bs_platform_code="tiktok")])
                              ))
    await worker.run_batch()
    store.get_platform_policy.assert_awaited_once_with("tiktok")
    assert [item.args[4] for item in repo.scan_batch.await_args_list] == [
        [*policy.filters, TIKTOK_AIGC_FILTER],
        [*policy.filters, TIKTOK_AIGC_FILTER],
    ]


@pytest.mark.asyncio
async def test_clean_does_not_duplicate_required_tiktok_aigc_filter():
    repo = SimpleNamespace(
        load_cursor=AsyncMock(return_value=cursor()),
        scan_batch=AsyncMock(return_value=[]),
        commit_batch=AsyncMock(),
        purge_expired=AsyncMock(return_value=0),
    )
    cfg = CleanerConfig(
        batch_size=10,
        max_batches_per_platform=1,
        thresholds={
            "tiktok": SimpleNamespace(
                p1=[GradeRule(2, 10)],
                p2=[],
                p3=[],
                filters=[TIKTOK_AIGC_FILTER],
            )
        },
    )
    worker = VideoCleanWorker(
        "clean", None, None, SimpleNamespace(), cleaner_config=cfg, cleaner_repo=repo
    )

    await worker.run_batch()

    assert repo.scan_batch.await_args.args[4] == [TIKTOK_AIGC_FILTER]


@pytest.mark.asyncio
async def test_clean_missing_policy_skips_without_scan_and_policy_error_propagates():
    settings = SimpleNamespace(enabled=True, batch_size=1, max_batches_per_platform=1,
                               ttl_days=2, suspect_seconds=30, thresholds={})
    repo = cursor_repo(scan_batch=AsyncMock())
    provider = SimpleNamespace(find_all_enabled=AsyncMock(return_value=[SimpleNamespace(bs_platform_code="tiktok")]))
    store = SimpleNamespace(get_cleaner=AsyncMock(return_value=settings),
                            get_platform_policy=AsyncMock(return_value=None))
    worker = VideoCleanWorker("clean", None, None, SimpleNamespace(), config_store=store,
                              cleaner_repo=repo, platform_provider=provider)
    assert (await worker.run_batch()).skipped == 1
    repo.scan_batch.assert_not_awaited()

    store.get_platform_policy.side_effect = RuntimeError("redis failed")
    with pytest.raises(RuntimeError, match="redis failed"):
        await worker.run_batch()


@pytest.mark.asyncio
async def test_clean_disabled_returns_zero_without_scan_or_purge():
    store = SimpleNamespace(
        get_cleaner=AsyncMock(return_value=SimpleNamespace(enabled=False)),
        get_platform_policy=AsyncMock(),
    )
    repo = cursor_repo(scan_batch=AsyncMock(), purge_expired=AsyncMock())
    provider = SimpleNamespace(find_all_enabled=AsyncMock())
    worker = VideoCleanWorker("clean", None, None, SimpleNamespace(), config_store=store,
                              cleaner_repo=repo, platform_provider=provider)
    result = await worker.run_batch()
    assert (result.total, result.succeeded, result.failed, result.skipped) == (0, 0, 0, 0)
    repo.scan_batch.assert_not_awaited()
    repo.purge_expired.assert_not_awaited()
    provider.find_all_enabled.assert_not_awaited()
    store.get_platform_policy.assert_not_awaited()


def test_clean_rejects_missing_or_conflicting_mode_dependencies():
    base = ("clean", None, None, SimpleNamespace())
    with pytest.raises(ValueError, match="static cleaner"):
        VideoCleanWorker(*base)
    with pytest.raises(ValueError, match="dynamic cleaner"):
        VideoCleanWorker(*base, config_store=object())
    with pytest.raises(ValueError, match="dynamic cleaner"):
        VideoCleanWorker(*base, config_store=object(), platform_provider=object(), cleaner_config=object())


def test_clean_policy_hash_is_stable_and_changes_with_policy_inputs():
    thresholds = PlatformThresholds([GradeRule(30, 10)], [], [])
    filters = [FilterRule(field="view_count", operator=">", value=10)]

    first = clean_policy_hash(
        thresholds, filters, suspect_seconds=30, ttl_days=14
    )
    same = clean_policy_hash(
        thresholds, list(filters), suspect_seconds=30, ttl_days=14
    )
    changed = clean_policy_hash(
        thresholds, filters, suspect_seconds=31, ttl_days=14
    )

    assert first == same
    assert len(first) == 64
    assert first != changed


@pytest.mark.asyncio
async def test_second_round_resumes_after_persisted_cursor():
    first_position = cursor()
    saved_position = cursor(datetime(2026, 8, 9), 100)
    tail = candidate("101")
    tail = ContentCandidate(**{**tail.__dict__, "id": 101})
    repo = cursor_repo(
        load_cursor=AsyncMock(side_effect=[first_position, saved_position]),
        scan_batch=AsyncMock(side_effect=[[candidate("100")], [tail]]),
    )
    worker = make_worker(repo)

    await worker.run_batch(consumer_key="task:41")
    await worker.run_batch(consumer_key="task:41")

    assert repo.scan_batch.await_args_list[1].args[1:3] == (
        saved_position.watermark_ts,
        saved_position.watermark_id,
    )
    assert [call.args[:2] for call in repo.commit_batch.await_args_list] == [
        ("task:41", "tiktok"),
        ("task:41", "tiktok"),
    ]
    assert repo.commit_batch.await_args_list[1].args[4] == cursor(
        tail.change_time, 101
    )


@pytest.mark.asyncio
async def test_unrated_batch_still_commits_cursor():
    unrated = candidate(views=0)
    repo = cursor_repo(scan_batch=AsyncMock(return_value=[unrated]))

    result = await make_worker(repo).run_batch(consumer_key="task:41")

    assert (result.total, result.succeeded, result.skipped) == (1, 0, 1)
    assert repo.commit_batch.await_args.args[3] == []
    assert repo.commit_batch.await_args.args[4] == cursor(
        unrated.change_time, unrated.id
    )


@pytest.mark.asyncio
async def test_failed_material_commit_logs_safe_structured_batch_event(
    caplog,
):
    secret_consumer_key = "task:SECRET-CONSUMER"
    repo = cursor_repo(
        scan_batch=AsyncMock(side_effect=[[candidate()], [candidate("2")]]),
        commit_batch=AsyncMock(
            side_effect=RuntimeError(
                "database commit unavailable "
                "url=https://private.invalid/batch token=full-secret"
            )
        ),
    )

    result = await make_worker(repo).run_batch(
        task_id=41, consumer_key=secret_consumer_key
    )

    assert result.failed == 1
    assert repo.commit_batch.await_count == 1
    assert repo.scan_batch.await_count == 1
    assert secret_consumer_key not in caplog.text
    assert "https://private.invalid/batch" not in caplog.text
    assert "full-secret" not in caplog.text
    record = next(record for record in caplog.records if record.outcome == "failed")
    assert record.getMessage() == (
        "RuntimeError: database commit unavailable "
        "url=[REDACTED_URL] token=***"
    )
    assert {
        field: getattr(record, field)
        for field in (
            "task_id",
            "consumer_key",
            "platform",
            "content_id",
            "batch_id",
            "claim_token_prefix",
            "attempt_count",
            "outcome",
            "latency_ms",
            "exception_type",
        )
    } == {
        "task_id": 41,
        "consumer_key": secret_consumer_key,
        "platform": "tiktok",
        "content_id": None,
        "batch_id": record.batch_id,
        "claim_token_prefix": None,
        "attempt_count": None,
        "outcome": "failed",
        "latency_ms": record.latency_ms,
        "exception_type": "RuntimeError",
    }
    assert len(record.batch_id) == 32
    assert record.latency_ms >= 0
