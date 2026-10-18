from datetime import datetime, timedelta

import pytest

from models.task import (
    BusTask,
    BusTaskLog,
    InvalidTaskTransitionError,
    TaskPriority,
    TaskRunStatus,
    TaskScheduleType,
    TaskStatus,
    TaskTrigger,
)
from models.task_config import TaskConfig


def test_bus_task_default_status():
    t = BusTask(platform="bilibili", action="getUserInfo")
    assert t.status == TaskStatus.PENDING.value
    assert t.attempts == 0


@pytest.mark.parametrize(
    ("priority", "db_value"),
    [
        (TaskPriority.LOWEST, 0),
        (TaskPriority.LOW, 1),
        (TaskPriority.NORMAL, 2),
        (TaskPriority.HIGH, 3),
        (TaskPriority.URGENT, 4),
    ],
)
def test_task_priority_maps_to_stable_db_values(priority, db_value):
    assert priority.db_value == db_value
    assert TaskPriority.from_db_value(db_value) is priority
    assert BusTask(
        platform="test",
        action=f"search-{db_value}",
        priority=priority,
    ).priority == db_value


def test_bus_task_defaults_to_normal_priority():
    assert BusTask(platform="test", action="search").priority == 2


@pytest.mark.parametrize("value", [True, False, -1, 5, "urgent", None])
def test_bus_task_rejects_invalid_priority_storage_values(value):
    with pytest.raises(ValueError, match="priority"):
        BusTask(platform="test", action="search", priority=value)


def test_bus_task_loop_defaults():
    t = BusTask(platform="bilibili", action="getUserInfo")
    assert t.loop_enabled is False
    assert t.loop_interval_seconds is None
    assert t.next_run_at is None


def test_bus_task_repr():
    t = BusTask(platform="bilibili", action="getUserInfo", status="pending")
    assert "bilibili/getUserInfo" in repr(t)


def test_bus_task_config_accepts_pydantic():
    cfg = TaskConfig.model_validate({
        "source": {"table": "t_user", "key_column": "user_id"},
    })
    t = BusTask(platform="bilibili", action="getUserInfo", config=cfg)
    assert t.config.source.table == "t_user"


def test_bus_task_no_legacy_aliases():
    """旧别名必须全部删除, 防止新老代码混用。"""
    for attr in ("ref_table", "ref_where", "params_columns", "entity_column",
                 "find_work", "result_column", "post_update_column", "post_update_table",
                 "fw_ref_table", "fw_ref_where", "fw_params_columns", "fw_entity_column"):
        assert not hasattr(BusTask, attr), f"legacy alias {attr!r} must be removed"


def test_bus_task_has_platform_id_column():
    t = BusTask(platform="p", action="a")
    assert hasattr(t, "platform_id")
    assert t.platform_id is None


def test_bus_task_platform_id_accepts_int():
    t = BusTask(platform="p", action="a", platform_id=42)
    assert t.platform_id == 42


def test_bus_task_normalizes_identity_fields():
    task = BusTask(platform=" bilibili ", action=" getUserInfo ")

    assert task.platform == "bilibili"
    assert task.action == "getUserInfo"


@pytest.mark.parametrize("field", ["platform", "action"])
def test_bus_task_rejects_blank_identity_fields(field):
    with pytest.raises(ValueError, match="不能为空"):
        BusTask(**{field: " ", "action" if field == "platform" else "platform": "valid"})


def test_bus_task_transition_updates_lifecycle_fields():
    now = datetime(2026, 8, 5, 12, 0, 0)
    task = BusTask(platform="bilibili", action="getUserInfo", error_msg="old error")

    task.transition_to(TaskStatus.RUNNING, at=now)

    assert task.status == TaskStatus.RUNNING.value
    assert task.last_run_at == now
    assert task.error_msg is None


def test_bus_task_rejects_invalid_transition():
    task = BusTask(platform="bilibili", action="getUserInfo", status=TaskStatus.DONE)

    with pytest.raises(InvalidTaskTransitionError):
        task.transition_to(TaskStatus.RUNNING)


def test_bus_task_is_ready_respects_status_and_schedule():
    now = datetime(2026, 8, 5, 12, 0, 0)
    task = BusTask(
        platform="bilibili",
        action="getUserInfo",
        next_run_at=now - timedelta(seconds=1),
    )

    assert task.is_ready(at=now) is True
    task.status = TaskStatus.PAUSED
    assert task.is_ready(at=now) is False


def test_new_task_schedule_defaults_preserve_legacy_one_shot():
    task = BusTask(platform="tiktok", action="search")
    assert task.schedule_type == TaskScheduleType.MANUAL.value
    assert task.run_count == 0
    assert task.retry_count == 0
    assert task.retry_max_attempts == 0
    assert task.retry_delay_seconds == 60
    assert task.retry_backoff_multiplier == 2
    assert task.retry_max_delay_seconds == 3600
    assert task.pause_requested is False
    assert task.next_retry_at is None
    assert task.run_now_requested_at is None


@pytest.mark.parametrize("field", ["run_count", "retry_count", "retry_max_attempts"])
def test_task_rejects_negative_counts(field):
    with pytest.raises(ValueError, match="不能小于 0"):
        BusTask(platform="p", action="a", **{field: -1})


@pytest.mark.parametrize("value", ["daily", "weekly"])
def test_task_rejects_unknown_schedule_type(value):
    with pytest.raises(ValueError, match="未知调度类型"):
        BusTask(platform="p", action="a", schedule_type=value)


def test_task_rejects_unknown_run_status():
    with pytest.raises(ValueError, match="未知运行状态"):
        BusTask(platform="p", action="a", last_run_status="crashed")


def test_task_rejects_unknown_active_trigger():
    with pytest.raises(ValueError, match="未知触发来源"):
        BusTask(platform="p", action="a", active_trigger="clicked")


def test_task_rejects_low_backoff_multiplier():
    with pytest.raises(ValueError, match="retry_backoff_multiplier 不能小于 1"):
        BusTask(platform="p", action="a", retry_backoff_multiplier=0.5)


def test_task_schedule_enums_documented():
    assert TaskScheduleType.CRON.value == "cron"
    assert TaskRunStatus.FAILED.value == "failed"
    assert TaskTrigger.COALESCED.value == "coalesced"


def test_task_log_schema_constrains_schedule_observability_fields():
    constraints = {constraint.name for constraint in BusTaskLog.__table__.constraints}
    assert "ck_task_log_active_trigger" in constraints
    assert "ck_task_log_retry_count_non_negative" in constraints
