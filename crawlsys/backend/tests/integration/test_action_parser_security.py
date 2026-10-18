"""Action 动态解析跨 API、日志与对象存储边界安全回归。"""
from __future__ import annotations

import hashlib
import json
import logging
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncEngine

from api.main import create_app
from core.config import McpConfig, ParserConfigurationConfig, PlatformQuota, SchedulerConfig
from core.sink_handlers import ResultSinkRouter
from models import BusTask
from models.action import Action
from models.action_parser import (
    ActionParserRevision,
    ActionParserRevisionSample,
    ActionParserSample,
)
from models.llm_provider import LlmProvider, ProviderProtocol
from models.platform import platformSource
from models.task_config import SinkConfig, TaskConfig
from parser.definition import FieldMapping, ParserDefinition, ParserOutput
from services.parser_configuration.assistant import (
    AssistantActionParserService,
    ParserSuggestion,
)
from services.parser_configuration.repository import ActionParserRepository
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.storage import ParserSampleObjectStore
from storage import SQLAlchemyDB
from worker.crawler import CrawlerWorker
from worker.work_item import SourceBatch


SERVICE_LOG_FIELDS = {
    "ba_id",
    "platform",
    "action",
    "sample_id",
    "revision_id",
    "revision_no",
    "rpc_duration_ms",
    "ai_duration_ms",
    "response_bytes",
    "source_records",
    "valid_records",
    "invalid_records",
    "error_code",
}
WORKER_LOG_FIELDS = {
    "ba_id",
    "platform",
    "action",
    "parser_source",
    "parser_revision_id",
}
SINK_LOG_FIELDS = WORKER_LOG_FIELDS | {"source_records", "valid_records"}


