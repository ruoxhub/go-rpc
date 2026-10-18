import asyncio
from contextlib import asynccontextmanager
from io import StringIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.config import PlatformQuota
from core.sink_handlers import SinkResult
from core.stream_queue import StreamDelivery, StreamQueue, StreamReceipt
from models import BusTask
from models.task import TaskPriority
from models.task_config import (
    DatabaseSourceCompletionConfig,
    PaginationConfig,
    RedisStreamSinkConfig,
    RedisStreamSourceConfig,
    SourceConfig,
    TaskConfig,
)
from utils.log import LogConfig, log
from worker.crawler import CrawlerWorker

from tests.core.test_stream_queue import FakeStreamRedis

SOURCE = RedisStreamSourceConfig(
    stream="crawler:{search}:input",
    group="crawler-workers",
    batch_size=2,
    max_deliveries=3,
    dead_letter_stream="crawler:{search}:dead",
)


def task():
    return BusTask(
        task_id=41,
        platform="tiktok",
        action="search",
        config=TaskConfig(source=SOURCE),
    )


def delivery(*, validation_error=None, delivery_count=1):
    receipt = StreamReceipt(
        stream=SOURCE.stream,
        group=SOURCE.group,
        message_id="1-0",
        delivery_count=delivery_count,
        dead_letter_stream=SOURCE.dead_letter_stream,
        raw_fields={"params": '{"keyword":"cats"}'},
    )
    return StreamDelivery(
        params={"keyword": "cats"} if validation_error is None else {},
        receipt=receipt,
        validation_error=validation_error,
    )


def worker(queue, router, *, consumer_name_factory=lambda: "instance-1"):
    return CrawlerWorker(
        rpc=MagicMock(invoke=AsyncMock(return_value={"itemList": [1]})),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        default_quota=PlatformQuota(platform="default", rps=0),
        stream_queue=queue,
        sink_router=router,
        consumer_name_factory=consumer_name_factory,
    )


@pytest.mark.asyncio
async def test_stream_message_is_acked_only_after_processor_and_sink_succeed():
    events = []
    queue = MagicMock(read_batch=AsyncMock(return_value=[delivery()]))

    async def ack(_receipt):
        events.append("ack")

    queue.ack = AsyncMock(side_effect=ack)
    queue.dead_letter = AsyncMock()
    router = MagicMock()

    async def persist(**_kwargs):
        events.append("persist")
        return SinkResult(processed=1)

    router.persist = AsyncMock(side_effect=persist)
    crawler = worker(queue, router)

    result = await crawler.execute_business(task())

    assert events == ["persist", "ack"]
    assert (result.total, result.succeeded, result.failed) == (1, 1, 0)
    assert crawler.last_round_stats.acked == 1
    queue.read_batch.assert_awaited_once_with(SOURCE, consumer="instance-1")


@pytest.mark.asyncio
async def test_invalid_stream_message_goes_to_dlq_without_failing_worker_round():
    queue = MagicMock(
        read_batch=AsyncMock(return_value=[delivery(validation_error="params invalid")]),
        ack=AsyncMock(),
        dead_letter=AsyncMock(return_value="2-0"),
    )
    router = MagicMock(persist=AsyncMock())
    crawler = worker(queue, router)

    result = await crawler.execute_business(task())

    router.persist.assert_not_awaited()
    queue.dead_letter.assert_awaited_once()
    queue.ack.assert_not_awaited()
    assert result.failed == 0
    assert crawler.last_round_stats.dead_lettered == 1


@pytest.mark.asyncio
async def test_processor_failure_stays_pending_and_does_not_cancel_sibling():
    second = delivery()
    second = StreamDelivery(
        params={"keyword": "dogs"},
        receipt=StreamReceipt(
            stream=SOURCE.stream,
            group=SOURCE.group,
            message_id="2-0",
            delivery_count=1,
            dead_letter_stream=SOURCE.dead_letter_stream,
            raw_fields={"params": '{"keyword":"dogs"}'},
        ),
    )
    queue = MagicMock(
        read_batch=AsyncMock(return_value=[delivery(), second]),
        ack=AsyncMock(),
        dead_letter=AsyncMock(),
    )
    router = MagicMock(
        persist=AsyncMock(side_effect=[RuntimeError("sink down"), SinkResult(processed=1)])
    )
    crawler = worker(queue, router)

    result = await crawler.execute_business(task())

    assert router.persist.await_count == 2
    assert queue.ack.await_count == 1
    assert result.failed == 0
    assert crawler.last_round_stats.retried == 1


