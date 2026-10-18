"""任务调度纯函数模块。

提供统一时区校验、Cron 预览、四种调度模式（manual/once/interval/cron）
的下一运行时间计算，以及任务级指数退避重试延迟计算。
所有函数均为无副作用纯函数，供 API、Worker 与系统设置更新共用。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

ScheduleType = Literal["manual", "once", "interval", "cron"]
UTC = timezone.utc

#: 调度规则，字段语义与 TaskSchedule API 模型保持一致。
@dataclass(frozen=True)
class ScheduleRule:
    type: ScheduleType
    interval_seconds: int | None = None
    cron_expression: str | None = None
    run_at: datetime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    max_runs: int | None = None


def validate_timezone(name: str) -> ZoneInfo:
    """校验 IANA 时区名并返回 ZoneInfo；未知时区抛出 ValueError。"""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区: {name}") from exc


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必须包含时区")


def _validate_cron(expression: str) -> None:
    if len(expression.split()) != 5:
        raise ValueError("Cron 表达式必须包含 5 段")


def cron_preview(expression: str, *, now: datetime, timezone_name: str, count: int = 5) -> list[datetime]:
    """按系统时区计算 count 个未来 Cron 触发点，返回 UTC 时刻。

    expression 必须为标准五段 Cron 表达式，最小粒度一分钟。
    """
    _require_aware(now, "now")
    _validate_cron(expression)
    if count <= 0:
        raise ValueError(f"count 必须是正整数: {count}")
    local_now = now.astimezone(validate_timezone(timezone_name))
    iterator = croniter(expression, local_now)
    return [iterator.get_next(datetime).astimezone(UTC) for _ in range(count)]


def retry_delay(*, attempt: int, initial_seconds: int, multiplier: float, max_seconds: int) -> timedelta:
    """指数退避重试延迟，capped 到 max_seconds；attempt 从 1 起。"""
    if attempt < 1:
        raise ValueError("attempt 必须大于等于 1")
    if initial_seconds <= 0:
        raise ValueError("initial_seconds 必须是正数")
    if multiplier < 1:
        raise ValueError("multiplier 不能小于 1")
    if max_seconds <= 0:
        raise ValueError("max_seconds 必须是正数")
    seconds = min(initial_seconds * multiplier ** max(0, attempt - 1), max_seconds)
    return timedelta(seconds=seconds)


def next_schedule_at(rule: ScheduleRule, *, now: datetime, timezone_name: str) -> datetime | None:
    """计算规则的下一次运行时刻（UTC）；无下一次触发时返回 None。

    - manual: 永不自动触发，返回 None。
    - once: 尚未过期且在 [start_at, end_at] 窗口内的 run_at。
    - interval: fixed-delay，本轮结束后才计算下一间隔（now + interval）。
    - cron: 严格晚于 now 的下一触发点（按系统时区），受起止窗口约束。
    """
    _require_aware(now, "now")
    for name, value in (("run_at", rule.run_at), ("start_at", rule.start_at), ("end_at", rule.end_at)):
        if value is not None:
            _require_aware(value, name)

    if rule.start_at is not None and rule.end_at is not None and rule.start_at > rule.end_at:
        raise ValueError("start_at 不能晚于 end_at")

    if rule.type == "manual":
        return None

    if rule.type == "interval":
        if rule.interval_seconds is None or rule.interval_seconds <= 0:
            raise ValueError(f"interval_seconds 必须是正整数: {rule.interval_seconds}")
        nxt = now + timedelta(seconds=rule.interval_seconds)
        if rule.start_at is not None and nxt < rule.start_at:
            nxt = rule.start_at
        if rule.end_at is not None and nxt > rule.end_at:
            return None
        return nxt

    if rule.type == "once":
        if rule.run_at is None:
            raise ValueError("once 调度必须设置 run_at")
        if rule.run_at <= now:
            return None
        if rule.start_at is not None and rule.run_at < rule.start_at:
            return None
        if rule.end_at is not None and rule.run_at > rule.end_at:
            return None
        return rule.run_at

    if rule.type == "cron":
        if rule.cron_expression is None:
            raise ValueError("cron 调度必须设置 cron_expression")
        _validate_cron(rule.cron_expression)
        search_from = now
        if rule.start_at is not None and rule.start_at > now:
            search_from = rule.start_at - timedelta(microseconds=1)
        local_search_from = search_from.astimezone(validate_timezone(timezone_name))
        iterator = croniter(rule.cron_expression, local_search_from)
        nxt = iterator.get_next(datetime).astimezone(UTC)
        if rule.end_at is not None and nxt > rule.end_at:
            return None
        return nxt

    raise ValueError(f"未知调度类型: {rule.type}")