class ObjectStore:
    def __init__(self, objects: dict[str, bytes], *, delete_error: Exception | None = None):
        self.objects = objects
        self.delete_error = delete_error

    async def read_redacted(self, key: str) -> bytes:
        return self.objects[key]

    async def read_raw(self, key: str) -> bytes:
        return self.objects[key]

    async def delete_pair(self, _raw_key: str, _redacted_key: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error


class CapturingLogger:
    def __init__(self, events: list[tuple[str, str, dict]], fields=None):
        self.events = events
        self.fields = fields or {}

    def bind(self, **fields):
        return CapturingLogger(self.events, {**self.fields, **fields})

    def _record(self, level: str, message: str, **_kwargs):
        self.events.append((level, message, self.fields))

    def info(self, message: str, **kwargs):
        self._record("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._record("warning", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._record("error", message, **kwargs)


@pytest_asyncio.fixture
async def security_db(tmp_path):
    database = SQLAlchemyDB("", "", "", 0, ":memory:", amode=True, driver="sqlite")
    engine = database.engine
    assert isinstance(engine, AsyncEngine)
    public_db = tmp_path / "security-public.sqlite3"

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public_schema(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    await database.aconnect()
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Action.metadata.create_all(
                sync_connection,
                tables=[
                    cast(Table, platformSource.__table__),
                    cast(Table, Action.__table__),
                    cast(Table, BusTask.__table__),
                    cast(Table, ActionParserSample.__table__),
                    cast(Table, ActionParserRevision.__table__),
                    cast(Table, ActionParserRevisionSample.__table__),
                ],
            )
        )
    try:
        yield database
    finally:
        await database.aclose()


async def _seed_actions_and_sample(db, secret: str):
    raw_key = f"actions/1/{secret}/raw.json"
    redacted_key = f"actions/1/{secret}/redacted.json"
    redacted = b'{"token":"<redacted:token>"}'
    async with db.asession_scope() as session:
        platform = platformSource(
            bs_name="test", bs_platform_code=f"test-{uuid4().hex}"
        )
        session.add(platform)
        await session.flush()
        first = Action(
            bs_id=platform.bs_id,
            ba_action="detail",
            ba_params_schema='{"type":"object"}',
            ba_sample_safe=True,
        )
        second = Action(
            bs_id=platform.bs_id,
            ba_action="search",
            ba_params_schema='{"type":"object"}',
            ba_sample_safe=True,
        )
        session.add_all([first, second])
        await session.flush()
        sample = ActionParserSample(
            ba_id=first.ba_id,
            request_params_redacted={},
            request_params_hmac_sha256="a" * 64,
            request_hmac_key_version="v1",
            raw_object_key=raw_key,
            redacted_object_key=redacted_key,
            response_sha256=hashlib.sha256(redacted).hexdigest(),
            response_bytes=len(redacted),
            sanitizer_version="v1",
            rpc_duration_ms=1,
        )
        revision = ActionParserRevision(
            ba_id=first.ba_id,
            revision_no=1,
            status="archived",
            definition={
                "schema_version": 1,
                "output": {"mode": "json"},
                "fields": [{"target": "/id", "value": "safe"}],
            },
            definition_sha256="b" * 64,
            source="manual",
        )
        session.add_all([sample, revision])
        await session.flush()
        return first, second, sample, revision, raw_key, redacted_key, redacted


def _service(db, store) -> AssistantActionParserService:
    class RateLimiter:
        async def require(self, **_kwargs) -> None:
            return None

    class Assistant:
        async def suggest(self, **_kwargs) -> ParserSuggestion:
            definition = ParserDefinition(
                schema_version=1,
                output=ParserOutput(mode="json"),
                fields=(FieldMapping(target="/id", value="safe"),),
            )
            return ParserSuggestion(
                definition=definition,
                model_id=7,
                model_name="test-model",
                prompt_version="test-v1",
                duration_ms=1,
                attempts=1,
                redacted_sample_sha256="c" * 64,
            )

    return AssistantActionParserService(
        repository=ActionParserRepository(db),
        rpc=cast(object, None),
        limiter_for=cast(object, None),
        rate_limiter=cast(object, RateLimiter()),
        object_store=cast(object, store),
        config=ParserConfigurationConfig(
            sample_hmac_key="test-key", assist_receipt_key="receipt-key"
        ),
        assistant=cast(object, Assistant()),
    )


@pytest.mark.asyncio
async def test_real_api_cross_action_ids_are_404_and_object_keys_never_leak(security_db):
    secret = "raw-token-123"
    first, second, sample, revision, raw_key, redacted_key, redacted = (
        await _seed_actions_and_sample(security_db, secret)
    )
    service = _service(
        security_db, ObjectStore({raw_key: redacted, redacted_key: redacted})
    )
    app = create_app(SchedulerConfig(mcp=McpConfig(enabled=False)))
    app.state.action_parser_service = service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        detail = await client.get(
            f"/api/crawler/actions/{first.ba_id}/parser-samples/{sample.sample_id}"
        )
        wrong_sample = await client.get(
            f"/api/crawler/actions/{second.ba_id}/parser-samples/{sample.sample_id}"
        )
        wrong_revision = await client.get(
            f"/api/crawler/actions/{second.ba_id}/parser-revisions/{revision.revision_id}"
        )

    assert detail.status_code == 200
    assert wrong_sample.status_code == 404
    assert wrong_revision.status_code == 404
    exposed = detail.text + wrong_sample.text + wrong_revision.text
    assert secret not in exposed
    assert "raw_object_key" not in exposed
    assert "redacted_object_key" not in exposed
    parser_paths = [
        path.split("/")
        for route in app.routes
        if "parser" in (path := getattr(route, "path", ""))
    ]
    assert all("raw" not in parts and "objects" not in parts for parts in parser_paths)


@pytest.mark.asyncio
async def test_real_assistant_signature_is_accepted_through_api_dependency(security_db):
    first, _, sample, _, raw_key, redacted_key, redacted = (
        await _seed_actions_and_sample(security_db, "receipt-object-key")
    )
    service = _service(
        security_db, ObjectStore({raw_key: redacted, redacted_key: redacted})
    )
    definition = ParserDefinition(
        schema_version=1,
        output=ParserOutput(mode="json"),
        fields=(FieldMapping(target="/id", value="safe"),),
    )
    draft = await service.create_draft(
        ba_id=first.ba_id,
        definition=definition.model_dump(mode="json", exclude_unset=True),
    )
    assisted = await service.assist(
        ba_id=first.ba_id,
        revision_id=draft.revision_id,
        expected_lock_version=draft.lock_version,
        sample_id=sample.sample_id,
        model_id=7,
        output=definition.output,
    )
    app = create_app(SchedulerConfig(mcp=McpConfig(enabled=False)))
    app.state.action_parser_service = service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            f"/api/crawler/actions/{first.ba_id}/parser-revisions/{draft.revision_id}",
            json={
                "lock_version": draft.lock_version,
                "definition": definition.model_dump(
                    mode="json", exclude_unset=True
                ),
                "assist_receipt": assisted.assist_receipt,
            },
        )

    assert response.status_code == 200
    assert response.json()["source"] == "ai"


@pytest.mark.asyncio
async def test_real_service_worker_and_sink_logs_only_bind_allowlisted_fields(
    security_db, monkeypatch
):
    secret = "object-key-secret"
    first, _, sample, _, raw_key, redacted_key, redacted = await _seed_actions_and_sample(
        security_db, secret
    )
    events: list[tuple[str, str, dict]] = []
    logger = CapturingLogger(events)
    import core.sink_handlers as sink_module
    import services.parser_configuration.service as service_module
    import worker.crawler as worker_module

    monkeypatch.setattr(service_module, "logger", logger)
    monkeypatch.setattr(worker_module, "logger", logger)
    monkeypatch.setattr(sink_module, "logger", logger)

    service = _service(
        security_db,
        ObjectStore(
            {raw_key: redacted, redacted_key: redacted},
            delete_error=RuntimeError(f"delete {secret}"),
        ),
    )
    with pytest.raises(Exception):
        await service.delete_sample(ba_id=first.ba_id, sample_id=sample.sample_id)

    class EmptySource:
        async def fetch(self):
            return SourceBatch([])

    worker = CrawlerWorker(
        rpc=cast(object, None),
        repo=cast(object, None),
        pipeline=cast(object, None),
        db=security_db,
        default_quota=PlatformQuota(platform="default", rps=0),
        source_factory=lambda *_: EmptySource(),
        runtime_repository=ActionParserRepository(security_db),
    )
    task = BusTask(
        task_id=99,
        ba_id=first.ba_id,
        platform="test",
        action="detail",
        config=TaskConfig(sink=SinkConfig(mode="none")),
    )
    await worker.execute_business(task)
    await ResultSinkRouter(
        db=security_db,
        pipeline=cast(object, None),
        stream_queue=cast(object, None),
        persist_results=True,
    ).persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="none"),
        raw={"body": secret, "prompt": secret, "model_output": secret},
        item=SimpleNamespace(entity_id=None),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert events
    allowed_by_message = {
        "parser_sample_cleanup_failed": SERVICE_LOG_FIELDS,
        "Crawler action round complete": WORKER_LOG_FIELDS,
        "Crawler sink parser selected": SINK_LOG_FIELDS,
    }
    for _level, message, fields in events:
        assert set(fields) <= allowed_by_message[message]
        assert secret not in message
        assert secret not in json.dumps(fields, ensure_ascii=False)


