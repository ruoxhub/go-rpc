"""Task 4: structured schedule/retry API contract and Cron preview tests."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.crawler import tasks as task_routes
from models.task import BusTask, TaskStatus
from runtime_config.models import SchedulerSettings


class TaskApiFixture:
    def __init__(self, client, repo, session):
        self.client = client
        self.repo = repo
        self.session = session

    def __iter__(self):
        return iter((self.client, self.repo))


def _task(**overrides):
    values = {
        "task_id": 7,
        "platform": "tiktok",
        "action": "SearchVideo",
        "ba_id": 1,
        "platform_id": 1,
        "status": TaskStatus.PENDING,
        "attempts": 0,
        "error_msg": None,
        "last_run_at": None,
        "loop_enabled": False,
        "loop_interval_seconds": None,
        "schedule_type": "manual",
        "cron_expression": None,
        "run_once_at": None,
        "schedule_start_at": None,
        "schedule_end_at": None,
        "max_runs": None,
        "run_count": 0,
        "last_run_status": None,
        "retry_max_attempts": 0,
        "retry_delay_seconds": 60,
        "retry_backoff_multiplier": 2.0,
        "retry_max_delay_seconds": 3600,
        "retry_count": 0,
        "next_retry_at": None,
        "run_now_requested_at": None,
        "pause_requested": False,
        "active_trigger": None,
        "active_scheduled_at": None,
        "next_run_at": None,
        "config": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def task_api(monkeypatch):
    app = FastAPI()
    app.include_router(task_routes.router)
    db = MagicMock()
    session = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = [("id",), ("platform",)]
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def session_scope():
        yield session

    db.asession_scope = session_scope
    app.dependency_overrides[task_routes.get_db] = lambda: db
    repo = MagicMock()
    repo.find_all = AsyncMock(return_value=[])
    repo.find_by_id = AsyncMock(return_value=_task())
    repo.save = AsyncMock()
    async def _mock_save_in_session(_session, item):
        await repo.save(item)
        return item
    repo.save_in_session = AsyncMock(side_effect=_mock_save_in_session)
    repo.delete = AsyncMock()
    repo.set_status = AsyncMock(return_value=True)
    repo.batch_set_status = AsyncMock(return_value=0)
    repo.request_run_now = AsyncMock(return_value=True)
    repo.pause = AsyncMock(return_value=True)
    repo.resume = AsyncMock(return_value=True)
    action_repo = MagicMock()
    action_repo.find_by_id = AsyncMock(
        return_value=SimpleNamespace(ba_id=1, bs_id=1, ba_action="SearchVideo")
    )
    action_repo.get_schema = AsyncMock(return_value=[])
    platform_repo = MagicMock()
    platform_repo.find_by_id = AsyncMock(
        return_value=SimpleNamespace(
            bs_id=1,
            bs_name="TikTok",
            bs_platform_code="tiktok",
        )
    )
    catalog = MagicMock()
    catalog.get_model = AsyncMock(
        return_value=(
            SimpleNamespace(enabled=True, remote_available=True),
            SimpleNamespace(enabled=True),
        )
    )
    app.dependency_overrides[task_routes.get_llm_catalog] = lambda: catalog
    store = MagicMock()
    store.get_scheduler = AsyncMock(return_value=SchedulerSettings())
    app.dependency_overrides[task_routes.get_runtime_config_store] = lambda: store
    monkeypatch.setattr(task_routes, "get_db", lambda: db)
    monkeypatch.setattr(task_routes, "TaskRepo", lambda _db: repo)
    monkeypatch.setattr(task_routes, "ActionRepo", lambda _db: action_repo)
    monkeypatch.setattr(task_routes, "PlatformRepo", lambda _db: platform_repo)
    client = TestClient(app)
    try:
        yield TaskApiFixture(client, repo, session)
    finally:
        app.dependency_overrides.clear()
        client.close()


def _base_payload(**overrides):
    payload = {
        "ba_id": 1,
        "schedule": {"type": "manual"},
        "retry_policy": {
            "max_attempts": 3,
            "initial_delay_seconds": 60,
            "backoff_multiplier": 2,
            "max_delay_seconds": 3600,
        },
    }
    payload.update(overrides)
    return payload


def test_preview_returns_five_system_timezone_occurrences(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks/schedule/preview", json={"cron": "0 2 * * *"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Shanghai"
    assert len(body["occurrences"]) == 5


def test_preview_rejects_malformed_cron(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks/schedule/preview", json={"cron": "0 2 * *"}
    )
    assert response.status_code == 422


def test_create_cron_task_applies_schedule_fields(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json=_base_payload(schedule={"type": "cron", "cron": "0 2 * * *"}),
    )

    assert response.status_code == 201
    saved = repo.save.await_args.args[0]
    assert saved.schedule_type == "cron"
    assert saved.cron_expression == "0 2 * * *"
    assert saved.retry_max_attempts == 3
    assert saved.next_run_at is not None
    body = response.json()
    assert body["schedule"]["type"] == "cron"
    assert body["schedule"]["cron"] == "0 2 * * *"
    assert body["retry_policy"]["max_attempts"] == 3


def test_cron_rejects_interval_field(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks",
        json=_base_payload(
            schedule={"type": "cron", "cron": "0 2 * * *", "interval_seconds": 60}
        ),
    )
    assert response.status_code == 422


def test_once_rejects_missing_run_at(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks",
        json=_base_payload(schedule={"type": "once"}),
    )
    assert response.status_code == 422


def test_interval_rejects_non_positive_seconds(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks",
        json=_base_payload(schedule={"type": "interval", "interval_seconds": 0}),
    )
    assert response.status_code == 422


def test_schedule_rejects_inverted_range(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks",
        json=_base_payload(
            schedule={
                "type": "interval",
                "interval_seconds": 60,
                "start_at": "2026-08-11T00:00:00Z",
                "end_at": "2026-08-10T00:00:00Z",
            }
        ),
    )
    assert response.status_code == 422


def test_retry_policy_rejects_too_small_max_delay(task_api):
    client, _ = task_api
    response = client.post(
        "/api/crawler/tasks",
        json=_base_payload(
            retry_policy={
                "max_attempts": 3,
                "initial_delay_seconds": 60,
                "backoff_multiplier": 2,
                "max_delay_seconds": 0,
            }
        ),
    )
    assert response.status_code == 422


def test_legacy_loop_request_converts_to_interval(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json={"ba_id": 1, "loop_enabled": True, "loop_interval_seconds": 30},
    )

    assert response.status_code == 201
    saved = repo.save.await_args.args[0]
    assert saved.schedule_type == "interval"
    assert saved.loop_enabled is True
    assert saved.loop_interval_seconds == 30


def test_legacy_plain_request_converts_to_manual(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post("/api/crawler/tasks", json={"ba_id": 1})

    assert response.status_code == 201
    saved = repo.save.await_args.args[0]
    assert saved.schedule_type == "manual"
    assert saved.next_run_at is None


def test_run_now_returns_204(task_api):
    client, repo = task_api
    repo.request_run_now = AsyncMock(return_value=True)

    response = client.post("/api/crawler/tasks/7/run-now")

    assert response.status_code == 204
    repo.request_run_now.assert_awaited_once_with(7)


def test_run_now_missing_task_returns_404(task_api):
    client, repo = task_api
    repo.find_by_id = AsyncMock(return_value=None)

    response = client.post("/api/crawler/tasks/7/run-now")

    assert response.status_code == 404


def test_run_now_at_limit_returns_409(task_api):
    client, repo = task_api
    repo.request_run_now = AsyncMock(return_value=False)

    response = client.post("/api/crawler/tasks/7/run-now")

    assert response.status_code == 409


def test_pause_running_task_requests_pause_after_current_run(task_api):
    client, repo = task_api
    running = _task(status=TaskStatus.RUNNING, pause_requested=False)
    pausing = _task(status=TaskStatus.RUNNING, pause_requested=True)
    repo.find_by_id = AsyncMock(side_effect=[running, pausing])

    response = client.post("/api/crawler/tasks/7/pause")

    assert response.status_code == 200
    repo.pause.assert_awaited_once_with(7)
    repo.set_status.assert_not_awaited()
    assert response.json()["status"] == "running"
    assert response.json()["pause_requested"] is True


def test_resume_cron_task_recomputes_next_future_run(task_api):
    client, repo = task_api
    paused = _task(
        status=TaskStatus.PAUSED,
        schedule_type="cron",
        cron_expression="0 2 * * *",
    )
    resumed = _task(
        status=TaskStatus.PENDING,
        schedule_type="cron",
        cron_expression="0 2 * * *",
    )
    repo.find_by_id = AsyncMock(side_effect=[paused, resumed])

    response = client.post("/api/crawler/tasks/7/start")

    assert response.status_code == 200
    repo.resume.assert_awaited_once()
    task_id = repo.resume.await_args.args[0]
    next_run_at = repo.resume.await_args.kwargs["next_run_at"]
    assert task_id == 7
    assert next_run_at.tzinfo == timezone.utc
    assert next_run_at > datetime.now(timezone.utc)
    repo.set_status.assert_not_awaited()
