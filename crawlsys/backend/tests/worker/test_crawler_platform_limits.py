import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from core.config import PlatformQuota
from core.sink_handlers import SinkResult
from go_rpc import BlockedRpcError, RateLimitedRpcError, RetryableRpcError
from models.task import BusTask
from models.task_config import TaskConfig
from runtime_config.models import SchedulerSettings
from worker import CrawlerWorker, WorkItem
from worker.processors import InvokeActionProcessor
from worker.rate_limit import PlatformLimiter
from worker.work_item import ItemDisposition, SourceBatch


def quota(
    platform: str, *, concurrency: int = 1, rps: float = 0, cooldown: int = 0
) -> PlatformQuota:
    return PlatformQuota(
        platform=platform,
        concurrency=concurrency,
        rps=rps,
        cooldown_on_block=cooldown,
    )


def global_worker(quotas=None, default_quota=None):
    return CrawlerWorker(
        rpc=MagicMock(),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        quotas=quotas or {},
        default_quota=default_quota or quota("default"),
    )


def test_global_and_legacy_platform_scopes():
    assert global_worker().task_platform_scope is None
    legacy = CrawlerWorker(
        platform="bilibili",
        rpc=MagicMock(),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        quota=quota("bilibili"),
    )
    assert legacy.task_platform_scope == "bilibili"


def test_limiter_is_cached_per_platform_and_uses_matching_quota():
    bilibili = quota("bilibili", concurrency=2, rps=3)
    worker = global_worker({"bilibili": bilibili})

    first = worker._limiter_for("bilibili")
    assert first is worker._limiter_for("bilibili")
    assert first is not worker._limiter_for("tiktok")
    assert first.quota is bilibili
    assert worker._limiter_for("tiktok").quota.platform == "default"


@pytest.mark.asyncio
async def test_crawler_run_uses_dynamic_scheduler_settings(monkeypatch):
    worker = global_worker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(
        return_value=SchedulerSettings(
            poll_interval_ms=25,
            zombie_reap_after_seconds=33,
            batch_size=7,
        )
    )
    worker.repo.get_pending_tasks = AsyncMock(return_value=[])
    worker.repo.reclaim_stuck_running = AsyncMock(return_value=0)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        worker.stop()

    monkeypatch.setattr("worker.crawler.asyncio.sleep", sleep)
    await worker.run()
    assert sleeps == [0.025]
    worker.repo.get_pending_tasks.assert_awaited_once_with(
        platform=None, executor="rpc_crawl", limit=7
    )
    older_than = worker.repo.reclaim_stuck_running.await_args.kwargs["older_than"]
    assert 32 <= (datetime.now() - older_than).total_seconds() <= 34  # noqa: DTZ005


@pytest.mark.asyncio
async def test_crawler_refreshes_settings_each_round(monkeypatch):
    worker = global_worker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(
        side_effect=[
            SchedulerSettings(poll_interval_ms=10, zombie_reap_after_seconds=31),
            SchedulerSettings(poll_interval_ms=20, zombie_reap_after_seconds=41),
        ]
    )
    worker.repo.get_pending_tasks = AsyncMock(return_value=[])
    worker.repo.reclaim_stuck_running = AsyncMock(return_value=0)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            worker.stop()

    monkeypatch.setattr("worker.crawler.asyncio.sleep", sleep)
    await worker.run()
    assert sleeps == [0.01, 0.02]


@pytest.mark.asyncio
async def test_crawler_config_read_failure_backs_off_without_polling(monkeypatch):
    worker = global_worker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(
        side_effect=RuntimeError("token=secret")
    )
    worker.repo.get_pending_tasks = AsyncMock()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        worker.stop()

    monkeypatch.setattr("worker.crawler.asyncio.sleep", sleep)
    await worker.run()
    assert sleeps == [0.5]
    worker.repo.get_pending_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_platform_concurrency_is_limited():
    limiter = PlatformLimiter(quota("p", concurrency=1))
    entered = asyncio.Event()
    release = asyncio.Event()
    order = []

    async def use_limiter(name):
        async with limiter:
            order.append(name)
            entered.set()
            await release.wait()

    first = asyncio.create_task(use_limiter("first"))
    await entered.wait()
    second = asyncio.create_task(use_limiter("second"))
    await asyncio.sleep(0)
    assert order == ["first"]
    release.set()
    await asyncio.gather(first, second)
    assert order == ["first", "second"]


@pytest.mark.asyncio
async def test_blocked_platform_does_not_pause_another_platform():
    first = PlatformLimiter(quota("first", concurrency=1))
    second = PlatformLimiter(quota("second", concurrency=1))
    release = asyncio.Event()
    second_entered = asyncio.Event()

    async def hold_first():
        async with first:
            await release.wait()

    async def enter_second():
        async with second:
            second_entered.set()

    first_task = asyncio.create_task(hold_first())
    await asyncio.sleep(0)
    await enter_second()
    assert second_entered.is_set()
    release.set()
    await first_task


