from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.migrate_add_task_priority import MIGRATION_STATEMENTS, run_migration


@pytest.mark.asyncio
async def test_run_migration_executes_every_statement():
    db = MagicMock()
    session = SimpleNamespace(execute=AsyncMock())
    db.asession_scope.return_value.__aenter__.return_value = session

    await run_migration(db)

    assert session.execute.await_count == len(MIGRATION_STATEMENTS)


def test_priority_migration_is_idempotent_and_constrained():
    combined = "\n".join(MIGRATION_STATEMENTS)
    assert "ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 2" in combined
    assert "ck_task_priority_range" in combined
    assert "priority BETWEEN 0 AND 4" in combined
    assert "IF NOT EXISTS" in combined
    assert "DROP" not in combined.upper()
    assert "UPDATE public.t_crawl_task SET priority" not in combined
