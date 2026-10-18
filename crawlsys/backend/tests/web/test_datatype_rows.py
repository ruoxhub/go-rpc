"""Tests for datatype row CRUD service and JSON API routes."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.crawler import datatype_rows as row_routes
from api.main import _datatype_data_error_handler
from models.follow import Follow
from services.datatype_data.errors import DatatypeDataError
from services.datatype_data.service import (
    DatatypeDataService,
    _coerce_value,
    parse_filters,
    parse_primary_key,
)


# ============== 纯函数：强制转换与解析 ==============

def test_parse_filters_rejects_malformed_input():
    assert parse_filters(None) == []
    assert parse_filters("  ") == []
    assert parse_filters('[{"field":"platform","operator":"eq","value":"x"}]') == [
        {"field": "platform", "operator": "eq", "value": "x"}
    ]
    with pytest.raises(DatatypeDataError) as raw:
        parse_filters("not json")
    assert raw.value.code == "invalid_filters"
    with pytest.raises(DatatypeDataError):
        parse_filters('{"field":"a"}')
    with pytest.raises(DatatypeDataError):
        parse_filters('[{"field":"a","operator":"drop_table"}]')


def test_parse_primary_key_requires_object():
    assert parse_primary_key('{"id": 1}') == {"id": 1}
    for raw in ("", "[]", "{}", "nope"):
        with pytest.raises(DatatypeDataError):
            parse_primary_key(raw)


def test_coerce_value_enforces_type_and_length():
    table = Follow.__table__
    service = DatatypeDataService(MagicMock())
    ctx = service.context("follow")
    user_id = ctx.column("user_id")
    follow_name = ctx.column("follow_name")
    assert user_id is not None and follow_name is not None

    assert _coerce_value(user_id, "abc") == "abc"
    assert _coerce_value(user_id, None) is None
    with pytest.raises(DatatypeDataError) as oversized:
        _coerce_value(user_id, "x" * 65)
    assert oversized.value.code == "invalid_field_value"
    assert oversized.value.status_code == 422
    with pytest.raises(DatatypeDataError):
        _coerce_value(follow_name, {"a": 1})


def test_context_excludes_autoincrement_pk_from_editing():
    service = DatatypeDataService(MagicMock())
    ctx = service.context("follow")
    pk = ctx.column("id")
    assert pk is not None
    assert pk.autoincrement is True
    assert pk.editable is False
    assert pk.required is False


def test_context_marks_required_columns_without_defaults():
    service = DatatypeDataService(MagicMock())
    ctx = service.context("challenge")
    challenge_id = ctx.column("challenge_id")
    assert challenge_id is not None
    assert challenge_id.required is True


def test_context_rejects_unknown_datatype():
    service = DatatypeDataService(MagicMock())
    with pytest.raises(DatatypeDataError) as exc:
        service.context("nope")
    assert exc.value.code == "unknown_datatype"
    assert exc.value.status_code == 404


def test_datatype_values_are_json_serialisable():
    service = DatatypeDataService(MagicMock())
    ctx = service.context("clean")
    grade_time = ctx.column("grade_time")
    assert grade_time is not None
    moment = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    coerced = _coerce_value(grade_time, moment.isoformat())
    # 时区时间统一规范化为朴素 UTC，避免写入带时区值的差异
    assert coerced == datetime(2026, 9, 23, 12, 0)


# ============== 集成：真实 SQLite 会话上的 Service + Routes ==============

class _SqliteDB:
    """最小 SQLAlchemyDB 替身：暴露 asession_scope 供服务使用。"""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    @asynccontextmanager
    async def asession_scope(self):
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@pytest_asyncio.fixture
async def rows_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text('ATTACH DATABASE ":memory:" AS public'))
        await connection.run_sync(lambda c: Follow.__table__.create(c))

    db = _SqliteDB(session_factory)
    app = FastAPI()
    app.include_router(row_routes.router)
    app.add_exception_handler(DatatypeDataError, _datatype_data_error_handler)
    app.dependency_overrides[row_routes.get_db] = lambda: db

    yield TestClient(app), DatatypeDataService(db)
    await engine.dispose()


def _create(client: TestClient, **values):
    return client.post(
        "/api/crawler/datatypes/follow/rows", json={"values": values}
    )


def test_rows_meta_exposes_editable_contract(rows_api):
    client, _ = rows_api
    response = client.get("/api/crawler/datatypes/follow/rows/meta")
    assert response.status_code == 200
    data = response.json()
    assert data["table_name"] == "t_busi_follow"
    assert data["pk_columns"] == ["id"]
    by_name = {column["name"]: column for column in data["columns"]}
    assert by_name["id"]["editable"] is False
    assert by_name["follow_id"]["value_type"] == "string"
    assert by_name["created_time"]["value_type"] == "datetime"


@pytest.mark.asyncio
async def test_rows_crud_round_trip(rows_api):
    client, _ = rows_api

    created = _create(client, user_id="u1", follow_id="f1", follow_name="N1", platform="bilibili")
    assert created.status_code == 201
    item = created.json()["item"]
    assert item["id"] == 1
    assert item["follow_name"] == "N1"

    listed = client.get("/api/crawler/datatypes/follow/rows")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.put(
        "/api/crawler/datatypes/follow/rows",
        params={"pk": '{"id": 1}'},
        json={"values": {"follow_name": "N2"}},
    )
    assert updated.status_code == 200
    assert updated.json()["item"]["follow_name"] == "N2"

    deleted = client.delete(
        "/api/crawler/datatypes/follow/rows", params={"pk": '{"id": 1}'}
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    assert client.get("/api/crawler/datatypes/follow/rows").json()["total"] == 0


def test_rows_keyword_and_filter_matching(rows_api):
    client, _ = rows_api
    _create(client, user_id="u1", follow_id="f1", follow_name="Alpha", platform="bilibili")
    _create(client, user_id="u2", follow_id="f2", follow_name="Beta", platform="douyin")

    keyword = client.get("/api/crawler/datatypes/follow/rows", params={"keyword": "alp"})
    assert keyword.json()["total"] == 1

    filtered = client.get(
        "/api/crawler/datatypes/follow/rows",
        params={"filters": '[{"field":"platform","operator":"eq","value":"douyin"}]'},
    )
    assert filtered.json()["total"] == 1

    null_filter = client.get(
        "/api/crawler/datatypes/follow/rows",
        params={"filters": '[{"field":"follow_name","operator":"is_null","value":true}]'},
    )
    assert null_filter.json()["total"] == 0


def test_rows_pagination_orders_by_primary_key_desc(rows_api):
    client, _ = rows_api
    for index in range(5):
        _create(client, user_id=f"u{index}", follow_id=f"f{index}", platform="bilibili")

    first = client.get(
        "/api/crawler/datatypes/follow/rows", params={"page": 1, "page_size": 2}
    ).json()
    assert first["total"] == 5
    assert first["page"] == 1
    assert [row["id"] for row in first["items"]] == [5, 4]

    second = client.get(
        "/api/crawler/datatypes/follow/rows", params={"page": 2, "page_size": 2}
    ).json()
    assert [row["id"] for row in second["items"]] == [3, 2]


def test_rows_error_mapping(rows_api):
    client, _ = rows_api

    assert client.get("/api/crawler/datatypes/nope/rows").json()["code"] == "unknown_datatype"

    unknown_field = _create(client, nope="x").json()
    assert unknown_field["code"] == "unknown_field"
    assert unknown_field["details"] == {"field": "nope"}

    readonly = _create(client, id=7).json()
    assert readonly["code"] == "readonly_field"

    missing = client.put(
        "/api/crawler/datatypes/follow/rows",
        params={"pk": '{"id": 42}'},
        json={"values": {"follow_name": "x"}},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "row_not_found"

    assert (
        client.delete("/api/crawler/datatypes/follow/rows", params={"pk": '{"id": 42}'}).status_code
        == 404
    )


def test_rows_required_field_enforced(rows_api):
    client, _ = rows_api
    # challenge 表 challenge_id 为非空且无默认值，缺失时必须拒绝
    response = client.post(
        "/api/crawler/datatypes/challenge/rows", json={"values": {"title": "x"}}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "missing_required_field"
    assert body["details"] == {"field": "challenge_id"}
