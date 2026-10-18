"""FastAPI mount, HTTP transport security, CORS, and lifespan tests."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.main import create_app
from core.config import McpConfig, SchedulerConfig


PROTOCOL_VERSION = "2026-07-28"
REQUEST_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientInfo": {"name": "asgi-test", "version": "1.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


class FakeResource:
    def __init__(self, name: str, events: list[str]):
        self.name = name
        self.events = events

    async def aconnect(self):
        self.events.append(f"{self.name}.connect")

    async def ainit_db(self):
        self.events.append(f"{self.name}.init")

    async def aclose(self):
        self.events.append(f"{self.name}.close")

    def get_redis_obj(self):
        return AsyncMock()


class FakeMinio(FakeResource):
    def __init__(self, events: list[str]):
        super().__init__("minio", events)
        self.alist_buckets = AsyncMock(
            return_value=[SimpleNamespace(name="media-assets", creation_date=None)]
        )


def _post_mcp(
    client: TestClient,
    method: str,
    params: dict | None = None,
    *,
    host: str,
    origin: str | None = "https://client.example",
):
    request_params = dict(params or {})
    request_params["_meta"] = REQUEST_META
    headers = {
        "Accept": "application/json, text/event-stream",
        "Host": host,
        "Mcp-Method": method,
        "Mcp-Protocol-Version": PROTOCOL_VERSION,
    }
    if origin is not None:
        headers["Origin"] = origin
    if method == "tools/call":
        headers["Mcp-Name"] = request_params["name"]
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": request_params},
        headers=headers,
    )


def _patch_storage(monkeypatch, events):
    db = FakeResource("db", events)
    minio = FakeMinio(events)
    redis = FakeResource("redis", events)
    monkeypatch.setattr("api.deps.SQLAlchemyDB", lambda **_kwargs: db)
    monkeypatch.setattr("api.deps.MinioDB", lambda **_kwargs: minio)
    monkeypatch.setattr("api.deps.RedisDB", lambda *_args, **_kwargs: redis)
    monkeypatch.setattr("api.deps.migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr("models.platform.platformSource.load_active_quotas", AsyncMock(return_value=[]))
    return db, minio, redis


def test_mcp_mount_serves_protocol_without_swallowing_existing_api(monkeypatch):
    events: list[str] = []
    _db, minio, _redis = _patch_storage(monkeypatch, events)
    config = SchedulerConfig(
        mcp=McpConfig(
            allowed_hosts=("mcp.internal", "mcp.internal:*"),
            allowed_origins=("https://client.example",),
        )
    )
    app = create_app(config)
    original_session_manager_run = app.state.mcp_server.session_manager.run

    @asynccontextmanager
    async def session_manager_run():
        assert app.state.db is not None
        assert app.state.minio is not None
        events.append("mcp.start")
        async with original_session_manager_run():
            yield
        events.append("mcp.stop")

    monkeypatch.setattr(app.state.mcp_server.session_manager, "run", session_manager_run)

    with TestClient(app, base_url="http://mcp.internal") as client:
        assert client.get("/openapi.json").status_code == 200
        assert "/api/crawler/platforms" in app.openapi()["paths"]

        listed = _post_mcp(client, "tools/list", host="mcp.internal")
        assert listed.status_code == 200
        assert listed.headers["access-control-expose-headers"] == "Mcp-Session-Id"
        listed_names = {tool["name"] for tool in listed.json()["result"]["tools"]}
        assert "list_buckets" in listed_names
        assert "/mcp/mcp" not in str(listed.url)

        called = _post_mcp(
            client,
            "tools/call",
            {"name": "list_buckets", "arguments": {}},
            host="mcp.internal",
        )
        assert called.status_code == 200
        assert called.json()["result"]["structuredContent"]["data"][0]["name"] == "media-assets"

        rejected = _post_mcp(client, "tools/list", host="evil.internal")
        assert rejected.status_code == 421

        preflight = client.options(
            "/mcp/",
            headers={
                "Host": "mcp.internal",
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "content-type,mcp-method,mcp-name,mcp-protocol-version,mcp-session-id"
                ),
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "https://client.example"
        assert {"GET", "POST", "DELETE"} <= set(
            preflight.headers["access-control-allow-methods"].split(", ")
        )

    assert minio.alist_buckets.await_count == 1
    assert events.index("db.init") < events.index("mcp.start")
    assert events.index("mcp.stop") < events.index("redis.close")
    assert events[-3:] == ["redis.close", "minio.close", "db.close"]


def test_empty_allowed_origins_does_not_enable_cors(monkeypatch):
    events: list[str] = []
    _patch_storage(monkeypatch, events)
    app = create_app(
        SchedulerConfig(mcp=McpConfig(allowed_hosts=("mcp.internal",), allowed_origins=()))
    )

    with TestClient(app, base_url="http://mcp.internal") as client:
        response = client.options(
            "/mcp/",
            headers={
                "Host": "mcp.internal",
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert "access-control-allow-origin" not in response.headers


def test_boolean_false_disables_mcp_mount():
    app = create_app(SchedulerConfig(mcp=McpConfig(enabled=False)))

    assert app.state.mcp_server is None
    assert all(getattr(route, "path", None) != "/mcp" for route in app.routes)


def test_default_host_allowlist_accepts_internal_hosts_with_ports(monkeypatch):
    events: list[str] = []
    _patch_storage(monkeypatch, events)
    app = create_app(SchedulerConfig())

    with TestClient(app) as client:
        for host in ("localhost:6274", "127.0.0.1:6274"):
            response = _post_mcp(
                client,
                "tools/list",
                host=host,
                origin=None,
            )
            assert response.status_code == 200

        rejected = _post_mcp(
            client,
            "tools/list",
            host="untrusted.internal:6274",
            origin=None,
        )
        assert rejected.status_code == 421
