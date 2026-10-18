import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.config import PlatformQuota
from core.sink_handlers import SinkResult
from models import BusTask
from models.task import BusTaskLog, TaskStatus
from models.task_config import TaskConfig
from worker.crawler import CrawlerWorker, WorkItem
from worker.processors import InvokeActionProcessor, WorkItemValidationError
from worker.result import WorkerResult
from worker.work_item import ItemDisposition, ItemResult, SourceBatch


class StubSource:
    def __init__(self, items):
        self.items = items
        self.completed = []
        self.failures = []

    async def fetch(self):
        return SourceBatch(self.items, read=len(self.items))

    async def complete(self, item):
        self.completed.append(item.entity_id)
        return ItemDisposition.SUCCEEDED

    async def fail(self, item, error, *, deterministic):
        self.failures.append((item.entity_id, deterministic))
        return ItemDisposition.FAILED


class StubProcessor:
    def __init__(self, process=None):
        self._process = process

    async def process(self, task, item, schema):
        if self._process is not None:
            return await self._process(task, item, schema)
        return ItemResult()


def make_worker(items=None, process=None):
    source = StubSource(items or [])
    processor = StubProcessor(process)
    worker = CrawlerWorker(
        platform="bilibili",
        rpc=MagicMock(),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        quota=PlatformQuota(platform="bilibili", rps=0),
        default_loop_interval_seconds=3600,
        source_factory=lambda _config, _task: source,
        processor_factory=lambda _config: processor,
    )
    return worker, source


def test_crawler_worker_scopes_tasks_to_its_platform():
    worker, _ = make_worker()
    assert worker.task_platform_scope == "bilibili"


def test_crawler_exposes_only_source_processor_execution_seam():
    for legacy_name in (
        "_build_items",
        "_query_source",
        "_invoke",
        "_dispatch",
        "_validate_order_by",
        "_limit_clause",
    ):
        assert not hasattr(CrawlerWorker, legacy_name)


def test_parse_config_normalizes_dict_and_preserves_model():
    worker, _ = make_worker()
    task = BusTask(platform="p", action="a", config={})
    assert isinstance(worker._parse_config(task), TaskConfig)
    config = TaskConfig()
    task.config = config
    assert worker._parse_config(task) is config


def test_invoke_processor_validates_params():
    schema = {
        "type": "object",
        "required": ["uid"],
        "properties": {"uid": {"type": "string"}},
    }
    InvokeActionProcessor._validate_params(schema, {"uid": "123"})
    with pytest.raises(WorkItemValidationError):
        InvokeActionProcessor._validate_params(schema, {})
    with pytest.raises(WorkItemValidationError, match="params schema"):
        InvokeActionProcessor._validate_params({"type": "invalid"}, {})


@pytest.mark.asyncio
async def test_execute_writes_success_log_from_source_processor_round():
    worker, source = make_worker([WorkItem({"id": "1"}, "1"), WorkItem({"id": "2"}, "2")])
    worker.repo.save = AsyncMock()
    worker.db.aadd = AsyncMock()
    task = BusTask(task_id=7, platform="bilibili", action="getContent", platform_id=10)

    await worker.execute(task)

    assert source.completed == ["1", "2"]
    log = worker.db.aadd.await_args.args[0]
    assert isinstance(log, BusTaskLog)
    assert (log.btl_all_item_num, log.btl_item_num, log.btl_err_num) == (2, 2, 0)
    assert log.btl_status == 1


@pytest.mark.asyncio
async def test_database_source_failure_keeps_partial_failure_semantics():
    async def process(_task, item, _schema):
        if item.entity_id == "bad":
            raise RuntimeError("rpc timeout")
        return ItemResult()

    worker, source = make_worker(
        [WorkItem({}, "one"), WorkItem({}, "bad"), WorkItem({}, "two")], process
    )
    worker.repo.save = AsyncMock()
    worker.db.aadd = AsyncMock()
    task = BusTask(task_id=10, platform="bilibili", action="getContent")

    await worker.execute(task)

    assert task.status == TaskStatus.FAILED
    assert task.error_msg == "Partial failure: succeeded=2 failed=1 total=3"
    assert source.failures == [("bad", False)]


