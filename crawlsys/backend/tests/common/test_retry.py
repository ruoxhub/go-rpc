from datetime import datetime, timezone

import pytest

from common.backoff import RetryBudget, full_jitter_delay, retry_after_seconds


def test_full_jitter_uses_exponential_upper_bound() -> None:
    calls = []

    def uniform(lower: float, upper: float) -> float:
        calls.append((lower, upper))
        return upper

    assert full_jitter_delay(
        4, base_delay=0.5, max_delay=3, uniform=uniform
    ) == 3
    assert calls == [(0.0, 3)]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12", 12.0),
        ("-1", 0.0),
        ("Wed, 21 Oct 2015 07:28:10 GMT", 10.0),
        ("invalid", None),
    ],
)
def test_retry_after_supports_seconds_and_http_date(value, expected) -> None:
    now = datetime(2015, 10, 21, 7, 28, tzinfo=timezone.utc)
    assert retry_after_seconds({"Retry-After": value}, now=now) == expected


def test_retry_budget_caps_amplification_and_refills() -> None:
    budget = RetryBudget(ratio=0.2, capacity=1)
    assert budget.consume_retry() is True
    assert budget.consume_retry() is False
    for _ in range(5):
        budget.record_request()
    assert budget.consume_retry() is True
    assert budget.consume_retry() is False