@pytest.mark.asyncio
async def test_consumer_name_is_reused_across_rounds_and_batch_size_is_unchanged():
    queue = MagicMock(
        read_batch=AsyncMock(side_effect=[[], []]), ack=AsyncMock(), dead_letter=AsyncMock()
    )
    crawler = worker(queue, MagicMock(), consumer_name_factory=lambda: "stable-consumer")

    await crawler.execute_business(task())
    await crawler.execute_business(task())

    assert [call.kwargs["consumer"] for call in queue.read_batch.await_args_list] == [
        "stable-consumer",
        "stable-consumer",
    ]
    assert all(call.args[0].batch_size == 2 for call in queue.read_batch.await_args_list)


def test_injected_consumer_name_factory_controls_each_worker_name():
    first = worker(MagicMock(), MagicMock())
    second = worker(MagicMock(), MagicMock())
    assert first.consumer_name == "instance-1"
    assert second.consumer_name == "instance-1"


def test_injected_stream_dependencies_are_exposed_by_crawler():
    queue = MagicMock()
    router = MagicMock()
    crawler = worker(queue, router)

    assert crawler.stream_queue is queue
    assert crawler.sink_router is router


def test_generated_consumer_names_are_unique_per_worker_instance():
    first = CrawlerWorker(default_quota=PlatformQuota(platform="default"))
    second = CrawlerWorker(default_quota=PlatformQuota(platform="default"))
    assert first.consumer_name != second.consumer_name


def keyword_publish_task():
    return BusTask(
        task_id=51,
        platform="tiktok",
        action="search",
        config=TaskConfig(
            execution_mode="publish_source",
            source=SourceConfig(
                table="keywords",
                where="enabled = true",
                key_column="id",
                param_map={"keyword": "keyword"},
                filter_by_platform=False,
                completion=DatabaseSourceCompletionConfig(column="published"),
            ),
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:output",
                param_map={"keyword": "keyword"},
            ),
        ),
    )


class Result:
    def __init__(self, *, rows=None, scalar=None):
        self.rows = rows or []
        self.value = scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar(self):
        return self.value


class KeywordDb:
    def __init__(self, *, fail_first_completion=False):
        self.completed = False
        self.fail_first_completion = fail_first_completion
        self.update_attempts = 0

    @asynccontextmanager
    async def asession_scope(self):
        db = self

        class Session:
            async def execute(self, statement, params):
                sql = str(statement)
                if sql.startswith("SELECT data_type"):
                    return Result(scalar="integer")
                if sql.startswith("SELECT"):
                    rows = [] if db.completed else [{"id": 11, "keyword": "cats"}]
                    return Result(rows=rows)
                if sql.startswith("UPDATE"):
                    db.update_attempts += 1
                    if db.fail_first_completion and db.update_attempts == 1:
                        raise RuntimeError("completion unavailable")
                    db.completed = True
                    return Result()
                raise AssertionError(sql)

        yield Session()


@pytest.mark.asyncio
async def test_database_publish_source_skips_rpc_parser_and_completes_row():
    db = KeywordDb()
    router = MagicMock(
        publish_work_item=AsyncMock(return_value=SinkResult(produced=1)),
        persist=AsyncMock(),
    )
    rpc = MagicMock(invoke=AsyncMock())
    crawler = CrawlerWorker(
        rpc=rpc,
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=db,
        default_quota=PlatformQuota(platform="default", rps=0),
        sink_router=router,
    )

    result = await crawler.execute_business(keyword_publish_task())

    rpc.invoke.assert_not_awaited()
    router.persist.assert_not_awaited()
    router.publish_work_item.assert_awaited_once()
    assert db.completed is True
    assert result == result.__class__(total=1, succeeded=1, failed=0, skipped=0)


@pytest.mark.asyncio
async def test_deduplicated_retry_still_completes_after_database_recovers():
    db = KeywordDb(fail_first_completion=True)
    router = MagicMock(
        publish_work_item=AsyncMock(
            side_effect=[
                SinkResult(produced=1),
                SinkResult(deduplicated=1),
            ]
        )
    )
    crawler = CrawlerWorker(
        rpc=MagicMock(),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=db,
        default_quota=PlatformQuota(platform="default", rps=0),
        sink_router=router,
    )

    with pytest.raises(RuntimeError, match="completion unavailable"):
        await crawler.execute_business(keyword_publish_task())
    assert db.completed is False
    assert crawler.last_round_stats.produced == 1

    result = await crawler.execute_business(keyword_publish_task())

    assert router.publish_work_item.await_count == 2
    assert db.completed is True
    assert result.succeeded == 1
    assert crawler.last_round_stats.deduplicated == 1