@pytest.mark.asyncio
async def test_rps_timing_is_isolated_and_non_positive_rps_does_not_sleep():
    now = 0.0
    sleeps = []

    def clock():
        return now

    async def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    limited = PlatformLimiter(quota("limited", rps=2), clock=clock, sleep=sleep)
    unlimited = PlatformLimiter(quota("unlimited", rps=0), clock=clock, sleep=sleep)
    async with limited:
        pass
    async with unlimited:
        pass
    async with limited:
        pass

    assert sleeps == [0.5]


@pytest.mark.asyncio
async def test_waiter_rechecks_cooldown_started_during_rps_sleep():
    now = 0.0
    sleeps = []
    other_entered = False

    def clock():
        return now

    other = PlatformLimiter(quota("other"), clock=clock)
    limited = None

    async def sleep(delay):
        nonlocal now, other_entered
        sleeps.append(delay)
        if len(sleeps) == 1:
            limited.start_cooldown()
            async with other:
                other_entered = True
        now += delay

    limited = PlatformLimiter(
        quota("limited", concurrency=2, rps=1, cooldown=5),
        clock=clock,
        sleep=sleep,
    )
    async with limited:
        pass
    async with limited:
        pass

    assert sleeps == [1, 4]
    assert other_entered is True


@pytest.mark.asyncio
async def test_tasks_route_rpc_and_source_platform_independently():
    worker = global_worker({"bilibili": quota("bilibili"), "tiktok": quota("tiktok")})
    worker.rpc.invoke = AsyncMock(return_value={"data": "ok"})
    router = MagicMock(persist=AsyncMock(return_value=SinkResult()))
    worker._sink_router = router
    worker._load_action_schema = AsyncMock(return_value=None)
    seen_platforms = []

    class Source:
        def __init__(self, platform):
            self.platform = platform

        async def fetch(self):
            seen_platforms.append(self.platform)
            return SourceBatch([WorkItem({"id": self.platform})], read=1)

        async def complete(self, item):
            return ItemDisposition.SUCCEEDED

        async def fail(self, item, error, *, deterministic):
            return ItemDisposition.FAILED

    worker._source_factory = lambda _config, task: Source(task.platform)
    for platform in ("bilibili", "tiktok"):
        await worker.execute_business(
            BusTask(platform=platform, action="detail", config=TaskConfig())
        )

    assert seen_platforms == ["bilibili", "tiktok"]
    assert [call.args[:2] for call in worker.rpc.invoke.await_args_list] == [
        ("bilibili", "detail"),
        ("tiktok", "detail"),
    ]
    assert [
        call.kwargs["task"].platform for call in router.persist.await_args_list
    ] == [
        "bilibili",
        "tiktok",
    ]


def http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://rpc.test/business/invoke")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("rpc failed", request=request, response=response)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [403, 429])
async def test_block_status_starts_cooldown_only_for_failed_platform(status_code):
    now = 0.0
    sleeps = []

    def clock():
        return now

    async def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    worker = global_worker()
    tiktok_limiter = PlatformLimiter(
        quota("tiktok", cooldown=10), clock=clock, sleep=sleep
    )
    bilibili_limiter = PlatformLimiter(
        quota("bilibili", cooldown=10), clock=clock, sleep=sleep
    )
    worker._limiters.update(tiktok=tiktok_limiter, bilibili=bilibili_limiter)
    error_type = BlockedRpcError if status_code == 403 else RateLimitedRpcError
    worker.rpc.invoke = AsyncMock(
        side_effect=[
            error_type("rpc failed", status_code=status_code),
            {"data": "ok"},
        ]
    )
    processor = InvokeActionProcessor(
        rpc=worker.rpc,
        limiter_for=worker._limiter_for,
        sink_router=MagicMock(),
    )

    with pytest.raises(error_type):
        await processor._invoke(BusTask(platform="tiktok", action="detail"), {})
    async with bilibili_limiter:
        pass
    assert sleeps == []

    await processor._invoke(BusTask(platform="tiktok", action="detail"), {})
    assert sleeps == [10]


