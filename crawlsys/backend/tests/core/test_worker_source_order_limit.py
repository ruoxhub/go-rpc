"""Worker source query: order_by + limit."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.sql_safety import limit_clause, validate_order_by
from models.task_config import SourceConfig
from worker.sources import DatabaseWorkItemSource


def _mock_db_capturing_sql(rows):
    db_mock = MagicMock()
    session_mock = AsyncMock()

    @asynccontextmanager
    async def async_session_scope():
        yield session_mock

    db_mock.asession_scope = async_session_scope

    class _MappingRow(dict):
        pass

    mapping_rows = [_MappingRow(r) for r in rows]
    result_mock = MagicMock()
    result_mock.mappings.return_value.all.return_value = mapping_rows
    session_mock.execute = AsyncMock(return_value=result_mock)
    return db_mock, session_mock


def test_validate_order_by_accepts_column_and_direction():
    assert validate_order_by(["updated_time ASC", "id", "view_count desc"]) == [
        "updated_time ASC",
        "id",
        "view_count desc",
    ]


@pytest.mark.parametrize(
    "bad",
    [
        ["updated_time;drop"],
        ["now()"],
        ["a.b"],
        ["id ASC, title DESC"],
        ["id NULLS FIRST"],
        [""],
    ],
)
def test_validate_order_by_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        validate_order_by(bad)


def test_limit_clause_bounds():
    assert limit_clause(50) == 50
    assert limit_clause(1) == 1
    assert limit_clause(500) == 500
    with pytest.raises(ValueError):
        limit_clause(0)
    with pytest.raises(ValueError):
        limit_clause(501)


@pytest.mark.asyncio
async def test_query_source_emits_order_by_and_limit():
    db_mock, session_mock = _mock_db_capturing_sql(
        [{"content_id": "v1", "itemId": "v1"}]
    )

    source = SourceConfig(
        table="t_busi_content",
        key_column="content_id",
        param_map={"content_id": "itemId"},
        where="pub_time >= now() - interval '7 days' AND content_id IS NOT NULL",
        order_by=["updated_time ASC", "id ASC"],
        limit=50,
        filter_by_platform=True,
    )
    adapter = DatabaseWorkItemSource(db_mock, source, platform="tiktok")
    adapter._has_platform_column = AsyncMock(return_value=True)
    items = (await adapter.fetch()).items

    sql = str(session_mock.execute.call_args.args[0])
    assert "ORDER BY updated_time ASC, id ASC" in sql
    assert "LIMIT 50" in sql
    assert "platform = :platform" in sql
    assert "pub_time >= now() - interval '7 days'" in sql
    assert len(items) == 1
    assert items[0].params["itemId"] == "v1"
    assert items[0].entity_id == "v1"


@pytest.mark.asyncio
async def test_query_source_default_limit_without_order_by():
    db_mock, session_mock = _mock_db_capturing_sql([])

    source = SourceConfig(
        table="t_busi_search_keyword",
        key_column="id",
        param_map={"keyword": "q"},
    )
    adapter = DatabaseWorkItemSource(db_mock, source, platform="bilibili")
    adapter._has_platform_column = AsyncMock(return_value=True)
    await adapter.fetch()

    sql = str(session_mock.execute.call_args.args[0])
    assert "ORDER BY" not in sql
    assert "LIMIT 50" in sql


@pytest.mark.asyncio
async def test_query_source_custom_limit():
    db_mock, session_mock = _mock_db_capturing_sql([])

    source = SourceConfig(
        table="t_busi_content",
        key_column="content_id",
        param_map={"content_id": "itemId"},
        limit=10,
    )
    adapter = DatabaseWorkItemSource(db_mock, source, platform="tiktok")
    adapter._has_platform_column = AsyncMock(return_value=True)
    await adapter.fetch()
    sql = str(session_mock.execute.call_args.args[0])
    assert "LIMIT 10" in sql
