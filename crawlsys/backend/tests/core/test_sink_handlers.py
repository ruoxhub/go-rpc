"""Tests for result sink routing."""

import inspect
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from core import sink_handlers
from core.sink_handlers import (
    DirectSinkHandler,
    NoneSinkHandler,
    ResultSinkRouter,
    SinkResult,
    SinkValidationError,
    StandardSinkHandler,
)
from core.stream_queue import EnqueueResult
from models import BusTask
from models.task_config import (
    DatabaseSourceCompletionConfig,
    DatabaseSourceConfig,
    RedisStreamSinkConfig,
    SinkConfig,
    TaskConfig,
)
from parser.definition import FieldMapping, ParserDefinition, ParserOutput
from parser.exceptions import ConfiguredParserError, ParserNotFoundError
from parser.parser import GeneralParser
from parser.registry import ParserRegistry
from worker.work_item import WorkItem


@pytest.fixture
def task():
    return BusTask(task_id=7, platform="test", action="detail")


@pytest.fixture
def publish_source_task():
    return BusTask(
        task_id=8,
        platform="test",
        action="search",
        config=TaskConfig(
            execution_mode="publish_source",
            source=DatabaseSourceConfig(
                table="seed",
                key_column="id",
                completion=DatabaseSourceCompletionConfig(column="published"),
            ),
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "keyword"},
            ),
        ),
    )


@pytest.fixture
def dependencies():
    parser = MagicMock()
    pipeline = MagicMock(process_items=AsyncMock())
    stream_queue = MagicMock(enqueue=AsyncMock())
    return MagicMock(), parser, pipeline, stream_queue


def make_router(dependencies, *, persist_results=True):
    db, parser, pipeline, stream_queue = dependencies
    return ResultSinkRouter(
        db=db,
        pipeline=pipeline,
        parser=parser,
        stream_queue=stream_queue,
        persist_results=persist_results,
    )


def async_context(value):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=value)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.fixture
def json_definition():
    return ParserDefinition(
        schema_version=1,
        record_path="/items",
        output=ParserOutput(mode="json"),
        fields=(FieldMapping(target="/id", source="/id"),),
    )


@pytest.fixture
def model_definition():
    return ParserDefinition(
        schema_version=1,
        record_path="/items",
        output=ParserOutput(mode="model", datatype="content"),
        fields=(FieldMapping(target="/content_id", source="/id"),),
    )


@pytest.mark.asyncio
async def test_router_standard_sink_uses_parser_and_pipeline(
    monkeypatch, task, dependencies
):
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "test", "content_id": "v1"}])
    model = object()
    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "test", lambda **_: model)

    result = await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="standard"),
        raw={"items": []},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=1)
    pipeline.process_items.assert_awaited_once_with([model])


def test_sink_module_does_not_depend_on_crawler_worker():
    source_code = Path("app/core/sink_handlers.py").read_text(encoding="utf-8")
    assert "CrawlerWorker" not in source_code
    for handler in (StandardSinkHandler, DirectSinkHandler, NoneSinkHandler):
        assert "worker" not in inspect.signature(handler.handle).parameters


def test_sink_module_has_no_legacy_worker_dispatch_adapter():
    source_code = Path("app/core/sink_handlers.py").read_text(encoding="utf-8")
    assert "_LegacySinkDispatchAdapter" not in source_code


@pytest.mark.asyncio
async def test_router_standard_dry_run_parses_without_pipeline(task, dependencies):
    router = make_router(dependencies, persist_results=False)
    _, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "content"}, {"datatype": "media"}])

    result = await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="standard"),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=2)
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_standard_sink_empty_parse_returns_zero_without_pipeline(
    task, dependencies
):
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([])

    result = await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="standard"),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult()
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_standard_sink_unknown_datatype_counts_without_pipeline(
    task, dependencies
):
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "not-registered"}])

    result = await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="standard"),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=1)
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_none_sink_returns_zero(task, dependencies):
    result = await make_router(dependencies).persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="none"),
        raw={},
            item=WorkItem({}, "v1"),
            parser_definition=None,
            parser_revision_id=None,
        )

    assert result == SinkResult()