@pytest.mark.asyncio
async def test_rate_limit_uses_retry_after_for_platform_cooldown():
    now = 0.0
    sleeps = []

    def clock():
        return now

    async def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    worker = global_worker()
    limiter = PlatformLimiter(quota("tiktok", cooldown=10), clock=clock, sleep=sleep)
    worker._limiters["tiktok"] = limiter
    worker.rpc.invoke = AsyncMock(
        side_effect=[
            RateLimitedRpcError(
                "rate limited", status_code=429, retry_after_seconds=23
            ),
            {"data": "ok"},
        ]
    )
    task = BusTask(platform="tiktok", action="detail")
    processor = InvokeActionProcessor(
        rpc=worker.rpc,
        limiter_for=worker._limiter_for,
        sink_router=MagicMock(),
    )
    with pytest.raises(RateLimitedRpcError):
        await processor._invoke(task, {})
    await processor._invoke(task, {})

    assert sleeps == [23]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rpc_error",
    [http_status_error(500), httpx.TransportError("connection failed")],
)
async def test_other_rpc_errors_do_not_start_cooldown(rpc_error):
    now = 0.0
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    worker = global_worker()
    limiter = PlatformLimiter(
        quota("tiktok", cooldown=10), clock=lambda: now, sleep=sleep
    )
    worker._limiters["tiktok"] = limiter
    worker.rpc.invoke = AsyncMock(side_effect=[rpc_error, {"data": "ok"}])
    task = BusTask(platform="tiktok", action="detail")
    processor = InvokeActionProcessor(
        rpc=worker.rpc,
        limiter_for=worker._limiter_for,
        sink_router=MagicMock(),
    )

    with pytest.raises(type(rpc_error)):
        await processor._invoke(task, {})
    await processor._invoke(task, {})

    assert sleeps == []


@pytest.mark.asyncio
async def test_limiter_records_normalized_rpc_feedback():
    worker = global_worker()
    limiter = worker._limiter_for("tiktok")
    worker.rpc.invoke = AsyncMock(
        side_effect=[
            {"data": "ok"},
            RetryableRpcError("upstream unavailable", status_code=503),
            BlockedRpcError("blocked", status_code=403),
            RateLimitedRpcError("rate limited", status_code=429, retry_after_seconds=7),
        ]
    )
    task = BusTask(platform="tiktok", action="detail")
    processor = InvokeActionProcessor(
        rpc=worker.rpc,
        limiter_for=worker._limiter_for,
        sink_router=MagicMock(),
    )

    assert await processor._invoke(task, {}) == {"data": "ok"}
    with pytest.raises(RetryableRpcError):
        await processor._invoke(task, {})
    with pytest.raises(BlockedRpcError):
        await processor._invoke(task, {})
    with pytest.raises(RateLimitedRpcError):
        await processor._invoke(task, {})

    snapshot = limiter.feedback_snapshot()
    assert snapshot.successes == 1
    assert snapshot.transient_failures == 1
    assert snapshot.blocks == 1
    assert snapshot.rate_limits == 1
    assert snapshot.cooldown_until > 0


def test_limiter_feedback_snapshot_is_read_only():
    limiter = PlatformLimiter(quota("tiktok"))
    snapshot = limiter.feedback_snapshot()

    with pytest.raises(AttributeError):
        snapshot.successes = 10


def test_rate_limit_halves_effective_rps_without_crossing_floor():
    limiter = PlatformLimiter(quota("tiktok", rps=10, cooldown=0))

    limiter.record_rate_limit(0)
    assert limiter.feedback_snapshot().effective_rps == 5

    for _ in range(10):
        limiter.record_rate_limit(0)
    assert limiter.feedback_snapshot().effective_rps == 1


def test_healthy_windows_additively_restore_effective_rps():
    limiter = PlatformLimiter(
        quota("tiktok", rps=10, cooldown=0), feedback_window_size=4
    )
    limiter.record_block()
    assert limiter.feedback_snapshot().effective_rps == 5

    for _ in range(4):
        limiter.record_success()
    assert limiter.feedback_snapshot().effective_rps == 5.5

    for _ in range(40):
        limiter.record_success()
    assert limiter.feedback_snapshot().effective_rps == 10


def test_transient_error_window_multiplicatively_reduces_effective_rps():
    limiter = PlatformLimiter(quota("tiktok", rps=10), feedback_window_size=5)

    for _ in range(4):
        limiter.record_success()
    limiter.record_transient_failure()

    assert limiter.feedback_snapshot().effective_rps == 8


def test_non_positive_rps_remains_unlimited_after_feedback():
    limiter = PlatformLimiter(quota("tiktok", rps=0), feedback_window_size=1)

    limiter.record_rate_limit(0)
    limiter.record_success()
    limiter.record_transient_failure()

    assert limiter.feedback_snapshot().effective_rps == 0


@pytest.mark.asyncio
async def test_reduced_effective_rps_controls_request_spacing():
    now = 0.0
    sleeps = []

    def clock():
        return now

    async def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    limiter = PlatformLimiter(
        quota("tiktok", rps=10, cooldown=0), clock=clock, sleep=sleep
    )
    limiter.record_rate_limit(0)

    async with limiter:
        pass
    async with limiter:
        pass

    assert sleeps == [pytest.approx(0.2)]
