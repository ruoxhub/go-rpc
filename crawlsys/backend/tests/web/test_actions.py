"""Target JSON contract tests for crawler action routes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.crawler import actions as action_routes
from services.parser_configuration.errors import ParserConfigurationError
from storage.exceptions import AlreadyExistsError


@pytest.fixture
def action_api(monkeypatch):
    app = FastAPI()
    app.include_router(action_routes.router)

    async def parser_error_handler(
        _request: Request, error: ParserConfigurationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    app.add_exception_handler(ParserConfigurationError, parser_error_handler)
    db = MagicMock()
    app.dependency_overrides[action_routes.get_db] = lambda: db
    repo = MagicMock()
    repo.find_all = AsyncMock(return_value=[])
    repo.find_by_id = AsyncMock(return_value=None)
    repo.find_by_name = AsyncMock(return_value=None)
    repo.save = AsyncMock(side_effect=lambda item: item)
    repo.update = AsyncMock(return_value=True)
    repo.batch_update_status = AsyncMock(return_value=3)
    repo.delete_with_unlink = AsyncMock()
    parser_service = AsyncMock()
    app.state.action_parser_service = parser_service
    platform_repo = MagicMock()
    platform_repo.find_by_id = AsyncMock(return_value=SimpleNamespace(bs_id=1))
    monkeypatch.setattr(action_routes, "get_db", lambda: db)
    monkeypatch.setattr(action_routes, "ActionRepo", lambda _db: repo)
    monkeypatch.setattr(action_routes, "PlatformRepo", lambda _db: platform_repo)
    return TestClient(app), repo, platform_repo

VALID_ACTION = {
    "bs_id": 1,
    "ba_action": "getUserInfo",
    "ba_desc": "用户详情",
    "ba_params_schema": "[]",
    "ba_api_url": None,
    "ba_api_method": "GET",
    "ba_enabled": True,
    "ba_sample_safe": False,
}


def test_action_list_uses_platform_id_and_json_envelope(action_api):
    client, repo, _platform_repo = action_api
    repo.find_all.return_value = []
    response = client.get("/api/crawler/actions", params={"platform_id": 1})
    assert response.status_code == 200
    assert "items" in response.json()


def test_create_action_uses_json_and_created_status(action_api):
    client, repo, _platform_repo = action_api
    def save(item):
        item.ba_id = 7
        return item

    repo.save.side_effect = save
    response = client.post("/api/crawler/actions", json=VALID_ACTION)
    assert response.status_code == 201
    assert response.json()["ba_action"] == "getUserInfo"


def test_create_action_rejects_blank_name(action_api):
    client, _repo, _platform_repo = action_api
    response = client.post(
        "/api/crawler/actions",
        json={**VALID_ACTION, "ba_action": " "},
    )
    assert response.status_code == 422


def test_create_action_returns_not_found_for_missing_platform(action_api):
    client, repo, platform_repo = action_api
    platform_repo.find_by_id.return_value = None
    response = client.post("/api/crawler/actions", json=VALID_ACTION)
    assert response.status_code == 404
    repo.save.assert_not_awaited()


def test_get_action_returns_json_resource(action_api):
    client, repo, _platform_repo = action_api
    repo.find_by_id.return_value = SimpleNamespace(ba_id=7, **VALID_ACTION)
    response = client.get("/api/crawler/actions/7")
    assert response.status_code == 200
    assert response.json()["ba_id"] == 7


def test_update_action_uses_put_json(action_api):
    client, repo, _platform_repo = action_api
    repo.find_by_id.return_value = SimpleNamespace(ba_id=7, **VALID_ACTION)
    response = client.put(
        "/api/crawler/actions/7",
        json={"ba_desc": "更新后的描述", "ba_enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["ba_desc"] == "更新后的描述"


def test_update_action_rejects_explicit_null_name(action_api):
    client, repo, _platform_repo = action_api
    repo.find_by_id.return_value = SimpleNamespace(ba_id=7, **VALID_ACTION)
    response = client.put("/api/crawler/actions/7", json={"ba_action": None})
    assert response.status_code == 422
    repo.save.assert_not_awaited()


def test_create_duplicate_action_returns_conflict(action_api):
    client, repo, _platform_repo = action_api
    repo.find_by_name.return_value = SimpleNamespace(ba_id=7)
    response = client.post("/api/crawler/actions", json=VALID_ACTION)
    assert response.status_code == 409


def test_create_storage_conflict_returns_safe_conflict(action_api):
    client, repo, _platform_repo = action_api
    repo.save.side_effect = AlreadyExistsError("database constraint detail")
    response = client.post("/api/crawler/actions", json=VALID_ACTION)
    assert response.status_code == 409
    assert "database constraint detail" not in response.text


def test_update_missing_action_returns_not_found(action_api):
    client, repo, _platform_repo = action_api
    repo.find_by_id.return_value = None
    response = client.put("/api/crawler/actions/999", json={"ba_desc": "更新"})
    assert response.status_code == 404


def test_delete_action_returns_no_content(action_api):
    client, repo, _platform_repo = action_api
    repo.find_by_id.return_value = SimpleNamespace(ba_id=7, **VALID_ACTION)
    response = client.delete("/api/crawler/actions/7")
    assert response.status_code == 204
    assert response.content == b""
    client.app.state.action_parser_service.delete_action.assert_awaited_once_with(7)
    repo.delete_with_unlink.assert_not_awaited()


def test_delete_missing_action_returns_not_found(action_api):
    client, repo, _platform_repo = action_api
    client.app.state.action_parser_service.delete_action.side_effect = (
        ParserConfigurationError("action_not_found", "接口不存在", status_code=404)
    )
    response = client.delete("/api/crawler/actions/999")
    assert response.status_code == 404
    repo.find_by_id.assert_not_awaited()


def test_action_round_trip_exposes_sample_safe(action_api):
    client, repo, _platform_repo = action_api

    def save(item):
        item.ba_id = 7
        return item

    repo.save.side_effect = save
    created = client.post(
        "/api/crawler/actions",
        json={
            "bs_id": 1,
            "ba_action": "detail",
            "ba_sample_safe": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["ba_sample_safe"] is True


def test_import_actions_uses_json_and_returns_counts(action_api):
    client, repo, _platform_repo = action_api
    existing = SimpleNamespace(
        ba_id=8,
        bs_id=1,
        ba_action="SearchVideo",
        ba_desc="旧描述",
        ba_params_schema="[]",
        ba_api_url="https://example.com/search",
        ba_api_method="POST",
        ba_enabled=False,
    )
    repo.find_by_name.side_effect = [None, existing]

    async def update_existing(_ba_id, **changes):
        for field, value in changes.items():
            setattr(existing, field, value)
        return True

    repo.update.side_effect = update_existing
    response = client.post(
        "/api/crawler/actions/import",
        json={
            "platform_id": 1,
            "actions": [
                {"name": "getUserInfo", "description": "用户详情", "params": []},
                {
                    "name": "SearchVideo",
                    "description": "新描述",
                    "params": [{"name": "keyword"}],
                },
            ],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"created_count": 1, "updated_count": 1}
    created = repo.save.await_args.args[0]
    assert created.bs_id == 1
    assert created.ba_action == "getUserInfo"
    repo.update.assert_awaited_once_with(
        8,
        ba_desc="新描述",
        ba_params_schema='[{"name": "keyword"}]',
    )
    assert existing.ba_desc == "新描述"
    assert existing.ba_params_schema == '[{"name": "keyword"}]'
    assert existing.ba_api_url == "https://example.com/search"
    assert existing.ba_api_method == "POST"
    assert existing.ba_enabled is False


def test_import_actions_returns_not_found_for_missing_platform(action_api):
    client, repo, platform_repo = action_api
    platform_repo.find_by_id.return_value = None
    response = client.post(
        "/api/crawler/actions/import",
        json={"platform_id": 999, "actions": [{"name": "getUserInfo"}]},
    )
    assert response.status_code == 404
    repo.find_by_name.assert_not_awaited()
    repo.save.assert_not_awaited()


def test_import_actions_rejects_missing_name(action_api):
    client, _repo, _platform_repo = action_api
    response = client.post(
        "/api/crawler/actions/import",
        json={"platform_id": 1, "actions": [{"description": "missing name"}]},
    )
    assert response.status_code == 422


def test_import_actions_rejects_non_array_actions_root(action_api):
    client, _repo, _platform_repo = action_api
    response = client.post(
        "/api/crawler/actions/import",
        json={"platform_id": 1, "actions": {"name": "getUserInfo"}},
    )
    assert response.status_code == 422


def test_import_actions_rejects_name_over_100_characters(action_api):
    client, _repo, _platform_repo = action_api
    response = client.post(
        "/api/crawler/actions/import",
        json={"platform_id": 1, "actions": [{"name": "a" * 101}]},
    )
    assert response.status_code == 422


def test_update_action_params_schema_marks_source_manual(action_api):
    client, repo, _platform_repo = action_api
    existing = SimpleNamespace(
        ba_id=7,
        bs_id=1,
        ba_action="getUserInfo",
        ba_desc="Desc",
        ba_params_schema="[]",
        ba_api_url=None,
        ba_api_method="GET",
        ba_enabled=True,
        ba_sample_safe=False,
        ba_schema_source="synced",
        ba_synced_at=None,
    )
    repo.find_by_id.return_value = existing

    response = client.put(
        "/api/crawler/actions/7",
        json={"ba_params_schema": '[{"name": "uid", "type": "string"}]'},
    )
    assert response.status_code == 200
    assert existing.ba_schema_source == "manual"


def test_batch_update_action_status_success(action_api):
    client, repo, _platform_repo = action_api
    repo.batch_update_status.return_value = 2
    response = client.post(
        "/api/crawler/actions/batch-status",
        json={"action_ids": [7, 8], "enabled": False},
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 2}
    repo.batch_update_status.assert_awaited_once_with(action_ids=[7, 8], enabled=False)


def test_batch_update_action_status_rejects_empty_ids(action_api):
    client, _repo, _platform_repo = action_api
    response = client.post(
        "/api/crawler/actions/batch-status",
        json={"action_ids": [], "enabled": True},
    )
    assert response.status_code == 422


def test_batch_delete_actions_success(action_api):
    client, _repo, _platform_repo = action_api
    response = client.post(
        "/api/crawler/actions/batch-delete",
        json={"action_ids": [7, 8]},
    )
    assert response.status_code == 200
    assert response.json() == {"deleted_count": 2}
    delete_mock = client.app.state.action_parser_service.delete_action
    assert delete_mock.await_count == 2
    delete_mock.assert_any_await(7)
    delete_mock.assert_any_await(8)


def test_batch_delete_actions_skips_missing(action_api):
    client, _repo, _platform_repo = action_api
    async def side_effect(ba_id):
        if ba_id == 7:
            raise ParserConfigurationError("action_not_found", "not found", status_code=404)

    client.app.state.action_parser_service.delete_action.side_effect = side_effect
    response = client.post(
        "/api/crawler/actions/batch-delete",
        json={"action_ids": [7, 8]},
    )
    assert response.status_code == 200
    assert response.json() == {"deleted_count": 1}


def test_sync_actions_endpoint_success(action_api, monkeypatch):
    client, _repo, platform_repo = action_api
    platform_repo.find_by_id.return_value = SimpleNamespace(bs_id=1, bs_platform_code="bilibili")

    async def mock_sync(db, platform_id=None, force=False):
        return {
            "inserted_count": 5,
            "updated_count": 2,
            "skipped_manual_count": 1,
            "total_synced": 7,
            "unknown_groups": [],
            "details": [
                {"platform": "bilibili", "action": "getUserInfo", "status": "inserted", "reason": None},
                {"platform": "bilibili", "action": "getComment", "status": "updated", "reason": "schema_updated"},
            ],
        }

    from api.crawler import actions as actions_module
    monkeypatch.setattr(actions_module, "sync_actions", mock_sync)

    response = client.post(
        "/api/crawler/actions/sync",
        json={"platform_id": 1, "force": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["inserted_count"] == 5
    assert data["updated_count"] == 2
    assert data["skipped_manual_count"] == 1
    assert data["total_synced"] == 7
    assert len(data["details"]) == 2
    assert data["details"][0]["action"] == "getUserInfo"


def test_sync_actions_endpoint_missing_platform(action_api):
    client, _repo, platform_repo = action_api
    platform_repo.find_by_id.return_value = None

    response = client.post(
        "/api/crawler/actions/sync",
        json={"platform_id": 999},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "平台不存在"


def test_sync_actions_endpoint_sync_all(action_api, monkeypatch):
    client, _repo, _platform_repo = action_api

    called_kwargs = {}

    async def mock_sync(db, platform_id=None, force=False):
        called_kwargs["platform_id"] = platform_id
        called_kwargs["force"] = force
        return {
            "inserted_count": 10,
            "updated_count": 0,
            "skipped_manual_count": 0,
            "total_synced": 10,
            "unknown_groups": [],
            "details": [],
        }

    from api.crawler import actions as actions_module
    monkeypatch.setattr(actions_module, "sync_actions", mock_sync)

    response = client.post("/api/crawler/actions/sync", json={})
    assert response.status_code == 200
    assert response.json()["total_synced"] == 10
    assert called_kwargs == {"platform_id": None, "force": False}



