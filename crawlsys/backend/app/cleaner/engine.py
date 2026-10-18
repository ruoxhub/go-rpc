"""Pure grading rules for candidate video materials."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum


class Grade(IntEnum):
    P1 = 1
    P2 = 2
    P3 = 3
    UNRATED = 0
    MANUAL_REVIEW = -1


@dataclass(frozen=True)
class GradeRule:
    max_hours: float
    min_views: int


@dataclass(frozen=True)
class PlatformThresholds:
    p1: list[GradeRule]
    p2: list[GradeRule]
    p3: list[GradeRule]


@dataclass(frozen=True)
class GradeResult:
    grade: Grade
    reason: str
    hours: float | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def grade(
    pub_time: datetime | None,
    view_count: int | None,
    thresholds: PlatformThresholds,
    now: datetime | None = None,
    download_time: datetime | None = None,
    suspect_seconds: float = 120.0,
) -> GradeResult:
    """Grade one candidate using P1 -> P2 -> P3 waterfall semantics."""
    current = _as_utc(now or datetime.now(timezone.utc))

    if pub_time is None:
        return GradeResult(Grade.MANUAL_REVIEW, "pub_time 缺失", None)

    published = _as_utc(pub_time)
    hours = (current - published).total_seconds() / 3600.0
    if hours < 0:
        return GradeResult(
            Grade.MANUAL_REVIEW,
            f"pub_time 未来时间(hours={hours:.1f})",
            hours,
        )

    if download_time is not None:
        reference = _as_utc(download_time)
        if abs((published - reference).total_seconds()) < suspect_seconds:
            return GradeResult(
                Grade.MANUAL_REVIEW,
                f"pub_time≈download_time(Δ<{suspect_seconds}s)，疑似缺 createTime",
                hours,
            )

    if view_count is None or view_count < 0:
        return GradeResult(Grade.UNRATED, "view_count 缺失/非法", hours)

    for grade_value, rules in (
        (Grade.P1, thresholds.p1),
        (Grade.P2, thresholds.p2),
        (Grade.P3, thresholds.p3),
    ):
        for rule in rules:
            if hours <= rule.max_hours and view_count >= rule.min_views:
                return GradeResult(
                    grade_value,
                    f"{grade_value.name}: ≤{rule.max_hours}h & ≥{rule.min_views} plays",
                    hours,
                )

    return GradeResult(Grade.UNRATED, "未命中任何规则", hours)
