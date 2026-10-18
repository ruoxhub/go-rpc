"""Reliable Redis Streams boundary for action workers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from redis.exceptions import ResponseError

from common.errors import format_error
from models.task_config import RedisStreamSinkConfig, RedisStreamSourceConfig


MAX_STREAM_PARAMS_BYTES = 65_536

_ENQUEUE_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return {0, ''}
end
local id = redis.call('XADD', KEYS[2], '*', unpack(ARGV, 2))
redis.call('SET', KEYS[1], '1', 'EX', ARGV[1])
return {1, id}
""".strip()

_DEAD_LETTER_SCRIPT = """
local id = redis.call('XADD', KEYS[2], '*', unpack(ARGV, 3))
redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
return id
""".strip()


@dataclass(frozen=True, slots=True)
class StreamReceipt:
    stream: str
    group: str
    message_id: str
    delivery_count: int
    dead_letter_stream: str
    raw_fields: dict[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class StreamDelivery:
    params: dict[str, Any]
    receipt: StreamReceipt
    validation_error: str | None = None


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    produced: bool
    deduplicated: bool
    message_id: str | None = None


def canonical_stream_params(params: Mapping[str, Any]) -> str:
    """Serialize stream parameters to their stable JSON representation."""
    return json.dumps(
        params,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_dedupe_key(stream: str, params: Mapping[str, Any]) -> str:
    """Build a deterministic dedupe key in the stream's Redis Cluster slot."""
    tag_end = stream.index("}") + 1
    digest_input = stream + canonical_stream_params(params)
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    return f"{stream[:tag_end]}:dedupe:{digest}"


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, bytearray):
        return bytes(value).decode("utf-8")
    return str(value)


def _as_field_text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def _mapping_value(mapping: Mapping[Any, Any], key: str) -> Any:
    if key in mapping:
        return mapping[key]
    return mapping.get(key.encode())


class StreamQueue:
    """Expose worker-oriented operations without leaking raw Redis responses."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def ensure_group(self, source: RedisStreamSourceConfig) -> None:
        try:
            await self._client.xgroup_create(
                source.stream,
                source.group,
                id="0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def read_batch(
        self,
        source: RedisStreamSourceConfig,
        *,
        consumer: str,
    ) -> list[StreamDelivery]:
        await self.ensure_group(source)
        claim_result = await self._client.xautoclaim(
            name=source.stream,
            groupname=source.group,
            consumername=consumer,
            min_idle_time=source.claim_idle_ms,
            start_id="0-0",
            count=source.batch_size,
        )
        claimed = list(claim_result[1])[: source.batch_size]
        delivery_counts = await self._delivery_counts(source, claimed, consumer)
        deliveries = [
            self._delivery(source, message_id, fields, delivery_counts.get(_as_text(message_id), 1))
            for message_id, fields in claimed
        ]

        remaining = source.batch_size - len(deliveries)
        if remaining <= 0:
            return deliveries

        fresh_result = await self._client.xreadgroup(
            groupname=source.group,
            consumername=consumer,
            streams={source.stream: ">"},
            count=remaining,
            block=source.block_ms,
        )
        for _, messages in fresh_result or []:
            for message_id, fields in messages:
                if len(deliveries) >= source.batch_size:
                    return deliveries
                deliveries.append(self._delivery(source, message_id, fields, 1))
        return deliveries

    async def enqueue(
        self,
        sink: RedisStreamSinkConfig,
        params: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> EnqueueResult:
        canonical = canonical_stream_params(params)
        encoded_size = len(canonical.encode("utf-8"))
        if encoded_size > MAX_STREAM_PARAMS_BYTES:
            raise ValueError(
                f"stream params exceed {MAX_STREAM_PARAMS_BYTES} UTF-8 bytes"
            )

        dedupe_key = build_dedupe_key(sink.stream, params)
        fields = ["params", canonical]
        for name, value in metadata.items():
            fields.extend((_as_text(name), _as_text(value)))
        result = await self._client.eval(
            _ENQUEUE_SCRIPT,
            2,
            dedupe_key,
            sink.stream,
            str(sink.dedupe_ttl_seconds),
            *fields,
        )
        produced = int(result[0]) == 1
        message_id = _as_text(result[1]) if produced else None
        return EnqueueResult(
            produced=produced,
            deduplicated=not produced,
            message_id=message_id,
        )

    async def ack(self, receipt: StreamReceipt) -> int:
        return await self._client.xack(
            receipt.stream,
            receipt.group,
            receipt.message_id,
        )

    async def dead_letter(
        self,
        receipt: StreamReceipt,
        *,
        consumer_task_id: int,
        error: BaseException,
    ) -> str:
        fields = [
            "original_stream",
            receipt.stream,
            "original_message_id",
            receipt.message_id,
            "params",
            receipt.raw_fields.get("params", ""),
            "producer_task_id",
            receipt.raw_fields.get("producer_task_id", ""),
            "consumer_task_id",
            str(consumer_task_id),
            "delivery_count",
            str(receipt.delivery_count),
            "error_type",
            type(error).__name__,
            "error_message",
            format_error(error, max_length=500),
            "failed_at",
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ]
        result = await self._client.eval(
            _DEAD_LETTER_SCRIPT,
            2,
            receipt.stream,
            receipt.dead_letter_stream,
            receipt.group,
            receipt.message_id,
            *fields,
        )
        return _as_text(result)

    async def _delivery_counts(
        self,
        source: RedisStreamSourceConfig,
        claimed: list[Any],
        consumer: str,
    ) -> dict[str, int]:
        if not claimed:
            return {}
        message_ids = [_as_text(message[0]) for message in claimed]
        pipeline = self._client.pipeline(transaction=False)
        for message_id in message_ids:
            pipeline.xpending_range(
                name=source.stream,
                groupname=source.group,
                min=message_id,
                max=message_id,
                count=1,
                consumername=consumer,
            )
        pending_pages = await pipeline.execute()
        counts: dict[str, int] = {}
        for expected_id, pending in zip(message_ids, pending_pages):
            if not pending:
                continue
            item = pending[0]
            message_id = _as_text(_mapping_value(item, "message_id"))
            if message_id == expected_id:
                counts[message_id] = int(_mapping_value(item, "times_delivered"))
        return counts

    def _delivery(
        self,
        source: RedisStreamSourceConfig,
        message_id: Any,
        fields: Mapping[Any, Any],
        delivery_count: int,
    ) -> StreamDelivery:
        raw_param_value = _mapping_value(fields, "params")
        raw_fields = {
            _as_field_text(key): _as_field_text(value) for key, value in fields.items()
        }
        receipt = StreamReceipt(
            stream=source.stream,
            group=source.group,
            message_id=_as_text(message_id),
            delivery_count=delivery_count,
            dead_letter_stream=source.dead_letter_stream,
            raw_fields=raw_fields,
        )
        if raw_param_value is None:
            return StreamDelivery({}, receipt, "stream message is missing params")
        try:
            raw_params = _as_text(raw_param_value)
        except UnicodeDecodeError as error:
            return StreamDelivery({}, receipt, f"params must be valid UTF-8 JSON: {error}")
        try:
            params = json.loads(raw_params)
        except json.JSONDecodeError as error:
            return StreamDelivery({}, receipt, f"params must be valid JSON: {error.msg}")
        if not isinstance(params, dict):
            return StreamDelivery({}, receipt, "params must be a JSON object")
        try:
            canonical = canonical_stream_params(params)
        except (TypeError, ValueError) as error:
            return StreamDelivery({}, receipt, f"params must be valid JSON: {error}")
        encoded_size = len(canonical.encode("utf-8"))
        if encoded_size > MAX_STREAM_PARAMS_BYTES:
            return StreamDelivery(
                params,
                receipt,
                f"stream params exceed {MAX_STREAM_PARAMS_BYTES} UTF-8 bytes",
            )
        return StreamDelivery(params, receipt)
