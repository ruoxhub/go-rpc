"""Official MCP SDK v2 server registration and Streamable HTTP adapter."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from core.config import McpConfig
from mcp_adapter import analysis_tools, content_tools, minio_tools, user_tools
from mcp_adapter.context import McpAppResources
from mcp_adapter.observability import ToolResult, complete_tool_failure


def _resolve_resources(ctx: Context) -> McpAppResources:
    resources = ctx.request_context.lifespan_context
    if not isinstance(resources, McpAppResources):
        raise RuntimeError("MCP lifespan resources are unavailable")
    return resources.require_ready()


async def _dispatch_with_resources(
    ctx: Context,
    *,
    tool_name: str,
    resource: str,
    operation: Callable[[McpAppResources], Awaitable[ToolResult]],
) -> ToolResult:
    """Resolve application resources inside the handler before invoking a tool."""
    try:
        return await operation(_resolve_resources(ctx))
    except Exception as exc:
        return complete_tool_failure(tool_name, resource=resource, exc=exc)


def _response_payload(response: ToolResult) -> dict[str, object]:
    """Keep the existing direct structured MCP response shape for both outcomes."""
    return response.model_dump(mode="json")


def _annotations(
    title: str,
    *,
    read_only: bool,
    destructive: bool = False,
) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=True,
        openWorldHint=False,
    )


def create_mcp_server(resources: McpAppResources, config: McpConfig) -> MCPServer:
    """Register the complete crawler tool surface on an official SDK server."""

    @asynccontextmanager
    async def server_lifespan(_server: MCPServer) -> AsyncIterator[object]:
        yield resources

    server = MCPServer(
        "crawler-content-analysis",
        title="Crawler Content Analysis",
        description="Query collected content, users and analysis results, and manage MinIO objects.",
        version="0.1.0",
        lifespan=server_lifespan,
    )

    @server.tool(
        name="get_content",
        description="Fetch one collected content record by platform and content ID.",
        annotations=_annotations("Get content", read_only=True),
    )
    async def get_content(
        ctx: Context,
        platform: str,
        content_id: str,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="get_content",
            resource="content",
            operation=lambda tool_resources: content_tools.get_content(
                tool_resources, platform, content_id
            ),
        ))

    @server.tool(
        name="list_contents",
        description="List collected content in stable newest-first cursor order.",
        annotations=_annotations("List contents", read_only=True),
    )
    async def list_contents(
        ctx: Context,
        platform: str | None = None,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="list_contents",
            resource="content",
            operation=lambda tool_resources: content_tools.list_contents(
                tool_resources,
                platform=platform,
                published_from=published_from,
                published_to=published_to,
                limit=limit,
                cursor=cursor,
            ),
        ))

    @server.tool(
        name="get_user",
        description="Fetch one collected platform user by platform and user ID.",
        annotations=_annotations("Get user", read_only=True),
    )
    async def get_user(
        ctx: Context,
        platform: str,
        user_id: str,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="get_user",
            resource="user",
            operation=lambda tool_resources: user_tools.get_user(
                tool_resources, platform, user_id
            ),
        ))

    @server.tool(
        name="list_users",
        description="List collected platform users in stable newest-first cursor order.",
        annotations=_annotations("List users", read_only=True),
    )
    async def list_users(
        ctx: Context,
        platform: str | None = None,
        username: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="list_users",
            resource="user",
            operation=lambda tool_resources: user_tools.list_users(
                tool_resources,
                platform=platform,
                username=username,
                limit=limit,
                cursor=cursor,
            ),
        ))

    @server.tool(
        name="get_analysis_result",
        description=(
            "Fetch one persisted video analysis result with content share, like, comment and "
            "view counts plus a temporary MinIO video URL when available."
        ),
        annotations=_annotations("Get analysis result", read_only=True),
    )
    async def get_analysis_result(
        ctx: Context,
        platform: str,
        content_id: str,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="get_analysis_result",
            resource="analysis",
            operation=lambda tool_resources: analysis_tools.get_analysis_result(
                tool_resources, platform, content_id
            ),
        ))

    @server.tool(
        name="list_analysis_results",
        description=(
            "List persisted video analysis summaries for content operators. Present results "
            "in this order: page overview, compact item list, review/issues, pagination hint. "
            "Prefer score_text, views_text, published_text (Beijing time), structure_text, "
            "review_status and key_issues; do not expand C/G/R dimensions unless "
            "detail_level='detailed'."
        ),
        annotations=_annotations("List analysis results", read_only=True),
    )
    async def list_analysis_results(
        ctx: Context,
        platform: str | None = None,
        status: str | None = None,
        updated_from: datetime | None = None,
        updated_to: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
        detail_level: Literal["compact", "detailed"] = "compact",
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="list_analysis_results",
            resource="analysis",
            operation=lambda tool_resources: analysis_tools.list_analysis_results(
                tool_resources,
                platform=platform,
                status=status,
                updated_from=updated_from,
                updated_to=updated_to,
                limit=limit,
                cursor=cursor,
                detail_level=detail_level,
            ),
        ))

    @server.tool(
        name="list_buckets",
        description="List buckets available to the configured MinIO client.",
        annotations=_annotations("List buckets", read_only=True),
    )
    async def list_buckets(ctx: Context) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="list_buckets",
            resource="bucket",
            operation=minio_tools.list_buckets,
        ))

    @server.tool(
        name="create_bucket",
        description="Create a MinIO bucket if it does not already exist.",
        annotations=_annotations("Create bucket", read_only=False),
    )
    async def create_bucket(
        ctx: Context,
        bucket: str,
        region: str | None = None,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="create_bucket",
            resource="bucket",
            operation=lambda tool_resources: minio_tools.create_bucket(tool_resources, bucket, region),
        ))

    @server.tool(
        name="list_objects",
        description="List a bounded page of MinIO objects using a stable cursor.",
        annotations=_annotations("List objects", read_only=True),
    )
    async def list_objects(
        ctx: Context,
        bucket: str,
        prefix: str | None = None,
        recursive: bool = False,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="list_objects",
            resource="object",
            operation=lambda tool_resources: minio_tools.list_objects(
                tool_resources,
                bucket,
                prefix=prefix,
                recursive=recursive,
                limit=limit,
                cursor=cursor,
            ),
        ))

    @server.tool(
        name="stat_object",
        description="Fetch metadata for one MinIO object.",
        annotations=_annotations("Stat object", read_only=True),
    )
    async def stat_object(
        ctx: Context,
        bucket: str,
        object_name: str,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="stat_object",
            resource="object",
            operation=lambda tool_resources: minio_tools.stat_object(
                tool_resources, bucket, object_name
            ),
        ))

    @server.tool(
        name="get_object_download_url",
        description="Create a temporary download URL for an existing MinIO object.",
        annotations=_annotations("Get object download URL", read_only=True),
    )
    async def get_object_download_url(
        ctx: Context,
        bucket: str,
        object_name: str,
        expires_minutes: int = config.presigned_expiry_minutes,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="get_object_download_url",
            resource="object",
            operation=lambda tool_resources: minio_tools.get_object_download_url(
                tool_resources,
                bucket,
                object_name,
                expires_minutes,
            ),
        ))

    @server.tool(
        name="get_object_content",
        description="Read a bounded MinIO object and return strict Base64 content.",
        annotations=_annotations("Get object content", read_only=True),
    )
    async def get_object_content(
        ctx: Context,
        bucket: str,
        object_name: str,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="get_object_content",
            resource="object",
            operation=lambda tool_resources: minio_tools.get_object_content(
                tool_resources, bucket, object_name
            ),
        ))

    @server.tool(
        name="create_upload_url",
        description="Create a temporary upload URL for an object in an existing bucket.",
        annotations=_annotations("Create upload URL", read_only=False),
    )
    async def create_upload_url(
        ctx: Context,
        bucket: str,
        object_name: str,
        expires_minutes: int = config.presigned_expiry_minutes,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="create_upload_url",
            resource="bucket",
            operation=lambda tool_resources: minio_tools.create_upload_url(
                tool_resources,
                bucket,
                object_name,
                expires_minutes,
            ),
        ))

    @server.tool(
        name="upload_base64_object",
        description="Upload or overwrite one bounded Base64 payload in MinIO.",
        annotations=_annotations(
            "Upload Base64 object",
            read_only=False,
            destructive=True,
        ),
    )
    async def upload_base64_object(
        ctx: Context,
        bucket: str,
        object_name: str,
        content_base64: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, object]:
        return _response_payload(await _dispatch_with_resources(
            ctx,
            tool_name="upload_base64_object",
            resource="object",
            operation=lambda tool_resources: minio_tools.upload_base64_object(
                tool_resources,
                bucket,
                object_name,
                content_base64,
                content_type,
                metadata,
            ),
        ))

    return server


def create_mcp_http_app(server: MCPServer, config: McpConfig) -> ASGIApp:
    """Build the mounted Streamable HTTP child app with explicit trust rules."""
    app = server.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(config.allowed_hosts),
            allowed_origins=list(config.allowed_origins),
        ),
    )
    if config.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.allowed_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Last-Event-ID",
                "Mcp-Method",
                "Mcp-Name",
                "Mcp-Protocol-Version",
                "Mcp-Session-Id",
            ],
            expose_headers=["Mcp-Session-Id"],
        )
    return app
