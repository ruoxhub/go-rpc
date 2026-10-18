"""Per-platform concurrency and request-rate limiting."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.config import PlatformQuota


@dataclass(frozen=True)
class LimiterFeedbackSnapshot:
    cooldown_until: float
    effective_rps: float
    successes: int
    rate_limits: int
    blocks: int
    transient_failures: int


class PlatformLimiter:
    """Limit one platform independently from all other platforms."""

    def __init__(
        self,
        quota: PlatformQuota,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        feedback_window_size: int = 20,
    ):
        if feedback_window_size <= 0:
            raise ValueError("feedback_window_size must be positive")
        self.quota = quota
        self._clock = clock
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(max(1, quota.concurrency))
        self._timing_lock = asyncio.Lock()
        self._last_request_at: float | None = None
        self._cooldown_until = 0.0
        self._effective_rps = quota.rps
        self._minimum_rps = min(quota.rps, max(0.1, quota.rps * 0.1))
        self._feedback_window_size = feedback_window_size
        self._window_successes = 0
        self._window_transient_failures = 0
        self._successes = 0
        self._rate_limits = 0
        self._blocks = 0
        self._transient_failures = 0

    async def __aenter__(self) -> "PlatformLimiter":
        await self._semaphore.acquire()
        try:
            await self._wait_for_slot()
        except BaseException:
            self._semaphore.release()
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._semaphore.release()

    async def _wait_for_slot(self) -> None:
        async with self._timing_lock:
            while True:
                now = self._clock()
                ready_at = self._cooldown_until
                if self._effective_rps > 0 and self._last_request_at is not None:
                    ready_at = max(
                        ready_at,
                        self._last_request_at + 1.0 / self._effective_rps,
                    )
                delay = ready_at - now
                if delay <= 0:
                    if self._effective_rps > 0:
                        self._last_request_at = now
                    return
                await self._sleep(delay)

    def start_cooldown(self, seconds: float | None = None) -> None:
        """Expose an explicit boundary for callers that detect platform blocking."""
        duration = self.quota.cooldown_on_block if seconds is None else seconds
        self._cooldown_until = max(self._cooldown_until, self._clock() + max(0.0, duration))

    def record_success(self) -> None:
        self._successes += 1
        self._window_successes += 1
        self._evaluate_feedback_window()

    def record_rate_limit(self, retry_after: float | None = None) -> None:
        self._rate_limits += 1
        self._decrease_rate(0.5)
        self._reset_feedback_window()
        self.start_cooldown(retry_after)

    def record_block(self) -> None:
        self._blocks += 1
        self._decrease_rate(0.5)
        self._reset_feedback_window()
        self.start_cooldown()

    def record_transient_failure(self) -> None:
        self._transient_failures += 1
        self._window_transient_failures += 1
        self._evaluate_feedback_window()

    def _evaluate_feedback_window(self) -> None:
        requests = self._window_successes + self._window_transient_failures
        if requests < self._feedback_window_size:
            return
        error_rate = self._window_transient_failures / requests
        if error_rate >= 0.2:
            self._decrease_rate(0.8)
        elif self._effective_rps > 0:
            additive_step = max(0.1, self.quota.rps * 0.05)
            self._effective_rps = min(
                self.quota.rps, self._effective_rps + additive_step
            )
        self._reset_feedback_window()

    def _decrease_rate(self, factor: float) -> None:
        if self._effective_rps <= 0:
            return
        self._effective_rps = max(
            self._minimum_rps, self._effective_rps * factor
        )

    def _reset_feedback_window(self) -> None:
        self._window_successes = 0
        self._window_transient_failures = 0

    def feedback_snapshot(self) -> LimiterFeedbackSnapshot:
        return LimiterFeedbackSnapshot(
            cooldown_until=self._cooldown_until,
            effective_rps=self._effective_rps,
            successes=self._successes,
            rate_limits=self._rate_limits,
            blocks=self._blocks,
            transient_failures=self._transient_failures,
        )
