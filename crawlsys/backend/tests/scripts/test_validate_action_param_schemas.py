from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import validate_action_param_schemas as preflight


def _db_with_rows(rows):
    db = MagicMock()
    session = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def session_scope():
        yield session

    db.asession_scope = session_scope
    return db, session


@pytest.mark.asyncio
async def test_preflight_returns_only_sorted_invalid_ids_without_schema_values():
    db, session = _db_with_rows(
        [
            (1, '{"type":"object"}'),
            (2, '{"type":"broken"}'),
            (3, "not-json"),
            (4, None),
        ]
    )

    assert await preflight.find_invalid_action_schemas(db) == [2, 3]
    sql = str(session.execute.await_args.args[0])
    assert sql == (
        "SELECT ba_id, ba_params_schema FROM public.t_busi_action ORDER BY ba_id"
    )


@pytest.mark.asyncio
async def test_run_reports_count_only_when_all_schemas_are_valid(capsys):
    db, _session = _db_with_rows(
        [(1, '{"type":"object"}'), (2, None)]
    )

    exit_code = await preflight.run(db)

    assert exit_code == 0
    assert capsys.readouterr().out == "validated 2 action schemas\n"


@pytest.mark.asyncio
async def test_run_prints_only_sorted_invalid_ids(capsys):
    secret_schema = '{"type":"broken","secret":"do-not-print"}'
    db, _session = _db_with_rows([(9, secret_schema), (3, "not-json")])

    exit_code = await preflight.run(db)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == "ba_id=3\nba_id=9\n"
    assert secret_schema not in captured.out + captured.err


def test_main_builds_database_from_scheduler_config_and_closes_it(
    monkeypatch, capsys
):
    pg = SimpleNamespace(
        username="user",
        password="password",
        host="db",
        port=5432,
        database="crawler",
    )
    monkeypatch.setattr(
        preflight.SchedulerConfig,
        "from_toml",
        MagicMock(return_value=SimpleNamespace(postgresql=pg)),
    )
    db = MagicMock()
    db.aconnect = AsyncMock()
    db.aclose = AsyncMock()
    monkeypatch.setattr(preflight, "SQLAlchemyDB", MagicMock(return_value=db))
    monkeypatch.setattr(preflight, "run", AsyncMock(return_value=0))

    assert preflight.main(["--config", "custom.toml"]) == 0
    preflight.SchedulerConfig.from_toml.assert_called_once_with("custom.toml")
    preflight.SQLAlchemyDB.assert_called_once_with(
        username="user",
        password="password",
        host="db",
        port=5432,
        database="crawler",
        amode=True,
        driver="postgresql",
    )
    db.aconnect.assert_awaited_once()
    db.aclose.assert_awaited_once()
    assert "password" not in capsys.readouterr().err


def test_main_returns_two_without_leaking_database_error(monkeypatch, capsys):
    monkeypatch.setattr(
        preflight,
        "_run_from_config",
        AsyncMock(side_effect=RuntimeError("schema-secret database exploded")),
    )

    assert preflight.main([]) == 2
    captured = capsys.readouterr()
    assert "schema-secret" not in captured.out + captured.err
