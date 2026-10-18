from unittest.mock import AsyncMock, MagicMock

import pytest
from core.sink_handlers import SinkResult
from models import BusTask
from models.task_config import PaginationConfig, TaskConfig
from services.parser_configuration.repository import ActionRuntimeDefinition
from worker.processors import InvokeActionProcessor
from worker.work_item import WorkItem


PAGINATION_RUNTIME = ActionRuntimeDefinition(
    {"type": "object"},
    23,
    MagicMock(name="parser_definition"),
)


class Limiter:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def record_success(self):
        pass


def make_processor(responses):
    rpc = MagicMock(invoke=AsyncMock(side_effect=responses))
    router = MagicMock(persist=AsyncMock(return_value=SinkResult()))
    processor = InvokeActionProcessor(
        rpc=rpc,
        limiter_for=lambda _platform: Limiter(),
        sink_router=router,
    )
    return processor, rpc, router


def config(max_pages=0):
    return TaskConfig(
        pagination=PaginationConfig(initial_cursor=0, max_pages=max_pages),
    )


async def run(processor, cfg):
    task = BusTask(platform="tiktok", action="SearchVideo", config=cfg)
    return await processor.process(
        task,
        WorkItem({"keyword": "x"}, "1"),
        PAGINATION_RUNTIME,
    )


@pytest.mark.asyncio
async def test_without_pagination_invokes_and_persists_once():
    processor, rpc, router = make_processor([{"data": "ok"}])

    await run(processor, TaskConfig())

    rpc.invoke.assert_awaited_once_with("tiktok", "SearchVideo", {"keyword": "x"})
    router.persist.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses",
    [
        [{"itemList": [{"id": 1}], "hasMore": False, "cursor": 1}],
        [{"itemList": [], "hasMore": True, "cursor": 1}],
        [{"itemList": [{"id": 1}], "hasMore": True, "cursor": 0}],
    ],
)
async def test_pagination_stop_conditions(responses):
    processor, rpc, _router = make_processor(responses)

    await run(processor, config())

    assert rpc.invoke.await_count == 1


@pytest.mark.asyncio
async def test_max_pages_and_each_page_persist():
    processor, rpc, router = make_processor(
        [
            {"itemList": [1], "hasMore": True, "cursor": 1},
            {"itemList": [2], "hasMore": True, "cursor": 2},
        ]
    )

    await run(processor, config(max_pages=2))

    assert router.persist.await_count == 2
    assert [
        call.kwargs["parser_revision_id"]
        for call in router.persist.await_args_list
    ] == [23, 23]
    assert all(
        call.kwargs["parser_definition"] is PAGINATION_RUNTIME.parser_definition
        for call in router.persist.await_args_list
    )
    assert [call.args[2] for call in rpc.invoke.await_args_list] == [
        {"keyword": "x", "cursor": 0},
        {"keyword": "x", "cursor": 1},
    ]


@pytest.mark.asyncio
async def test_repeated_visited_cursor_stops():
    processor, rpc, _router = make_processor(
        [
            {"itemList": [1], "hasMore": True, "cursor": 1},
            {"itemList": [2], "hasMore": True, "cursor": 0},
        ]
    )

    await run(processor, config())

    assert rpc.invoke.await_count == 2


@pytest.mark.asyncio
async def test_cursor_keys_fall_back_after_missing_none_and_invalid_values():
    processor, rpc, _router = make_processor(
        [
            {
                "itemList": [1],
                "hasMore": True,
                "nextCursor": "invalid",
                "next_cursor": None,
                "maxCursor": "2",
                "cursor": 1,
            },
            {"itemList": [2], "hasMore": False, "cursor": 3},
        ]
    )

    await run(processor, config())

    assert rpc.invoke.await_args_list[1].args[2]["cursor"] == 2


@pytest.mark.asyncio
async def test_snake_case_is_normalized_without_overwriting_camel_case():
    processor, _rpc, router = make_processor(
        [
            {
                "itemList": ["camel"],
                "item_list": ["snake"],
                "hasMore": True,
                "has_more": False,
                "next_cursor": 2,
            },
            {"item_list": ["second"], "has_more": False, "cursor": 3},
        ]
    )

    await run(processor, config())

    first, second = [call.kwargs["raw"] for call in router.persist.await_args_list]
    assert first["itemList"] == ["camel"] and first["hasMore"] is True
    assert second["itemList"] == ["second"] and second["hasMore"] is False


@pytest.mark.asyncio
async def test_second_page_failure_propagates():
    processor, _rpc, router = make_processor(
        [
            {"itemList": [1], "hasMore": True, "cursor": 1},
            {"itemList": [2], "hasMore": False, "cursor": 2},
        ]
    )
    router.persist.side_effect = [SinkResult(), RuntimeError("parse failed")]

    with pytest.raises(RuntimeError, match="parse failed"):
        await run(processor, config())


@pytest.mark.asyncio
async def test_successful_pagination_returns_all_page_sink_totals():
    processor, _rpc, router = make_processor(
        [
            {"itemList": [1], "hasMore": True, "cursor": 1},
            {"itemList": [2], "hasMore": False, "cursor": 2},
        ]
    )
    router.persist.side_effect = [SinkResult(processed=1), SinkResult(processed=2)]

    result = await run(processor, config())

    assert result.sink.processed == 3
