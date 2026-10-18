"""Crawler API 应用工厂集成测试。"""
from starlette.routing import Mount

from api.main import create_app
from core.config import SchedulerConfig


def test_create_app_registers_all_crawler_resources():
    config = SchedulerConfig()
    app = create_app(config)
    paths = app.openapi()["paths"]

    assert app.state.config is config
    assert "/api/crawler/platforms" in paths
    assert "/api/crawler/actions" in paths
    assert "/api/crawler/keywords" in paths
    assert "/api/crawler/tasks" in paths
    assert "/api/settings" in paths
    assert "/api/settings/llm" in paths
    assert "/api/settings/platforms/{platform}" in paths


def test_create_app_does_not_serve_legacy_web_ui():
    app = create_app(SchedulerConfig())
    paths = app.openapi()["paths"]

    assert "/" not in paths
    assert not any(
        isinstance(route, Mount) and route.path == "/static"
        for route in app.routes
    )
