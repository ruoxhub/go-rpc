"""Target JSON contract tests for crawler keyword routes."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.crawler import keywords as keyword_routes
from storage.exceptions import AlreadyExistsError


@pytest.fixture
def keyword_api(monkeypatch):
    app = FastAPI()
    app.include_router(keyword_routes.router)
    db = MagicMock()
    app.dependency_overrides[keyword_routes.get_db] = lambda: db
    repo = MagicMock()
    repo.find_all = AsyncMock(return_value=[])
    repo.find_by_id = AsyncMock(return_value=None)
    repo.save = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    repo.platform_exists = AsyncMock(return_value=True)
    platform_repo = MagicMock()
    monkeypatch.setattr(keyword_routes, "get_db", lambda: db)
    monkeypatch.setattr(keyword_routes, "KeywordRepo", lambda _db: repo)
    return TestClient(app), repo, platform_repo


VALID_KEYWORD = {"platform": "tiktok", "keyword": "AI"}


def test_keyword_list_uses_platform_filter_and_json_envelope(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.find_all.return_value = []
    response = client.get("/api/crawler/keywords", params={"platform": "tiktok"})
    assert response.status_code == 200
    assert "items" in response.json()
    repo.find_all.assert_awaited_once_with(platform="tiktok")


def test_get_keyword_returns_explicit_dto(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.find_by_id.return_value = SimpleNamespace(
        id=7,
        platform="tiktok",
        keyword="AI",
        is_crawled=False,
        created_at=datetime.now(),
    )
    response = client.get("/api/crawler/keywords/7")
    assert response.status_code == 200
    assert response.json()["id"] == 7


def test_create_keyword_uses_json_and_created_status(keyword_api):
    client, repo, _platform_repo = keyword_api

    def save(item):
        item.id = 7
        item.is_crawled = False
        item.created_at = datetime.now()
        return item

    repo.save.side_effect = save
    response = client.post("/api/crawler/keywords", json=VALID_KEYWORD)
    assert response.status_code == 201
    assert response.json()["keyword"] == "AI"


def test_create_keyword_rejects_missing_platform(keyword_api):
    client, _repo, _platform_repo = keyword_api
    response = client.post(
        "/api/crawler/keywords",
        json={"platform": "", "keyword": "AI"},
    )
    assert response.status_code == 422


def test_create_keyword_rejects_blank_keyword(keyword_api):
    client, _repo, _platform_repo = keyword_api
    response = client.post(
        "/api/crawler/keywords",
        json={"platform": "tiktok", "keyword": " "},
    )
    assert response.status_code == 422


def test_create_keyword_rejects_keyword_over_1000_characters(keyword_api):
    client, _repo, _platform_repo = keyword_api
    response = client.post(
        "/api/crawler/keywords",
        json={"platform": "tiktok", "keyword": "a" * 1001},
    )
    assert response.status_code == 422


def test_create_keyword_rejects_unknown_platform(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.platform_exists.return_value = False
    response = client.post("/api/crawler/keywords", json=VALID_KEYWORD)
    assert response.status_code == 404


def test_create_keyword_rejects_disabled_or_deleted_platform(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.platform_exists.return_value = False
    response = client.post("/api/crawler/keywords", json=VALID_KEYWORD)
    assert response.status_code == 404
    repo.platform_exists.assert_awaited_once_with("tiktok")


def test_create_keyword_maps_storage_constraint_conflict_without_details(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.save.side_effect = AlreadyExistsError("sensitive database constraint")
    response = client.post("/api/crawler/keywords", json=VALID_KEYWORD)
    assert response.status_code == 409
    assert "sensitive" not in response.text
    assert response.json()["detail"] == "无法保存关键词：数据约束冲突"


def test_get_missing_keyword_returns_not_found(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.find_by_id.return_value = None
    response = client.get("/api/crawler/keywords/999")
    assert response.status_code == 404


def test_update_keyword_uses_put_json(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.find_by_id.return_value = SimpleNamespace(
        id=7,
        platform="tiktok",
        keyword="AI",
        is_crawled=False,
        created_at=datetime.now(),
    )
    repo.save.side_effect = lambda item: item
    response = client.put(
        "/api/crawler/keywords/7",
        json={"platform": "tiktok", "keyword": "LLM"},
    )
    assert response.status_code == 200
    assert response.json()["keyword"] == "LLM"


def test_update_keyword_rejects_unknown_platform(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.find_by_id.return_value = SimpleNamespace(
        id=7,
        platform="tiktok",
        keyword="AI",
        is_crawled=False,
        created_at=datetime.now(),
    )
    repo.platform_exists.return_value = False
    response = client.put(
        "/api/crawler/keywords/7",
        json={"platform": "unknown", "keyword": "LLM"},
    )
    assert response.status_code == 404
    repo.save.assert_not_awaited()
    repo.platform_exists.assert_awaited_once_with("unknown")


def test_delete_keyword_returns_no_content(keyword_api):
    client, _repo, _platform_repo = keyword_api
    response = client.delete("/api/crawler/keywords/7")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_missing_keyword_returns_not_found(keyword_api):
    client, repo, _platform_repo = keyword_api
    repo.delete.return_value = False
    response = client.delete("/api/crawler/keywords/999")
    assert response.status_code == 404