@pytest.mark.asyncio
async def test_standard_sink_marks_done_after_pipeline(monkeypatch, task, dependencies):
    router = make_router(dependencies)
    db, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "test"}])
    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "test", lambda **_: object())
    events = []
    pipeline.process_items.side_effect = lambda _: events.append("pipeline")
    probe_result = MagicMock(scalar=MagicMock(return_value="integer"))
    probe_session = MagicMock(execute=AsyncMock(return_value=probe_result))
    update_session = MagicMock()
    update_session.execute = AsyncMock(side_effect=lambda *_: events.append("mark_done"))
    db.asession_scope.side_effect = [
        async_context(probe_session),
        async_context(update_session),
    ]

    await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(mode="standard", mark_done_column="published"),
            raw={},
            item=WorkItem({}, "9"),
            parser_definition=None,
            parser_revision_id=None,
        )

    assert events == ["pipeline", "mark_done"]
    assert update_session.execute.await_args.args[1] == {"eid": 9}


@pytest.mark.asyncio
async def test_standard_sink_fills_platform_from_task_when_missing(
    monkeypatch, task, dependencies
):
    router = make_router(dependencies)
    db, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "test", "content_id": "123"}])
    created_models = []

    class DummyModel:
        platform = None

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.platform = kwargs.get("platform")
            created_models.append(self)

    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "test", DummyModel)

    result = await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="standard"),
        raw={},
        item=WorkItem({}, "1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=1)
    assert len(created_models) == 1
    assert created_models[0].platform == task.platform


@pytest.mark.asyncio
async def test_standard_sink_does_not_mark_done_when_pipeline_fails(
    monkeypatch, task, dependencies
):
    router = make_router(dependencies)
    db, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "test"}])
    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "test", lambda **_: object())
    pipeline.process_items.side_effect = RuntimeError("pipeline failed")

    with pytest.raises(RuntimeError, match="pipeline failed"):
        await router.persist(
            task=task,
            source=DatabaseSourceConfig(table="seed", key_column="id"),
            sink=SinkConfig(mode="standard", mark_done_column="published"),
            raw={},
            item=WorkItem({}, "9"),
            parser_definition=None,
            parser_revision_id=None,
        )

    db.asession_scope.assert_not_called()


@pytest.mark.asyncio
async def test_direct_sink_updates_result_then_marks_done(task, dependencies):
    router = make_router(dependencies)
    db, parser, _, _ = dependencies
    parser.parse.return_value = iter([{"ok": True}])
    events = []
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=lambda statement, *_: events.append(
            "mark_done" if "published" in str(statement) else "result"
        )
    )
    db.asession_scope.return_value = async_context(session)

    result = await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(
            mode="direct",
            result_column="result",
            mark_done_column="published",
        ),
        raw={"ok": True},
        item=WorkItem({}, "9"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=1)
    assert events == ["result", "mark_done"]
    assert session.execute.await_args_list[0].args[1] == {
        "val": '{"ok":true}',
        "eid": "9",
    }
    assert session.execute.await_args_list[1].args[1] == {"eid": "9"}
    db.asession_scope.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_statement", [1, 2])
async def test_direct_sink_result_and_mark_done_failures_roll_back_atomically(
    task, failing_statement
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    class Database:
        @asynccontextmanager
        async def asession_scope(self):
            async with sessions() as session, session.begin():
                calls = 0
                original_execute = session.execute

                async def execute(statement, params=None):
                    nonlocal calls
                    calls += 1
                    if calls == failing_statement:
                        raise RuntimeError("database write failed")
                    return await original_execute(statement, params or {})

                yield SimpleNamespace(execute=execute)

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE seed (id TEXT PRIMARY KEY, result TEXT, published BOOLEAN DEFAULT false)"
            )
        )
        await connection.execute(text("INSERT INTO seed (id) VALUES ('9')"))

    registry = ParserRegistry()

    @registry.register_direct(task.platform, task.action)
    def parse_direct(_raw):
        return [{"ok": True}]

    router = ResultSinkRouter(
        db=Database(),
        pipeline=MagicMock(),
        parser=GeneralParser(registry),
        stream_queue=MagicMock(),
        persist_results=True,
    )
    try:
        with pytest.raises(RuntimeError, match="database write failed"):
            await router.persist(
                task=task,
                source=DatabaseSourceConfig(table="seed", key_column="id"),
                sink=SinkConfig(
                    mode="direct",
                    result_column="result",
                    mark_done_column="published",
                ),
                raw={},
                item=WorkItem({}, "9"),
                parser_definition=None,
                parser_revision_id=None,
            )

        async with sessions() as session:
            row = (await session.execute(text("SELECT result, published FROM seed"))).one()
        assert row == (None, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_direct_sink_dry_run_parses_without_database_write(task, dependencies):
    router = make_router(dependencies, persist_results=False)
    db, parser, _, _ = dependencies
    parser.parse.return_value = iter([{"ok": True}])

    result = await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(
            mode="direct", result_column="result", mark_done_column="published"
        ),
        raw={"ok": True},
        item=WorkItem({}, "9"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=1)
    parser.parse.assert_called_once_with(
        task.platform,
        {"ok": True},
        task.action,
        definition=None,
        as_dto=False,
    )
    db.asession_scope.assert_not_called()


@pytest.mark.asyncio
async def test_direct_sink_requires_result_column_and_source(task, dependencies):
    router = make_router(dependencies)
    with pytest.raises(ValueError, match="result_column"):
        await router.persist(
            task=task,
            source=None,
            sink=SinkConfig(mode="direct"),
            raw={},
            item=WorkItem({}, "9"),
            parser_definition=None,
            parser_revision_id=None,
        )
    with pytest.raises(ValueError, match="direct_requires_source_key"):
        await router.persist(
            task=task,
            source=None,
            sink=SinkConfig(mode="direct", result_column="result"),
            raw={},
            item=WorkItem({}, "9"),
            parser_definition=None,
            parser_revision_id=None,
        )


@pytest.mark.asyncio
async def test_direct_sink_ignores_item_without_entity_id(task, dependencies):
    router = make_router(dependencies)
    db, parser, _, _ = dependencies

    result = await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="direct", result_column="result"),
        raw={"ok": True},
        item=WorkItem({}),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult()
    parser.parse.assert_not_called()
    db.asession_scope.assert_not_called()


