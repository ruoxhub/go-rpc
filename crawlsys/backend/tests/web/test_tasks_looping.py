"""Loop settings regressions and target JSON contract tests for task routes."""
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.crawler import tasks as task_routes
from models.task import BusTask, TaskPriority, TaskStatus
from models.task_config import VideoAnalysisTaskConfig, VideoDownloadTaskConfig
from runtime_config.models import SchedulerSettings


_apply_loop_settings = task_routes._apply_loop_settings
_parse_params_columns = task_routes._parse_params_columns


class TaskApiFixture:
    def __init__(self, client, repo, catalog, session):
        self.client = client
        self.repo = repo
        self.catalog = catalog
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
        "priority": 2,
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
    repo.find_by_id = AsyncMock(return_value=None)
    repo.save = AsyncMock()

    async def save_in_session(_session, item):
        return await repo.save(item)

    repo.save_in_session = AsyncMock(side_effect=save_in_session)
    repo.delete = AsyncMock()
    repo.set_status = AsyncMock(return_value=True)
    repo.batch_set_status = AsyncMock(return_value=0)
    repo.pause = AsyncMock(return_value=True)
    repo.resume = AsyncMock(return_value=True)
    repo.update_priority = AsyncMock(return_value=None)
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
        yield TaskApiFixture(client, repo, catalog, session)
    finally:
        app.dependency_overrides.clear()
        client.close()

VALID_TASK = {
    "ba_id": 1,
    "ref_table": "",
    "ref_where": "",
    "params_columns": "",
    "entity_column": "",
    "result_column": "",
    "post_update_column": "",
    "post_update_table": "",
    "sink_mode": "auto",
    "loop_enabled": False,
    "loop_interval_seconds": None,
}


def test_apply_loop_settings_resets_done_status_to_pending():
    task = BusTask(platform="p", action="a", status=TaskStatus.DONE)
    _apply_loop_settings(task, True, None)
    assert task.status == TaskStatus.PENDING
    assert task.loop_enabled is True
    assert task.loop_interval_seconds is None


def test_apply_loop_settings_enables_task_with_custom_interval():
    task = BusTask(platform="p", action="a")
    _apply_loop_settings(task, True, 120)
    assert task.loop_enabled is True
    assert task.loop_interval_seconds == 120


def test_apply_loop_settings_keeps_interval_empty_for_global_default():
    task = BusTask(platform="p", action="a")
    _apply_loop_settings(task, True, None)
    assert task.loop_interval_seconds is None


def test_apply_loop_settings_clears_schedule_when_disabled():
    task = BusTask(
        platform="p",
        action="a",
        loop_enabled=True,
        loop_interval_seconds=60,
    )
    task.next_run_at = object()
    _apply_loop_settings(task, False, 120)
    assert task.loop_enabled is False
    assert task.loop_interval_seconds is None
    assert task.next_run_at is None


@pytest.mark.parametrize(
    "params_columns",
    [
        "user_id as safe_alias\nmalicious_tail",
        "safe_column\nmalicious_tail as user_id",
    ],
)
def test_parse_params_columns_rejects_malicious_identifier_suffix(params_columns):
    with pytest.raises(ValueError):
        _parse_params_columns(params_columns, "id")


def test_task_list_uses_platform_filter_and_json_envelope(task_api):
    client, repo = task_api
    repo.find_all.return_value = []
    response = client.get("/api/crawler/tasks", params={"platform": "tiktok"})
    assert response.status_code == 200
    assert "items" in response.json()


def test_create_task_uses_json_and_created_status(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )
    response = client.post("/api/crawler/tasks", json=VALID_TASK)
    assert response.status_code == 201
    assert response.json()["ba_id"] == 1


