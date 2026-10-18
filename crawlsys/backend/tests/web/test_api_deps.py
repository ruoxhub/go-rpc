"""API resource lifespan isolation and cleanup tests."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.config import SchedulerConfig


class FakeResource:
    def __init__(self, name, events, *, connect_error=None, init_error=None, close_error=None):
        self.name = name
        self.events = events
        self.connect_error = connect_error
        self.init_error = init_error
        self.close_error = close_error

    async def aconnect(self):
        self.events.append(f"{self.name}.connect")
        if self.connect_error:
            raise self.connect_error

    async def ainit_db(self):
        self.events.append(f"{self.name}.init")
        if self.init_error:
            raise self.init_error

    async def aclose(self):
        self.events.append(f"{self.name}.close")
        if self.close_error:
            raise self.close_error

    def get_redis_obj(self):
        return AsyncMock()


def _patch_resources(monkeypatch, db_factory, minio_factory, redis_factory):
    monkeypatch.setattr("api.deps.SQLAlchemyDB", db_factory)
    monkeypatch.setattr("api.deps.MinioDB", minio_factory)
    monkeypatch.setattr("api.deps.RedisDB", redis_factory)
    monkeypatch.setattr("api.deps.migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr("models.platform.platformSource.load_active_quotas", AsyncMock(return_value=[]))


def test_lifespan_starts_and_closes_all_resources(monkeypatch):
    events = []
    db = FakeResource("db", events)
    minio = FakeResource("minio", events)
    redis = FakeResource("redis", events)
    _patch_resources(monkeypatch, lambda **_: db, lambda **_: minio, lambda *_args, **_kwargs: redis)
    app = create_app(SchedulerConfig())

    with TestClient(app):
        assert app.state.db is db
        assert app.state.minio is minio
        assert app.state.redis is redis
        assert app.state.runtime_config_store is not None

    assert events == ["db.connect", "db.init", "redis.connect", "redis.close", "minio.close", "db.close"]
    assert app.state.db is app.state.minio is app.state.redis is None
    assert app.state.runtime_config_store is None


@pytest.mark.parametrize("failure", ["db_init", "redis_connect"])
def test_startup_failure_closes_every_constructed_resource(monkeypatch, failure):
    events = []
    db = FakeResource("db", events, init_error=RuntimeError("init") if failure == "db_init" else None)
    minio = FakeResource("minio", events)
    redis = FakeResource("redis", events, connect_error=RuntimeError("connect") if failure == "redis_connect" else None)
    _patch_resources(monkeypatch, lambda **_: db, lambda **_: minio, lambda *_args, **_kwargs: redis)
    app = create_app(SchedulerConfig())

    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass

    assert "db.close" in events
    if failure == "redis_connect":
        assert "redis.close" in events
        assert "minio.close" in events
    assert app.state.db is app.state.minio is app.state.redis is None


def test_shutdown_failure_still_closes_remaining_resources(monkeypatch):
    events = []
    db = FakeResource("db", events)
    minio = FakeResource("minio", events)
    redis = FakeResource("redis", events, close_error=RuntimeError("close"))
    _patch_resources(monkeypatch, lambda **_: db, lambda **_: minio, lambda *_args, **_kwargs: redis)
    app = create_app(SchedulerConfig())

    with pytest.raises(RuntimeError, match="close"):
        with TestClient(app):
            pass

    assert events[-3:] == ["redis.close", "minio.close", "db.close"]
    assert app.state.runtime_config_store is None


def test_nested_apps_keep_resources_isolated(monkeypatch):
    events = []
    databases = [FakeResource("db1", events), FakeResource("db2", events)]
    minios = [FakeResource("minio1", events), FakeResource("minio2", events)]
    redis_clients = [FakeResource("redis1", events), FakeResource("redis2", events)]
    _patch_resources(
        monkeypatch,
        lambda **_: databases.pop(0),
        lambda **_: minios.pop(0),
        lambda *_args, **_kwargs: redis_clients.pop(0),
    )
    first = create_app(SchedulerConfig())
    second = create_app(SchedulerConfig())

    with TestClient(first):
        first_db = first.state.db
        first_store = first.state.runtime_config_store
        with TestClient(second):
            assert second.state.db is not first_db
            assert second.state.runtime_config_store is not first_store
            assert first.state.db is first_db
        assert first.state.db is first_db
        assert second.state.db is None

    assert first.state.db is None
