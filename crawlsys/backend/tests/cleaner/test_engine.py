from datetime import datetime, timedelta, timezone

import pytest

from cleaner.engine import Grade, GradeRule, PlatformThresholds, grade


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
THRESHOLDS = PlatformThresholds(
    p1=[GradeRule(24, 8000), GradeRule(72, 50000)],
    p2=[GradeRule(24, 5000)],
    p3=[GradeRule(168, 80000)],
)


@pytest.mark.parametrize(
    ("hours", "views", "expected"),
    [
        (24, 8000, Grade.P1),
        (24, 7999, Grade.P2),
        (72, 50000, Grade.P1),
        (72, 80000, Grade.P1),
        (24, 5000, Grade.P2),
        (24, 4999, Grade.UNRATED),
        (168, 80000, Grade.P3),
        (168.01, 80000, Grade.UNRATED),
        (73, 80000, Grade.P3),
        (12, 0, Grade.UNRATED),
    ],
)
def test_grade_boundaries_and_waterfall_precedence(hours, views, expected):
    result = grade(
        pub_time=NOW - timedelta(hours=hours),
        view_count=views,
        thresholds=THRESHOLDS,
        now=NOW,
    )

    assert result.grade is expected
    assert result.hours == pytest.approx(hours)


def test_p1_precedes_p3_when_both_match():
    result = grade(
        pub_time=NOW - timedelta(hours=48),
        view_count=80000,
        thresholds=THRESHOLDS,
        now=NOW,
    )

    assert result.grade is Grade.P1
    assert result.reason.startswith("P1:")


def test_missing_pub_time_requires_manual_review():
    result = grade(None, 100000, THRESHOLDS, now=NOW)

    assert result.grade is Grade.MANUAL_REVIEW
    assert result.hours is None
    assert result.reason == "pub_time 缺失"


def test_future_pub_time_requires_manual_review():
    result = grade(
        NOW + timedelta(minutes=1),
        100000,
        THRESHOLDS,
        now=NOW,
    )

    assert result.grade is Grade.MANUAL_REVIEW
    assert result.hours < 0
    assert "未来时间" in result.reason


def test_naive_pub_time_is_interpreted_as_utc():
    result = grade(
        datetime(2026, 7, 27, 7, 0),
        8000,
        THRESHOLDS,
        now=NOW,
    )

    assert result.grade is Grade.P1
    assert result.hours == pytest.approx(1.0)


def test_naive_now_is_interpreted_as_utc():
    result = grade(
        datetime(2026, 7, 27, 7, 0),
        8000,
        THRESHOLDS,
        now=datetime(2026, 7, 27, 8, 0),
    )

    assert result.hours == pytest.approx(1.0)


@pytest.mark.parametrize("delta_seconds", [-119, 0, 119])
def test_pub_time_near_download_time_requires_manual_review(delta_seconds):
    pub_time = NOW - timedelta(hours=1)
    result = grade(
        pub_time=pub_time,
        view_count=100000,
        thresholds=THRESHOLDS,
        now=NOW,
        download_time=pub_time + timedelta(seconds=delta_seconds),
        suspect_seconds=120,
    )

    assert result.grade is Grade.MANUAL_REVIEW
    assert "pub_time≈download_time" in result.reason


def test_suspicious_boundary_is_exclusive():
    pub_time = NOW - timedelta(hours=1)
    result = grade(
        pub_time=pub_time,
        view_count=8000,
        thresholds=THRESHOLDS,
        now=NOW,
        download_time=pub_time + timedelta(seconds=120),
        suspect_seconds=120,
    )

    assert result.grade is Grade.P1


@pytest.mark.parametrize("views", [None, -1])
def test_missing_or_negative_views_are_unrated(views):
    result = grade(
        pub_time=NOW - timedelta(hours=1),
        view_count=views,
        thresholds=THRESHOLDS,
        now=NOW,
    )

    assert result.grade is Grade.UNRATED
    assert result.reason == "view_count 缺失/非法"
