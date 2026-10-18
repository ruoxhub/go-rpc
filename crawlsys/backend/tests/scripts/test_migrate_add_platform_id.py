import pytest
from unittest.mock import AsyncMock, MagicMock
from scripts.migrate_add_platform_id import run_migration


@pytest.mark.asyncio
async def test_run_migration_executes_alter_and_update():
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.asession_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db.asession_scope.return_value.__aexit__ = AsyncMock(return_value=None)

    await run_migration(mock_db)

    assert mock_session.execute.call_count == 2
