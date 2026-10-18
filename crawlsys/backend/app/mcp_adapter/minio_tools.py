"""Non-destructive MCP adapter tools for MinIO bucket and object management."""

import base64
import binascii
from datetime import timedelta
from io import BytesIO
from typing import Any

from mcp_adapter.context import McpAppResources
from mcp_adapter.errors import McpToolError, map_tool_error
from mcp_adapter.observability import observe_tool_call
from mcp_adapter.schemas import (
    BucketInfo,
    ObjectInfo,
    ToolErrorCode,
    ToolResponse,
    UploadResult,
)


_MAX_PRESIGNED_EXPIRY_MINUTES = 60
_MAX_INLINE_OBJECT_HARD_LIMIT_BYTES = 50 * 1024 * 1024


@observe_tool_call("list_buckets", resource="bucket")
async def list_buckets(resources: McpAppResources):
    """List buckets available to the configured MinIO client."""
    try:
        buckets = await resources.minio.alist_buckets()
        return ToolResponse(data=[_to_bucket_info(bucket) for bucket in buckets])
    except Exception as exc:
        return map_tool_error(exc, resource="bucket")


@observe_tool_call("create_bucket", resource="bucket")
async def create_bucket(
    resources: McpAppResources,
    bucket: str,
    region: str | None = None,
):
    """Create a bucket when it does not already exist."""
    try:
        _validate_bucket(bucket)
        if await resources.minio.abucket_exists(bucket):
            return ToolResponse(data=BucketInfo(name=bucket), meta={"created": False})
        await resources.minio.amake_bucket(bucket, region)
        return ToolResponse(data=BucketInfo(name=bucket), meta={"created": True})
    except Exception as exc:
        return map_tool_error(exc, resource="bucket")


@observe_tool_call("list_objects", resource="object")
async def list_objects(
    resources: McpAppResources,
    bucket: str,
    prefix: str | None = None,
    recursive: bool = False,
    limit: int = 100,
    cursor: str | None = None,
):
    """Stream one stable MinIO page without materializing a complete bucket."""
    try:
        _validate_bucket(bucket)
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        objects = []
        stream = resources.minio.alist_objects_stream(
            bucket,
            prefix=prefix,
            recursive=recursive,
            start_after=cursor,
            include_user_meta=True,
            include_version=True,
        )
        async for item in stream:
            objects.append(_to_object_info(bucket, item))
            if len(objects) == limit + 1:
                break

        has_more = len(objects) > limit
        page = objects[:limit]
        return ToolResponse(
            data=page,
            meta={
                "has_more": has_more,
                "limit": limit,
                "next_cursor": page[-1].object_name if has_more else None,
            },
        )
    except Exception as exc:
        return map_tool_error(exc, resource="object")


@observe_tool_call("stat_object", resource="object")
async def stat_object(resources: McpAppResources, bucket: str, object_name: str):
    """Return one object's metadata."""
    try:
        _validate_object(bucket, object_name)
        item = await resources.minio.astat_object(bucket, object_name)
        return ToolResponse(data=_to_object_info(bucket, item, object_name=object_name))
    except Exception as exc:
        return map_tool_error(exc, resource="object")


@observe_tool_call("get_object_download_url", resource="object")
async def get_object_download_url(
    resources: McpAppResources,
    bucket: str,
    object_name: str,
    expires_minutes: int = 15,
):
    """Create a temporary download URL for an existing object."""
    try:
        _validate_object(bucket, object_name)
        expires = _to_expiry(expires_minutes)
        await resources.minio.astat_object(bucket, object_name)
        url = await resources.minio.apresigned_get_object(bucket, object_name, expires=expires)
        return ToolResponse(data={"url": url, "expires_minutes": expires_minutes})
    except Exception as exc:
        return map_tool_error(exc, resource="object")


@observe_tool_call("get_object_content", resource="object")
async def get_object_content(resources: McpAppResources, bucket: str, object_name: str):
    """Return a bounded object's bytes as strict ASCII Base64."""
    try:
        _validate_object(bucket, object_name)
        stat = await resources.minio.astat_object(bucket, object_name)
        size = _object_size(stat)
        if size > _inline_read_limit(resources):
            raise McpToolError(ToolErrorCode.OBJECT_TOO_LARGE, "Object is too large.")

        response = await resources.minio.aget_object(bucket, object_name, length=size)
        async with response:
            payload = await response.read()

        if len(payload) > _inline_read_limit(resources):
            raise McpToolError(ToolErrorCode.OBJECT_TOO_LARGE, "Object is too large.")

        return ToolResponse(
            data={
                "bucket": bucket,
                "object_name": object_name,
                "content_base64": base64.b64encode(payload).decode("ascii"),
                "content_type": getattr(stat, "content_type", None),
                "size": size,
            }
        )
    except Exception as exc:
        return map_tool_error(exc, resource="object")


