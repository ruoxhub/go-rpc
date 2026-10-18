"""Target JSON contract tests for crawler platform routes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.crawler import platforms as platform_routes
from storage.exceptions import AlreadyExistsError


@pytest.fixture
def platform_api(monkeypatch):
    app = FastAPI()
    app.include_router(platform_routes.router)
    db = MagicMock()
    app.dependency_overrides[platform_routes.get_db] = lambda: db
    repo = MagicMock()
    repo.find_all = AsyncMock(return_value=[])
    repo.find_by_id = AsyncMock(return_value=None)
    repo.find_by_code = AsyncMock(return_value=None)
    repo.find_by_name = AsyncMock(return_value=None)
    repo.save = AsyncMock()
    repo.soft_delete = AsyncMock(return_value=True)
    repo.restore = AsyncMock(return_value=True)
    monkeypatch.setattr(platform_routes, "get_db", lambda: db)
    monkeypatch.setattr(platform_routes, "PlatformRepo", lambda _db: repo)
    return TestClient(app), repo

VALID_PLATFORM = {
    "bs_name": "TikTok",
    "bs_platform_code": "tiktok",
    "bs_url": "https://www.tiktok.com",
    "bs_remark": "短视频平台",
    "bs_status": "1",
    "bs_concurrency": 2,
    "bs_rps": 5.0,
    "bs_burst": 10,
    "bs_cooldown": 60,
}


def test_platform_list_uses_json_envelope(platform_api):
    client, repo = platform_api
    repo.find_all.return_value = []
    response = client.get("/api/crawler/platforms", params={"include_deleted": False})
    assert response.status_code == 200
    assert "items" in response.json()


def test_create_platform_uses_json_and_created_status(platform_api):
    client, repo = platform_api
    repo.save.side_effect = lambda item: SimpleNamespace(bs_id=7, **VALID_PLATFORM)
    response = client.post("/api/crawler/platforms", json=VALID_PLATFORM)
    assert response.status_code == 201
    assert response.json()["bs_id"] == 7
    assert response.json()["bs_platform_code"] == "tiktok"


def test_create_platform_rejects_blank_name(platform_api):
    client, _repo = platform_api
    response = client.post(
        "/api/crawler/platforms",
        json={**VALID_PLATFORM, "bs_name": " "},
    )
    assert response.status_code == 422


def test_create_platform_rejects_invalid_quota(platform_api):
    client, _repo = platform_api
    response = client.post(
        "/api/crawler/platforms",
        json={**VALID_PLATFORM, "bs_concurrency": 0},
    )
    assert response.status_code == 422


def test_create_duplicate_platform_returns_conflict(platform_api):
    client, repo = platform_api
    repo.find_by_code.return_value = SimpleNamespace(bs_id=7)
    response = client.post("/api/crawler/platforms", json=VALID_PLATFORM)
    assert response.status_code == 409


def test_create_storage_unique_conflict_returns_conflict(platform_api):
    client, repo = platform_api
    repo.save.side_effect = AlreadyExistsError("database constraint details")

    response = client.post("/api/crawler/platforms", json=VALID_PLATFORM)

    assert response.status_code == 409
    assert "database constraint details" not in response.text


def test_create_does_not_hide_other_storage_errors(platform_api):
    client, repo = platform_api
    repo.save.side_effect = RuntimeError("storage unavailable")

    with pytest.raises(RuntimeError, match="storage unavailable"):
        client.post("/api/crawler/platforms", json=VALID_PLATFORM)


def test_get_missing_platform_returns_not_found(platform_api):
    client, repo = platform_api
    repo.find_by_id.return_value = None
    response = client.get("/api/crawler/platforms/999")
    assert response.status_code == 404


def test_update_platform_uses_put_json(platform_api):
    client, repo = platform_api
    platform = SimpleNamespace(bs_id=7, **VALID_PLATFORM)
    repo.find_by_id.return_value = platform
    repo.save.side_effect = lambda item: item
    response = client.put(
        "/api/crawler/platforms/7",
        json={**VALID_PLATFORM, "bs_name": "X"},
    )
    assert response.status_code == 200
    assert response.json()["bs_name"] == "X"


def test_update_storage_unique_conflict_returns_conflict(platform_api):
    client, repo = platform_api
    platform = SimpleNamespace(bs_id=7, **VALID_PLATFORM)
    repo.find_by_id.return_value = platform
    repo.save.side_effect = AlreadyExistsError("database constraint details")

    response = client.put("/api/crawler/platforms/7", json=VALID_PLATFORM)

    assert response.status_code == 409
    assert "database constraint details" not in response.text


def test_delete_platform_returns_no_content(platform_api):
    client, _repo = platform_api
    response = client.delete("/api/crawler/platforms/7")
    assert response.status_code == 204
    assert response.content == b""


def test_restore_platform_returns_resource(platform_api):
    client, repo = platform_api
    repo.find_by_id.return_value = SimpleNamespace(
        bs_id=7,
        **{**VALID_PLATFORM, "bs_status": "1"},
    )
    response = client.post("/api/crawler/platforms/7/restore")
    assert response.status_code == 200
    assert response.json()["bs_status"] == "1"
