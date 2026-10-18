"""Tests for SysDatatype ORM introspection, repository, and JSON API routes."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.crawler import datatypes as datatype_routes
from core.repository import DatatypeRepo
from models.datatype import (
    SysDatatype,
    SysDatatypeRead,
    introspect_datatype_models,
    parser_value_types,
)


def _mock_datatype(key: str = "content"):
    return SysDatatype(
        datatype_id=1,
        datatype_key=key,
        table_name=f"t_busi_{key}",
        model_name=key.capitalize(),
        description=f"{key} model",
        unique_field=f"{key}_id",
        update_fields=[f"{key}_id", "platform"],
        columns=[
            {
                "name": f"{key}_id",
                "type": "VARCHAR(64)",
                "nullable": True,
                "primary_key": False,
                "comment": f"{key} ID",
            }
        ],
        dto_fields=[
            {
                "name": f"{key}_id",
                "target": f"/{key}_id",
                "required": False,
                "value_types": ["string"],
                "description": None,
            }
        ],
        is_active=True,
        created_at=datetime(2026, 9, 15, 12, 0, 0),
        updated_at=datetime(2026, 9, 15, 12, 0, 0),
    )


def test_introspect_datatype_models_discovers_all_registered_models():
    models_data = introspect_datatype_models()
    keys = {item["datatype_key"] for item in models_data}
    expected_keys = {"content", "user", "comment", "media", "job", "challenge", "clean", "follow"}
    assert expected_keys.issubset(keys), f"Missing keys: {expected_keys - keys}"

    # Verify content model details
    content_meta = next(item for item in models_data if item["datatype_key"] == "content")
    assert content_meta["table_name"] == "t_busi_content"
    assert content_meta["model_name"] == "Content"
    assert content_meta["unique_field"] == "content_id"
    assert "content_id" in content_meta["update_fields"]
    assert len(content_meta["columns"]) > 20
    assert any(c["name"] == "content_id" for c in content_meta["columns"])
    assert any(c["name"] == "title" for c in content_meta["columns"])
    assert any(d["name"] == "title" for d in content_meta["dto_fields"])


def test_introspect_datatype_models_discovers_follow():
    models_data = introspect_datatype_models()
    follow_meta = next(item for item in models_data if item["datatype_key"] == "follow")
    assert follow_meta["table_name"] == "t_busi_follow"
    assert follow_meta["model_name"] == "Follow"
    assert follow_meta["unique_field"] == "follow_id"
    assert "follow_id" in follow_meta["update_fields"]
    assert "platform" in follow_meta["update_fields"]
    assert any(c["name"] == "follow_id" for c in follow_meta["columns"])
    assert any(d["name"] == "follow_id" for d in follow_meta["dto_fields"])


def test_parser_value_types_inference():
    assert parser_value_types(str) == ["string"]
    assert parser_value_types(int) == ["integer"]
    assert parser_value_types(float) == ["number"]
    assert parser_value_types(bool) == ["boolean"]
    assert parser_value_types(datetime) == ["datetime"]
    assert parser_value_types(dict) == ["object"]
    assert parser_value_types(list) == ["array"]
    assert "string" in parser_value_types(str | None)


@pytest.fixture
def datatype_api(monkeypatch):
    app = FastAPI()
    app.include_router(datatype_routes.router)
    db = MagicMock()
    app.dependency_overrides[datatype_routes.get_db] = lambda: db

    repo = MagicMock()
    repo.find_all = AsyncMock(return_value=[_mock_datatype("content"), _mock_datatype("user")])
    repo.find_by_key = AsyncMock(side_effect=lambda key: _mock_datatype(key) if key in ("content", "user") else None)
    repo.sync_from_code = AsyncMock(return_value=(8, ["content", "user", "comment", "media", "job", "challenge", "clean", "follow"]))

    async def _update_status(key: str, is_active: bool):
        if key not in ("content", "user"):
            return None
        record = _mock_datatype(key)
        record.is_active = is_active
        return record

    repo.update_status = AsyncMock(side_effect=_update_status)

    monkeypatch.setattr(datatype_routes, "get_db", lambda: db)
    monkeypatch.setattr(datatype_routes, "DatatypeRepo", lambda _db: repo)
    return TestClient(app), repo


def test_list_datatypes_returns_items_and_total(datatype_api):
    client, repo = datatype_api
    response = client.get("/api/crawler/datatypes")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 2
    assert data["items"][0]["datatype_key"] == "content"
    assert data["items"][1]["datatype_key"] == "user"


def test_get_datatype_detail_returns_columns_and_dto(datatype_api):
    client, repo = datatype_api
    response = client.get("/api/crawler/datatypes/content")
    assert response.status_code == 200
    data = response.json()
    assert data["datatype_key"] == "content"
    assert data["table_name"] == "t_busi_content"
    assert len(data["columns"]) == 1
    assert data["columns"][0]["name"] == "content_id"
    assert len(data["dto_fields"]) == 1


def test_get_nonexistent_datatype_returns_404(datatype_api):
    client, repo = datatype_api
    response = client.get("/api/crawler/datatypes/unknown_key")
    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


def test_sync_datatypes_endpoint_triggers_introspection(datatype_api):
    client, repo = datatype_api
    response = client.post("/api/crawler/datatypes/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["synced_count"] == 8
    assert "content" in data["datatypes"]
    repo.sync_from_code.assert_awaited_once()


def test_update_datatype_status_enabled(datatype_api):
    client, repo = datatype_api
    response = client.patch("/api/crawler/datatypes/content/status", json={"is_active": False})
    assert response.status_code == 200
    data = response.json()
    assert data["datatype_key"] == "content"
    assert data["is_active"] is False
    repo.update_status.assert_awaited_once_with("content", False)


def test_update_datatype_status_not_found(datatype_api):
    client, repo = datatype_api
    response = client.patch("/api/crawler/datatypes/unknown_key/status", json={"is_active": True})
    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_datatype_repo_real_sqlite_sync_and_idempotence():
    from contextlib import asynccontextmanager
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: SysDatatype.__table__.create(sync_conn))

    class RealTestDB:
        def __init__(self, eng):
            self.session_factory = async_sessionmaker(eng, expire_on_commit=False)

        @asynccontextmanager
        async def asession_scope(self):
            async with self.session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

    test_db = RealTestDB(engine)
    repo = DatatypeRepo(test_db)

    # First sync
    count, keys = await repo.sync_from_code()
    assert count >= 8
    assert "content" in keys
    assert "follow" in keys

    # Verify query
    rows = await repo.find_all()
    assert len(rows) == count

    content = await repo.find_by_key("content")
    assert content is not None
    assert content.table_name == "t_busi_content"
    assert content.model_name == "Content"
    assert content.unique_field == "content_id"
    assert len(content.columns) >= 20

    follow = await repo.find_by_key("follow")
    assert follow is not None
    assert follow.table_name == "t_busi_follow"
    assert follow.model_name == "Follow"
    assert follow.unique_field == "follow_id"
    assert follow.is_active is True

    # update_status 持久化并返回更新后的记录
    updated = await repo.update_status("follow", False)
    assert updated is not None
    assert updated.is_active is False
    reloaded = await repo.find_by_key("follow")
    assert reloaded is not None
    assert reloaded.is_active is False

    # 恢复状态，避免影响后续重复同步断言
    await repo.update_status("follow", True)

    missing = await repo.update_status("unknown_key", True)
    assert missing is None

    # Test idempotence on repeated sync
    count2, keys2 = await repo.sync_from_code()
    assert count2 == count
    rows2 = await repo.find_all()
    assert len(rows2) == count

