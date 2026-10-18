from datetime import datetime

from models.task import BusTask, TaskStatus


def test_exec_status_values():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.RUNNING == "running"
    assert TaskStatus.PAUSED == "paused"
    assert TaskStatus.DONE == "done"
    assert TaskStatus.FAILED == "failed"


def test_exec_task_table_name():
    assert BusTask.__tablename__ == "t_crawl_task"


def test_exec_task_columns():
    col_names = {c.name for c in BusTask.__table__.columns}
    expected = {
        "task_id", "platform", "action", "status",
        "attempts", "error_msg", "last_run_at",
        "created_at", "updated_at",
    }
    assert expected.issubset(col_names)


def test_exec_task_has_unique_constraint():
    table = BusTask.__table__
    unique_cols = set()
    for constraint in table.constraints:
        if hasattr(constraint, "columns") and constraint.__class__.__name__ == "UniqueConstraint":
            unique_cols = {c.name for c in constraint.columns}
    assert unique_cols == {"platform", "action"}


def test_exec_task_default_values():
    task = BusTask(platform="bilibili", action="getFeedRcmd")
    assert task.status == "pending"
    assert task.attempts == 0
    assert task.error_msg is None
    assert task.last_run_at is None
