"""Official MCP SDK registration and in-memory protocol tests."""

from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.server import MCPServer

from core.config import McpConfig
import mcp_adapter.server as server_module
from mcp_adapter.context import McpAppResources
from mcp_adapter.schemas import ToolResponse
from mcp_adapter.server import create_mcp_server
from utils.log import log


TOOL_SCHEMAS = {
    "get_content": ({"platform", "content_id"}, {"platform", "content_id"}),
    "list_contents": (
        {"platform", "published_from", "published_to", "limit", "cursor"},
        set(),
    ),
    "get_user": ({"platform", "user_id"}, {"platform", "user_id"}),
    "list_users": (
        {"platform", "username", "limit", "cursor"},
        set(),
    ),
    "get_analysis_result": ({"platform", "content_id"}, {"platform", "content_id"}),
    "list_analysis_results": (
        {
            "platform",
            "status",
            "updated_from",
            "updated_to",
            "limit",
            "cursor",
            "detail_level",
        },
        set(),
    ),
    "list_buckets": (set(), set()),
    "create_bucket": ({"bucket", "region"}, {"bucket"}),
    "list_objects": (
        {"bucket", "prefix", "recursive", "limit", "cursor"},
        {"bucket"},
    ),
    "stat_object": ({"bucket", "object_name"}, {"bucket", "object_name"}),
    "get_object_download_url": (
        {"bucket", "object_name", "expires_minutes"},
        {"bucket", "object_name"},
    ),
    "get_object_content": ({"bucket", "object_name"}, {"bucket", "object_name"}),
    "create_upload_url": (
        {"bucket", "object_name", "expires_minutes"},
        {"bucket", "object_name"},
    ),
    "upload_base64_object": (
        {"bucket", "object_name", "content_base64", "content_type", "metadata"},
        {"bucket", "object_name", "content_base64", "content_type"},
    ),
}

READ_ONLY_TOOLS = {
    "get_content",
    "list_contents",
    "get_user",
    "list_users",
    "get_analysis_result",
    "list_analysis_results",
    "list_buckets",
    "list_objects",
    "stat_object",
    "get_object_download_url",
    "get_object_content",
}

WRITE_TOOLS = {"create_bucket", "create_upload_url", "upload_base64_object"}


@pytest.fixture
def resources():
    minio = SimpleNamespace(alist_buckets=AsyncMock())
    return McpAppResources(db=object(), minio=minio, config=McpConfig())


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_tools_list_exposes_exact_schemas_and_truthful_annotations(resources, mode):
    server = create_mcp_server(resources, resources.config)

    assert isinstance(server, MCPServer)
    async with Client(server, mode=mode) as client:
        listed = await client.list_tools()

    tools = {tool.name: tool for tool in listed.tools}
    assert set(tools) == set(TOOL_SCHEMAS)
    assert not {name for name in tools if "delete" in name or "remove" in name}

    for name, (properties, required) in TOOL_SCHEMAS.items():
        tool = tools[name]
        assert tool.input_schema["type"] == "object"
        assert set(tool.input_schema.get("properties", {})) == properties
        assert set(tool.input_schema.get("required", [])) == required
        assert tool.annotations is not None
        assert tool.annotations.title
        assert tool.annotations.read_only_hint is (name in READ_ONLY_TOOLS)
        assert tool.annotations.destructive_hint is (name == "upload_base64_object")
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False

    assert all(tools[name].annotations.read_only_hint is False for name in WRITE_TOOLS)
    analysis_tool = tools["list_analysis_results"]
    assert analysis_tool.input_schema["properties"]["detail_level"]["enum"] == [
        "compact",
        "detailed",
    ]
    assert "score_text" in analysis_tool.description
    assert "published_text" in analysis_tool.description