def test_hmac_receipt_and_provider_keys_do_not_enter_repr_or_log(caplog):
    secrets = ("hmac-secret", "receipt-secret", "provider-secret")
    config = ParserConfigurationConfig(
        sample_hmac_key=secrets[0], assist_receipt_key=secrets[1]
    )
    provider = LlmProvider(
        name="test",
        litellm_prefix="openai",
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        api_key=secrets[2],
        base_url=None,
    )
    logging.getLogger("parser-security").info("config=%r provider=%r", config, provider)
    exposed = repr(config) + repr(provider) + caplog.text
    for secret in secrets:
        assert secret not in exposed


@pytest.mark.asyncio
async def test_private_bucket_rejects_anonymous_policy():
    from unittest.mock import AsyncMock, MagicMock

    minio = MagicMock(abucket_exists=AsyncMock(return_value=True))
    minio.client.get_bucket_policy.return_value = '{"Statement":[{}]}'
    store = ParserSampleObjectStore(
        minio, bucket="parser-samples", sse_enabled=True, storage_ready=True
    )
    with pytest.raises(ParserConfigurationError) as caught:
        await store.write_pair(ba_id=7, raw=b"{}", redacted=b"{}")
    assert getattr(caught.value, "code", None) == "parser_storage_not_private"
    minio.aput_object.assert_not_called()