@pytest.mark.asyncio
async def test_one_time_and_loop_success_states_are_unchanged():
    one_time, _ = make_worker([WorkItem({})])
    one_time.repo.save = AsyncMock()
    one_time.db.aadd = AsyncMock()
    task = BusTask(
        platform="bilibili",
        action="a",
        next_run_at=datetime(2030, 1, 1),  # noqa: DTZ001 - model uses DB-naive time
    )
    await one_time.execute(task)
    assert task.status == TaskStatus.DONE and task.next_run_at is None

    looping, _ = make_worker([WorkItem({})])
    looping.repo.save = AsyncMock()
    looping.db.aadd = AsyncMock()
    task = BusTask(
        platform="bilibili",
        action="a",
        schedule_type="interval",
        loop_enabled=True,
        loop_interval_seconds=120,
    )
    before = datetime.now(timezone.utc)  # noqa: DTZ005 - model 时间按 UTC 语义比较
    await looping.execute(task)
    assert task.status == TaskStatus.PENDING
    assert task.last_run_at >= before.replace(tzinfo=None)
    assert task.next_run_at == task.last_run_at + timedelta(seconds=120)


@pytest.mark.asyncio
async def test_run_task_items_limits_inflight_and_keeps_siblings():
    inflight = 0
    maximum = 0

    async def process(_task, item, _schema):
        nonlocal inflight, maximum
        inflight += 1
        maximum = max(maximum, inflight)
        await asyncio.sleep(0)
        inflight -= 1
        if item.entity_id == "bad":
            raise RuntimeError("failed")
        return ItemResult()

    items = [WorkItem({}, str(index)) for index in range(7)] + [WorkItem({}, "bad")]
    worker, source = make_worker(items, process)
    result = await worker.execute_business(
        BusTask(
            platform="p",
            action="a",
            config=TaskConfig(max_inflight_items=3),
        )
    )
    assert result == WorkerResult(total=8, succeeded=7, failed=1, skipped=0)
    assert maximum == 3
    assert source.failures == [("bad", False)]


@pytest.mark.asyncio
async def test_cancellation_does_not_complete_unfinished_items():
    started = asyncio.Event()

    async def process(_task, _item, _schema):
        started.set()
        await asyncio.Future()

    worker, source = make_worker([WorkItem({}, "one"), WorkItem({}, "two")], process)
    running = asyncio.create_task(
        worker.execute_business(
            BusTask(
                platform="p",
                action="a",
                config=TaskConfig(max_inflight_items=2),
            )
        )
    )
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert source.completed == []


@pytest.mark.asyncio
async def test_concurrent_task_round_stats_do_not_mix():
    release_first = asyncio.Event()

    class OrderedSource(StubSource):
        def __init__(self, item, *, releases=False):
            super().__init__([item])
            self.releases = releases

        async def complete(self, item):
            if self.releases:
                release_first.set()
            else:
                await release_first.wait()
            return await super().complete(item)

    sources = {
        1: OrderedSource(WorkItem({}, "one")),
        2: OrderedSource(WorkItem({}, "two"), releases=True),
    }

    class StatsProcessor:
        async def process(self, task, item, schema):
            if task.task_id == 1:
                return ItemResult(SinkResult(produced=1, skipped=1))
            return ItemResult(SinkResult(produced=10, skipped=2))

    worker = CrawlerWorker(
        rpc=MagicMock(),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        default_quota=PlatformQuota(platform="default", rps=0),
        source_factory=lambda _config, task: sources[task.task_id],
        processor_factory=lambda _config: StatsProcessor(),
    )

    first, second = await asyncio.gather(
        worker.execute_business(BusTask(task_id=1, platform="p", action="a")),
        worker.execute_business(BusTask(task_id=2, platform="p", action="a")),
    )

    assert (first.skipped, second.skipped) == (1, 2)
    assert (worker.last_round_stats.produced, worker.last_round_stats.skipped) in {
        (1, 1),
        (10, 2),
    }


def test_worker_result_contract_is_not_extended_with_crawler_metrics():
    assert tuple(WorkerResult.__dataclass_fields__) == (
        "total",
        "succeeded",
        "failed",
        "skipped",
    )
