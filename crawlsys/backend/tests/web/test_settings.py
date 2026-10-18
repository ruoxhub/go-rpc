"""系统运行时设置 API 测试。"""
import logging
from types import SimpleNamespace
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from api.settings.routes import get_platform_repo, get_task_repo
from api.main import create_app
from core.config import SchedulerConfig
from runtime_config.models import (
    AnalysisVideoSettings, CleanerSettings, LlmSettings, PlatformCleanerPolicy,
    ProxySettings, RpcSettings, SchedulerSettings,
)
from runtime_config.store import RuntimeConfigReadError
from api.deps import get_llm_catalog, get_runtime_config_store


POLICY = PlatformCleanerPolicy(p1=[{"max_hours": 24.0, "min_views": 100}])


class FakeStore:
    def __init__(self):
        self.llm = LlmSettings(default_analysis_model_id=12)
        self.scheduler = SchedulerSettings()
        self.rpc = RpcSettings()
        self.video = AnalysisVideoSettings()
        self.proxy = ProxySettings(url="http://user:password@proxy.local:8080/path?token=x")
        self.cleaner = CleanerSettings(enabled=True)
        self.policies = {"tiktok": POLICY}
        self.calls = []

    async def get_llm(self): return self.llm
    async def get_scheduler(self): return self.scheduler
    async def get_rpc(self): return self.rpc
    async def get_analysis_video(self): return self.video
    async def get_proxy(self): return self.proxy
    async def get_cleaner(self): return self.cleaner
    async def get_platform_policy(self, code): return self.policies.get(code)
    async def update_llm(self, value):
        self.calls.append(("llm", value)); return self.llm
    async def replace_scheduler(self, value):
        self.calls.append(("scheduler", value)); return value
    async def replace_rpc(self, value): self.calls.append(("rpc", value)); return value
    async def replace_analysis_video(self, value): self.calls.append(("video", value)); return value
    async def update_proxy(self, value): self.calls.append(("proxy", value)); return self.proxy
    async def replace_cleaner(self, value): self.calls.append(("cleaner", value)); return value
    async def replace_platform_policy(self, code, value):
        self.calls.append((code, value)); return value


class FakeRepo:
    def __init__(self):
        self.rows = [
            SimpleNamespace(bs_platform_code="tiktok", bs_status="1"),
            SimpleNamespace(bs_platform_code="youtube", bs_status="0"),
        ]
        self.recompute_calls = 0
        self.last_recompute_timezone = None

    async def find_all_active(self): return self.rows
    async def find_by_code(self, code):
        return next((row for row in self.rows if row.bs_platform_code == code), None)
    async def recompute_cron_schedules(self, *, timezone_name, now):
        self.recompute_calls += 1
        self.last_recompute_timezone = timezone_name
        return 0


class FakeCatalog:
    @asynccontextmanager
    async def reference_guard(self, model_ids):
        yield


@pytest.fixture
def client_and_fakes():
    store, repo = FakeStore(), FakeRepo()
    app = create_app(SchedulerConfig())
    app.dependency_overrides[get_runtime_config_store] = lambda: store
    app.dependency_overrides[get_llm_catalog] = FakeCatalog
    app.dependency_overrides[get_platform_repo] = lambda: repo
    app.dependency_overrides[get_task_repo] = lambda: repo
    return TestClient(app), store, repo


def test_get_settings_is_secret_free_and_shows_platform_configuration(client_and_fakes):
    client, _, _ = client_and_fakes
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    encoded = response.text
    assert body["llm"]["default_analysis_model_id"] == 12
    assert "api_key" not in body["llm"]
    assert body["proxy"] == {"url_configured": True, "target": "http://proxy.local:8080"}
    assert "user:password" not in encoded
    assert "token=x" not in encoded
    assert body["scheduler"]["inactive_fields"] == ["worker_id", "batch_size", "graceful_shutdown_seconds"]
    assert body["cleaner"]["inactive_fields"] == ["poll_interval", "watermark_key"]
    assert "thresholds" not in body["cleaner"]
    assert body["platforms"][0]["configured"] is True
    assert body["platforms"][1] == {"platform": "youtube", "configured": False, "policy": None}


