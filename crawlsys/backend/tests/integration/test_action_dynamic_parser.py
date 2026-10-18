"""Action 动态解析配置面与运行时的一致性集成测试。"""
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncEngine

from core.config import ParserConfigurationConfig, PlatformQuota
from core.sink_handlers import ResultSinkRouter
from core.stream_queue import EnqueueResult
from models import BusTask
from models.action import Action
from models.action_parser import (
    ActionParserRevision,
    ActionParserRevisionSample,
    ActionParserSample,
)
from models.platform import platformSource
from models.task_config import (
    DatabaseSourceConfig,
    RedisStreamSinkConfig,
    SinkConfig,
    TaskConfig,
)
from parser.definition import FieldMapping, ParserDefinition, ParserOutput
from parser.parser import GeneralParser
from parser.registry import ParserRegistry
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.repository import ActionParserRepository
from services.parser_configuration.service import ActionParserService
from storage import SQLAlchemyDB
from worker.crawler import CrawlerWorker
from worker.work_item import ItemDisposition, SourceBatch, WorkItem


def _definition(**constants: str) -> ParserDefinition:
    return ParserDefinition(
        schema_version=1,
        record_path="/items",
        output=ParserOutput(mode="json"),
        fields=(
            FieldMapping(target="/id", source="/id"),
            *(FieldMapping(target=f"/{key}", value=value) for key, value in constants.items()),
        ),
    )


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def read_raw(self, key: str) -> bytes:
        return self.objects[key]

    async def read_redacted(self, key: str) -> bytes:
        return self.objects[key]


class MemorySource:
    def __init__(self, on_fetch: Callable[[], Awaitable[None]] | None = None) -> None:
        self.failures: list[tuple[Exception, bool]] = []
        self._on_fetch = on_fetch

    async def fetch(self) -> SourceBatch:
        if self._on_fetch is not None:
            await self._on_fetch()
        return SourceBatch([WorkItem({}, "1")])

    async def complete(self, _item: WorkItem) -> ItemDisposition:
        return ItemDisposition.SUCCEEDED

    async def fail(
        self, _item: WorkItem, error: Exception, *, deterministic: bool
    ) -> ItemDisposition:
        self.failures.append((error, deterministic))
        return ItemDisposition.FAILED


class MemoryQueue:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def enqueue(self, _sink, params, _metadata) -> EnqueueResult:
        self.records.append(params)
        return EnqueueResult(True, False, str(len(self.records)))


class Limiter:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def record_success(self) -> None:
        pass


@pytest_asyncio.fixture
async def parser_db(tmp_path):
    database = SQLAlchemyDB("", "", "", 0, ":memory:", amode=True, driver="sqlite")
    engine = database.engine
    assert isinstance(engine, AsyncEngine)
    public_db = tmp_path / "parser-public.sqlite3"

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


async def _seed_action(db, *, action_name: str = "detail") -> Action:
    async with db.asession_scope() as session:
        platform = platformSource(
            bs_name="test", bs_platform_code=f"test-{uuid4().hex}"
        )
        session.add(platform)
        await session.flush()
        action = Action(
            bs_id=platform.bs_id,
            ba_action=action_name,
            ba_params_schema='{"type":"object"}',
            ba_sample_safe=True,
        )
        session.add(action)
        await session.flush()
        return action


async def _seed_sample(db, action: Action, store: MemoryObjectStore, raw: bytes):
    digest = hashlib.sha256(raw).hexdigest()
    raw_key = f"actions/{action.ba_id}/{uuid4().hex}/raw.json"
    redacted_key = raw_key.replace("raw.json", "redacted.json")
    store.objects[raw_key] = raw
    store.objects[redacted_key] = raw
    async with db.asession_scope() as session:
        sample = ActionParserSample(
            ba_id=action.ba_id,
            request_params_redacted={},
            request_params_hmac_sha256="b" * 64,
            request_hmac_key_version="v1",
            raw_object_key=raw_key,
            redacted_object_key=redacted_key,
            response_sha256=digest,
            response_bytes=len(raw),
            sanitizer_version="v1",
            rpc_duration_ms=1,
        )
        session.add(sample)
        await session.flush()
        return sample