@pytest.mark.asyncio
async def test_direct_sink_rejects_unregistered_parser(task, dependencies):
    router = make_router(dependencies)
    _, parser, _, _ = dependencies
    parser.parse.side_effect = ParserNotFoundError(task.platform, task.action)

    with pytest.raises(ValueError, match="parser_not_found"):
        await router.persist(
            task=task,
            source=DatabaseSourceConfig(table="seed", key_column="id"),
            sink=SinkConfig(mode="direct", result_column="result"),
            raw={},
            item=WorkItem({}, "9"),
            parser_definition=None,
            parser_revision_id=None,
        )


@pytest.mark.asyncio
async def test_redis_sink_maps_parser_records_to_downstream_params(task, dependencies):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies
    parser.parse.return_value = iter(
        [
            {"content_id": "v1", "datatype": "social"},
            {"content_id": "v2", "datatype": "social"},
        ]
    )
    stream_queue.enqueue.side_effect = [
        EnqueueResult(True, False, "1-0"),
        EnqueueResult(False, True, None),
    ]

    result = await router.persist(
        task=task,
        source=DatabaseSourceConfig(
            table="seed",
            key_column="id",
            completion=DatabaseSourceCompletionConfig(column="published"),
        ),
        sink=RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={"content_id": "item_id"},
        ),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=2, produced=1, deduplicated=1)
    assert [call.args[1] for call in stream_queue.enqueue.await_args_list] == [
        {"item_id": "v1"},
        {"item_id": "v2"},
    ]
    metadata = stream_queue.enqueue.await_args_list[0].args[2]
    assert metadata["producer_task_id"] == "7"
    assert metadata["producer_platform"] == "test"
    assert metadata["producer_action"] == "detail"
    assert "produced_at" in metadata
    assert "raw" not in metadata


@pytest.mark.asyncio
async def test_redis_sink_counts_partially_invalid_records_as_skipped(task, dependencies):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies
    parser.parse.return_value = iter([{"content_id": "v1"}, {"other": "secret"}])
    stream_queue.enqueue.return_value = EnqueueResult(True, False, "1-0")

    result = await router.persist(
        task=task,
        source=None,
        sink=RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={"content_id": "item_id"},
        ),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=2, produced=1, skipped=1)


@pytest.mark.asyncio
async def test_redis_sink_rejects_all_invalid_records_before_enqueue(task, dependencies):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies
    parser.parse.return_value = iter([{"token": "super-secret"}])

    with pytest.raises(SinkValidationError) as error:
        await router.persist(
            task=task,
            source=None,
            sink=RedisStreamSinkConfig(
                stream="crawler:{detail}:stream",
                param_map={"content_id": "item_id"},
            ),
            raw={},
            item=WorkItem({}, "v1"),
            parser_definition=None,
            parser_revision_id=None,
        )

    assert error.value.code == "no_valid_downstream_params"
    assert "super-secret" not in str(error.value)
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_work_item_maps_and_validates_without_parser(
    publish_source_task, dependencies
):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies
    stream_queue.enqueue.return_value = EnqueueResult(True, False, "1-0")
    sink = RedisStreamSinkConfig(
        stream="crawler:{search}:stream",
        param_map={"keyword": "query"},
    )

    result = await router.publish_work_item(
        task=publish_source_task,
        sink=sink,
        item=WorkItem(params={"keyword": "cats"}, entity_id="9"),
        params_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )

    parser.parse.assert_not_called()
    stream_queue.enqueue.assert_awaited_once()
    assert stream_queue.enqueue.await_args.args[1] == {"query": "cats"}
    assert result == SinkResult(processed=1, produced=1)


