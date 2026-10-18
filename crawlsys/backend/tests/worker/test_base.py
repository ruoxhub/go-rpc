import asyncio
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models import BusTask, TaskStatus
from models.task import TaskPriority
from worker.base import BaseWorker
from worker.result import WorkerResult


class StubWorker(BaseWorker):
    executor = "video_clean"

    def __init__(self, heartbeat_interval_seconds=None, concurrency=10):
        super().__init__("test", MagicMock(), MagicMock(),
                         MagicMock(rps=0, concurrency=concurrency, cooldown_on_block=1),
                         heartbeat_interval_seconds=heartbeat_interval_seconds)
        self.repo.save = AsyncMock()
        self.repo.heartbeat_running = AsyncMock(return_value=True)
        self.db.aadd = AsyncMock()
        self.business = AsyncMock(return_value=WorkerResult())

    async def execute_business(self, task):
        return await self.business(task)


def test_worker_result_defaults_and_is_frozen():
    result = WorkerResult()
    assert result == WorkerResult(total=0, succeeded=0, failed=0, skipped=0)
    with pytest.raises(Exception):
        result.total = 1


@pytest.mark.asyncio
async def test_partial_failure_fails_batch_and_records_counts():
    worker = StubWorker()
    worker.business.return_value = WorkerResult(total=3, succeeded=2, failed=1)
    task = BusTask(task_id=1, platform="test", action="action")

    await worker.execute(task)

    assert task.status == TaskStatus.FAILED
    assert task.error_msg == "Partial failure: succeeded=2 failed=1 total=3"
    log = worker.db.aadd.call_args.args[0]
    assert (log.btl_all_item_num, log.btl_item_num, log.btl_err_num) == (3, 2, 1)
    assert log.btl_status == -1
    assert log.btl_err_msg == task.error_msg


@pytest.mark.asyncio
async def test_partial_failure_does_not_schedule_next_loop():
    worker = StubWorker()
    worker.business.return_value = WorkerResult(total=3, succeeded=2, failed=1)
    task = BusTask(
        task_id=1,
        platform="test",
        action="action",
        loop_enabled=True,
        loop_interval_seconds=10,
        next_run_at=datetime(2030, 1, 1),
    )

    await worker.execute(task)

    assert task.status == TaskStatus.FAILED
    assert task.next_run_at is None


@pytest.mark.asyncio
async def test_business_exception_fails_task_and_records_error():
    worker = StubWorker()
    worker.business.side_effect = RuntimeError("business broken")
    task = BusTask(task_id=2, platform="test", action="action")

    await worker.execute(task)

    assert task.status == TaskStatus.FAILED
    assert task.error_msg == "RuntimeError: business broken"
    log = worker.db.aadd.call_args.args[0]
    assert log.btl_status == -1
    assert log.btl_err_msg == "RuntimeError: business broken"


@pytest.mark.asyncio
async def test_business_exception_uses_same_redacted_summary_everywhere(caplog, monkeypatch):
    lifecycle_logger = logging.getLogger("worker.lifecycle.redaction")
    monkeypatch.setattr("worker.base.logger", lifecycle_logger)
    worker = StubWorker()
    worker.business.side_effect = RuntimeError(
        "token=tok password=pw Bearer bearer-secret "
        "https://user:url-pass@host diagnosis"
    )
    task = BusTask(task_id=20, platform="test", action="action")

    with caplog.at_level(logging.ERROR, logger=lifecycle_logger.name):
        await worker.execute(task)

    log = worker.db.aadd.call_args.args[0]
    assert task.error_msg == log.btl_err_msg
    assert task.error_msg.startswith("RuntimeError: ")
    assert "diagnosis" in task.error_msg
    for secret in ("token=tok", "password=pw", "bearer-secret", "url-pass"):
        assert secret not in task.error_msg
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_business_exception_logs_priority_and_failed_outcome(caplog, monkeypatch):
    lifecycle_logger = logging.getLogger("worker.lifecycle.failure")
    monkeypatch.setattr("worker.base.logger", lifecycle_logger)
    worker = StubWorker()
    worker.business.side_effect = RuntimeError("failed")
    task = BusTask(
        task_id=22,
        platform="test",
        action="action",
        priority=TaskPriority.URGENT,
        retry_max_attempts=0,
    )

    with caplog.at_level(logging.ERROR, logger=lifecycle_logger.name):
        await worker.execute(task)

    assert "priority=4" in caplog.text
    assert "outcome=failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