@observe_tool_call("create_upload_url", resource="bucket")
async def create_upload_url(
    resources: McpAppResources,
    bucket: str,
    object_name: str,
    expires_minutes: int = 15,
):
    """Create a temporary upload URL for an existing bucket."""
    try:
        _validate_object(bucket, object_name)
        expires = _to_expiry(expires_minutes)
        if not await resources.minio.abucket_exists(bucket):
            raise FileNotFoundError(bucket)
        url = await resources.minio.apresigned_put_object(bucket, object_name, expires=expires)
        return ToolResponse(data={"url": url, "expires_minutes": expires_minutes})
    except Exception as exc:
        return map_tool_error(exc, resource="bucket")


@observe_tool_call("upload_base64_object", resource="object")
async def upload_base64_object(
    resources: McpAppResources,
    bucket: str,
    object_name: str,
    content_base64: str,
    content_type: str,
    metadata: dict[str, str] | None = None,
):
    """Upload a bounded Base64 payload without accepting a deletion operation."""
    try:
        _validate_object(bucket, object_name, metadata=metadata)
        payload = _decode_bounded_base64(content_base64, _effective_hard_limit(resources))
        if not await resources.minio.abucket_exists(bucket):
            raise FileNotFoundError(bucket)

        result = await resources.minio.aput_object(
            bucket,
            object_name,
            BytesIO(payload),
            len(payload),
            content_type=content_type,
            metadata=metadata,
        )
        return ToolResponse(
            data=UploadResult(
                bucket=bucket,
                object_name=object_name,
                size=len(payload),
                etag=getattr(result, "etag", None),
                version_id=getattr(result, "version_id", None),
            )
        )
    except Exception as exc:
        return map_tool_error(exc, resource="object")


def _validate_bucket(bucket: str) -> None:
    BucketInfo(name=bucket)


def _validate_object(
    bucket: str,
    object_name: str,
    *,
    metadata: dict[str, str] | None = None,
) -> None:
    ObjectInfo(
        bucket=bucket,
        object_name=object_name,
        size=0,
        metadata=metadata or {},
    )


def _to_bucket_info(bucket: Any) -> BucketInfo:
    return BucketInfo(
        name=bucket.name,
        creation_date=getattr(bucket, "creation_date", None),
    )


def _to_object_info(bucket: str, item: Any, *, object_name: str | None = None) -> ObjectInfo:
    return ObjectInfo(
        bucket=bucket,
        object_name=object_name or item.object_name,
        size=_object_size(item),
        etag=getattr(item, "etag", None),
        content_type=getattr(item, "content_type", None),
        last_modified=getattr(item, "last_modified", None),
        version_id=getattr(item, "version_id", None),
        metadata=getattr(item, "metadata", None) or {},
    )


def _object_size(item: Any) -> int:
    size = getattr(item, "size", None)
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("Object size is invalid")
    return size


def _to_expiry(expires_minutes: int) -> timedelta:
    if (
        not isinstance(expires_minutes, int)
        or isinstance(expires_minutes, bool)
        or not 1 <= expires_minutes <= _MAX_PRESIGNED_EXPIRY_MINUTES
    ):
        raise ValueError("expires_minutes is invalid")
    return timedelta(minutes=expires_minutes)


def _effective_hard_limit(resources: McpAppResources) -> int:
    return min(resources.config.inline_object_hard_limit_bytes, _MAX_INLINE_OBJECT_HARD_LIMIT_BYTES)


def _inline_read_limit(resources: McpAppResources) -> int:
    return min(resources.config.inline_object_limit_bytes, _effective_hard_limit(resources))


def _decode_bounded_base64(content_base64: str, limit: int) -> bytes:
    if not isinstance(content_base64, str):
        raise ValueError("content_base64 must be a string")
    max_encoded_length = 4 * ((limit + 2) // 3)
    if len(content_base64) > max_encoded_length:
        raise McpToolError(ToolErrorCode.OBJECT_TOO_LARGE, "Object is too large.")
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("content_base64 is invalid") from exc
    if len(payload) > limit:
        raise McpToolError(ToolErrorCode.OBJECT_TOO_LARGE, "Object is too large.")
    return payload