@pytest.mark.asyncio
async def test_tools_call_uses_lifespan_injected_resources(resources):
    resources.minio.alist_buckets.return_value = [
        SimpleNamespace(
            name="media-assets",
            creation_date=datetime(2026, 8, 6, 10, 0),
        )
    ]
    server = create_mcp_server(resources, resources.config)

    async with Client(server) as client:
        result = await client.call_tool("list_buckets")

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["data"][0]["name"] == "media-assets"
    resources.minio.alist_buckets.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_every_registered_handler_dispatches_through_tools_call(resources, monkeypatch):
    calls = {
        "get_content": (server_module.content_tools, {"platform": "tiktok", "content_id": "1"}),
        "list_contents": (server_module.content_tools, {}),
        "get_user": (server_module.user_tools, {"platform": "tiktok", "user_id": "1"}),
        "list_users": (server_module.user_tools, {}),
        "get_analysis_result": (
            server_module.analysis_tools,
            {"platform": "tiktok", "content_id": "1"},
        ),
        "list_analysis_results": (server_module.analysis_tools, {}),
        "list_buckets": (server_module.minio_tools, {}),
        "create_bucket": (server_module.minio_tools, {"bucket": "media-assets"}),
        "list_objects": (server_module.minio_tools, {"bucket": "media-assets"}),
        "stat_object": (
            server_module.minio_tools,
            {"bucket": "media-assets", "object_name": "clips/one.mp4"},
        ),
        "get_object_download_url": (
            server_module.minio_tools,
            {"bucket": "media-assets", "object_name": "clips/one.mp4"},
        ),
        "get_object_content": (
            server_module.minio_tools,
            {"bucket": "media-assets", "object_name": "clips/one.mp4"},
        ),
        "create_upload_url": (
            server_module.minio_tools,
            {"bucket": "media-assets", "object_name": "clips/new.mp4"},
        ),
        "upload_base64_object": (
            server_module.minio_tools,
            {
                "bucket": "media-assets",
                "object_name": "clips/new.txt",
                "content_base64": "ZGF0YQ==",
                "content_type": "text/plain",
            },
        ),
    }
    mocks = {}
    for name, (module, _arguments) in calls.items():
        mock = AsyncMock(return_value=ToolResponse(data={"tool": name}))
        monkeypatch.setattr(module, name, mock)
        mocks[name] = mock

    server = create_mcp_server(resources, resources.config)
    async with Client(server) as client:
        for name, (_module, arguments) in calls.items():
            result = await client.call_tool(name, arguments)
            assert result.is_error is False
            assert result.structured_content == {
                "ok": True,
                "data": {"tool": name},
                "meta": {},
            }

    assert all(mock.await_count == 1 for mock in mocks.values())
    mocks["list_analysis_results"].assert_awaited_once_with(
        resources,
        platform=None,
        status=None,
        updated_from=None,
        updated_to=None,
        limit=20,
        cursor=None,
        detail_level="compact",
    )


def _tool_completion_lines(sink: StringIO, tool_name: str) -> list[str]:
    return [line for line in sink.getvalue().splitlines() if f"tool_name={tool_name}" in line]


def _assert_completion_line(line: str, *, status_code: str) -> str:
    assert "duration_ms=" in line
    assert f"status_code={status_code}" in line
    assert "resource=bucket" in line
    correlation_id = line.rsplit("correlation_id=", maxsplit=1)[1]
    assert correlation_id
    return correlation_id


@pytest.mark.asyncio
async def test_client_call_tool_logs_once_for_success_and_tool_failure(resources):
    resources.minio.alist_buckets.return_value = []
    server = create_mcp_server(resources, resources.config)
    sink = StringIO()
    sink_id = log.add(sink, format="{message}", colorize=False)

    try:
        async with Client(server) as client:
            success = await client.call_tool("list_buckets")
            resources.minio.alist_buckets.side_effect = OSError("private storage failure")
            failure = await client.call_tool("list_buckets")
    finally:
        log.remove(sink_id)

    assert success.structured_content == {"ok": True, "data": [], "meta": {}}
    assert failure.structured_content is not None
    error = failure.structured_content["error"]
    assert error["code"] == "STORAGE_UNAVAILABLE"
    lines = _tool_completion_lines(sink, "list_buckets")
    assert len(lines) == 2
    _assert_completion_line(lines[0], status_code="OK")
    assert _assert_completion_line(lines[1], status_code="STORAGE_UNAVAILABLE") == error["correlation_id"]
    assert "private storage failure" not in sink.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource_factory",
    [
        lambda config: McpAppResources(db=None, minio=object(), config=config),
        lambda _config: None,
        lambda _config: object(),
    ],
    ids=["require-ready", "none", "wrong-type"],
)
async def test_client_call_tool_logs_once_when_context_resources_are_unavailable(resource_factory):
    config = McpConfig()
    server = create_mcp_server(resource_factory(config), config)
    sink = StringIO()
    sink_id = log.add(sink, format="{message}", colorize=False)

    try:
        async with Client(server) as client:
            result = await client.call_tool("list_buckets")
    finally:
        log.remove(sink_id)

    assert result.structured_content is not None
    error = result.structured_content["error"]
    assert error["code"] == "INTERNAL_ERROR"
    lines = _tool_completion_lines(sink, "list_buckets")
    assert len(lines) == 1
    assert _assert_completion_line(lines[0], status_code="INTERNAL_ERROR") == error["correlation_id"]