async def test_execute_stops_heartbeat_for_every_outcome(outcome):
    worker = StubWorker(heartbeat_interval_seconds=0.001)
    heartbeat_seen = asyncio.Event()

    async def heartbeat(*_args, **_kwargs):
        heartbeat_seen.set()
        return True

    worker.repo.heartbeat_running.side_effect = heartbeat

    async def business(_task):
        await asyncio.wait_for(heartbeat_seen.wait(), timeout=0.1)
        if outcome == "error":
            raise RuntimeError("failed")
        if outcome == "cancel":
            raise asyncio.CancelledError
        return WorkerResult()

    worker.business.side_effect = business
    task = BusTask(task_id=21, platform="test", action="action")
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await worker.execute(task)
    else:
        await worker.execute(task)
    heartbeat_count = worker.repo.heartbeat_running.await_count
    assert heartbeat_count > 0
    await asyncio.sleep(0.005)
    assert worker.repo.heartbeat_running.await_count == heartbeat_count


@pytest.mark.asyncio
async def test_dynamic_heartbeat_adopts_lower_zombie_threshold_quickly(monkeypatch):
    from runtime_config.models import SchedulerSettings

    worker = StubWorker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(
        return_value=SchedulerSettings(zombie_reap_after_seconds=30)
    )
    now = 0.0

    def monotonic():
        return now

    async def sleep(seconds):
        nonlocal now
        now += seconds

    async def heartbeat(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr("worker.base.time.monotonic", monotonic)
    monkeypatch.setattr("worker.base.asyncio.sleep", sleep)
    worker.repo.heartbeat_running.side_effect = heartbeat

    with pytest.raises(asyncio.CancelledError):
        await worker._heartbeat(
            BusTask(task_id=23, platform="test", action="a"),
            SchedulerSettings(zombie_reap_after_seconds=600),
        )

    assert now == 10
    assert now < 30
    worker.repo.heartbeat_running.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_survives_continuous_config_failures_without_missing_deadline(monkeypatch):
    from runtime_config.models import SchedulerSettings

    worker = StubWorker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(side_effect=RuntimeError("token=secret"))
    now = 0.0
    heartbeats = []

    async def sleep(seconds):
        nonlocal now
        assert seconds >= 0.5
        now += seconds

    async def heartbeat(*args, **kwargs):
        heartbeats.append(now)
        if len(heartbeats) == 4:
            raise asyncio.CancelledError

    monkeypatch.setattr("worker.base.time.monotonic", lambda: now)
    monkeypatch.setattr("worker.base.asyncio.sleep", sleep)
    worker.repo.heartbeat_running.side_effect = heartbeat

    with pytest.raises(asyncio.CancelledError):
        await worker._heartbeat(
            BusTask(task_id=24, platform="test", action="a"),
            SchedulerSettings(zombie_reap_after_seconds=600),
        )

    assert heartbeats == [10, 20, 30, 40]
    assert worker.config_store.get_scheduler.await_count > 4


def test_non_positive_heartbeat_override_is_rejected():
    with pytest.raises(ValueError, match="heartbeat_interval_seconds must be > 0"):
        StubWorker(heartbeat_interval_seconds=0)


@pytest.mark.asyncio
async def test_cancelled_error_is_re_raised_without_business_failure_log():
    worker = StubWorker()
    worker.business.side_effect = asyncio.CancelledError
    task = BusTask(task_id=3, platform="test", action="action")

    with pytest.raises(asyncio.CancelledError):
        await worker.execute(task)

    assert task.status == TaskStatus.RUNNING
    assert task.error_msg is None
    worker.db.aadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_logs_start_and_picked_up_tasks(caplog, monkeypatch):
    lifecycle_logger = logging.getLogger("worker.lifecycle.run")
    monkeypatch.setattr("worker.base.logger", lifecycle_logger)
    worker = StubWorker()
    task = BusTask(platform="test", action="action")
    worker.repo.get_pending_tasks = AsyncMock(return_value=[task])

    async def execute_once(_task, _settings):
        worker.stop()

    worker.execute = execute_once
    with caplog.at_level(logging.INFO, logger=lifecycle_logger.name):
        await worker.run()

    assert "Worker[test] started" in caplog.text
    assert "Worker[test] picked up 1 pending task(s)" in caplog.text
    assert "Worker[test] stop requested" in caplog.text
    worker.repo.get_pending_tasks.assert_awaited_once_with(
        platform=None, executor="video_clean", limit=10
    )


@pytest.mark.asyncio
async def test_run_does_not_claim_more_tasks_than_available_concurrency():
    worker = StubWorker(concurrency=2)
    worker.repo.get_pending_tasks = AsyncMock(return_value=[])
    worker.repo.reclaim_stuck_running = AsyncMock(return_value=0)

    async def stop_after_poll(_seconds):
        worker.stop()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("worker.base.asyncio.sleep", stop_after_poll)
        await worker.run()

    worker.repo.get_pending_tasks.assert_awaited_once_with(
        platform=None, executor="video_clean", limit=2
    )


@pytest.mark.asyncio
async def test_run_uses_fresh_scheduler_settings_each_round(monkeypatch):
    from runtime_config.models import SchedulerSettings

    worker = StubWorker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(side_effect=[
        SchedulerSettings(poll_interval_ms=10, zombie_reap_after_seconds=31,
                          default_loop_interval_seconds=12, batch_size=3),
        SchedulerSettings(poll_interval_ms=20, zombie_reap_after_seconds=41,
                          default_loop_interval_seconds=22, batch_size=5),
    ])
    worker.repo.get_pending_tasks = AsyncMock(return_value=[])
    worker.repo.reclaim_stuck_running = AsyncMock(return_value=0)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            worker.stop()

    monkeypatch.setattr("worker.base.asyncio.sleep", sleep)
    await worker.run()

    assert sleeps == [0.01, 0.02]
    assert [
        call.kwargs["limit"]
        for call in worker.repo.get_pending_tasks.await_args_list
    ] == [3, 5]
    thresholds = [call.kwargs["older_than"] for call in worker.repo.reclaim_stuck_running.await_args_list]
    assert 30 <= (datetime.now() - thresholds[0]).total_seconds() <= 32
    assert 40 <= (datetime.now() - thresholds[1]).total_seconds() <= 42


@pytest.mark.asyncio
async def test_concurrent_execute_keeps_each_scheduler_snapshot():
    from runtime_config.models import SchedulerSettings

    worker = StubWorker()
    gate = asyncio.Event()

    async def business(_task):
        await gate.wait()
        return WorkerResult(succeeded=1)

    worker.business.side_effect = business
    tasks = [
        BusTask(task_id=i, platform="test", action="action",
                schedule_type="interval", loop_enabled=True)
        for i in (31, 32)
    ]
    executions = [
        asyncio.create_task(worker.execute(tasks[0], SchedulerSettings(default_loop_interval_seconds=10))),
        asyncio.create_task(worker.execute(tasks[1], SchedulerSettings(default_loop_interval_seconds=20))),
    ]
    gate.set()
    await asyncio.gather(*executions)
    intervals = [(task.next_run_at - task.last_run_at).total_seconds() for task in tasks]
    assert intervals == [10, 20]


@pytest.mark.asyncio
async def test_runtime_config_read_failure_does_not_poll_or_fallback(monkeypatch):
    worker = StubWorker()
    worker.config_store = MagicMock()
    worker.config_store.get_scheduler = AsyncMock(side_effect=RuntimeError("password=secret"))
    worker.repo.get_pending_tasks = AsyncMock()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        worker.stop()

    monkeypatch.setattr("worker.base.asyncio.sleep", sleep)
    await worker.run()
    assert sleeps == [0.5]
    worker.repo.get_pending_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_reclaims_only_own_executor(monkeypatch):
    worker = StubWorker()
    worker.zombie_reap_after_seconds = 77
    worker.repo.get_pending_tasks = AsyncMock(return_value=[])
    worker.repo.reclaim_stuck_running = AsyncMock(return_value=0)

    async def stop_after_poll(_seconds):
        worker.stop()

    monkeypatch.setattr("worker.base.asyncio.sleep", stop_after_poll)
    await worker.run()

    kwargs = worker.repo.reclaim_stuck_running.await_args.kwargs
    assert kwargs["executor"] == "video_clean"
    assert kwargs["platform"] is None
    assert isinstance(kwargs["older_than"], datetime)
    assert 76 <= (datetime.now() - kwargs["older_than"]).total_seconds() <= 78


@pytest.mark.asyncio
async def test_infrastructure_error_logs_are_redacted(caplog, monkeypatch):
    lifecycle_logger = logging.getLogger("worker.lifecycle.infrastructure")
    monkeypatch.setattr("worker.base.logger", lifecycle_logger)
    worker = StubWorker()
    secret_error = RuntimeError(
        'token="abc def" password=pw https://user:url-pass@host'
    )
    worker.repo.get_pending_tasks = AsyncMock(return_value=[])
    worker.repo.reclaim_stuck_running = AsyncMock(side_effect=secret_error)

    async def stop_after_poll(_seconds):
        worker.stop()

    monkeypatch.setattr("worker.base.asyncio.sleep", stop_after_poll)
    with caplog.at_level(logging.WARNING, logger=lifecycle_logger.name):
        await worker.run()
        worker.db.aadd.side_effect = secret_error
        await worker.execute(BusTask(task_id=22, platform="test", action="action"))

    assert caplog.text.count("RuntimeError:") == 2
    for secret in ("abc def", "password=pw", "url-pass"):
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_execute_logs_success_summary(caplog, monkeypatch):
    lifecycle_logger = logging.getLogger("worker.lifecycle.execute")
    monkeypatch.setattr("worker.base.logger", lifecycle_logger)
    worker = StubWorker()
    worker.business.return_value = WorkerResult(total=3, succeeded=2, failed=1)
    task = BusTask(platform="test", action="action", priority=TaskPriority.HIGH)

    with caplog.at_level(logging.INFO, logger=lifecycle_logger.name):
        await worker.execute(task)

    assert "task test/action round complete" in caplog.text
    assert "task_id=None" in caplog.text
    assert "priority=3" in caplog.text
    assert "processed=2 failed=1 total=3" in caplog.text
    assert "outcome=partial_failure" in caplog.text
    assert "next_status=failed" in caplog.text

# Task 6：重试、合并触发与运行次数生命周期

@pytest.fixture
def worker():
    return StubWorker()


@pytest.fixture
def now():
    return datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc)