@pytest.mark.parametrize("path,payload,call", [
    ("/api/settings/llm", {"default_transcription_model_id": 8}, "llm"),
    ("/api/settings/scheduler", SchedulerSettings(
        worker_id="settings-test",
        poll_interval_ms=2000,
        default_loop_interval_seconds=7200,
        batch_size=20,
        zombie_reap_after_seconds=1200,
        graceful_shutdown_seconds=60,
    ).model_dump(), "scheduler"),
    ("/api/settings/scheduler/rpc", {"base_url": "https://rpc.test", "timeout_seconds": 2}, "rpc"),
    ("/api/settings/analysis/video", {"is_base64": True}, "video"),
    ("/api/settings/proxy", {"url": "   "}, "proxy"),
    ("/api/settings/cleaner", CleanerSettings(
        enabled=True,
        poll_interval=1800.0,
        batch_size=500,
        max_batches_per_platform=5,
        ttl_days=7,
        watermark_key="cleaner:test:watermark",
        suspect_seconds=90.0,
    ).model_dump(mode="json"), "cleaner"),
])
def test_put_updates_only_its_partition(client_and_fakes, path, payload, call):
    client, store, _ = client_and_fakes
    response = client.put(path, json=payload)
    assert response.status_code == 200
    assert [name for name, _ in store.calls] == [call]
    if call == "llm":
        assert store.calls[0][1].default_transcription_model_id == 8
    if call == "proxy":
        assert store.calls[0][1].url == "   "
    if call in {"scheduler", "cleaner"}:
        body = response.json()
        assert all(body[key] == value for key, value in payload.items())


def test_platform_put_requires_existing_non_deleted_platform(client_and_fakes):
    client, _, repo = client_and_fakes
    assert client.put("/api/settings/platforms/unknown", json=POLICY.model_dump()).status_code == 404
    repo.rows.append(SimpleNamespace(bs_platform_code="deleted", bs_status="D"))
    assert client.put("/api/settings/platforms/deleted", json=POLICY.model_dump()).status_code == 404
    assert client.put("/api/settings/platforms/tiktok", json=POLICY.model_dump()).status_code == 200


def test_cleaner_can_be_enabled_after_platform_policy_is_saved(client_and_fakes):
    client, store, _ = client_and_fakes
    store.cleaner = CleanerSettings(enabled=False)
    assert client.put("/api/settings/platforms/tiktok", json=POLICY.model_dump()).status_code == 200
    payload = store.cleaner.model_dump()
    payload["enabled"] = True
    response = client.put("/api/settings/cleaner", json=payload)
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert "thresholds" not in response.json()


def test_invalid_payload_preserves_fastapi_field_location(client_and_fakes):
    client, _, _ = client_and_fakes
    response = client.put("/api/settings/scheduler/rpc", json={"base_url": "secret", "timeout_seconds": 2})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "base_url"]


def test_invalid_proxy_validation_does_not_expose_authenticated_url(
    client_and_fakes, caplog
):
    client, _, _ = client_and_fakes
    marker = "proxy-password-must-not-leak"
    with caplog.at_level(logging.WARNING, logger="api.main"):
        response = client.put(
            "/api/settings/proxy",
            json={"url": f"http://user:{marker}@invalid host"},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "url"]
    assert marker not in response.text
    assert "Request validation failed" in caplog.text
    assert marker not in caplog.text


@pytest.mark.parametrize("field", ["max_tokens", "temperature", "enable_thinking"])
def test_llm_generation_fields_reject_explicit_null(client_and_fakes, field):
    client, _, _ = client_and_fakes
    response = client.put("/api/settings/llm", json={field: None})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


def test_store_error_returns_safe_503(client_and_fakes):
    client, store, _ = client_and_fakes
    async def fail():
        raise RuntimeConfigReadError("redis://user:secret@internal")
    store.get_llm = fail
    response = client.get("/api/settings")
    assert response.status_code == 503
    assert response.json() == {"detail": "运行时配置服务暂不可用"}
    assert "secret" not in response.text


def test_unknown_store_error_is_not_mapped_to_503(client_and_fakes):
    client, store, _ = client_and_fakes
    async def fail():
        raise RuntimeError("programming error")
    store.get_llm = fail
    with pytest.raises(RuntimeError, match="programming error"):
        client.get("/api/settings")

def test_put_scheduler_recomputes_cron_when_timezone_changes(client_and_fakes):
    client, store, repo = client_and_fakes
    store.scheduler = SchedulerSettings(timezone="America/New_York")
    payload = SchedulerSettings(timezone="Asia/Shanghai").model_dump()

    response = client.put("/api/settings/scheduler", json=payload)

    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Shanghai"
    assert repo.recompute_calls == 1
    assert repo.last_recompute_timezone == "Asia/Shanghai"


def test_put_scheduler_skips_recompute_when_timezone_unchanged(client_and_fakes):
    client, store, repo = client_and_fakes
    store.scheduler = SchedulerSettings()  # 默认 Asia/Shanghai

    response = client.put("/api/settings/scheduler", json=SchedulerSettings().model_dump())

    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Shanghai"
    assert repo.recompute_calls == 0


def test_put_scheduler_rejects_unknown_timezone(client_and_fakes):
    client, _, _ = client_and_fakes

    response = client.put("/api/settings/scheduler", json={"timezone": "Mars/Olympus"})

    assert response.status_code == 422
