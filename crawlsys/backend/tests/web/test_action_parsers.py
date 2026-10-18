"""Action parser configuration API contract tests."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.crawler.action_parsers import (
    FIELD_TYPES,
    model_field_target,
    parser_value_types,
)
from api.main import create_app
from core.config import (
    McpConfig,
    ParserConfigurationConfig,
    PlatformQuota,
    SchedulerConfig,
)
from parser.definition import ParserDefinition, ParserOutput
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.repository import ActionContext, ActionParserRepository
from services.parser_configuration.service import ActionParserService
from services.parser_configuration.assistant import AssistantActionParserService


DEFINITION = {
    "schema_version": 1,
    "record_path": "/data",
    "output": {"mode": "json"},
    "fields": [{"target": "/id", "source": "/id"}],
}


def _sample(sample_id: int = 3):
    return SimpleNamespace(
        sample_id=sample_id,
        ba_id=7,
        request_params_redacted={"cursor": 1},
        request_params_hmac_sha256="hmac",
        request_hmac_key_version="v1",
        raw_object_key="private/raw.json",
        redacted_object_key="private/redacted.json",
        response_sha256="a" * 64,
        response_bytes=128,
        sanitizer_version="v1",
        rpc_duration_ms=12,
        created_at=datetime(2026, 8, 11, 8, 0, 0),
    )


def _revision(
    revision_id: int = 11,
    *,
    status: str = "draft",
    definition: dict[str, object] | None = None,
):
    return SimpleNamespace(
        revision_id=revision_id,
        ba_id=7,
        revision_no=2,
        status=status,
        definition=DEFINITION if definition is None else definition,
        definition_sha256="b" * 64,
        source="manual",
        source_sample_id=None,
        restored_from_revision_id=None,
        validation_report=None,
        lock_version=2,
        generation_metadata=None,
        created_at=datetime(2026, 8, 11, 8, 0, 0),
        updated_at=datetime(2026, 8, 11, 8, 1, 0),
        published_at=None,
    )


@pytest.fixture
def parser_service():
    service = AsyncMock()
    service.create_sample.return_value = _sample()
    service.list_samples.return_value = [_sample()]
    service.get_sample_detail.return_value = (
        _sample(),
        {"data": [{"id": "safe"}]},
    )
    service.create_draft.return_value = _revision()
    service.get_revision.return_value = _revision()
    service.list_revisions.return_value = [_revision()]
    service.patch_draft.return_value = _revision()
    service.preview.return_value = SimpleNamespace(
        definition_sha256="b" * 64,
        samples=({"sample_id": 3, "sample_sha256": "a" * 64},),
        sample_ids=(3,),
        source_records=1,
        valid_records=1,
        invalid_records=0,
        passed=True,
        errors=(),
        errors_truncated=False,
        preview=({"id": "safe"},),
    )
    service.publish.return_value = _revision(status="published")
    service.archive.return_value = _revision(status="archived")
    service.restore.return_value = _revision(revision_id=12)
    service.assist.return_value = SimpleNamespace(
        definition=ParserDefinition.model_validate(DEFINITION),
        preview=({"id": "safe"},),
        assist_receipt="signed-receipt",
    )
    service.suggest_initial.return_value = SimpleNamespace(
        definition=ParserDefinition.model_validate(DEFINITION),
        preview=({"id": "safe"},),
        assist_receipt="signed-receipt",
    )
    return service


@pytest.fixture
def app(parser_service):
    application = create_app(SchedulerConfig(mcp=McpConfig(enabled=False)))
    application.state.action_parser_service = parser_service
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


def test_parser_routes_are_nested_under_action(client, parser_service):
    response = client.post(
        "/api/crawler/actions/7/parser-samples",
        json={"params": {"cursor": 1}, "confirm_side_effect": True},
    )
    assert response.status_code == 201
    parser_service.create_sample.assert_awaited_once_with(
        ba_id=7,
        params={"cursor": 1},
        confirm_side_effect=True,
    )


def test_cross_action_sample_is_404_not_disclosed(client, parser_service):
    parser_service.get_sample_detail.side_effect = ParserConfigurationError(
        "sample_not_found", "样例不存在", status_code=404
    )
    response = client.get("/api/crawler/actions/7/parser-samples/99")
    assert response.status_code == 404
    assert response.json() == {
        "code": "sample_not_found",
        "message": "样例不存在",
        "details": {},
    }


def test_revision_lifecycle_paths_are_explicit(app):
    routes = (
        item
        for route in app.routes
        for item in (
            route.effective_route_contexts()
            if hasattr(route, "effective_route_contexts")
            else (route,)
        )
    )
    paths = {
        path for route in routes if (path := getattr(route, "path", ""))
    }
    base = "/api/crawler/actions/{ba_id}/parser-revisions/{revision_id}"
    assert {
        "/api/crawler/actions/{ba_id}/parser-revisions",
        base,
        f"{base}/preview",
        f"{base}/assist",
        f"{base}/publish",
        f"{base}/archive",
        f"{base}/restore",
    }.issubset(paths)


def test_parser_capabilities_expose_model_field_contract(client):
    payload = client.get("/api/crawler/parser-capabilities").json()

    assert payload["model_datatypes"] == [
        "challenge",
        "comment",
        "content",
        "follow",
        "job",
        "media",
        "user",
    ]
    assert payload["field_types"] == [
        "string",
        "integer",
        "number",
        "boolean",
        "datetime",
        "object",
        "array",
    ]
    content_fields = {
        item["target"]: item for item in payload["model_fields"]["content"]
    }
    assert "/content_id" in content_fields
    assert content_fields["/content_id"]["required"] is False
    assert content_fields["/content_id"]["value_types"] == ["string"]
    assert "/datatype" not in content_fields
    assert list(content_fields) == sorted(content_fields)


def test_model_field_metadata_is_conservative_for_any_and_escapes_target():
    assert parser_value_types(Any) == list(FIELD_TYPES)
    assert model_field_target("a/b~c") == "/a~1b~0c"


def test_assist_returns_candidate_and_receipt(client, parser_service):
    response = client.post(
        "/api/crawler/actions/7/parser-revisions/11/assist",
        json={
            "lock_version": 2,
            "sample_id": 3,
            "model_id": 4,
            "output": {"mode": "json"},
        },
    )
    assert response.status_code == 201
    assert response.json()["definition"]["schema_version"] == 1
    assert response.json()["assist_receipt"] == "signed-receipt"
    parser_service.assist.assert_awaited_once_with(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        sample_id=3,
        model_id=4,
        output=ParserOutput(mode="json"),
    )


def test_initial_suggestion_route_returns_candidate_without_revision(
    client, parser_service
):
    response = client.post(
        "/api/crawler/actions/7/parser-suggestions",
        json={"sample_id": 3, "model_id": 4, "output": {"mode": "json"}},
    )
    assert response.status_code == 201
    assert response.json()["assist_receipt"] == "signed-receipt"
    parser_service.suggest_initial.assert_awaited_once_with(
        ba_id=7, sample_id=3, model_id=4, output=ParserOutput(mode="json")
    )


def test_revision_create_forwards_optional_receipt(client, parser_service):
    response = client.post(
        "/api/crawler/actions/7/parser-revisions",
        json={"definition": DEFINITION, "assist_receipt": "create-receipt"},
    )
    assert response.status_code == 201
    parser_service.create_draft.assert_awaited_once_with(
        ba_id=7,
        definition=ParserDefinition.model_validate(DEFINITION),
        assist_receipt="create-receipt",
    )


def test_parser_definition_responses_preserve_unset_semantics(
    client, parser_service
):
    suggested = client.post(
        "/api/crawler/actions/7/parser-suggestions",
        json={"sample_id": 3, "model_id": 4, "output": {"mode": "json"}},
    ).json()["definition"]
    created = client.post(
        "/api/crawler/actions/7/parser-revisions",
        json={"definition": DEFINITION},
    ).json()["definition"]
    revision = client.get(
        "/api/crawler/actions/7/parser-revisions/11"
    ).json()["definition"]
    assisted = client.post(
        "/api/crawler/actions/7/parser-revisions/11/assist",
        json={
            "lock_version": 2,
            "sample_id": 3,
            "model_id": 4,
            "output": {"mode": "json"},
        },
    ).json()["definition"]

    for definition in (suggested, created, revision, assisted):
        field = definition["fields"][0]
        assert field == {"target": "/id", "source": "/id"}
        assert "value" not in field
        assert "default" not in field


def test_parser_definition_unset_semantics_preserve_explicit_null(
    client,
    parser_service,
):
    explicit_null = {
        **DEFINITION,
        "fields": [{"target": "/id", "source": "/id", "default": None}],
    }
    parser_service.get_revision.return_value = _revision(definition=explicit_null)

    field = client.get(
        "/api/crawler/actions/7/parser-revisions/11"
    ).json()["definition"]["fields"][0]

    assert "default" in field
    assert field["default"] is None
    assert "value" not in field


def test_assist_checks_owned_sample_before_ai_availability(client, parser_service):
    parser_service.assist.side_effect = ParserConfigurationError(
        "sample_not_found", "sample not found", status_code=404
    )
    response = client.post(
        "/api/crawler/actions/7/parser-revisions/11/assist",
        json={
            "lock_version": 2,
            "sample_id": 99,
            "model_id": 4,
            "output": {"mode": "json"},
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "sample_not_found"


def test_sample_lifecycle_statuses_and_safe_response_fields(client, parser_service):
    created = client.post(
        "/api/crawler/actions/7/parser-samples",
        json={"params": {}, "confirm_side_effect": False},
    )
    listed = client.get(
        "/api/crawler/actions/7/parser-samples", params={"offset": 0, "limit": 100}
    )
    detail = client.get("/api/crawler/actions/7/parser-samples/3")
    deleted = client.delete("/api/crawler/actions/7/parser-samples/3")

    assert (created.status_code, listed.status_code, detail.status_code) == (201, 200, 200)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert listed.json()["items"][0]["sample_id"] == 3
    assert detail.json() == {
        "sample_id": 3,
        "ba_id": 7,
        "response_sha256": "a" * 64,
        "response_bytes": 128,
        "sanitizer_version": "v1",
        "rpc_duration_ms": 12,
        "created_at": "2026-08-11T08:00:00",
        "redacted_preview": {"data": [{"id": "safe"}]},
    }
    for payload in (created.json(), listed.json()["items"][0], detail.json()):
        serialized = str(payload)
        assert "raw_object_key" not in payload
        assert "redacted_object_key" not in payload
        assert "request_params" not in serialized
        assert "private/" not in serialized
    parser_service.list_samples.assert_awaited_once_with(ba_id=7, offset=0, limit=100)
    parser_service.delete_sample.assert_awaited_once_with(ba_id=7, sample_id=3)


def test_revision_lifecycle_statuses_and_service_arguments(client, parser_service):
    created = client.post(
        "/api/crawler/actions/7/parser-revisions", json={"definition": DEFINITION}
    )
    listed = client.get(
        "/api/crawler/actions/7/parser-revisions", params={"offset": 0, "limit": 100}
    )
    detail = client.get("/api/crawler/actions/7/parser-revisions/11")
    patched = client.patch(
        "/api/crawler/actions/7/parser-revisions/11",
        json={"lock_version": 2, "definition": DEFINITION},
    )
    previewed = client.post(
        "/api/crawler/actions/7/parser-revisions/11/preview",
        json={"lock_version": 2, "sample_ids": [3]},
    )
    published = client.post("/api/crawler/actions/7/parser-revisions/11/publish")
    archived = client.post("/api/crawler/actions/7/parser-revisions/11/archive")
    restored = client.post("/api/crawler/actions/7/parser-revisions/11/restore")
    deleted = client.delete("/api/crawler/actions/7/parser-revisions/11")

    assert [
        created.status_code,
        listed.status_code,
        detail.status_code,
        patched.status_code,
        previewed.status_code,
        published.status_code,
        archived.status_code,
        restored.status_code,
        deleted.status_code,
    ] == [201, 200, 200, 200, 201, 201, 201, 201, 204]
    listed_definition = listed.json()["items"][0]["definition"]
    assert listed_definition["record_path"] == "/data"
    assert listed_definition["output"]["mode"] == "json"
    assert listed_definition["fields"][0]["source"] == "/id"
    assert deleted.content == b""
    definition = ParserDefinition.model_validate(DEFINITION)
    parser_service.create_draft.assert_awaited_once_with(
        ba_id=7,
        definition=definition,
        assist_receipt=None,
    )
    parser_service.get_revision.assert_awaited_once_with(ba_id=7, revision_id=11)
    parser_service.list_revisions.assert_awaited_once_with(ba_id=7, offset=0, limit=100)
    parser_service.patch_draft.assert_awaited_once_with(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        definition=definition,
        assist_receipt=None,
    )
    parser_service.preview.assert_awaited_once_with(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        sample_ids=[3],
    )
    parser_service.publish.assert_awaited_once_with(ba_id=7, revision_id=11)
    parser_service.archive.assert_awaited_once_with(ba_id=7, revision_id=11)
    parser_service.restore.assert_awaited_once_with(ba_id=7, revision_id=11)
    parser_service.delete_draft.assert_awaited_once_with(ba_id=7, revision_id=11)


def test_patch_forwards_assist_receipt_for_explicit_acceptance(client, parser_service):
    response = client.patch(
        "/api/crawler/actions/7/parser-revisions/11",
        json={
            "lock_version": 2,
            "definition": DEFINITION,
            "assist_receipt": "signed-receipt",
        },
    )

    assert response.status_code == 200
    parser_service.patch_draft.assert_awaited_once_with(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        definition=ParserDefinition.model_validate(DEFINITION),
        assist_receipt="signed-receipt",
    )


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/crawler/actions/7/parser-samples", {"offset": -1}),
        ("/api/crawler/actions/7/parser-samples", {"limit": 0}),
        ("/api/crawler/actions/7/parser-samples", {"limit": 101}),
        ("/api/crawler/actions/7/parser-revisions", {"offset": -1}),
        ("/api/crawler/actions/7/parser-revisions", {"limit": 0}),
        ("/api/crawler/actions/7/parser-revisions", {"limit": 101}),
    ],
)
def test_parser_list_pagination_is_bounded(client, path, params):
    assert client.get(path, params=params).status_code == 422


def test_parser_requests_forbid_unknown_user_fields(client):
    response = client.post(
        "/api/crawler/actions/7/parser-samples",
        json={"params": {}, "provider": "internal"},
    )
    assert response.status_code == 422
    assert "internal" not in response.text


def test_parser_error_details_are_allowlisted(client, parser_service):
    parser_service.get_sample_detail.side_effect = ParserConfigurationError(
        "sample_not_found",
        "sample not found",
        status_code=404,
        details={
            "sample_id": 3,
            "path": "$.cursor",
            "validator": "type",
            "retry_after_seconds": 5,
            "raw_object_key": "private/raw.json",
            "exception": "database exploded",
        },
    )
    response = client.get("/api/crawler/actions/7/parser-samples/3")
    assert response.status_code == 404
    assert response.json()["details"] == {
        "sample_id": 3,
        "path": "$.cursor",
        "validator": "type",
        "retry_after_seconds": 5,
    }
    assert "private/raw.json" not in response.text
    assert "database exploded" not in response.text


def test_parser_rate_limit_sets_retry_after(client, parser_service):
    parser_service.get_sample_detail.side_effect = ParserConfigurationError(
        "sample_rate_limited",
        "sample rate limit exceeded",
        status_code=429,
        details={"retry_after_seconds": 2.8, "exception": "secret"},
    )
    response = client.get("/api/crawler/actions/7/parser-samples/3")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
    assert response.json()["details"] == {"retry_after_seconds": 2.8}


def test_revision_detail_reads_published_revision(client, parser_service):
    parser_service.get_revision.return_value = _revision(status="published")
    response = client.get("/api/crawler/actions/7/parser-revisions/11")
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    parser_service.get_revision.assert_awaited_once_with(ba_id=7, revision_id=11)


@pytest.mark.parametrize("operation", ["archive", "restore"])
def test_cross_action_revision_lifecycle_is_404(client, parser_service, operation):
    getattr(parser_service, operation).side_effect = ParserConfigurationError(
        "revision_not_found", "revision not found", status_code=404
    )
    response = client.post(
        f"/api/crawler/actions/7/parser-revisions/99/{operation}"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "revision_not_found"


def test_malformed_parser_json_is_400(client):
    response = client.post(
        "/api/crawler/actions/7/parser-samples",
        content=b'{"params":',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


def _service_with_repository(repository):
    limiter = MagicMock()
    limiter.__aenter__ = AsyncMock(return_value=limiter)
    limiter.__aexit__ = AsyncMock(return_value=None)
    return ActionParserService(
        repository=repository,
        rpc=MagicMock(invoke=AsyncMock()),
        limiter_for=MagicMock(return_value=limiter),
        rate_limiter=MagicMock(require=AsyncMock()),
        object_store=MagicMock(
            read_raw=AsyncMock(),
            read_redacted=AsyncMock(),
            write_pair=AsyncMock(),
            delete_pair=AsyncMock(),
        ),
        config=ParserConfigurationConfig(sample_hmac_key="test-hmac"),
    )


@pytest.mark.asyncio
async def test_list_samples_validates_parent_before_repository_list():
    repository = MagicMock(
        require_action_context=AsyncMock(
            side_effect=ParserConfigurationError(
                "action_not_found", "action not found", status_code=404
            )
        ),
        list_samples=AsyncMock(),
    )
    service = _service_with_repository(repository)
    with pytest.raises(ParserConfigurationError) as caught:
        await service.list_samples(ba_id=7)
    assert caught.value.status_code == 404
    repository.list_samples.assert_not_awaited()


@pytest.mark.asyncio
async def test_assist_validates_owned_revision_and_sample_before_503():
    repository = MagicMock(
        require_action_context=AsyncMock(
            return_value=ActionContext(7, "test", "detail", {}, True)
        ),
        get_draft=AsyncMock(return_value=_revision()),
        get_sample=AsyncMock(
            side_effect=ParserConfigurationError(
                "sample_not_found", "sample not found", status_code=404
            )
        ),
    )
    service = _service_with_repository(repository)
    with pytest.raises(ParserConfigurationError) as caught:
        await service.assist(
            ba_id=7,
            revision_id=11,
            expected_lock_version=2,
            sample_id=99,
            model_id=4,
            output=ParserOutput(mode="json"),
        )
    assert caught.value.code == "sample_not_found"


@pytest.mark.asyncio
async def test_parser_semantic_errors_have_stable_status_codes():
    repository = MagicMock(
        require_action_context=AsyncMock(
            return_value=ActionContext(7, "test", "detail", {}, False)
        )
    )
    service = _service_with_repository(repository)
    with pytest.raises(ParserConfigurationError) as confirmation:
        await service.create_sample(
            ba_id=7, params={}, confirm_side_effect=False
        )
    assert confirmation.value.status_code == 409

    with pytest.raises(ParserConfigurationError) as definition:
        ActionParserRepository._validated_definition({})
    assert definition.value.status_code == 422
    assert ActionParserRepository._invalid_transition().status_code == 409


def test_production_lifespan_requires_and_builds_parser_resources(monkeypatch):
    events: list[str] = []

    class Resource:
        def __init__(self, name: str):
            self.name = name

        async def aconnect(self):
            events.append(f"{self.name}.connect")

        async def ainit_db(self):
            events.append(f"{self.name}.init")

        async def aclose(self):
            events.append(f"{self.name}.close")

    class Database(Resource):
        def asession_scope(self):
            raise AssertionError("repository sessions are not opened during startup")

    class Redis(Resource):
        def get_redis_obj(self):
            return self

    class Rpc:
        def __init__(self, *, token, config_store):
            self.token = token
            self.config_store = config_store

        async def close(self):
            events.append("rpc.close")

    class Limiter:
        def __init__(self, quota):
            self.quota = quota

    db = Database("db")
    minio = Resource("minio")
    redis = Redis("redis")
    monkeypatch.setattr("api.deps.SQLAlchemyDB", lambda **_kwargs: db)
    monkeypatch.setattr("api.deps.MinioDB", lambda **_kwargs: minio)
    monkeypatch.setattr("api.deps.RedisDB", lambda *_args, **_kwargs: redis)
    monkeypatch.setattr("api.deps.RpcClient", Rpc)
    monkeypatch.setattr("api.deps._platform_limiter_class", lambda: Limiter)
    monkeypatch.setattr(
        "api.deps.SiteSource.load_active_quotas",
        AsyncMock(return_value=[PlatformQuota(platform="known")]),
    )
    monkeypatch.setattr("api.deps.migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr("api.deps.LlmCatalog", MagicMock())
    monkeypatch.setattr("api.deps.ModelDiscoveryService", MagicMock())

    app = create_app(
        SchedulerConfig(rpc_token="rpc-secret", mcp=McpConfig(enabled=False))
    )
    with TestClient(app):
        service = app.state.action_parser_service
        assert isinstance(service, AssistantActionParserService)
        assert service._rpc.token == "rpc-secret"
        assert service._limiter_for("known").quota.platform == "known"
        assert service._limiter_for("unknown").quota.platform == "default"
        assert service._rate_limiter._redis is redis
        assert service._object_store._minio is minio

    assert events == [
        "db.connect",
        "db.init",
        "redis.connect",
        "rpc.close",
        "redis.close",
        "minio.close",
        "db.close",
    ]
    assert app.state.action_parser_service is None

    incomplete_redis = Resource("incomplete_redis")
    monkeypatch.setattr(
        "api.deps.RedisDB", lambda *_args, **_kwargs: incomplete_redis
    )
    incomplete_app = create_app(SchedulerConfig(mcp=McpConfig(enabled=False)))
    with pytest.raises(AttributeError, match="get_redis_obj"):
        with TestClient(incomplete_app):
            pass