def _service(db, store: MemoryObjectStore) -> ActionParserService:
    return ActionParserService(
        repository=ActionParserRepository(db),
        rpc=cast(object, None),
        limiter_for=cast(object, None),
        rate_limiter=cast(object, None),
        object_store=cast(object, store),
        config=ParserConfigurationConfig(sample_hmac_key="test-key"),
    )


async def _publish(service, action, sample, definition):
    draft = await service.create_draft(
        ba_id=action.ba_id,
        definition=definition.model_dump(mode="json", exclude_none=True),
    )
    preview = await service.preview(
        ba_id=action.ba_id,
        revision_id=draft.revision_id,
        expected_lock_version=draft.lock_version,
        sample_ids=[sample.sample_id],
    )
    published = await service.publish(
        ba_id=action.ba_id, revision_id=draft.revision_id
    )
    return published, preview


def _worker(db, action, queue, source, registry, rpc_result):
    class Rpc:
        async def invoke(self, *_args, **_kwargs):
            return rpc_result

    parser = GeneralParser(registry)
    router = ResultSinkRouter(
        db=db,
        pipeline=cast(object, None),
        parser=parser,
        stream_queue=queue,
        persist_results=True,
    )
    return CrawlerWorker(
        rpc=Rpc(),
        repo=cast(object, None),
        pipeline=cast(object, None),
        db=db,
        default_quota=PlatformQuota(platform="default", rps=0),
        source_factory=lambda *_: source,
        runtime_repository=ActionParserRepository(db),
        sink_router=router,
    )


def _redis_task(action: Action, *fields: str) -> BusTask:
    return BusTask(
        task_id=1,
        ba_id=action.ba_id,
        platform="test",
        action=action.ba_action,
        config=TaskConfig(
            sink=RedisStreamSinkConfig(
                stream="crawler:{detail}:stream",
                param_map={field: field for field in ("id", *fields)},
            )
        ),
    )


@pytest.mark.asyncio
async def test_publish_b_is_loaded_by_real_worker_on_next_execution(parser_db):
    action = await _seed_action(parser_db)
    store = MemoryObjectStore()
    sample = await _seed_sample(
        parser_db, action, store, b'{"items":[{"id":"c1"}]}'
    )
    service = _service(parser_db, store)
    queue = MemoryQueue()
    source = MemorySource()
    worker = _worker(
        parser_db, action, queue, source, ParserRegistry(), {"items": [{"id": "c1"}]}
    )
    task = _redis_task(action, "version")

    _, preview_a = await _publish(service, action, sample, _definition(version="A"))
    await worker.execute_business(task)
    _, preview_b = await _publish(service, action, sample, _definition(version="B"))
    await worker.execute_business(task)

    assert queue.records == [preview_a.preview[0], preview_b.preview[0]]


@pytest.mark.asyncio
async def test_running_round_keeps_revision_loaded_before_source_fetch(parser_db):
    action = await _seed_action(parser_db)
    store = MemoryObjectStore()
    sample = await _seed_sample(
        parser_db, action, store, b'{"items":[{"id":"c1"}]}'
    )
    service = _service(parser_db, store)
    _, preview_a = await _publish(service, action, sample, _definition(version="A"))
    draft_b = await service.create_draft(
        ba_id=action.ba_id,
        definition=_definition(version="B").model_dump(
            mode="json", exclude_none=True
        ),
    )
    preview_b = await service.preview(
        ba_id=action.ba_id,
        revision_id=draft_b.revision_id,
        expected_lock_version=draft_b.lock_version,
        sample_ids=[sample.sample_id],
    )

    published_b = False

    async def publish_b() -> None:
        nonlocal published_b
        if published_b:
            return
        await service.publish(ba_id=action.ba_id, revision_id=draft_b.revision_id)
        published_b = True

    queue = MemoryQueue()
    worker = _worker(
        parser_db,
        action,
        queue,
        MemorySource(publish_b),
        ParserRegistry(),
        {"items": [{"id": "c1"}]},
    )

    await worker.execute_business(_redis_task(action, "version"))
    await worker.execute_business(_redis_task(action, "version"))

    assert queue.records == [preview_a.preview[0], preview_b.preview[0]]


