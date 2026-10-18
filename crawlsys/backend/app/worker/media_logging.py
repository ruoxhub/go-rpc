"""媒体 Worker 的安全结构化日志边界。"""
from __future__ import annotations

from typing import Any

from common.errors import format_error


MEDIA_LOG_FIELDS = (
    "task_id",
    "consumer_key",
    "platform",
    "content_id",
    "batch_id",
    "claim_token_prefix",
    "attempt_count",
    "outcome",
    "latency_ms",
    "exception_type",
)

_MESSAGES = {
    "success": "media event succeeded",
    "skipped": "media event skipped",
}


def log_media_event(
    logger: Any,
    level: int | str,
    *,
    task_id: int | None = None,
    consumer_key: str | None = None,
    platform: str | None = None,
    content_id: str | None = None,
    batch_id: str | None = None,
    claim_token_prefix: str | None = None,
    attempt_count: int | None = None,
    outcome: str,
    latency_ms: int | None = None,
    exception_type: str | None = None,
    error: BaseException | None = None,
) -> None:
    """Emit one media event without accepting arbitrary structured context."""
    if outcome == "failed":
        if error is None:
            raise ValueError("failed media event requires error")
        message = format_error(error, max_length=500)
    else:
        try:
            message = _MESSAGES[outcome]
        except KeyError as exc:
            raise ValueError(f"unsupported media outcome: {outcome}") from exc

    fields = {
        "task_id": task_id,
        "consumer_key": consumer_key,
        "platform": platform,
        "content_id": content_id,
        "batch_id": batch_id,
        "claim_token_prefix": claim_token_prefix,
        "attempt_count": attempt_count,
        "outcome": outcome,
        "latency_ms": latency_ms,
        "exception_type": exception_type,
    }
    if hasattr(logger, "bind"):
        logger.bind(**fields).log(level, message)
    else:
        logger.log(level, message, extra=fields)
