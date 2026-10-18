"""Shared retry timing helpers."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping


def full_jitter_delay(
    attempt: int,
    *,
    base_delay: float,
    max_delay: float,
    uniform: Callable[[float, float], float] = random.uniform,
) -> float:
    """Return a full-jitter exponential backoff delay."""
    upper_bound = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    return uniform(0.0, upper_bound)


def retry_after_seconds(
    headers: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse Retry-After delta-seconds or HTTP-date into a non-negative delay."""
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    value = raw.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (target - current).total_seconds())


class RetryBudget:
    """Small process-local token budget that caps retry amplification."""

    def __init__(self, ratio: float, capacity: float) -> None:
        if not 0 <= ratio <= 1:
            raise ValueError("retry budget ratio must be between 0 and 1")
        self._ratio = ratio
        self._capacity = max(0.0, capacity)
        self._credits = self._capacity

    def record_request(self) -> None:
        self._credits = min(self._capacity, self._credits + self._ratio)

    def consume_retry(self) -> bool:
        if self._credits < 1.0:
            return False
        self._credits -= 1.0
        return True