def test_create_task_defaults_priority_to_normal(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post("/api/crawler/tasks", json=VALID_TASK)

    assert response.status_code == 201
    assert repo.save.await_args.args[0].priority == 2
    assert response.json()["priority"] == "normal"


def test_create_task_accepts_string_priority(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json={**VALID_TASK, "priority": "urgent"},
    )

    assert response.status_code == 201
    assert repo.save.await_args.args[0].priority == 4
    assert response.json()["priority"] == "urgent"


def test_create_task_round_trips_structured_redis_source(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json={
            "ba_id": 1,
            "loop_enabled": True,
            "execution_mode": "invoke_action",
            "source": {
                "type": "redis_stream",
                "stream": "crawler:{video-detail}:stream",
                "group": "video-detail",
                "dead_letter_stream": "crawler:{video-detail}:dlq",
            },
            "sink": {"type": "database", "mode": "standard"},
        },
    )

    assert response.status_code == 201
    saved = repo.save.await_args.args[0]
    assert saved.config.source.type == "redis_stream"
    assert saved.config.execution_mode == "invoke_action"
    assert response.json()["config"]["source"]["group"] == "video-detail"
    assert response.json()["config"]["source"]["type"] == "redis_stream"
    assert response.json()["config"]["sink"]["type"] == "database"
    assert all(
        "information_schema.columns" not in str(call.args[0])
        for call in task_api.session.execute.await_args_list
    )


def test_video_download_retry_config_create_and_update_round_trip(task_api):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )
    initial = {
        "max_attempts": 7,
        "claim_timeout_seconds": 900,
        "retry_base_seconds": 30,
        "retry_max_seconds": 600,
    }

    created = client.post(
        "/api/crawler/tasks",
        json={**VALID_TASK, "executor": "video_download", "download": initial},
    )

    assert created.status_code == 201
    task = repo.save.await_args.args[0]
    assert task.config.download == VideoDownloadTaskConfig(**initial)
    assert created.json()["config"]["download"] == {
        "batch_size": 50,
        "min_grade": 3,
        "use_proxy": True,
        "rps": 0.0,
        **initial,
    }

    updated_values = {
        "max_attempts": 9,
        "claim_timeout_seconds": 1200,
        "retry_base_seconds": 45,
        "retry_max_seconds": 900,
    }
    repo.find_by_id.return_value = task
    changed = client.put(
        "/api/crawler/tasks/7",
        json={
            **VALID_TASK,
            "executor": "video_download",
            "download": updated_values,
        },
    )

    assert changed.status_code == 200
    assert task.config.download == VideoDownloadTaskConfig(**updated_values)
    assert changed.json()["config"]["download"] == {
        "batch_size": 50,
        "min_grade": 3,
        "use_proxy": True,
        "rps": 0.0,
        **updated_values,
    }


@pytest.mark.parametrize(
    ("structured_field", "legacy_field", "expected_message"),
    [
        (
            "source",
            {"ref_table": "seed", "entity_column": "id"},
            "source 不能与旧数据源字段同时提交",
        ),
        (
            "sink",
            {"sink_mode": "none"},
            "sink 不能与旧结果字段同时提交",
        ),
    ],
)
def test_create_task_rejects_mixed_structured_and_legacy_io(
    task_api,
    structured_field,
    legacy_field,
    expected_message,
):
    client, repo = task_api
    structured = {
        "source": {
            "type": "redis_stream",
            "stream": "crawler:{detail}:stream",
            "group": "detail",
            "dead_letter_stream": "crawler:{detail}:dlq",
        },
        "sink": {"type": "database", "mode": "standard"},
    }

    response = client.post(
        "/api/crawler/tasks",
        json={
            "ba_id": 1,
            structured_field: structured[structured_field],
            **legacy_field,
        },
    )

    assert response.status_code == 422
    assert expected_message in str(response.json()["detail"])
    repo.save.assert_not_awaited()


@pytest.mark.parametrize(
    ("structured_field", "legacy_field", "expected_message"),
    [
        (
            "source",
            {"ref_table": "seed", "entity_column": "id"},
            "source 不能与旧数据源字段同时提交",
        ),
        (
            "sink",
            {"sink_mode": "none"},
            "sink 不能与旧结果字段同时提交",
        ),
    ],
)
def test_create_task_rejects_null_structured_and_legacy_io(
    task_api,
    structured_field,
    legacy_field,
    expected_message,
):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json={"ba_id": 1, structured_field: None, **legacy_field},
    )

    assert response.status_code == 422
    assert expected_message in str(response.json()["detail"])
    repo.save.assert_not_awaited()


def test_create_publish_source_round_trips_completion(task_api):
    client, repo = task_api
    task_api.session.execute.return_value.fetchall.return_value = [
        ("id",),
        ("keyword",),
        ("published",),
    ]
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json={
            "ba_id": 7,
            "execution_mode": "publish_source",
            "source": {
                "type": "database",
                "table": "t_busi_search_keyword",
                "key_column": "id",
                "param_map": {"keyword": "keyword"},
                "completion": {"column": "published", "value": True},
            },
            "sink": {
                "type": "redis_stream",
                "stream": "crawler:{search}:stream",
                "param_map": {"keyword": "keyword"},
            },
        },
    )

    assert response.status_code == 201
    saved = repo.save.await_args.args[0]
    assert saved.config.execution_mode == "publish_source"
    assert response.json()["config"]["execution_mode"] == "publish_source"
    assert response.json()["config"]["source"]["completion"] == {
        "column": "published",
        "value": True,
    }
    assert response.json()["config"]["sink"]["stream"] == (
        "crawler:{search}:stream"
    )
    assert response.json()["config"]["sink"]["param_map"] == {
        "keyword": "keyword"
    }