def _cron_task(**overrides):
    values = {
        "task_id": 99,
        "platform": "test",
        "action": "cron",
        "schedule_type": "cron",
        "cron_expression": "0 3 * * *",
        "retry_max_attempts": 3,
        "retry_delay_seconds": 60,
        "retry_backoff_multiplier": 2.0,
        "retry_max_delay_seconds": 300,
        "status": TaskStatus.RUNNING,
    }
    values.update(overrides)
    return BusTask(**values)


@pytest.fixture
def cron_task():
    return _cron_task()


def test_failure_schedules_first_retry(worker, cron_task, now):
    worker._mark_failure(cron_task, now=now, error="boom")
    assert cron_task.status == TaskStatus.PENDING.value
    assert cron_task.retry_count == 1
    assert cron_task.next_retry_at == now.replace(tzinfo=None) + timedelta(seconds=60)
    assert cron_task.run_count == 0


def test_recurring_retry_exhaustion_keeps_future_schedule(worker, cron_task, now):
    cron_task.retry_count = cron_task.retry_max_attempts
    worker._mark_failure(cron_task, now=now, error="boom")
    assert cron_task.last_run_status == "failed"
    assert cron_task.run_count == 1
    assert cron_task.status == TaskStatus.PENDING.value
    assert cron_task.next_run_at > now.replace(tzinfo=None)