@pytest.mark.asyncio
async def test_publish_work_item_validation_error_is_path_only(
    publish_source_task, dependencies
):
    router = make_router(dependencies)
    _, _, _, stream_queue = dependencies
    secret = "credential-that-must-not-leak"

    with pytest.raises(ValueError, match=r"query") as error:
        await router.publish_work_item(
            task=publish_source_task,
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "query"},
            ),
            item=WorkItem(params={"keyword": secret}, entity_id="9"),
            params_schema={
                "type": "object",
                "properties": {"query": {"type": "integer"}},
                "required": ["query"],
            },
        )

    assert secret not in str(error.value)
    assert error.value.__cause__ is None
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_work_item_validates_legacy_list_schema_without_value_leak(
    publish_source_task, dependencies
):
    router = make_router(dependencies)
    _, _, _, stream_queue = dependencies
    secret = "credential-that-must-not-leak"

    with pytest.raises(ValueError, match=r"query") as error:
        await router.publish_work_item(
            task=publish_source_task,
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "query"},
            ),
            item=WorkItem(params={"keyword": secret}, entity_id="9"),
            params_schema=[{"name": "query", "type": "integer", "required": True}],
        )

    assert secret not in str(error.value)
    assert error.value.__cause__ is None
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_work_item_rejects_unsupported_schema_without_leak(
    publish_source_task, dependencies, caplog
):
    router = make_router(dependencies)
    _, _, _, stream_queue = dependencies
    secret = "unsupported-schema-secret"

    with pytest.raises(SinkValidationError) as error:
        await router.publish_work_item(
            task=publish_source_task,
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "query"},
            ),
            item=WorkItem(params={"keyword": "cats"}, entity_id="9"),
            params_schema=secret,
        )

    assert error.value.code == "invalid_downstream_schema"
    assert secret not in str(error.value)
    assert secret not in caplog.text
    assert error.value.__cause__ is None
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_work_item_rejects_schema_error_without_leak(
    publish_source_task, dependencies, caplog
):
    router = make_router(dependencies)
    _, _, _, stream_queue = dependencies
    secret = "invalid-schema-secret"

    with pytest.raises(SinkValidationError) as error:
        await router.publish_work_item(
            task=publish_source_task,
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "query"},
            ),
            item=WorkItem(params={"keyword": "cats"}, entity_id="9"),
            params_schema={"type": secret},
        )

    assert error.value.code == "invalid_downstream_schema"
    assert secret not in str(error.value)
    assert secret not in caplog.text
    assert error.value.__cause__ is None
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_work_item_rejects_duplicate_legacy_parameter_names(
    publish_source_task, dependencies
):
    router = make_router(dependencies)
    _, _, _, stream_queue = dependencies

    with pytest.raises(SinkValidationError) as error:
        await router.publish_work_item(
            task=publish_source_task,
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "query"},
            ),
            item=WorkItem(params={"keyword": "cats"}, entity_id="9"),
            params_schema=[{"name": "query"}, {"name": "query"}],
        )

    assert error.value.code == "invalid_downstream_schema"
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_sink_empty_parser_result_does_not_enqueue(task, dependencies):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies
    parser.parse.return_value = iter([])

    result = await router.persist(
        task=task,
        source=None,
        sink=RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={"content_id": "item_id"},
        ),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult()
    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_sink_materializes_parser_before_enqueue(task, dependencies):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies

    def records():
        yield {"content_id": "v1"}
        raise RuntimeError("parser failed")

    parser.parse.return_value = records()
    with pytest.raises(RuntimeError, match="parser failed"):
        await router.persist(
            task=task,
            source=None,
            sink=RedisStreamSinkConfig(
                stream="crawler:{detail}:stream",
                param_map={"content_id": "item_id"},
            ),
            raw={},
            item=WorkItem({}, "v1"),
            parser_definition=None,
            parser_revision_id=None,
        )

    stream_queue.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_sink_dry_run_maps_without_enqueue(task, dependencies):
    router = make_router(dependencies, persist_results=False)
    _, parser, _, stream_queue = dependencies
    parser.parse.return_value = iter([{"content_id": "v1"}])

    result = await router.persist(
        task=task,
        source=None,
        sink=RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={"content_id": "item_id"},
        ),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    assert result == SinkResult(processed=1)
    stream_queue.enqueue.assert_not_awaited()


