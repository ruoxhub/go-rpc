"""Smoke test: DatabaseWorkItemSource with the keyword table.

Spec (2026-06-30-search-keyword-driven-design) dictates ZERO changes to
The keyword table naturally flows through DatabaseWorkItemSource
because the table has a `platform` column which aligns with the hardcoded
WHERE platform = :platform clause.

This test documents the expected behavior by mocking the DB session to
return keyword rows and asserting the resulting WorkItems.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from models.task_config import SourceConfig
from worker.sources import DatabaseWorkItemSource


def _mock_db_with_rows(rows):
    """构造一个 session.execute 返回指定 rows (list[dict]) 的 db mock。"""
    db_mock = MagicMock()
    session_mock = AsyncMock()

    @asynccontextmanager
    async def async_session_scope():
        yield session_mock

    db_mock.asession_scope = async_session_scope

    class _MappingRow(dict):
        """dict-like 但 .mappings().all() 返回自身列表。"""

    mapping_rows = [_MappingRow(r) for r in rows]

    result_mock = MagicMock()
    result_mock.mappings.return_value.all.return_value = mapping_rows
    session_mock.execute = AsyncMock(return_value=result_mock)
    return db_mock


@pytest.mark.asyncio
async def test_query_source_keyword_table_produces_workitems():
    """ref_table='t_busi_search_keyword' + param_map={'keyword':'q'}
    → 3 rows → 3 WorkItem, params = {'q': <keyword>}, entity_id = str(id)."""
    db = _mock_db_with_rows([
        {"id": 1, "q": "AI"},
        {"id": 2, "q": "LLM"},
        {"id": 3, "q": "RAG"},
    ])

    source = SourceConfig(
        table="t_busi_search_keyword",
        key_column="id",
        param_map={"keyword": "q"},
    )
    items = (await DatabaseWorkItemSource(db, source, platform="bilibili").fetch()).items

    assert len(items) == 3
    assert items[0].params == {"q": "AI", "id": "1"}
    assert items[0].entity_id == "1"
    assert items[1].params == {"q": "LLM", "id": "2"}
    assert items[2].params == {"q": "RAG", "id": "3"}


@pytest.mark.asyncio
async def test_query_source_keyword_table_empty():
    """平台下没有关键词 → 返回空列表，任务会被置 DONE（由 execute 处理）。"""
    db = _mock_db_with_rows([])

    source = SourceConfig(
        table="t_busi_search_keyword",
        key_column="id",
        param_map={"keyword": "keyword"},
    )
    items = (await DatabaseWorkItemSource(db, source, platform="bilibili").fetch()).items

    assert items == []


@pytest.mark.asyncio
async def test_query_source_keyword_table_default_param_name():
    """用户不覆盖参数名 → params = {'keyword': <value>}。"""
    db = _mock_db_with_rows([{"id": 10, "keyword": "搜索词"}])

    source = SourceConfig(
        table="t_busi_search_keyword",
        key_column="id",
        param_map={"keyword": "keyword"},
    )
    items = (await DatabaseWorkItemSource(db, source, platform="bilibili").fetch()).items

    assert items[0].params == {"keyword": "搜索词", "id": "10"}
    assert items[0].entity_id == "10"


@pytest.mark.asyncio
async def test_query_source_skips_platform_filter_when_column_absent():
    """平台专属表（如 tk_challenge）无 platform 列 → 不追加 platform 过滤，仍能取数。

    回归测试：此前 _query_source 无条件追加 `WHERE platform = :platform`，
    对无该列的 tk_challenge 会报 UndefinedColumnError。
    """
    db_mock = MagicMock()
    session_mock = AsyncMock()

    @asynccontextmanager
    async def async_session_scope():
        yield session_mock

    db_mock.asession_scope = async_session_scope
    result_mock = MagicMock()
    result_mock.mappings.return_value.all.return_value = [
        {"challenge_id": "870345", "challengeID": "870345"},
    ]
    session_mock.execute = AsyncMock(return_value=result_mock)

    source = SourceConfig(
        table="tk_challenge",
        key_column="challenge_id",
        param_map={"challenge_id": "challengeID"},
    )
    adapter = DatabaseWorkItemSource(db_mock, source, platform="bilibili")
    adapter._has_platform_column = AsyncMock(return_value=False)
    items = (await adapter.fetch()).items

    assert len(items) == 1
    assert items[0].params == {"challengeID": "870345", "challenge_id": "870345"}
    assert items[0].entity_id == "870345"
    # 列探测已被 mock 跳过，故 session.execute 仅被主查询调用一次；
    # 其 SQL 文本不应包含 platform 过滤条件。
    executed_sql = str(session_mock.execute.call_args.args[0])
    assert "platform" not in executed_sql