def test_once_exhausted_failure_ends_failed(worker, now):
    task = BusTask(
        task_id=1, platform="test", action="once", schedule_type="once",
        run_once_at=now, retry_max_attempts=0, status=TaskStatus.RUNNING,
    )
    worker._mark_failure(task, now=now, error="boom")
    assert task.status == TaskStatus.FAILED.value
    assert task.last_run_status == "failed"
    assert task.next_run_at is None


def test_manual_success_ends_done(worker, now):
    task = BusTask(
        task_id=1, platform="test", action="manual", schedule_type="manual",
        status=TaskStatus.RUNNING,
    )
    worker._finish_success(task, processed=5, now=now)
    assert task.status == TaskStatus.DONE.value
    assert task.last_run_status == "success"
    assert task.run_count == 1
    assert task.next_run_at is None


def test_pause_requested_ends_paused(worker, now):
    task = _cron_task(pause_requested=True)
    worker._finish_success(task, processed=1, now=now)
    assert task.status == TaskStatus.PAUSED.value
    assert task.pause_requested is False
    assert task.next_run_at is None


def test_interval_fixed_delay_from_completion(worker, now):
    task = BusTask(
        task_id=1, platform="test", action="interval", schedule_type="interval",
        loop_interval_seconds=300, status=TaskStatus.RUNNING,
    )
    worker._finish_success(task, processed=1, now=now)
    assert task.status == TaskStatus.PENDING.value
    assert task.next_run_at == now.replace(tzinfo=None) + timedelta(seconds=300)