def test_sink_result_adds_each_counter():
    assert SinkResult(processed=2, skipped=1) + SinkResult(
        produced=3, deduplicated=1
    ) == SinkResult(processed=2, produced=3, deduplicated=1, skipped=1)


@pytest.mark.asyncio
async def test_dynamic_model_runs_parser_then_orm_then_pipeline(
    monkeypatch, task, dependencies, model_definition
):
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter([{"datatype": "content", "content_id": "c1"}])
    model = object()
    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "content", lambda **record: model)

    await router.persist(
        task=task,
        source=None,
        sink=SinkConfig(mode="standard"),
        raw={"items": [{"id": "c1"}]},
        item=WorkItem({}, "c1"),
        parser_definition=model_definition,
        parser_revision_id=4,
    )

    parser.parse.assert_called_once_with(
        task.platform,
        {"items": [{"id": "c1"}]},
        task.action,
        definition=model_definition,
        as_dto=False,
    )
    pipeline.process_items.assert_awaited_once_with([model])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("definition_fixture", "sink"),
    [
        ("model_definition", SinkConfig(mode="direct", result_column="payload")),
        ("json_definition", SinkConfig(mode="standard")),
        ("json_definition", SinkConfig(mode="auto")),
    ],
)
async def test_dynamic_database_sink_rejects_incompatible_matrix_before_dispatch(
    request, task, dependencies, definition_fixture, sink
):
    definition = request.getfixturevalue(definition_fixture)
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies

    with pytest.raises(SinkValidationError) as caught:
        await router.persist(
            task=task,
            source=DatabaseSourceConfig(table="seed", key_column="id"),
            sink=sink,
            raw={"token": "must-not-leak"},
            item=WorkItem({}, "1"),
            parser_definition=definition,
            parser_revision_id=4,
        )

    assert caught.value.code == "parser_sink_incompatible"
    assert "must-not-leak" not in str(caught.value)
    parser.parse.assert_not_called()
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("construction_error", [TypeError, ValueError])
async def test_dynamic_model_construction_error_is_stable_and_secret_free(
    monkeypatch, task, dependencies, model_definition, construction_error
):
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies
    parser.parse.return_value = iter(
        [{"datatype": "content", "content_id": "must-not-leak"}]
    )

    def reject_record(**_record):
        raise construction_error("must-not-leak")

    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "content", reject_record)

    with pytest.raises(SinkValidationError) as caught:
        await router.persist(
            task=task,
            source=None,
            sink=SinkConfig(mode="standard"),
            raw={},
            item=WorkItem({}, "1"),
            parser_definition=model_definition,
            parser_revision_id=4,
        )

    assert caught.value.code == "model_construction_failed"
    assert "must-not-leak" not in str(caught.value)
    assert caught.value.__cause__ is None
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_dynamic_json_direct_multiple_records_never_writes_or_marks(
    task, dependencies, json_definition
):
    router = make_router(dependencies)
    db, parser, _, _ = dependencies
    parser.parse.return_value = iter([{"id": 1}, {"id": 2}])

    with pytest.raises(sink_handlers.SinkValidationError) as caught:
        await router.persist(
            task=task,
            source=DatabaseSourceConfig(table="seed", key_column="id"),
            sink=SinkConfig(
                mode="direct",
                result_column="payload",
                mark_done_column="done",
            ),
            raw={},
            item=WorkItem({}, "1"),
            parser_definition=json_definition,
            parser_revision_id=5,
        )

    assert caught.value.code == "direct_requires_single_record"
    db.asession_scope.assert_not_called()


@pytest.mark.asyncio
async def test_dynamic_json_direct_zero_records_never_writes_or_marks(
    task, dependencies, json_definition
):
    router = make_router(dependencies)
    db, parser, _, _ = dependencies
    parser.parse.return_value = iter([])

    result = await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(
            mode="direct", result_column="payload", mark_done_column="done"
        ),
        raw={},
        item=WorkItem({}, "1"),
        parser_definition=json_definition,
        parser_revision_id=5,
    )

    assert result == SinkResult()
    db.asession_scope.assert_not_called()


