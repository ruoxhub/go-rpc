"""Safe, bounded completion logs for MCP tool invocations."""

from collections.abc import Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import ParamSpec
from uuid import uuid4

from common.logging import get_logger
from mcp_adapter.errors import map_tool_error, safe_exception_type
from mcp_adapter.schemas import ToolErrorResponse, ToolResponse


logger = get_logger(__name__)

P = ParamSpec("P")
ToolResult = ToolResponse | ToolErrorResponse
_SAFE_RESOURCES = frozenset({"content", "user", "analysis", "bucket", "object"})
_MAX_TOOL_NAME_LENGTH = 64


def observe_tool_call(
    tool_name: str,
    *,
    resource: str,
) -> Callable[
    [Callable[P, Awaitable[ToolResult]]],
    Callable[P, Awaitable[ToolResult]],
]:
    """Record exactly one safe completion event for a tool invocation.

    The wrapper deliberately avoids arguments, return data and exception details:
    MCP inputs can carry payloads, metadata and signed URLs.  ``resource`` is a
    fixed category instead of a caller-provided identifier to keep log fields
    safe and bounded.
    """
    if resource not in _SAFE_RESOURCES:
        raise ValueError("resource must be a safe MCP resource category")
    _validate_tool_name(tool_name)

    def decorator(
        function: Callable[P, Awaitable[ToolResult]],
    ) -> Callable[P, Awaitable[ToolResult]]:
        @wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> ToolResult:
            started = perf_counter()
            exception_type = None
            try:
                response = await function(*args, **kwargs)
            except Exception as exc:
                response = map_tool_error(exc, resource=resource)
                exception_type = safe_exception_type(exc)

            record_tool_completion(
                tool_name,
                resource=resource,
                response=response,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
                exception_type=exception_type,
            )
            return response

        wrapped._mcp_observed = True
        return wrapped

    return decorator


def complete_tool_failure(
    tool_name: str,
    *,
    resource: str,
    exc: Exception,
) -> ToolErrorResponse:
    """Return and log one safe failure response for pre-tool dispatch errors."""
    response = map_tool_error(exc, resource=resource)
    record_tool_completion(
        tool_name,
        resource=resource,
        response=response,
        duration_ms=0,
        exception_type=safe_exception_type(exc),
    )
    return response


def record_tool_completion(
    tool_name: str,
    *,
    resource: str,
    response: ToolResult,
    duration_ms: int,
    exception_type: str | None = None,
) -> None:
    """Emit a single bounded completion line that works with text formatters."""
    _validate_tool_name(tool_name)
    if resource not in _SAFE_RESOURCES:
        raise ValueError("resource must be a safe MCP resource category")

    if isinstance(response, ToolErrorResponse):
        status_code = response.error.code.value
        correlation_id = response.error.correlation_id
    else:
        status_code = "OK"
        correlation_id = uuid4().hex

    duration_ms = max(0, int(duration_ms))
    message = (
        "MCP tool completed "
        f"tool_name={tool_name} duration_ms={duration_ms} "
        f"status_code={status_code} resource={resource}"
    )
    fields = dict(
        tool_name=tool_name,
        duration_ms=duration_ms,
        status_code=status_code,
        resource=resource,
        correlation_id=correlation_id,
    )
    if exception_type is not None:
        fields["exception_type"] = exception_type
        message += f" exception_type={exception_type}"
    message += f" correlation_id={correlation_id}"
    logger.bind(**fields).info(message)


def _validate_tool_name(tool_name: str) -> None:
    if (
        not isinstance(tool_name, str)
        or not tool_name
        or len(tool_name) > _MAX_TOOL_NAME_LENGTH
        or not all(character.isascii() and (character.isalnum() or character == "_") for character in tool_name)
    ):
        raise ValueError("tool_name must be a safe MCP tool identifier")
