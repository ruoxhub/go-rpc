"""Stable, safe error responses for MCP adapter tools."""

from uuid import uuid4

from minio.error import S3Error

from mcp_adapter.schemas import InvalidCursorError, ToolError, ToolErrorCode, ToolErrorResponse

_SAFE_MESSAGES = {
    ToolErrorCode.CONTENT_NOT_FOUND: "Content not found.",
    ToolErrorCode.USER_NOT_FOUND: "User not found.",
    ToolErrorCode.ANALYSIS_NOT_FOUND: "Analysis result not found.",
    ToolErrorCode.INVALID_CURSOR: "Invalid cursor.",
    ToolErrorCode.INVALID_ARGUMENT: "Invalid argument.",
    ToolErrorCode.BUCKET_NOT_FOUND: "Bucket not found.",
    ToolErrorCode.OBJECT_NOT_FOUND: "Object not found.",
    ToolErrorCode.OBJECT_TOO_LARGE: "Object exceeds the permitted size.",
    ToolErrorCode.BUCKET_ALREADY_EXISTS: "Bucket already exists.",
    ToolErrorCode.STORAGE_UNAVAILABLE: "Storage service is unavailable.",
    ToolErrorCode.INTERNAL_ERROR: "Internal service error.",
}


def safe_exception_type(exc: Exception) -> str:
    """Return a bounded exception class name without inspecting its message."""
    name = type(exc).__name__
    if len(name) <= 64 and name.isascii() and name.isidentifier():
        return name
    return "Exception"


class McpToolError(Exception):
    """An expected tool failure with an explicitly safe public response."""

    def __init__(
        self,
        code: ToolErrorCode,
        message: str,
        issues: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = issues or []


def map_tool_error(exc: Exception, *, resource: str) -> ToolErrorResponse:
    """Return a stable safe response without exposing exception details."""
    correlation_id = uuid4().hex

    if isinstance(exc, McpToolError):
        code, issues = exc.code, exc.issues
        message = _SAFE_MESSAGES[code]
    elif isinstance(exc, InvalidCursorError):
        code, message, issues = ToolErrorCode.INVALID_CURSOR, "Invalid cursor.", []
    elif isinstance(exc, S3Error):
        code, message, issues = _map_s3_error(exc)
    elif isinstance(exc, FileExistsError) and resource == "bucket":
        code, message, issues = ToolErrorCode.BUCKET_ALREADY_EXISTS, "Bucket already exists.", []
    elif isinstance(exc, (FileNotFoundError, KeyError)):
        code, message, issues = _not_found_error(resource)
    elif isinstance(exc, ValueError):
        code, message, issues = ToolErrorCode.INVALID_ARGUMENT, "Invalid argument.", []
    elif isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        code, message, issues = ToolErrorCode.STORAGE_UNAVAILABLE, "Storage service is unavailable.", []
    else:
        code, message, issues = ToolErrorCode.INTERNAL_ERROR, "Internal service error.", []

    return ToolErrorResponse(
        error=ToolError(
            code=code,
            message=message,
            issues=issues,
            correlation_id=correlation_id,
        )
    )


def _map_s3_error(exc: S3Error) -> tuple[ToolErrorCode, str, list[dict[str, str]]]:
    if exc.code in {"NoSuchKey", "NoSuchObject"}:
        return ToolErrorCode.OBJECT_NOT_FOUND, "Object not found.", []
    if exc.code == "NoSuchBucket":
        return ToolErrorCode.BUCKET_NOT_FOUND, "Bucket not found.", []
    return ToolErrorCode.STORAGE_UNAVAILABLE, "Storage service is unavailable.", []


def _not_found_error(resource: str) -> tuple[ToolErrorCode, str, list[dict[str, str]]]:
    mapping = {
        "content": (ToolErrorCode.CONTENT_NOT_FOUND, "Content not found."),
        "user": (ToolErrorCode.USER_NOT_FOUND, "User not found."),
        "analysis": (ToolErrorCode.ANALYSIS_NOT_FOUND, "Analysis result not found."),
        "bucket": (ToolErrorCode.BUCKET_NOT_FOUND, "Bucket not found."),
        "object": (ToolErrorCode.OBJECT_NOT_FOUND, "Object not found."),
    }
    code, message = mapping.get(resource, (ToolErrorCode.INTERNAL_ERROR, "Internal service error."))
    return code, message, []