@pytest.mark.asyncio
async def test_paginated_item_is_not_acked_until_every_page_is_persisted():
    events = []

    async def ack(_receipt):
        events.append("ack")

    async def persist(**_kwargs):
        events.append("persist")
        return SinkResult(processed=1)

    queue = MagicMock(
        read_batch=AsyncMock(return_value=[delivery(delivery_count=2)]),
        ack=AsyncMock(side_effect=ack),
        dead_letter=AsyncMock(),
    )
    router = MagicMock(persist=AsyncMock(side_effect=persist))
    crawler = worker(queue, router)
    crawler.rpc.invoke.side_effect = [
        {"itemList": [1], "hasMore": True, "cursor": 1},
        {"itemList": [2], "hasMore": False, "cursor": 2},
    ]
    paginated = task()
    paginated.config = paginated.config.model_copy(
        update={"pagination": PaginationConfig()}
    )

    await crawler.execute_business(paginated)

    assert router.persist.await_count == 2
    queue.ack.assert_awaited_once()
    assert events == ["persist", "persist", "ack"]
    assert crawler.last_round_stats.acked == 1


@pytest.mark.asyncio
async def test_paginated_sink_failure_leaves_message_pending():
    queue = MagicMock(
        read_batch=AsyncMock(return_value=[delivery()]),
        ack=AsyncMock(),
        dead_letter=AsyncMock(),
    )
    router = MagicMock(
        persist=AsyncMock(
            side_effect=[SinkResult(processed=1), RuntimeError("second page failed")]
        )
    )
    crawler = worker(queue, router)
    crawler.rpc.invoke.side_effect = [
        {"itemList": [1], "hasMore": True, "cursor": 1},
        {"itemList": [2], "hasMore": False, "cursor": 2},
    ]
    paginated = task()
    paginated.config = paginated.config.model_copy(
        update={"pagination": PaginationConfig()}
    )

    result = await crawler.execute_business(paginated)

    queue.ack.assert_not_awaited()
    queue.dead_letter.assert_not_awaited()
    assert result.failed == 0
    assert crawler.last_round_stats.retried == 1


@pytest.mark.asyncio
async def test_round_stats_aggregate_sink_outcomes_without_extending_worker_result():
    queue = MagicMock(
        read_batch=AsyncMock(return_value=[delivery()]),
        ack=AsyncMock(),
        dead_letter=AsyncMock(),
    )
    router = MagicMock(
        persist=AsyncMock(
            return_value=SinkResult(produced=1, deduplicated=2, skipped=3)
        )
    )
    crawler = worker(queue, router)

    result = await crawler.execute_business(task())

    assert result.skipped == 3
    assert crawler.last_round_stats.produced == 1
    assert crawler.last_round_stats.deduplicated == 2
    assert crawler.last_round_stats.skipped == 3


