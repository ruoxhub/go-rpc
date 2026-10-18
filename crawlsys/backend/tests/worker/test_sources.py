from contextlib import asynccontextmanager
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.stream_queue import StreamDelivery, StreamReceipt
from go_rpc import RetryableRpcError
from models.task_config import (
    DatabaseSourceCompletionConfig,
    DatabaseSourceConfig,
    RedisStreamSourceConfig,
)
from worker.sources import DatabaseWorkItemSource, RedisStreamWorkItemSource
from worker.work_item import ItemDisposition, WorkItem

SOURCE = RedisStreamSourceConfig(
    stream="crawler:{search}:input",
    group="crawler-workers",
    batch_size=7,
    dead_letter_stream="crawler:{search}:dead",
)
RECEIPT = StreamReceipt(
    stream=SOURCE.stream,
    group=SOURCE.group,
    message_id="1-0",
    delivery_count=1,
    dead_letter_stream=SOURCE.dead_letter_stream,
    raw_fields={"params": '{"content_id":"v1"}'},
)


@pytest.mark.asyncio
async def test_stream_source_keeps_receipt_out_of_rpc_params():
    queue = AsyncMock()
    queue.read_batch.return_value = [
        StreamDelivery(params={"content_id": "v1"}, receipt=RECEIPT)
    ]
    source = RedisStreamWorkItemSource(
        queue, SOURCE, consumer="instance-1", consumer_task_id=41
    )

    batch = await source.fetch()

    assert batch.items[0].params == {"content_id": "v1"}
    assert batch.items[0].receipt == RECEIPT
    assert "message_id" not in batch.items[0].params
    assert (batch.read, batch.claimed) == (1, 1)
    queue.read_batch.assert_awaited_once_with(SOURCE, consumer="instance-1")


@pytest.mark.asyncio
async def test_stream_source_maps_validation_error_and_message_id():
    queue = AsyncMock()
    queue.read_batch.return_value = [
        StreamDelivery({}, RECEIPT, "params is not an object")
    ]
    source = RedisStreamWorkItemSource(
        queue, SOURCE, consumer="instance-1", consumer_task_id=41
    )

    item = (await source.fetch()).items[0]

    assert item.entity_id == RECEIPT.message_id
    assert item.input_error == "params is not an object"


@pytest.mark.asyncio
async def test_stream_source_complete_acks_receipt():
    queue = AsyncMock()
    source = RedisStreamWorkItemSource(
        queue, SOURCE, consumer="instance-1", consumer_task_id=41
    )

    disposition = await source.complete(WorkItem(params={}, receipt=RECEIPT))

    queue.ack.assert_awaited_once_with(RECEIPT)
    assert disposition is ItemDisposition.SUCCEEDED


@pytest.mark.asyncio
async def test_stream_source_rejects_terminal_operations_without_receipt():
    queue = AsyncMock()
    source = RedisStreamWorkItemSource(
        queue, SOURCE, consumer="instance-1", consumer_task_id=41
    )
    item = WorkItem(params={})

    with pytest.raises(ValueError, match="missing its receipt"):
        await source.complete(item)
    with pytest.raises(ValueError, match="missing its receipt"):
        await source.fail(item, RuntimeError("failed"), deterministic=False)

    queue.ack.assert_not_awaited()
    queue.dead_letter.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_source_transient_failure_stays_pending():
    queue = AsyncMock()
    source = RedisStreamWorkItemSource(
        queue, SOURCE, consumer="instance-1", consumer_task_id=41
    )

    disposition = await source.fail(
        WorkItem(params={}, receipt=replace(RECEIPT, delivery_count=2)),
        RetryableRpcError("later"),
        deterministic=False,
    )

    queue.ack.assert_not_awaited()
    queue.dead_letter.assert_not_awaited()
    assert disposition is ItemDisposition.RETRY


@pytest.mark.asyncio
@pytest.mark.parametrize("deterministic, delivery_count", [(True, 1), (False, 5)])
async def test_stream_source_terminal_failure_goes_to_dlq(
    deterministic, delivery_count
):
    queue = AsyncMock()
    source = RedisStreamWorkItemSource(
        queue, SOURCE, consumer="instance-1", consumer_task_id=41
    )
    item = WorkItem(params={}, receipt=replace(RECEIPT, delivery_count=delivery_count))
    error = ValueError("bad params")

    disposition = await source.fail(item, error, deterministic=deterministic)

    queue.dead_letter.assert_awaited_once_with(
        item.receipt, consumer_task_id=41, error=error
    )
    queue.ack.assert_not_awaited()
    assert disposition is ItemDisposition.DEAD_LETTERED


