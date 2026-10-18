import pytest
from unittest.mock import AsyncMock, MagicMock

from scripts.migrate_add_task_loop_fields import run_migration


@pytest.mark.asyncio
async def test_run_migration_adds_loop_columns_idempotently():
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.asession_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db.asession_scope.return_value.__aexit__ = AsyncMock(return_value=None)

    await run_migration(mock_db)

    assert mock_session.execute.call_count == 3
    sql = [call.args[0].text for call in mock_session.execute.call_args_list]
    assert all("ADD COLUMN IF NOT EXISTS" in statement for statement in sql)
    loop_enabled_sql = next(statement for statement in sql if "loop_enabled" in statement)
    interval_sql = next(statement for statement in sql if "loop_interval_seconds" in statement)
    next_run_sql = next(statement for statement in sql if "next_run_at" in statement)

    assert "loop_enabled BOOLEAN NOT NULL DEFAULT FALSE" in loop_enabled_sql
    assert "NOT NULL" not in interval_sql
    assert "NOT NULL" not in next_run_sql