def test_publish_source_rejects_missing_completion_column(task_api):
    client, repo = task_api
    task_api.session.execute.return_value.fetchall.return_value = [
        ("id",),
        ("keyword",),
    ]
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )

    response = client.post(
        "/api/crawler/tasks",
        json={
            "ba_id": 7,
            "execution_mode": "publish_source",
            "source": {
                "type": "database",
                "table": "t_busi_search_keyword",
                "key_column": "id",
                "param_map": {"keyword": "keyword"},
                "completion": {"column": "missing_column"},
            },
            "sink": {
                "type": "redis_stream",
                "stream": "crawler:{search}:stream",
                "param_map": {"keyword": "keyword"},
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "完成标记列不存在"
    repo.save.assert_not_awaited()


@pytest.mark.parametrize("review_route", ["R", "G", None])
def test_create_video_analysis_task_keeps_explicit_review_route(
    task_api,
    review_route,
):
    client, repo = task_api
    repo.save.side_effect = lambda item: (
        setattr(item, "task_id", 7),
        setattr(item, "platform_id", 1),
        setattr(item, "created_at", datetime.now()),
        setattr(item, "updated_at", datetime.now()),
    )
    response = client.post(
        "/api/crawler/tasks",
        json={
            **VALID_TASK,
            "executor": "video_analysis",
            "llm_model_id": 23,
            "review_route": review_route,
        },
    )

    assert response.status_code == 201
    saved = repo.save.await_args.args[0]
    assert saved.config.executor == "video_analysis"
    assert saved.config.analysis == VideoAnalysisTaskConfig(
        llm_model_id=23,
        review_route=review_route,
    )
    assert response.json()["config"]["analysis"]["llm_model_id"] == 23
    assert response.json()["config"]["analysis"]["review_route"] == review_route


@pytest.mark.parametrize("review_route", ["R", "G", None])
def test_update_video_analysis_task_keeps_explicit_review_route(
    task_api,
    review_route,
):
    client, repo = task_api
    initial_route = "R" if review_route is None else None
    task = _task(
        config=task_routes.TaskConfig(
            executor="video_analysis",
            analysis=VideoAnalysisTaskConfig(review_route=initial_route),
        )
    )
    repo.find_by_id.return_value = task

    changed = client.put(
        "/api/crawler/tasks/7",
        json={
            **VALID_TASK,
            "executor": "video_analysis",
            "review_route": review_route,
        },
    )
    assert changed.status_code == 200
    assert task.config.analysis.review_route == review_route
    assert changed.json()["config"]["analysis"]["review_route"] == review_route


def test_update_video_analysis_task_omitted_review_route_keeps_existing_value(
    task_api,
):
    client, repo = task_api
    task = _task(
        config=task_routes.TaskConfig(
            executor="video_analysis",
            analysis=VideoAnalysisTaskConfig(review_route="R"),
        )
    )
    repo.find_by_id.return_value = task

    response = client.put(
        "/api/crawler/tasks/7",
        json={
            **VALID_TASK,
            "executor": "video_analysis",
        },
    )
    assert response.status_code == 200
    assert task.config.analysis.review_route == "R"
    assert response.json()["config"]["analysis"]["review_route"] == "R"


def test_task_api_rejects_invalid_review_route(task_api):
    client, _repo = task_api

    response = client.post(
        "/api/crawler/tasks",
        json={
            **VALID_TASK,
            "executor": "video_analysis",
            "review_route": "B",
        },
    )

    assert response.status_code == 422


def test_switching_task_to_rpc_clears_review_route(task_api):
    client, repo = task_api
    task = _task(
        config=task_routes.TaskConfig(
            executor="video_analysis",
            analysis=VideoAnalysisTaskConfig(review_route="R"),
        )
    )
    repo.find_by_id.return_value = task

    response = client.put(
        "/api/crawler/tasks/7",
        json={**VALID_TASK, "executor": "rpc_crawl"},
    )

    assert response.status_code == 200
    assert task.config.executor == "rpc_crawl"
    assert task.config.analysis.review_route is None


def test_rpc_task_rejects_model_override(task_api):
    client, _repo = task_api

    response = client.post(
        "/api/crawler/tasks",
        json={**VALID_TASK, "llm_model_id": 23},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/crawler/tasks"),
        ("put", "/api/crawler/tasks/7"),
    ],
)
def test_non_download_task_rejects_top_level_download_config(
    task_api,
    method,
    path,
):
    client, repo = task_api
    if method == "put":
        repo.find_by_id.return_value = _task()

    response = getattr(client, method)(
        path,
        json={
            **VALID_TASK,
            "executor": "rpc_crawl",
            "download": {"batch_size": 20, "min_grade": 2, "use_proxy": False},
        },
    )

    assert response.status_code == 422
    repo.save.assert_not_awaited()


def test_create_video_analysis_rejects_unusable_model(task_api):
    client, _repo = task_api
    task_api.catalog.get_model.return_value = None

    response = client.post(
        "/api/crawler/tasks",
        json={
            **VALID_TASK,
            "executor": "video_analysis",
            "llm_model_id": 404,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "指定的分析模型不存在或不可用"


def test_create_task_rejects_incomplete_source_config(task_api):
    client, _repo = task_api
    response = client.post(
        "/api/crawler/tasks",
        json={**VALID_TASK, "ref_table": "t_content"},
    )
    assert response.status_code == 422


def test_create_task_rejects_non_positive_loop_interval(task_api):
    client, _repo = task_api
    response = client.post(
        "/api/crawler/tasks",
        json={**VALID_TASK, "loop_enabled": True, "loop_interval_seconds": 0},
    )
    assert response.status_code == 422


def test_get_task_returns_json_resource(task_api):
    client, repo = task_api
    repo.find_by_id.return_value = _task()
    response = client.get("/api/crawler/tasks/7")
    assert response.status_code == 200
    assert response.json()["task_id"] == 7


def test_patch_priority_allows_running_task_and_returns_resource(task_api):
    client, repo = task_api
    repo.update_priority.return_value = _task(
        priority=4,
        status=TaskStatus.RUNNING,
    )

    response = client.patch(
        "/api/crawler/tasks/7/priority",
        json={"priority": "urgent"},
    )

    assert response.status_code == 200
    assert response.json()["priority"] == "urgent"
    repo.update_priority.assert_awaited_once_with(7, TaskPriority.URGENT)


def test_patch_priority_is_idempotent(task_api):
    client, repo = task_api
    repo.update_priority.return_value = _task(priority=3)

    first = client.patch(
        "/api/crawler/tasks/7/priority",
        json={"priority": "high"},
    )
    second = client.patch(
        "/api/crawler/tasks/7/priority",
        json={"priority": "high"},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["priority"] == second.json()["priority"] == "high"
    assert repo.update_priority.await_count == 2


def test_patch_priority_returns_not_found(task_api):
    client, _repo = task_api

    response = client.patch(
        "/api/crawler/tasks/404/priority",
        json={"priority": "normal"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


@pytest.mark.parametrize("priority", [4, "critical", False])
def test_patch_priority_rejects_invalid_wire_values(task_api, priority):
    client, repo = task_api

    response = client.patch(
        "/api/crawler/tasks/7/priority",
        json={"priority": priority},
    )

    assert response.status_code == 422
    repo.update_priority.assert_not_awaited()


def test_update_task_uses_put_json_and_returns_updated_resource(task_api):
    client, repo = task_api
    repo.find_by_id.return_value = _task()
    response = client.put(
        "/api/crawler/tasks/7",
        json={
            **VALID_TASK,
            "loop_enabled": True,
            "loop_interval_seconds": 120,
        },
    )
    assert response.status_code == 200
    assert response.json()["task_id"] == 7
    assert response.json()["loop_enabled"] is True
    assert response.json()["loop_interval_seconds"] == 120


def test_update_task_omitted_priority_preserves_existing_value(task_api):
    client, repo = task_api
    task = _task(priority=4)
    repo.find_by_id.return_value = task
    repo.save.return_value = task

    response = client.put("/api/crawler/tasks/7", json=VALID_TASK)

    assert response.status_code == 200
    assert task.priority == 4
    assert response.json()["priority"] == "urgent"


def test_update_task_changes_explicit_priority(task_api):
    client, repo = task_api
    task = _task(priority=4)
    repo.find_by_id.return_value = task
    repo.save.return_value = task

    response = client.put(
        "/api/crawler/tasks/7",
        json={**VALID_TASK, "priority": "low"},
    )

    assert response.status_code == 200
    assert task.priority == 1
    assert response.json()["priority"] == "low"


@pytest.mark.parametrize("priority", [0, 4, "critical", True])
def test_task_write_api_rejects_non_string_or_unknown_priority(task_api, priority):
    client, repo = task_api

    response = client.post(
        "/api/crawler/tasks",
        json={**VALID_TASK, "priority": priority},
    )

    assert response.status_code == 422
    repo.save.assert_not_awaited()


def test_update_task_returns_not_found_when_task_disappears_during_save(task_api):
    client, repo = task_api
    repo.find_by_id.return_value = _task()
    repo.save.return_value = None

    response = client.put("/api/crawler/tasks/7", json=VALID_TASK)

    assert response.status_code == 404


def test_start_task_returns_updated_resource(task_api):
    client, repo = task_api
    task = _task(status=TaskStatus.PAUSED)
    repo.find_by_id.return_value = task

    async def resume(task_id, *, next_run_at):
        task.status = TaskStatus.PENDING
        task.next_run_at = next_run_at
        return True

    repo.resume.side_effect = resume
    response = client.post("/api/crawler/tasks/7/start")
    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.PENDING
    repo.resume.assert_awaited_once_with(7, next_run_at=None)


def test_pause_task_returns_updated_resource(task_api):
    client, repo = task_api
    task = _task(status=TaskStatus.RUNNING)
    repo.find_by_id.return_value = task

    async def pause(task_id):
        task.pause_requested = True
        return True

    repo.pause.side_effect = pause
    response = client.post("/api/crawler/tasks/7/pause")
    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.RUNNING
    assert response.json()["pause_requested"] is True
    repo.pause.assert_awaited_once_with(7)


def test_update_missing_task_returns_not_found(task_api):
    client, repo = task_api
    repo.find_by_id.return_value = None
    response = client.put("/api/crawler/tasks/999", json=VALID_TASK)
    assert response.status_code == 404


def test_delete_task_returns_no_content(task_api):
    client, repo = task_api
    repo.find_by_id.return_value = _task()
    response = client.delete("/api/crawler/tasks/7")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_missing_task_returns_not_found(task_api):
    client, repo = task_api
    repo.find_by_id.return_value = None
    response = client.delete("/api/crawler/tasks/999")
    assert response.status_code == 404


def test_batch_start_accepts_optional_platform_json(task_api):
    client, repo = task_api
    repo.batch_set_status.return_value = 3
    response = client.post("/api/crawler/tasks/start-all", json={"platform": "tiktok"})
    assert response.status_code == 200
    assert "updated_count" in response.json()


def test_batch_pause_accepts_empty_json(task_api):
    client, repo = task_api
    repo.batch_set_status.return_value = 4
    response = client.post("/api/crawler/tasks/pause-all", json={})
    assert response.status_code == 200
    assert "updated_count" in response.json()


def test_table_columns_metadata_is_structured_json(task_api):
    client, _repo = task_api
    response = client.get(
        "/api/crawler/tasks/meta/table-columns",
        params={"table_name": "t_content"},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["columns"], list)


def test_action_schema_metadata_is_structured_json(task_api):
    client, _repo = task_api
    response = client.get("/api/crawler/tasks/meta/action-schemas/1")
    assert response.status_code == 200
    assert isinstance(response.json()["schema"], list)


def test_action_schema_metadata_returns_json_schema_object(task_api):
    client, _repo = task_api
    action_repo = task_routes.ActionRepo(None)
    action_repo.get_schema.return_value = {
        "type": "object",
        "properties": {"keyword": {"type": "string"}},
    }

    response = client.get("/api/crawler/tasks/meta/action-schemas/1")
    assert response.status_code == 200
    assert response.json()["schema"]["type"] == "object"


def test_action_schema_metadata_preserves_boolean_schema(task_api):
    client, _repo = task_api
    action_repo = task_routes.ActionRepo(None)
    action_repo.get_schema.return_value = False

    response = client.get("/api/crawler/tasks/meta/action-schemas/1")
    assert response.status_code == 200
    assert response.json()["schema"] is False


@pytest.mark.asyncio
async def test_llm_model_metadata_returns_only_repository_results():
    model = SimpleNamespace(
        id=8,
        display_name="Claude Sonnet",
        litellm_model="anthropic/claude-sonnet",
    )
    session = MagicMock()
    session.scalars = AsyncMock(return_value=[model])
    db = MagicMock()

    @asynccontextmanager
    async def session_scope():
        yield session

    db.asession_scope = session_scope
    response = await task_routes.get_usable_llm_models(db)

    assert response.llm_models[0].id == 8
    statement = session.scalars.await_args.args[0]
    assert "t_llm_provider.enabled IS true" in str(statement)
    assert "t_llm_model.remote_available IS true" in str(statement)
