from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pytest
from redis.exceptions import ResponseError

from app.core.stream_queue import (
    MAX_STREAM_PARAMS_BYTES,
    StreamQueue,
    StreamReceipt,
    build_dedupe_key,
    canonical_stream_params,
)
from models.task_config import RedisStreamSinkConfig, RedisStreamSourceConfig


SOURCE = RedisStreamSourceConfig(
    stream="crawler:{detail}:stream",
    group="workers",
    batch_size=10,
    block_ms=25,
    claim_idle_ms=1_000,
    dead_letter_stream="crawler:{detail}:dlq",
)
SINK = RedisStreamSinkConfig(
    stream=SOURCE.stream,
    param_map={"content_id": "content_id"},
    dedupe_ttl_seconds=60,
)
META = {
    "producer_task_id": "1",
    "producer_platform": "kalodata",
    "producer_action": "querylist",
    "produced_at": "2026-08-09T00:00:00Z",
}
RECEIPT = StreamReceipt(
    stream=SOURCE.stream,
    group=SOURCE.group,
    message_id="2-0",
    delivery_count=4,
    dead_letter_stream=SOURCE.dead_letter_stream,
    raw_fields={"params": '{"content_id":"1"}', "producer_task_id": "1"},
)


@dataclass
class EvalCall:
    script: str
    keys: list[str]
    args: list[str]


class FakePendingPipeline:
    def __init__(self, client: "FakeStreamRedis") -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def xpending_range(self, **kwargs: Any) -> "FakePendingPipeline":
        self.calls.append(kwargs)
        return self

    async def execute(self) -> list[list[dict[str, Any]]]:
        for call in self.calls:
            self.client.operations.append("xpending_range")
            self.client.xpending_range_calls.append(call)
        return [self.client.pending_rows(call) for call in self.calls]