@pytest.mark.asyncio
async def test_dynamic_json_direct_writes_canonical_json_before_marking(
    task, dependencies, json_definition
):
    router = make_router(dependencies)
    db, parser, _, _ = dependencies
    parser.parse.return_value = iter([{"z": 2, "a": "你好"}])
    events = []
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=lambda statement, *_: events.append(
            "mark_done" if "done" in str(statement) else "result"
        )
    )
    db.asession_scope.return_value = async_context(session)

    result = await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(
            mode="direct", result_column="payload", mark_done_column="done"
        ),
        raw={},
        item=WorkItem({}, "1"),
        parser_definition=json_definition,
        parser_revision_id=5,
    )

    assert result == SinkResult(processed=1)
    assert events == ["result", "mark_done"]
    assert session.execute.await_args_list[0].args[1]["val"] == '{"a":"你好","z":2}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("definition_fixture", "expected_mode"),
    [("model_definition", "standard"), ("json_definition", "direct")],
)
async def test_dynamic_auto_selects_mode_from_definition(
    request, monkeypatch, task, dependencies, definition_fixture, expected_mode
):
    definition = request.getfixturevalue(definition_fixture)
    router = make_router(dependencies)
    _, parser, pipeline, _ = dependencies
    record = (
        {"datatype": "content", "content_id": "c1"}
        if expected_mode == "standard"
        else {"id": "c1"}
    )
    parser.parse.return_value = iter([record])
    monkeypatch.setitem(sink_handlers.DATATYPE_TO_MODEL, "content", lambda **_: object())

    result = await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(mode="auto", result_column="payload"),
        raw={},
        item=WorkItem({}, "1"),
        parser_definition=definition,
        parser_revision_id=6,
    )

    assert result == SinkResult(processed=1)
    if expected_mode == "standard":
        pipeline.process_items.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_sink_passes_dynamic_definition_without_changing_param_map(
    task, dependencies, json_definition
):
    router = make_router(dependencies)
    _, parser, _, stream_queue = dependencies
    parser.parse.return_value = iter([{"content_id": "v1"}])
    stream_queue.enqueue.return_value = EnqueueResult(True, False, "1-0")

    await router.persist(
        task=task,
        source=None,
        sink=RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={"content_id": "item_id"},
        ),
        raw={},
        item=WorkItem({}, "v1"),
        parser_definition=json_definition,
        parser_revision_id=7,
    )

    parser.parse.assert_called_once_with(
        task.platform,
        {},
        task.action,
        definition=json_definition,
        as_dto=False,
    )
    assert stream_queue.enqueue.await_args.args[1] == {"item_id": "v1"}


@pytest.mark.asyncio
async def test_static_generator_direct_writes_canonical_json(task, dependencies):
    db, _, pipeline, stream_queue = dependencies
    registry = ParserRegistry()

    @registry.register_direct(task.platform, task.action)
    def parse_direct(_raw):
        yield {"z": 2, "a": 1}

    router = ResultSinkRouter(
        db=db,
        pipeline=pipeline,
        parser=GeneralParser(registry),
        stream_queue=stream_queue,
        persist_results=True,
    )
    result_session = MagicMock(execute=AsyncMock())
    db.asession_scope.return_value = async_context(result_session)

    await router.persist(
        task=task,
        source=DatabaseSourceConfig(table="seed", key_column="id"),
        sink=SinkConfig(mode="direct", result_column="payload"),
        raw={},
        item=WorkItem({}, "1"),
        parser_definition=None,
        parser_revision_id=None,
    )

    value = result_session.execute.await_args.args[1]["val"]
    assert value == '{"a":1,"z":2}'
    assert "<generator object" not in value


@pytest.mark.asyncio
async def test_dynamic_parser_call_error_is_sink_validation_error(
    task, dependencies, json_definition
):
    router = make_router(dependencies)
    _, parser, _, _ = dependencies
    parser.parse.side_effect = ConfiguredParserError("required_field_missing")

    with pytest.raises(sink_handlers.SinkValidationError) as caught:
        await router.persist(
            task=task,
            source=DatabaseSourceConfig(table="seed", key_column="id"),
            sink=SinkConfig(mode="direct", result_column="payload"),
            raw={},
            item=WorkItem({}, "1"),
            parser_definition=json_definition,
            parser_revision_id=8,
        )

    assert caught.value.code == "required_field_missing"
