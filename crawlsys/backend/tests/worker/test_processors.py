from unittest.mock import AsyncMock, MagicMock

import pytest
from core.sink_handlers import SinkResult, SinkValidationError
from models import BusTask
from models.task_config import (
    DatabaseSourceCompletionConfig,
    PaginationConfig,
    RedisStreamSinkConfig,
    SourceConfig,
    TaskConfig,
)
from services.parser_configuration.repository import ActionRuntimeDefinition
from worker.processors import (
    InvokeActionProcessor,
    PublishSourceProcessor,
    WorkItemValidationError,
)
from worker.work_item import WorkItem


EMPTY_RUNTIME = ActionRuntimeDefinition(None, None, None)


class Limiter:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def record_success(self):
        pass


def invoke_task(*, pagination=None):
    return BusTask(
        task_id=41,
        ba_id=7,
        platform="tiktok",
        action="search",
        config=TaskConfig(pagination=pagination),
    )


def publish_task():
    return BusTask(
        task_id=41,
        ba_id=7,
        platform="tiktok",
        action="search",
        config=TaskConfig(
            execution_mode="publish_source",
            source=SourceConfig(
                table="keywords",
                key_column="id",
                param_map={"keyword": "keyword"},
                completion=DatabaseSourceCompletionConfig(column="published"),
            ),
            sink=RedisStreamSinkConfig(
                stream="crawler:{search}:stream",
                param_map={"keyword": "keyword"},
            ),
        ),
    )


@pytest.mark.asyncio
async def test_invoke_processor_calls_rpc_and_sink_router():
    rpc = MagicMock(invoke=AsyncMock(return_value={"itemList": [1]}))
    sink_router = MagicMock(persist=AsyncMock(return_value=SinkResult(processed=1)))
    processor = InvokeActionProcessor(
        rpc=rpc,
        limiter_for=lambda _platform: Limiter(),
        sink_router=sink_router,
    )
    task = invoke_task()

    runtime = ActionRuntimeDefinition(
        {"type": "object"},
        17,
        MagicMock(name="parser_definition"),
    )

    result = await processor.process(task, WorkItem({"keyword": "cats"}), runtime)

    rpc.invoke.assert_awaited_once_with("tiktok", "search", {"keyword": "cats"})
    sink_router.persist.assert_awaited_once()
    assert sink_router.persist.await_args.kwargs["parser_definition"] is runtime.parser_definition
    assert sink_router.persist.await_args.kwargs["parser_revision_id"] == 17
    assert result.sink.processed == 1


@pytest.mark.asyncio
async def test_invoke_processor_classifies_sink_validation_as_deterministic():
    rpc = MagicMock(invoke=AsyncMock(return_value={"itemList": [1]}))
    sink_router = MagicMock(
        persist=AsyncMock(side_effect=SinkValidationError("model_construction_failed"))
    )
    processor = InvokeActionProcessor(
        rpc=rpc,
        limiter_for=lambda _platform: Limiter(),
        sink_router=sink_router,
    )

    with pytest.raises(WorkItemValidationError) as caught:
        await processor.process(
            invoke_task(),
            WorkItem({"keyword": "cats"}),
            EMPTY_RUNTIME,
        )

    assert caught.value.code == "model_construction_failed"


@pytest.mark.asyncio
async def test_publish_processor_skips_rpc_parser_and_persist():
    sink_router = MagicMock(
        publish_work_item=AsyncMock(return_value=SinkResult(produced=1)),
        persist=AsyncMock(),
    )
    processor = PublishSourceProcessor(sink_router=sink_router)
    task = publish_task()

    result = await processor.process(
        task,
        WorkItem(params={"keyword": "cats"}, entity_id="11"),
        ActionRuntimeDefinition(
            {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
            },
            None,
            None,
        ),
    )

    sink_router.publish_work_item.assert_awaited_once_with(
        task=task,
        sink=task.config.sink,
        item=WorkItem(params={"keyword": "cats"}, entity_id="11"),
        params_schema={
            "type": "object",
            "properties": {"keyword": {"type": "string"}},
        },
    )
    assert "schema" not in sink_router.publish_work_item.await_args.kwargs
    assert "parser_definition" not in sink_router.publish_work_item.await_args.kwargs
    assert "parser_revision_id" not in sink_router.publish_work_item.await_args.kwargs
    sink_router.persist.assert_not_awaited()
    assert result.sink.produced == 1


@pytest.mark.asyncio
async def test_publish_processor_classifies_router_validation_as_deterministic():
    sink_router = MagicMock(
        publish_work_item=AsyncMock(side_effect=SinkValidationError("invalid_downstream_params"))
    )
    processor = PublishSourceProcessor(sink_router=sink_router)

    with pytest.raises(WorkItemValidationError):
        await processor.process(
            publish_task(),
            WorkItem(params={"keyword": "cats"}, entity_id="11"),
            EMPTY_RUNTIME,
        )


@pytest.mark.asyncio
async def test_invoke_processor_accumulates_all_page_sink_results():
    rpc = MagicMock(
        invoke=AsyncMock(
            side_effect=[
                {"itemList": [1], "hasMore": True, "cursor": 1},
                {"itemList": [2], "hasMore": False, "cursor": 2},
            ]
        )
    )
    sink_router = MagicMock(
        persist=AsyncMock(
            side_effect=[
                SinkResult(processed=1, produced=1),
                SinkResult(processed=1, deduplicated=1),
            ]
        )
    )
    processor = InvokeActionProcessor(
        rpc=rpc,
        limiter_for=lambda _platform: Limiter(),
        sink_router=sink_router,
    )
    task = invoke_task(pagination=PaginationConfig())

    result = await processor.process(task, WorkItem({"keyword": "cats"}), EMPTY_RUNTIME)

    assert rpc.invoke.await_count == 2
    assert sink_router.persist.await_count == 2
    assert result.sink == SinkResult(processed=2, produced=1, deduplicated=1)


def test_validation_error_does_not_include_sensitive_parameter_value():
    schema = {
        "type": "object",
        "properties": {"token": {"type": "integer"}},
    }

    with pytest.raises(WorkItemValidationError) as captured:
        InvokeActionProcessor._validate_params(schema, {"token": "secret-value"})

    assert "secret-value" not in str(captured.value)
    assert "token" in str(captured.value)


def test_legacy_list_schema_validates_named_required_parameters():
    schema = [
        {"name": "count", "type": "int", "required": True},
        {"name": "tags", "type": "list", "required": False},
    ]

    InvokeActionProcessor._validate_params(schema, {"count": 1, "tags": ["ai"]})

    with pytest.raises(WorkItemValidationError) as captured:
        InvokeActionProcessor._validate_params(schema, {"tags": ["ai"]})

    assert "required" in str(captured.value)


def test_invalid_schema_is_classified_as_deterministic():
    with pytest.raises(WorkItemValidationError, match="invalid work item params"):
        InvokeActionProcessor._validate_params(
            {"type": "not-a-json-schema-type"},
            {"token": "secret-value"},
        )


def test_config_accepts_legacy_raw_mapping():
    task = invoke_task()
    task.config = {"sink": {"mode": "none"}}

    config = InvokeActionProcessor._config(task)

    assert config.sink.mode == "none"


def test_normalize_page_rejects_non_mapping_response():
    assert InvokeActionProcessor._normalize_page(None) == {}