class FakeStreamRedis:
    def __init__(
        self,
        *,
        claimed: list[tuple[Any, dict[Any, Any]]] | None = None,
        fresh: list[tuple[Any, dict[Any, Any]]] | None = None,
        deliveries: dict[str, int] | None = None,
        eval_results: list[Any] | None = None,
        group_error: ResponseError | None = None,
    ) -> None:
        self.claimed = claimed or []
        self.fresh = fresh or []
        self.deliveries = deliveries or {}
        self.eval_results = list(eval_results or [])
        self.group_error = group_error
        self.eval_calls: list[EvalCall] = []
        self.xack_calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.xgroup_create_calls: list[dict[str, Any]] = []
        self.xautoclaim_calls: list[dict[str, Any]] = []
        self.xpending_range_calls: list[dict[str, Any]] = []
        self.xreadgroup_calls: list[dict[str, Any]] = []
        self.operations: list[str] = []

    async def xgroup_create(
        self, name: str, groupname: str, id: str, mkstream: bool
    ) -> bool:
        self.operations.append("xgroup_create")
        self.xgroup_create_calls.append(
            {"name": name, "groupname": groupname, "id": id, "mkstream": mkstream}
        )
        if self.group_error:
            raise self.group_error
        return True

    async def xautoclaim(self, **kwargs: Any) -> list[Any]:
        self.operations.append("xautoclaim")
        self.xautoclaim_calls.append(kwargs)
        return [b"0-0", self.claimed, []]

    async def xpending_range(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.operations.append("xpending_range")
        self.xpending_range_calls.append(kwargs)
        return self.pending_rows(kwargs)

    def pending_rows(self, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        minimum = kwargs["min"]
        maximum = kwargs["max"]
        count = kwargs["count"]
        return [
            {
                "message_id": message_id.encode(),
                "times_delivered": delivery_count,
            }
            for message_id, delivery_count in self.deliveries.items()
            if minimum <= message_id <= maximum
        ][:count]

    def pipeline(self, *, transaction: bool) -> FakePendingPipeline:
        assert transaction is False
        return FakePendingPipeline(self)

    async def xreadgroup(self, **kwargs: Any) -> list[Any]:
        self.operations.append("xreadgroup")
        self.xreadgroup_calls.append(kwargs)
        if not self.fresh:
            return []
        return [(SOURCE.stream.encode(), self.fresh)]

    async def xack(self, stream: str, group: str, *message_ids: str) -> int:
        self.xack_calls.append((stream, group, message_ids))
        return len(message_ids)

    async def eval(self, script: str, numkeys: int, *values: str) -> Any:
        self.eval_calls.append(
            EvalCall(script=script, keys=list(values[:numkeys]), args=list(values[numkeys:]))
        )
        return self.eval_results.pop(0)


@pytest.mark.asyncio
async def test_read_batch_claims_pending_before_new_messages():
    client = FakeStreamRedis(
        claimed=[("1-0", {b"params": b'{"content_id":"old"}'})],
        fresh=[("2-0", {b"params": b'{"content_id":"new"}'})],
        deliveries={"1-0": 3},
    )
    queue = StreamQueue(client)
    batch = await queue.read_batch(SOURCE, consumer="host-1")
    assert [item.params["content_id"] for item in batch] == ["old", "new"]
    assert batch[0].receipt.delivery_count == 3
    assert client.operations == [
        "xgroup_create",
        "xautoclaim",
        "xpending_range",
        "xreadgroup",
    ]
    assert client.xgroup_create_calls == [
        {"name": SOURCE.stream, "groupname": SOURCE.group, "id": "0", "mkstream": True}
    ]
    assert client.xautoclaim_calls[0]["count"] == SOURCE.batch_size
    assert client.xautoclaim_calls[0]["start_id"] == "0-0"
    assert client.xpending_range_calls[0] == {
        "name": SOURCE.stream,
        "groupname": SOURCE.group,
        "min": "1-0",
        "max": "1-0",
        "count": 1,
        "consumername": "host-1",
    }
    assert client.xreadgroup_calls[0] == {
        "groupname": SOURCE.group,
        "consumername": "host-1",
        "streams": {SOURCE.stream: ">"},
        "count": SOURCE.batch_size - 1,
        "block": SOURCE.block_ms,
    }


@pytest.mark.asyncio
async def test_read_batch_never_exceeds_batch_size_or_pages_claims():
    source = SOURCE.model_copy(update={"batch_size": 1})
    client = FakeStreamRedis(
        claimed=[
            ("1-0", {b"params": b'{"content_id":"old"}'}),
            ("2-0", {b"params": b'{"content_id":"extra"}'}),
        ],
        fresh=[("3-0", {b"params": b'{"content_id":"new"}'})],
    )
    batch = await StreamQueue(client).read_batch(source, consumer="host-1")
    assert len(batch) == 1
    assert len(client.xautoclaim_calls) == 1
    assert client.xreadgroup_calls == []


@pytest.mark.asyncio
async def test_read_batch_gets_each_claimed_delivery_count_despite_interleaved_pending():
    client = FakeStreamRedis(
        claimed=[
            ("1-0", {b"params": b'{"content_id":"first"}'}),
            ("2-0", {b"params": b'{"content_id":"second"}'}),
        ],
        deliveries={"1-0": 3, "1-5": 99, "2-0": 4},
    )
    batch = await StreamQueue(client).read_batch(SOURCE, consumer="host-1")
    assert [item.receipt.delivery_count for item in batch] == [3, 4]


@pytest.mark.asyncio
async def test_enqueue_returns_deduplicated_when_lua_does_not_xadd():
    client = FakeStreamRedis(eval_results=[[0, ""]])
    result = await StreamQueue(client).enqueue(SINK, {"content_id": "1"}, META)
    assert result.produced is False
    assert result.deduplicated is True


def test_canonical_stream_params_has_stable_utf8_json():
    assert canonical_stream_params({"z": "中文", "a": 1}) == '{"a":1,"z":"中文"}'
    with pytest.raises(ValueError):
        canonical_stream_params({"invalid": float("nan")})


def test_dedupe_key_is_canonical_and_uses_stream_hash_tag():
    params = {"z": "中文", "a": 1}
    canonical = json.dumps(
        params, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256((SINK.stream + canonical).encode("utf-8")).hexdigest()
    assert build_dedupe_key(SINK.stream, params) == f"crawler:{{detail}}:dedupe:{digest}"


@pytest.mark.asyncio
async def test_enqueue_rejects_params_larger_than_64_kib_before_redis_call():
    client = FakeStreamRedis()
    queue = StreamQueue(client)
    with pytest.raises(ValueError, match="65536"):
        await queue.enqueue(SINK, {"value": "x" * 65_537}, META)
    assert client.eval_calls == []


@pytest.mark.asyncio
async def test_read_batch_marks_oversized_params_as_deterministic_input_error():
    oversized = json.dumps({"value": "x" * 65_537}).encode()
    client = FakeStreamRedis(fresh=[("2-0", {b"params": oversized})])
    batch = await StreamQueue(client).read_batch(SOURCE, consumer="host-1")
    assert str(MAX_STREAM_PARAMS_BYTES) in (batch[0].validation_error or "")
    assert batch[0].receipt.message_id == "2-0"


@pytest.mark.asyncio
async def test_read_batch_marks_invalid_utf8_as_validation_error():
    client = FakeStreamRedis(fresh=[("2-0", {b"params": b'{"value":"\xff"}'})])
    batch = await StreamQueue(client).read_batch(SOURCE, consumer="host-1")
    assert len(batch) == 1
    assert "JSON" in (batch[0].validation_error or "")
    assert batch[0].receipt.message_id == "2-0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fields", "error_fragment"),
    [
        ({}, "params"),
        ({b"params": b"[]"}, "object"),
        ({b"params": b"not-json"}, "JSON"),
    ],
)
async def test_read_batch_preserves_invalid_messages(fields: dict[Any, Any], error_fragment: str):
    batch = await StreamQueue(FakeStreamRedis(fresh=[("2-0", fields)])).read_batch(
        SOURCE, consumer="host-1"
    )
    assert len(batch) == 1
    assert error_fragment in (batch[0].validation_error or "")


@pytest.mark.asyncio
async def test_ensure_group_only_ignores_busygroup():
    await StreamQueue(FakeStreamRedis(group_error=ResponseError("BUSYGROUP exists"))).ensure_group(
        SOURCE
    )
    with pytest.raises(ResponseError, match="NOPERM"):
        await StreamQueue(FakeStreamRedis(group_error=ResponseError("NOPERM denied"))).ensure_group(
            SOURCE
        )


@pytest.mark.asyncio
async def test_ack_uses_receipt_without_exposing_redis_details():
    client = FakeStreamRedis()
    assert await StreamQueue(client).ack(RECEIPT) == 1
    assert client.xack_calls == [(RECEIPT.stream, RECEIPT.group, (RECEIPT.message_id,))]


@pytest.mark.asyncio
async def test_dead_letter_uses_original_and_dlq_keys_in_one_eval():
    client = FakeStreamRedis(eval_results=["3-0"])
    queue = StreamQueue(client)
    await queue.dead_letter(RECEIPT, consumer_task_id=9, error=ValueError("bad"))
    keys = client.eval_calls[0].keys
    assert keys == [RECEIPT.stream, RECEIPT.dead_letter_stream]
    assert "bad" in " ".join(client.eval_calls[0].args)
    assert "XDEL" not in client.eval_calls[0].script
    assert client.eval_calls[0].script.index("XADD") < client.eval_calls[0].script.index("XACK")
    assert client.eval_calls[0].args[2::2] == [
        "original_stream",
        "original_message_id",
        "params",
        "producer_task_id",
        "consumer_task_id",
        "delivery_count",
        "error_type",
        "error_message",
        "failed_at",
    ]


@pytest.mark.asyncio
async def test_dead_letter_bounds_and_redacts_error_message():
    client = FakeStreamRedis(eval_results=["3-0"])
    error = RuntimeError("redis://user:secret@localhost " + "x" * 600)
    await StreamQueue(client).dead_letter(RECEIPT, consumer_task_id=9, error=error)
    args = client.eval_calls[0].args
    fields = dict(zip(args[2::2], args[3::2]))
    assert len(fields["error_message"]) <= 500
    assert "secret" not in fields["error_message"]
    assert "[REDACTED_URL]" in fields["error_message"]


@pytest.mark.asyncio
async def test_enqueue_lua_sets_dedupe_only_after_xadd():
    client = FakeStreamRedis(eval_results=[[1, b"7-0"]])
    result = await StreamQueue(client).enqueue(SINK, {"content_id": "1"}, META)
    call = client.eval_calls[0]
    assert call.script.index("EXISTS") < call.script.index("XADD") < call.script.index("SET")
    assert call.keys == [build_dedupe_key(SINK.stream, {"content_id": "1"}), SINK.stream]
    assert result.message_id == "7-0"