@pytest.mark.asyncio
async def test_stream_round_logs_structured_crawler_stats():
    source = RedisStreamSourceConfig(
        stream="crawler:{detail}:stream",
        group="detail-workers",
        batch_size=4,
        max_deliveries=3,
        dead_letter_stream="crawler:{detail}:dead",
    )
    receipts = [
        StreamReceipt(
            stream=source.stream,
            group=source.group,
            message_id=f"{index}-0",
            delivery_count=1,
            dead_letter_stream=source.dead_letter_stream,
            raw_fields={"params": '{"password":"redis-secret"}'},
        )
        for index in range(1, 5)
    ]
    deliveries = [
        StreamDelivery(params={"id": 1}, receipt=receipts[0]),
        StreamDelivery(params={"id": 2}, receipt=receipts[1]),
        StreamDelivery(params={"id": 3}, receipt=receipts[2]),
        StreamDelivery(
            params={}, receipt=receipts[3], validation_error="params invalid"
        ),
    ]
    queue = MagicMock(
        read_batch=AsyncMock(return_value=deliveries),
        ack=AsyncMock(),
        dead_letter=AsyncMock(return_value="5-0"),
    )
    router = MagicMock(
        persist=AsyncMock(
            side_effect=[
                SinkResult(processed=1),
                SinkResult(processed=1),
                RuntimeError("retry"),
            ]
        )
    )
    crawler = worker(queue, router, consumer_name_factory=lambda: "detail-consumer")
    task_to_run = BusTask(
        task_id=41,
        platform="tiktok",
        action="videoDetail",
        config=TaskConfig(source=source),
        priority=TaskPriority.URGENT,
    )
    rendered = StringIO()
    records = []
    rendered_sink = log.add(rendered, format=LogConfig().file_format, colorize=False)
    record_sink = log.add(lambda message: records.append(message.record), level="INFO")
    try:
        await crawler.execute_business(task_to_run)
    finally:
        log.remove(record_sink)
        log.remove(rendered_sink)

    record = next(
        item["extra"] for item in records if item["extra"].get("outcome") == "round_complete"
    )
    assert record["task_id"] == 41
    assert record["platform"] == "tiktok"
    assert record["action"] == "videoDetail"
    assert record["priority"] == 4
    assert record["stream"] == "crawler:{detail}:stream"
    assert record["group"] == "detail-workers"
    assert record["consumer"] == crawler.consumer_name
    assert record["message_id"] is None
    assert record["delivery_count"] is None
    assert record["latency_ms"] >= 0
    assert (record["acked"], record["retried"], record["dead_lettered"]) == (2, 1, 1)
    assert set(record) == {
        "module",
        "task_id",
        "platform",
        "action",
        "priority",
        "stream",
        "group",
        "consumer",
        "message_id",
        "delivery_count",
        "outcome",
        "latency_ms",
        "acked",
        "retried",
        "dead_lettered",
    }
    message_records = [
        item["extra"] for item in records if item["extra"].get("message_id") is not None
    ]
    assert {
        (item["message_id"], item["delivery_count"], item["outcome"])
        for item in message_records
    } == {
        ("1-0", 1, "succeeded"),
        ("2-0", 1, "succeeded"),
        ("3-0", 1, "retry"),
        ("4-0", 1, "dead_lettered"),
    }
    assert all(item["latency_ms"] >= 0 for item in message_records)
    assert all(
        set(item)
        == {
            "module",
            "task_id",
            "platform",
            "action",
            "stream",
            "group",
            "consumer",
            "message_id",
            "delivery_count",
            "outcome",
            "latency_ms",
        }
        for item in message_records
    )
    assert all(
        not ({"params", "raw_fields", "password"} & item.keys())
        for item in [record, *message_records]
    )
    output = rendered.getvalue()
    for field in (
        "task_id=41",
        'platform="tiktok"',
        'action="videoDetail"',
        'stream="crawler:{detail}:stream"',
        'group="detail-workers"',
        'consumer="detail-consumer"',
        'outcome="round_complete"',
        "acked=2",
        "retried=1",
        "dead_lettered=1",
    ):
        assert field in output
    assert "redis-secret" not in output


@pytest.mark.asyncio
async def test_cancelled_pending_delivery_is_claimed_and_acked_once_next_round():
    fields = {b"params": b'{"keyword":"cats"}'}
    client = FakeStreamRedis(fresh=[("1-0", fields)])
    stream_queue = StreamQueue(client)
    started = asyncio.Event()
    delivery_counts = []
    attempts = 0

    async def persist(**kwargs):
        nonlocal attempts
        attempts += 1
        delivery_counts.append(kwargs["item"].receipt.delivery_count)
        if attempts == 1:
            started.set()
            await asyncio.Future()
        return SinkResult(processed=1)

    router = MagicMock(persist=AsyncMock(side_effect=persist))
    crawler = CrawlerWorker(
        rpc=MagicMock(invoke=AsyncMock(return_value={"itemList": [1]})),
        repo=MagicMock(),
        pipeline=MagicMock(),
        db=MagicMock(),
        default_quota=PlatformQuota(platform="default", rps=0),
        stream_queue=stream_queue,
        sink_router=router,
        consumer_name_factory=lambda: "stable-consumer",
    )

    first_round = asyncio.create_task(crawler.execute_business(task()))
    await started.wait()
    first_round.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_round
    assert client.xack_calls == []

    client.fresh = []
    client.claimed = [("1-0", fields)]
    client.deliveries = {"1-0": 2}

    result = await crawler.execute_business(task())

    assert result.succeeded == 1
    assert attempts == 2
    assert delivery_counts == [1, 2]
    assert len(client.xautoclaim_calls) == 2
    assert client.xautoclaim_calls[1]["consumername"] == "stable-consumer"
    assert client.xack_calls == [(SOURCE.stream, SOURCE.group, ("1-0",))]