def _database_source():
    return DatabaseSourceConfig(
        table="keywords",
        where="enabled = true",
        key_column="id",
        param_map={"keyword": "keyword"},
        filter_by_platform=False,
        completion=DatabaseSourceCompletionConfig(column="published", value=True),
    )


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._rows


@pytest.mark.asyncio
async def test_database_source_without_config_yields_default_item_and_completes():
    source = DatabaseWorkItemSource(MagicMock(), None, platform=None)

    batch = await source.fetch()
    disposition = await source.complete(batch.items[0])

    assert batch.items == [WorkItem({})]
    assert batch.read == 1
    assert disposition is ItemDisposition.SUCCEEDED


@pytest.mark.asyncio
async def test_database_fetch_preserves_where_and_excludes_completed_rows():
    session = AsyncMock()
    session.execute.return_value = _Rows([{"id": 11, "keyword": "cats"}])
    db = MagicMock()

    @asynccontextmanager
    async def scope():
        yield session

    db.asession_scope = scope
    source = DatabaseWorkItemSource(db, _database_source(), platform="tiktok")

    batch = await source.fetch()

    statement, params = session.execute.await_args.args
    sql = str(statement)
    assert "(enabled = true)" in sql
    assert "published IS DISTINCT FROM :completion_value" in sql
    assert params["completion_value"] is True
    assert batch.items == [WorkItem({"keyword": "cats", "id": "11"}, "11")]
    assert batch.read == 1


@pytest.mark.asyncio
async def test_database_fetch_filters_platform_and_handles_key_alias_and_empty_rows():
    session = AsyncMock()
    session.execute.side_effect = [
        _Rows(1),
        _Rows([{"id": None, "keyword": None}, {"id": 7, "keyword": None}]),
    ]
    db = MagicMock()

    @asynccontextmanager
    async def scope():
        yield session

    db.asession_scope = scope
    config = DatabaseSourceConfig(
        table="keywords",
        key_column="id",
        param_map={"id": "id", "keyword": "keyword"},
        filter_by_platform=True,
    )
    source = DatabaseWorkItemSource(db, config, platform="tiktok")

    batch = await source.fetch()

    statement, params = session.execute.await_args_list[1].args
    assert "platform = :platform" in str(statement)
    assert params == {"platform": "tiktok"}
    assert batch.items == [WorkItem({"id": "7"}, "7")]
    assert batch.read == 2


@pytest.mark.asyncio
async def test_database_complete_updates_source_row_and_fail_does_not_update():
    session = AsyncMock()
    session.execute.side_effect = [_Rows("text"), MagicMock()]
    db = MagicMock()

    @asynccontextmanager
    async def scope():
        yield session

    db.asession_scope = scope
    source = DatabaseWorkItemSource(db, _database_source(), platform="tiktok")
    item = WorkItem({"keyword": "cats"}, "11")

    disposition = await source.complete(item)
    failed = await source.fail(item, RuntimeError("rpc failed"), deterministic=False)

    statement, params = session.execute.await_args.args
    assert (
        str(statement)
        == "UPDATE keywords SET published = :completion_value WHERE id = :entity_id"
    )
    assert params == {"completion_value": True, "entity_id": "11"}
    assert session.execute.await_count == 2
    assert disposition is ItemDisposition.SUCCEEDED
    assert failed is ItemDisposition.FAILED


@pytest.mark.asyncio
async def test_database_complete_converts_numeric_id_for_integer_key_column():
    metadata = _Rows("integer")
    session = AsyncMock()
    session.execute.side_effect = [metadata, MagicMock()]
    db = MagicMock()

    @asynccontextmanager
    async def scope():
        yield session

    db.asession_scope = scope
    source = DatabaseWorkItemSource(db, _database_source(), platform="tiktok")

    await source.complete(WorkItem({"keyword": "cats"}, "11"))

    assert session.execute.await_args_list[1].args[1]["entity_id"] == 11


@pytest.mark.asyncio
async def test_database_fetch_preserves_zero_entity_id():
    session = AsyncMock()
    session.execute.return_value = _Rows([{"id": 0, "keyword": "cats"}])
    db = MagicMock()

    @asynccontextmanager
    async def scope():
        yield session

    db.asession_scope = scope
    source_config = _database_source().model_copy(update={"completion": None})
    source = DatabaseWorkItemSource(db, source_config, platform="tiktok")

    item = (await source.fetch()).items[0]

    assert item.entity_id == "0"


@pytest.mark.asyncio
async def test_database_complete_propagates_update_failure():
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("database unavailable")
    db = MagicMock()

    @asynccontextmanager
    async def scope():
        yield session

    db.asession_scope = scope
    source = DatabaseWorkItemSource(db, _database_source(), platform="tiktok")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await source.complete(WorkItem({"keyword": "cats"}, "11"))
