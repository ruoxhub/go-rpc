from datetime import datetime, timedelta, timezone

import pytest

from core.task_schedule import (
    ScheduleRule,
    cron_preview,
    next_schedule_at,
    retry_delay,
    validate_timezone,
)


UTC = timezone.utc


def test_cron_preview_uses_system_timezone_and_returns_utc():
    now = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)
    assert cron_preview("0 3 * * *", now=now, timezone_name="Asia/Shanghai", count=2) == [
        datetime(2026, 8, 9, 19, 0, tzinfo=UTC),
        datetime(2026, 8, 10, 19, 0, tzinfo=UTC),
    ]


def test_interval_is_fixed_delay():
    finished_at = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    rule = ScheduleRule(type="interval", interval_seconds=300)
    assert next_schedule_at(rule, now=finished_at, timezone_name="Asia/Shanghai") == finished_at + timedelta(
        seconds=300
    )


def test_retry_delay_is_capped():
    assert retry_delay(attempt=4, initial_seconds=60, multiplier=2, max_seconds=300) == timedelta(seconds=300)


def test_unknown_timezone_is_rejected():
    with pytest.raises(ValueError, match="未知时区"):
        validate_timezone("Mars/Olympus")


def test_cron_expression_must_have_five_fields():
    now = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="Cron 表达式必须包含 5 段"):
        cron_preview("0 3 * *", now=now, timezone_name="Asia/Shanghai")


def test_next_cron_expression_must_have_five_fields():
    now = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)
    rule = ScheduleRule(type="cron", cron_expression="0 0 3 * * *")
    with pytest.raises(ValueError, match="Cron 表达式必须包含 5 段"):
        next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai")


def test_cron_preview_count_must_be_positive():
    now = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="count"):
        cron_preview("0 3 * * *", now=now, timezone_name="Asia/Shanghai", count=0)


def test_interval_requires_positive_seconds():
    finished_at = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    rule = ScheduleRule(type="interval", interval_seconds=0)
    with pytest.raises(ValueError, match="正整数"):
        next_schedule_at(rule, now=finished_at, timezone_name="Asia/Shanghai")


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (ScheduleRule(type="once"), "run_at"),
        (ScheduleRule(type="cron"), "cron_expression"),
    ],
)
def test_schedule_requires_mode_specific_value(rule, message):
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match=message):
        next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai")


def test_start_at_must_not_exceed_end_at():
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    rule = ScheduleRule(
        type="interval",
        interval_seconds=60,
        start_at=datetime(2026, 8, 11, tzinfo=UTC),
        end_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="start_at"):
        next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai")


def test_manual_returns_none():
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    rule = ScheduleRule(type="manual")
    assert next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai") is None


def test_once_returns_future_run_at_within_window():
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    run_at = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)
    rule = ScheduleRule(
        type="once",
        run_at=run_at,
        start_at=datetime(2026, 8, 10, 0, 0, tzinfo=UTC),
        end_at=datetime(2026, 8, 11, 0, 0, tzinfo=UTC),
    )
    assert next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai") == run_at


def test_once_returns_none_when_expired():
    now = datetime(2026, 8, 10, 6, 0, tzinfo=UTC)
    rule = ScheduleRule(type="once", run_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC))
    assert next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai") is None


def test_cron_next_is_strictly_after_now():
    now = datetime(2026, 8, 9, 19, 0, tzinfo=UTC)  # exactly 03:00 Asia/Shanghai
    rule = ScheduleRule(type="cron", cron_expression="0 3 * * *")
    assert next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai") == datetime(
        2026, 8, 10, 19, 0, tzinfo=UTC
    )


def test_schedule_outside_end_at_returns_none():
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    rule = ScheduleRule(
        type="interval",
        interval_seconds=300,
        end_at=datetime(2026, 8, 10, 1, 2, tzinfo=UTC),
    )
    assert next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai") is None


def test_cron_uses_future_start_boundary_as_search_origin():
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    start_at = datetime(2026, 8, 12, 19, 0, tzinfo=UTC)
    rule = ScheduleRule(
        type="cron",
        cron_expression="0 3 * * *",
        start_at=start_at,
    )
    assert next_schedule_at(rule, now=now, timezone_name="Asia/Shanghai") == start_at


def test_schedule_rejects_naive_now():
    with pytest.raises(ValueError, match="now 必须包含时区"):
        next_schedule_at(
            ScheduleRule(type="interval", interval_seconds=60),
            now=datetime(2026, 8, 10, 1, 0),
            timezone_name="Asia/Shanghai",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempt": 0, "initial_seconds": 60, "multiplier": 2, "max_seconds": 300},
        {"attempt": 1, "initial_seconds": 0, "multiplier": 2, "max_seconds": 300},
        {"attempt": 1, "initial_seconds": 60, "multiplier": 0.5, "max_seconds": 300},
        {"attempt": 1, "initial_seconds": 60, "multiplier": 2, "max_seconds": 0},
    ],
)
def test_retry_delay_rejects_invalid_policy(kwargs):
    with pytest.raises(ValueError):
        retry_delay(**kwargs)


def test_cron_preview_handles_america_new_york_dst_spring_forward():
    # 2026-03-08 02:00 local does not exist (spring forward). 0 2 * * * next after
    # 2026-03-07 12:00 UTC should still produce valid UTC instants.
    now = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
    previews = cron_preview("0 2 * * *", now=now, timezone_name="America/New_York", count=3)
    assert len(previews) == 3
    assert all(dt.tzinfo is UTC or dt.tzinfo == UTC for dt in previews)
    assert previews[0] == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)  # 02:00 EST = 07:00 UTC
    # After spring forward (2026-03-08 02:00 -> 03:00), 02:00 EDT = 06:00 UTC
    assert previews[1] == datetime(2026, 3, 9, 6, 0, tzinfo=UTC)
    assert previews[2] == datetime(2026, 3, 10, 6, 0, tzinfo=UTC)
