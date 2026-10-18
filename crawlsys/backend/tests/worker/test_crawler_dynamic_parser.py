from unittest.mock import AsyncMock, MagicMock

import pytest
from core.config import PlatformQuota
from models import BusTask
from models.task_config import TaskConfig
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.repository import ActionRuntimeDefinition
from worker.crawler import CrawlerWorker
from worker.work_item import ItemDisposition, ItemResult, SourceBatch, WorkItem


def make_worker(*, source, processor, runtime_repository):
    return CrawlerWorker(
        rpc=MagicMock(invoke=AsyncMock()),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        default_quota=PlatformQuota(platform="default", rps=0),
        source_factory=MagicMock(return_value=source),
        processor_factory=MagicMock(return_value=processor),
        runtime_repository=runtime_repository,
    )


def task(*, max_inflight_items=1):
    return BusTask(
        task_id=12,
        ba_id=7,
        platform="test",
        action="detail",
        config=TaskConfig(max_inflight_items=max_inflight_items),
    )


@pytest.mark.asyncio
async def test_each_execute_loads_one_fresh_runtime_before_source_fetch():
    events = []
    runtimes = iter(
        [
            ActionRuntimeDefinition(None, 10, None),
            ActionRuntimeDefinition(None, 11, None),
        ]
    )

    async def load_runtime(ba_id, *, include_parser):
        events.append(f"load:{ba_id}:{include_parser}")
        return next(runtimes)

    async def fetch():
        events.append("fetch")
        return SourceBatch([])

    source = MagicMock(fetch=AsyncMock(side_effect=fetch))
    runtime_repository = MagicMock(load_runtime=AsyncMock(side_effect=load_runtime))
    worker = make_worker(
        source=source,
        processor=MagicMock(process=AsyncMock()),
        runtime_repository=runtime_repository,
    )
    work = task()

    await worker.execute_business(work)
    await worker.execute_business(work)

    assert events == ["load:7:True", "fetch", "load:7:True", "fetch"]
    assert not hasattr(worker, "_schema_cache")


@pytest.mark.asyncio
async def test_invalid_published_definition_fails_before_source_or_rpc():
    source = MagicMock(fetch=AsyncMock())
    runtime_repository = MagicMock(
        load_runtime=AsyncMock(
            side_effect=ParserConfigurationError(
                "parser_definition_invalid",
                "解析规则损坏",
                status_code=422,
            )
        )
    )
    worker = make_worker(
        source=source,
        processor=MagicMock(process=AsyncMock()),
        runtime_repository=runtime_repository,
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await worker.execute_business(task())

    assert caught.value.code == "parser_definition_invalid"
    worker._source_factory.assert_not_called()
    worker.rpc.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_pagination_keeps_one_revision_snapshot_for_all_items():
    source = MagicMock(
        fetch=AsyncMock(
            return_value=SourceBatch([WorkItem({}, "1"), WorkItem({}, "2")])
        ),
        complete=AsyncMock(return_value=ItemDisposition.SUCCEEDED),
    )
    processor = MagicMock(process=AsyncMock(return_value=ItemResult()))
    runtime = ActionRuntimeDefinition(None, 23, None)
    runtime_repository = MagicMock(load_runtime=AsyncMock(return_value=runtime))
    worker = make_worker(
        source=source,
        processor=processor,
        runtime_repository=runtime_repository,
    )
    work = task(max_inflight_items=2)

    await worker.execute_business(work)

    runtime_repository.load_runtime.assert_awaited_once_with(7, include_parser=True)
    snapshots = [call.args[2] for call in processor.process.await_args_list]
    assert snapshots == [runtime, runtime]
    assert snapshots[0] is snapshots[1]


@pytest.mark.asyncio
async def test_ba_id_none_uses_empty_runtime_without_repository_query():
    source = MagicMock(fetch=AsyncMock(return_value=SourceBatch([])))
    runtime_repository = MagicMock(load_runtime=AsyncMock())
    worker = make_worker(
        source=source,
        processor=MagicMock(process=AsyncMock()),
        runtime_repository=runtime_repository,
    )
    work = task()
    work.ba_id = None

    await worker.execute_business(work)

    runtime_repository.load_runtime.assert_not_awaited()
