"""Runtime-only work item and crawler round result models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.sink_handlers import SinkResult
from core.stream_queue import StreamReceipt


@dataclass(slots=True)
class WorkItem:
    params: dict[str, Any]
    entity_id: str = ""
    receipt: StreamReceipt | None = field(default=None, repr=False)
    input_error: str | None = None


class ItemDisposition(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY = "retry"
    DEAD_LETTERED = "dead_lettered"


@dataclass(slots=True)
class ItemResult:
    sink: SinkResult = field(default_factory=SinkResult)


@dataclass(slots=True)
class SourceBatch:
    items: list[WorkItem]
    read: int = 0
    claimed: int = 0


@dataclass(slots=True)
class CrawlerRoundStats:
    read: int = 0
    claimed: int = 0
    acked: int = 0
    retried: int = 0
    dead_lettered: int = 0
    produced: int = 0
    deduplicated: int = 0
    skipped: int = 0