@pytest.mark.asyncio
async def test_interval_execute_uses_business_completion_time(monkeypatch):
    worker = StubWorker()
    started_at = datetime(2026, 8, 10, 1, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(minutes=10)
    business_finished = False

    class Clock:
        @classmethod
        def now(cls, tz=None):
            value = finished_at if business_finished else started_at
            return value if tz is not None else value.replace(tzinfo=None)

    async def business(_task):
        nonlocal business_finished
        business_finished = True
        return WorkerResult(succeeded=1)

    monkeypatch.setattr("worker.base.datetime", Clock)
    worker.business.side_effect = business
    task = BusTask(
        task_id=1, platform="test", action="interval", schedule_type="interval",
        loop_interval_seconds=300, status=TaskStatus.RUNNING,
    )

    await worker.execute(task)

    assert task.last_run_at == finished_at.replace(tzinfo=None)
    assert task.next_run_at == finished_at.replace(tzinfo=None) + timedelta(seconds=300)


def test_manual_run_requested_while_running_is_coalesced(worker, now):
    task = BusTask(
        task_id=1, platform="test", action="manual", schedule_type="manual",
        run_now_requested_at=now, status=TaskStatus.RUNNING,
    )

    worker._finish_success(task, processed=1, now=now)

    assert task.status == TaskStatus.PENDING.value
    assert task.run_now_requested_at == now


@pytest.mark.asyncio
async def test_execute_logs_trigger_snapshot_and_persists_it_cleared(now):
    worker = StubWorker()
    saved_snapshots = []

    async def save(task):
        saved_snapshots.append(
            (task.status, task.active_trigger, task.active_scheduled_at)
        )

    worker.repo.save.side_effect = save
    task = BusTask(
        task_id=1,
        platform="test",
        action="manual",
        schedule_type="manual",
        active_trigger="retry",
        active_scheduled_at=now,
        retry_count=2,
        status=TaskStatus.RUNNING,
    )

    await worker.execute(task)

    log = worker.db.aadd.await_args.args[0]
    assert (log.btl_active_trigger, log.btl_active_scheduled_at, log.btl_retry_count) == (
        "retry",
        now,
        2,
    )
    assert saved_snapshots[-1] == (TaskStatus.DONE.value, None, None)


def test_cron_missed_while_running_coalesces_once(worker, now):
    # active_scheduled_at=08-08 19:00Z(03:00+8)，下一触发 08-09 19:00Z 已错过
    task = _cron_task(
        active_scheduled_at=datetime(2026, 8, 8, 19, 0, tzinfo=timezone.utc),
    )
    worker._finish_success(task, processed=1, now=now)
    assert task.status == TaskStatus.PENDING.value
    assert task.next_run_at is None
    assert task.run_now_requested_at == now  # 合并触发只设置一次

    later = now + timedelta(minutes=1)
    worker._finish_success(task, processed=1, now=later)
    assert task.run_now_requested_at == now  # 已存在合并请求，不重复设置


def test_max_runs_stops_periodic_task(worker, now):
    task = _cron_task(max_runs=2, run_count=2)
    worker._finish_success(task, processed=1, now=now)
    assert task.status == TaskStatus.DONE.value
    assert task.next_run_at is None