@pytest.mark.asyncio
async def test_archive_falls_back_to_static_parser_on_next_execution(parser_db):
    action = await _seed_action(parser_db)
    store = MemoryObjectStore()
    sample = await _seed_sample(
        parser_db, action, store, b'{"items":[{"id":"c1"}]}'
    )
    service = _service(parser_db, store)
    published, _ = await _publish(
        service, action, sample, _definition(source="dynamic")
    )
    registry = ParserRegistry()

    @registry.register("test", "detail")
    def static_parser(_raw):
        return [{"id": "c1", "source": "static"}]

    queue = MemoryQueue()
    worker = _worker(
        parser_db,
        action,
        queue,
        MemorySource(),
        registry,
        {"items": [{"id": "c1"}]},
    )
    task = _redis_task(action, "source")

    await worker.execute_business(task)
    await service.archive(ba_id=action.ba_id, revision_id=published.revision_id)
    await worker.execute_business(task)

    assert [record["source"] for record in queue.records] == ["dynamic", "static"]


@pytest.mark.asyncio
async def test_corrupt_published_fails_closed_before_source_and_rpc(parser_db):
    action = await _seed_action(parser_db)
    async with parser_db.asession_scope() as session:
        session.add(
            ActionParserRevision(
                ba_id=action.ba_id,
                revision_no=1,
                status="published",
                definition={"secret": "broken"},
                definition_sha256="c" * 64,
                source="manual",
            )
        )
    source_called = False

    def source_factory(*_args):
        nonlocal source_called
        source_called = True
        return MemorySource()

    worker = CrawlerWorker(
        rpc=cast(object, None),
        repo=cast(object, None),
        pipeline=cast(object, None),
        db=parser_db,
        default_quota=PlatformQuota(platform="default", rps=0),
        source_factory=source_factory,
        runtime_repository=ActionParserRepository(parser_db),
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await worker.execute_business(_redis_task(action))

    assert caught.value.code == "parser_definition_invalid"
    assert source_called is False
    assert "broken" not in str(caught.value)


@pytest.mark.asyncio
async def test_restore_requires_new_preview_before_publish(parser_db):
    action = await _seed_action(parser_db)
    store = MemoryObjectStore()
    sample = await _seed_sample(
        parser_db, action, store, b'{"items":[{"id":"c1"}]}'
    )
    service = _service(parser_db, store)
    repository = ActionParserRepository(parser_db)
    published, _ = await _publish(service, action, sample, _definition(version="A"))
    await service.archive(ba_id=action.ba_id, revision_id=published.revision_id)

    restored = await service.restore(
        ba_id=action.ba_id, revision_id=published.revision_id
    )
    assert restored.validation_report is None
    assert await repository.list_validation_samples(restored.revision_id) == []
    with pytest.raises(ParserConfigurationError):
        await service.publish(ba_id=action.ba_id, revision_id=restored.revision_id)

    await service.preview(
        ba_id=action.ba_id,
        revision_id=restored.revision_id,
        expected_lock_version=restored.lock_version,
        sample_ids=[sample.sample_id],
    )
    republished = await service.publish(
        ba_id=action.ba_id, revision_id=restored.revision_id
    )
    assert republished.status == "published"


@pytest.mark.asyncio
async def test_direct_multi_record_is_deterministic_and_not_retried(parser_db):
    action = await _seed_action(parser_db)
    store = MemoryObjectStore()
    sample = await _seed_sample(
        parser_db, action, store, b'{"items":[{"id":"1"},{"id":"2"}]}'
    )
    service = _service(parser_db, store)
    await _publish(service, action, sample, _definition())
    source = MemorySource()
    worker = _worker(
        parser_db,
        action,
        MemoryQueue(),
        source,
        ParserRegistry(),
        {"items": [{"id": "1"}, {"id": "2"}]},
    )
    task = BusTask(
        task_id=2,
        ba_id=action.ba_id,
        platform="test",
        action="detail",
        config=TaskConfig(
            source=DatabaseSourceConfig(table="seed", key_column="id"),
            sink=SinkConfig(mode="direct", result_column="payload"),
        ),
    )

    result = await worker.execute_business(task)

    assert result.failed == 1
    assert len(source.failures) == 1
    error, deterministic = source.failures[0]
    assert getattr(error, "code", None) == "direct_requires_single_record"
    assert deterministic is True
