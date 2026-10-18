"""MCP 工具调用日志的安全与关联标识回归测试。"""

from io import StringIO

import pytest

from mcp_adapter.errors import map_tool_error
from mcp_adapter.schemas import ToolResponse
from utils.log import LogConfig, log


class CapturingLogger:
    """Capture bound structured log fields without rendering sensitive data."""

    def __init__(self):
        self.records: list[dict[str, object]] = []
        self._fields: dict[str, object] = {}

    def bind(self, **fields):
        self._fields = fields
        return self

    def info(self, _message):
        self.records.append(dict(self._fields))


@pytest.mark.asyncio
async def test_failed_tool_logs_once_without_sensitive_inputs_and_reuses_error_correlation_id(
    monkeypatch,
):
    from mcp_adapter import observability

    logger = CapturingLogger()
    monkeypatch.setattr(observability, "logger", logger)
    secret_base64 = "c2VjcmV0LWJhc2U2NC1wYXlsb2Fk"
    secret_analysis = '{"analysis_result":"private-analysis"}'
    secret_metadata = "metadata-secret-value"
    secret_query = "X-Amz-Signature=private-query"

    @observability.observe_tool_call("upload_base64_object", resource="object")
    async def failing_tool(_content_base64, _metadata):
        return map_tool_error(
            RuntimeError(f"{secret_base64} {secret_analysis} {secret_metadata} {secret_query}"),
            resource="object",
        )

    response = await failing_tool(secret_base64, {"private": secret_metadata})

    assert len(logger.records) == 1
    record = logger.records[0]
    assert record["tool_name"] == "upload_base64_object"
    assert record["resource"] == "object"
    assert record["status_code"] == response.error.code.value
    assert record["correlation_id"] == response.error.correlation_id
    assert isinstance(record["duration_ms"], int)
    rendered = repr(record)
    for sensitive_value in (secret_base64, secret_analysis, secret_metadata, secret_query):
        assert sensitive_value not in rendered


@pytest.mark.asyncio
async def test_successful_tool_logs_exactly_one_safe_completion_record(monkeypatch):
    from mcp_adapter import observability

    logger = CapturingLogger()
    monkeypatch.setattr(observability, "logger", logger)

    @observability.observe_tool_call("list_buckets", resource="bucket")
    async def successful_tool():
        return ToolResponse(data=[])

    response = await successful_tool()

    assert response.ok is True
    assert logger.records == [
        {
            "tool_name": "list_buckets",
            "duration_ms": logger.records[0]["duration_ms"],
            "status_code": "OK",
            "resource": "bucket",
            "correlation_id": logger.records[0]["correlation_id"],
        }
    ]
    assert isinstance(logger.records[0]["duration_ms"], int)
    assert isinstance(logger.records[0]["correlation_id"], str)


@pytest.mark.asyncio
async def test_internal_exception_log_includes_only_safe_exception_type(monkeypatch):
    from mcp_adapter import observability

    logger = CapturingLogger()
    monkeypatch.setattr(observability, "logger", logger)
    secret = "X-Amz-Signature=private-query"

    @observability.observe_tool_call("get_object_content", resource="object")
    async def failing_tool():
        raise RuntimeError(secret)

    response = await failing_tool()

    assert logger.records[0]["exception_type"] == "RuntimeError"
    assert logger.records[0]["correlation_id"] == response.error.correlation_id
    assert secret not in repr(logger.records[0])


@pytest.mark.asyncio
async def test_default_project_formatter_renders_safe_completion_fields():
    from mcp_adapter.observability import observe_tool_call

    sink = StringIO()
    sink_id = log.add(sink, format=LogConfig().file_format, colorize=False)
    secret_base64 = "c2VjcmV0LWJhc2U2NC1wYXlsb2Fk"
    secret_analysis = '{"analysis_result":"private-analysis"}'
    secret_metadata = "metadata-secret-value"
    secret_query = "X-Amz-Signature=private-query"

    @observe_tool_call("upload_base64_object", resource="object")
    async def failing_tool(_content_base64, _metadata):
        return map_tool_error(
            RuntimeError(f"{secret_base64} {secret_analysis} {secret_metadata} {secret_query}"),
            resource="object",
        )

    try:
        response = await failing_tool(secret_base64, {"private": secret_metadata})
    finally:
        log.remove(sink_id)

    rendered = sink.getvalue()
    for field in (
        "tool_name=upload_base64_object",
        "duration_ms=",
        f"status_code={response.error.code.value}",
        "resource=object",
        f"correlation_id={response.error.correlation_id}",
    ):
        assert field in rendered
    for sensitive_value in (secret_base64, secret_analysis, secret_metadata, secret_query):
        assert sensitive_value not in rendered


def test_every_public_mcp_tool_is_observed_once():
    from mcp_adapter import analysis_tools, content_tools, minio_tools, user_tools

    expected_tools = {
        content_tools: {"get_content", "list_contents"},
        user_tools: {"get_user", "list_users"},
        analysis_tools: {"get_analysis_result", "list_analysis_results"},
        minio_tools: {
            "list_buckets",
            "create_bucket",
            "list_objects",
            "stat_object",
            "get_object_download_url",
            "get_object_content",
            "create_upload_url",
            "upload_base64_object",
        },
    }

    for module, names in expected_tools.items():
        assert all(getattr(getattr(module, name), "_mcp_observed", False) for name in names)
