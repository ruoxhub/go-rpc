import pytest
from unittest.mock import AsyncMock, MagicMock

from scripts.migrate_expand_task_schedule import MIGRATION_STATEMENTS, run_migration


@pytest.mark.asyncio
async def test_run_migration_executes_every_statement():
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.asession_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db.asession_scope.return_value.__aexit__ = AsyncMock(return_value=None)

    await run_migration(mock_db)

    assert mock_session.execute.call_count == len(MIGRATION_STATEMENTS)
    sql = [call.args[0].text for call in mock_session.execute.call_args_list]
    assert sql == MIGRATION_STATEMENTS


def test_migration_adds_schedule_columns_idempotently():
    schedule_sql = next(s for s in MIGRATION_STATEMENTS if "ADD COLUMN IF NOT EXISTS schedule_type" in s)
    assert "VARCHAR(20) NOT NULL DEFAULT 'manual'" in schedule_sql
    for column in (
        "cron_expression",
        "run_once_at",
        "schedule_start_at",
        "schedule_end_at",
        "max_runs",
        "run_count",
        "last_run_status",
    ):
        assert any(f"ADD COLUMN IF NOT EXISTS {column}" in s for s in MIGRATION_STATEMENTS), column


def test_migration_adds_retry_columns_idempotently():
    for column in (
        "retry_max_attempts",
        "retry_delay_seconds",
        "retry_backoff_multiplier",
        "retry_max_delay_seconds",
        "retry_count",
        "next_retry_at",
    ):
        assert any(f"ADD COLUMN IF NOT EXISTS {column}" in s for s in MIGRATION_STATEMENTS), column


def test_migration_adds_trigger_and_pause_columns():
    for column in ("run_now_requested_at", "pause_requested", "active_trigger", "active_scheduled_at"):
        assert any(f"ADD COLUMN IF NOT EXISTS {column}" in s for s in MIGRATION_STATEMENTS), column


def test_migration_adds_log_columns_idempotently():
    for column in ("btl_active_trigger", "btl_active_scheduled_at", "btl_retry_count"):
        assert any(f"ADD COLUMN IF NOT EXISTS {column}" in s for s in MIGRATION_STATEMENTS), column


def test_migration_adds_enum_check_constraints():
    assert any("ck_task_schedule_type" in s and "IF NOT EXISTS" in s for s in MIGRATION_STATEMENTS)
    assert any("ck_task_last_run_status" in s and "IF NOT EXISTS" in s for s in MIGRATION_STATEMENTS)
    assert any("ck_task_active_trigger" in s and "IF NOT EXISTS" in s for s in MIGRATION_STATEMENTS)
    assert any("ck_task_log_active_trigger" in s and "IF NOT EXISTS" in s for s in MIGRATION_STATEMENTS)


def test_migration_uses_postgresql_supported_idempotent_constraint_sql():
    constraint_sql = [statement for statement in MIGRATION_STATEMENTS if "ADD CONSTRAINT" in statement]
    assert constraint_sql
    assert all("ADD CONSTRAINT IF NOT EXISTS" not in statement for statement in constraint_sql)


def test_migration_adds_non_negative_and_backoff_constraints():
    for constraint in (
        "ck_task_run_count_non_negative",
        "ck_task_retry_count_non_negative",
        "ck_task_retry_max_attempts_non_negative",
        "ck_task_retry_backoff_multiplier_ge_1",
        "ck_task_log_retry_count_non_negative",
    ):
        assert any(constraint in s and "IF NOT EXISTS" in s for s in MIGRATION_STATEMENTS), constraint


def test_migration_backfills_legacy_loop_tasks_to_interval():
    interval_sql = next(s for s in MIGRATION_STATEMENTS if "loop_enabled = TRUE" in s)
    assert "schedule_type = 'interval'" in interval_sql
    # 其他旧任务（loop_enabled=false/缺省）由列默认 'manual' 承担
    schedule_sql = next(s for s in MIGRATION_STATEMENTS if "ADD COLUMN IF NOT EXISTS schedule_type" in s)
    assert "DEFAULT 'manual'" in schedule_sql


def test_migration_creates_due_index():
    assert any("CREATE INDEX IF NOT EXISTS idx_task_due" in s for s in MIGRATION_STATEMENTS)


@pytest.mark.parametrize("statement", MIGRATION_STATEMENTS)
def test_migration_ddl_is_idempotent(statement):
    if statement.startswith("UPDATE"):
        return
    assert "IF NOT EXISTS" in statement, statement
