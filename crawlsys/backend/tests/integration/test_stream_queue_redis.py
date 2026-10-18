from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import redis.asyncio
from redis.exceptions import ResponseError

from app.core.stream_queue import StreamQueue, build_dedupe_key
from models.task_config import RedisStreamSinkConfig, RedisStreamSourceConfig


TEST_REDIS_URL = os.getenv("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not TEST_REDIS_URL,
    reason="set TEST_REDIS_URL to run Redis Streams integration tests",
)


@pytest.mark.asyncio
async def test_real_redis_claim_ack_and_dead_letter():
    tag = f"test-{uuid.uuid4().hex}"
    source = RedisStreamSourceConfig(
        stream=f"crawler:{{{tag}}}:stream",
        group="workers",
        claim_idle_ms=1000,
        dead_letter_stream=f"crawler:{{{tag}}}:dlq",
    )
    client = redis.asyncio.from_url(TEST_REDIS_URL)
    params = {"content_id": "v1"}
    try:
        queue = StreamQueue(client)
        sink = RedisStreamSinkConfig(
            stream=source.stream,
            param_map={"content_id": "content_id"},
            dedupe_ttl_seconds=60,
        )
        await queue.enqueue(
            sink,
            params,
            {
                "producer_task_id": "1",
                "producer_platform": "kalodata",
                "producer_action": "querylist",
                "produced_at": "2026-08-09T00:00:00Z",
            },
        )
        first = await queue.read_batch(source, consumer="consumer-a")
        assert first[0].params == params
        await asyncio.sleep(1.1)
        claimed = await queue.read_batch(source, consumer="consumer-b")
        assert claimed[0].receipt.delivery_count >= 2
        await queue.dead_letter(
            claimed[0].receipt,
            consumer_task_id=2,
            error=RuntimeError("permanent"),
        )
        assert (await client.xpending(source.stream, source.group))["pending"] == 0
        assert await client.xlen(source.stream) == 1
        assert await client.xlen(source.dead_letter_stream) == 1
    finally:
        await client.delete(
            source.stream,
            source.dead_letter_stream,
            build_dedupe_key(source.stream, params),
        )
        await client.aclose()


@pytest.mark.asyncio
async def test_real_redis_dedupe_expires_and_allows_reenqueue():
    tag = f"test-{uuid.uuid4().hex}"
    stream = f"crawler:{{{tag}}}:stream"
    dead_letter_stream = f"crawler:{{{tag}}}:dlq"
    params = {"content_id": "v1"}
    sink = RedisStreamSinkConfig(
        stream=stream,
        param_map={"content_id": "content_id"},
        dedupe_ttl_seconds=1,
    )
    client = redis.asyncio.from_url(TEST_REDIS_URL)
    try:
        queue = StreamQueue(client)
        first = await queue.enqueue(sink, params, {"producer_task_id": "1"})
        duplicate = await queue.enqueue(sink, params, {"producer_task_id": "1"})
        await asyncio.sleep(1.1)
        after_expiry = await queue.enqueue(sink, params, {"producer_task_id": "1"})
        assert first.produced is True
        assert duplicate.deduplicated is True
        assert after_expiry.produced is True
        assert await client.xlen(stream) == 2
    finally:
        await client.delete(stream, dead_letter_stream, build_dedupe_key(stream, params))
        await client.aclose()


@pytest.mark.asyncio
async def test_real_redis_xadd_wrongtype_does_not_poison_dedupe_key():
    tag = f"test-{uuid.uuid4().hex}"
    stream = f"crawler:{{{tag}}}:stream"
    dead_letter_stream = f"crawler:{{{tag}}}:dlq"
    params = {"content_id": "v1"}
    dedupe_key = build_dedupe_key(stream, params)
    sink = RedisStreamSinkConfig(
        stream=stream,
        param_map={"content_id": "content_id"},
        dedupe_ttl_seconds=60,
    )
    client = redis.asyncio.from_url(TEST_REDIS_URL)
    try:
        await client.set(stream, "not-a-stream")
        queue = StreamQueue(client)
        with pytest.raises(ResponseError, match="WRONGTYPE"):
            await queue.enqueue(sink, params, {"producer_task_id": "1"})
        assert await client.exists(dedupe_key) == 0

        await client.delete(stream)
        result = await queue.enqueue(sink, params, {"producer_task_id": "1"})
        assert result.produced is True
        assert await client.exists(dedupe_key) == 1
    finally:
        await client.delete(stream, dead_letter_stream, dedupe_key)
        await client.aclose()
