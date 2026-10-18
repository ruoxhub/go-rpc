"""MinIO MCP adapter non-destructive management tool behavior tests."""

import base64
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from minio.error import S3Error

from core.config import McpConfig
from mcp_adapter.context import McpAppResources
from mcp_adapter.schemas import ToolErrorCode, ToolResponse


def _object(name: str, *, size: int = 4, content_type: str = "text/plain"):
    return SimpleNamespace(
        object_name=name,
        size=size,
        etag="etag-1",
        content_type=content_type,
        last_modified=datetime(2026, 8, 6, 12, 0),
        version_id="version-1",
        metadata={"source": "test"},
    )


async def _stream(items):
    for item in items:
        yield item


async def _raising_stream(exc):
    raise exc
    yield  # pragma: no cover


class _AsyncResponse:
    def __init__(self, *, payload: bytes | None = None, error: Exception | None = None):
        self.read = AsyncMock(return_value=payload)
        if error is not None:
            self.read.side_effect = error
        self.close = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        await self.close()


class _OversizedBase64(str):
    def __new__(cls, length: int):
        instance = super().__new__(cls, "A")
        instance._length = length
        return instance

    def __len__(self):
        return self._length


def _s3_error(code: str, *, message: str = "storage secret") -> S3Error:
    return S3Error(
        response=MagicMock(),
        code=code,
        message=message,
        resource="private/object",
        request_id="request-secret",
        host_id="host-secret",
        bucket_name="private-bucket",
        object_name="private-object",
    )


@pytest.fixture
def minio():
    client = SimpleNamespace(
        alist_buckets=AsyncMock(),
        amake_bucket=AsyncMock(),
        abucket_exists=AsyncMock(),
        astat_object=AsyncMock(),
        apresigned_get_object=AsyncMock(),
        apresigned_put_object=AsyncMock(),
        aget_object=AsyncMock(),
        aput_object=AsyncMock(),
        alist_objects_stream=MagicMock(),
    )
    return client


@pytest.fixture
def resources(minio):
    config = McpConfig(
        inline_object_limit_bytes=8,
        inline_object_hard_limit_bytes=10,
        presigned_expiry_minutes=15,
    )
    return McpAppResources(db=object(), minio=minio, config=config)


@pytest.mark.asyncio
async def test_list_buckets_returns_structured_bucket_metadata(resources, minio):
    from mcp_adapter.minio_tools import list_buckets

    minio.alist_buckets.return_value = [
        SimpleNamespace(name="media-assets", creation_date=datetime(2026, 8, 6, 10, 0))
    ]

    response = await list_buckets(resources)

    assert isinstance(response, ToolResponse)
    assert response.data[0].model_dump() == {
        "name": "media-assets",
        "creation_date": datetime(2026, 8, 6, 10, 0),
    }
    minio.alist_buckets.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_list_buckets_maps_storage_failure_without_sdk_details(resources, minio):
    from mcp_adapter.minio_tools import list_buckets

    minio.alist_buckets.side_effect = _s3_error("AccessDenied")

    response = await list_buckets(resources)

    assert response.error.code is ToolErrorCode.STORAGE_UNAVAILABLE
    assert "secret" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_create_bucket_creates_missing_bucket_with_optional_region(resources, minio):
    from mcp_adapter.minio_tools import create_bucket

    minio.abucket_exists.return_value = False

    response = await create_bucket(resources, "media-assets", region="cn-east-1")

    assert isinstance(response, ToolResponse)
    assert response.data.model_dump() == {"name": "media-assets", "creation_date": None}
    minio.amake_bucket.assert_awaited_once_with("media-assets", "cn-east-1")


@pytest.mark.asyncio
async def test_create_bucket_is_idempotent_when_bucket_already_exists(resources, minio):
    from mcp_adapter.minio_tools import create_bucket

    minio.abucket_exists.return_value = True

    response = await create_bucket(resources, "media-assets")

    assert response.ok is True
    assert response.meta == {"created": False}
    minio.amake_bucket.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_bucket_maps_storage_failure_without_sdk_details(resources, minio):
    from mcp_adapter.minio_tools import create_bucket

    minio.abucket_exists.return_value = False
    minio.amake_bucket.side_effect = _s3_error("AccessDenied")

    response = await create_bucket(resources, "media-assets")

    assert response.error.code is ToolErrorCode.STORAGE_UNAVAILABLE
    assert "secret" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_list_objects_reads_only_limit_plus_one_and_uses_stable_start_after_cursor(resources, minio):
    from mcp_adapter.minio_tools import list_objects

    minio.alist_objects_stream.return_value = _stream([
        _object("clips/one.mp4"),
        _object("clips/two.mp4"),
        _object("clips/three.mp4"),
        _object("clips/must-not-be-read.mp4"),
    ])

    response = await list_objects(
        resources,
        "media-assets",
        prefix="clips/",
        recursive=True,
        limit=2,
        cursor="clips/previous.mp4",
    )

    assert [item.object_name for item in response.data] == ["clips/one.mp4", "clips/two.mp4"]
    assert response.meta == {"has_more": True, "limit": 2, "next_cursor": "clips/two.mp4"}
    minio.alist_objects_stream.assert_called_once_with(
        "media-assets",
        prefix="clips/",
        recursive=True,
        start_after="clips/previous.mp4",
        include_user_meta=True,
        include_version=True,
    )


@pytest.mark.asyncio
async def test_list_objects_maps_storage_failure_without_sdk_details(resources, minio):
    from mcp_adapter.minio_tools import list_objects

    minio.alist_objects_stream.return_value = _raising_stream(_s3_error("AccessDenied"))

    response = await list_objects(resources, "media-assets")

    assert response.error.code is ToolErrorCode.STORAGE_UNAVAILABLE
    assert "secret" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_stat_object_returns_not_found_error(resources, minio):
    from mcp_adapter.minio_tools import stat_object

    minio.astat_object.side_effect = FileNotFoundError

    response = await stat_object(resources, "media-assets", "missing.mp4")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.OBJECT_NOT_FOUND


@pytest.mark.asyncio
async def test_stat_object_returns_structured_metadata(resources, minio):
    from mcp_adapter.minio_tools import stat_object

    minio.astat_object.return_value = _object("clips/video.mp4")

    response = await stat_object(resources, "media-assets", "clips/video.mp4")

    assert isinstance(response, ToolResponse)
    assert response.data.object_name == "clips/video.mp4"
    assert response.data.metadata == {"source": "test"}


@pytest.mark.asyncio
async def test_download_url_uses_requested_expiry_after_confirming_object_exists(resources, minio):
    from mcp_adapter.minio_tools import get_object_download_url

    minio.astat_object.return_value = _object("clips/video.mp4")
    minio.apresigned_get_object.return_value = "https://minio.example/download"

    response = await get_object_download_url(resources, "media-assets", "clips/video.mp4", 30)

    assert response.data == {"url": "https://minio.example/download", "expires_minutes": 30}
    minio.apresigned_get_object.assert_awaited_once_with(
        "media-assets", "clips/video.mp4", expires=timedelta(minutes=30)
    )


@pytest.mark.asyncio
async def test_download_url_rejects_invalid_expiry_without_storage_call(resources, minio):
    from mcp_adapter.minio_tools import get_object_download_url

    response = await get_object_download_url(resources, "media-assets", "clips/video.mp4", 0)

    assert response.error.code is ToolErrorCode.INVALID_ARGUMENT
    minio.astat_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_object_content_checks_size_encodes_payload_and_closes_response(resources, minio):
    from mcp_adapter.minio_tools import get_object_content

    minio.astat_object.return_value = _object("clips/video.txt", size=4)
    response_object = _AsyncResponse(payload=b"data")
    minio.aget_object.return_value = response_object
    response = await get_object_content(resources, "media-assets", "clips/video.txt")

    assert response.data == {
        "bucket": "media-assets",
        "object_name": "clips/video.txt",
        "content_base64": base64.b64encode(b"data").decode("ascii"),
        "content_type": "text/plain",
        "size": 4,
    }
    minio.aget_object.assert_awaited_once_with("media-assets", "clips/video.txt", length=4)
    response_object.read.assert_awaited_once_with()
    response_object.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_get_object_content_rejects_oversized_object_before_download(resources, minio):
    from mcp_adapter.minio_tools import get_object_content

    minio.astat_object.return_value = _object("clips/large.mp4", size=9)

    response = await get_object_content(resources, "media-assets", "clips/large.mp4")

    assert response.error.code is ToolErrorCode.OBJECT_TOO_LARGE
    minio.aget_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_object_content_closes_response_when_reading_raises(resources, minio):
    from mcp_adapter.minio_tools import get_object_content

    minio.astat_object.return_value = _object("clips/failing.txt", size=4)
    response_object = _AsyncResponse(error=OSError("read failed"))
    minio.aget_object.return_value = response_object
    response = await get_object_content(resources, "media-assets", "clips/failing.txt")

    assert response.error.code is ToolErrorCode.STORAGE_UNAVAILABLE
    response_object.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_upload_url_uses_requested_expiry_after_confirming_bucket(resources, minio):
    from mcp_adapter.minio_tools import create_upload_url

    minio.abucket_exists.return_value = True
    minio.apresigned_put_object.return_value = "https://minio.example/upload"

    response = await create_upload_url(resources, "media-assets", "clips/new.mp4", 10)

    assert response.data == {"url": "https://minio.example/upload", "expires_minutes": 10}
    minio.apresigned_put_object.assert_awaited_once_with(
        "media-assets", "clips/new.mp4", expires=timedelta(minutes=10)
    )


@pytest.mark.asyncio
async def test_upload_url_returns_bucket_not_found(resources, minio):
    from mcp_adapter.minio_tools import create_upload_url

    minio.abucket_exists.return_value = False

    response = await create_upload_url(resources, "missing-bucket", "clips/new.mp4")

    assert response.error.code is ToolErrorCode.BUCKET_NOT_FOUND
    minio.apresigned_put_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_base64_decodes_strictly_and_uploads_real_byte_length(resources, minio):
    from mcp_adapter.minio_tools import upload_base64_object

    minio.abucket_exists.return_value = True
    minio.aput_object.return_value = SimpleNamespace(etag="etag-new", version_id="version-new")

    response = await upload_base64_object(
        resources,
        "media-assets",
        "clips/new.txt",
        base64.b64encode(b"data").decode("ascii"),
        "text/plain",
        {"source": "test"},
    )

    assert response.data.model_dump() == {
        "bucket": "media-assets",
        "object_name": "clips/new.txt",
        "size": 4,
        "etag": "etag-new",
        "version_id": "version-new",
    }
    args, kwargs = minio.aput_object.await_args
    assert args[:3] == ("media-assets", "clips/new.txt", args[2])
    assert args[2].read() == b"data"
    assert args[3] == 4
    assert kwargs == {"content_type": "text/plain", "metadata": {"source": "test"}}


@pytest.mark.asyncio
async def test_upload_base64_rejects_invalid_encoding_before_storage_calls(resources, minio):
    from mcp_adapter.minio_tools import upload_base64_object

    response = await upload_base64_object(
        resources, "media-assets", "clips/new.txt", "%%%%", "text/plain"
    )

    assert response.error.code is ToolErrorCode.INVALID_ARGUMENT
    minio.abucket_exists.assert_not_awaited()
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_base64_rejects_encoded_payload_before_allocating_decode_buffer(resources, minio):
    from mcp_adapter.minio_tools import upload_base64_object

    response = await upload_base64_object(
        resources, "media-assets", "clips/new.txt", "A" * 17, "text/plain"
    )

    assert response.error.code is ToolErrorCode.OBJECT_TOO_LARGE
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_base64_rechecks_actual_decoded_size(resources, minio):
    from mcp_adapter.minio_tools import upload_base64_object

    encoded = base64.b64encode(b"0123456789ab").decode("ascii")

    response = await upload_base64_object(
        resources, "media-assets", "clips/new.txt", encoded, "text/plain"
    )

    assert response.error.code is ToolErrorCode.OBJECT_TOO_LARGE
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_base64_enforces_service_hard_limit_when_config_is_bypassed(minio):
    from mcp_adapter.minio_tools import upload_base64_object

    service_hard_limit = 50 * 1024 * 1024
    resources = McpAppResources(
        db=object(),
        minio=minio,
        config=McpConfig(
            inline_object_limit_bytes=service_hard_limit + 1,
            inline_object_hard_limit_bytes=service_hard_limit + 1,
        ),
    )
    encoded_length = 4 * ((service_hard_limit + 2) // 3) + 1

    response = await upload_base64_object(
        resources,
        "media-assets",
        "clips/new.txt",
        _OversizedBase64(encoded_length),
        "text/plain",
    )

    assert response.error.code is ToolErrorCode.OBJECT_TOO_LARGE
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_object_content_enforces_service_hard_limit_when_config_is_bypassed(minio):
    from mcp_adapter.minio_tools import get_object_content

    service_hard_limit = 50 * 1024 * 1024
    resources = McpAppResources(
        db=object(),
        minio=minio,
        config=McpConfig(
            inline_object_limit_bytes=service_hard_limit + 1,
            inline_object_hard_limit_bytes=service_hard_limit + 1,
        ),
    )
    minio.astat_object.return_value = _object("clips/large.bin", size=service_hard_limit + 1)

    response = await get_object_content(resources, "media-assets", "clips/large.bin")

    assert response.error.code is ToolErrorCode.OBJECT_TOO_LARGE
    minio.aget_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_base64_rejects_oversized_metadata(resources, minio):
    from mcp_adapter.minio_tools import upload_base64_object

    response = await upload_base64_object(
        resources,
        "media-assets",
        "clips/new.txt",
        base64.b64encode(b"data").decode("ascii"),
        "text/plain",
        {"key": "v" * 1025},
    )

    assert response.error.code is ToolErrorCode.INVALID_ARGUMENT
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "setup", "args", "resource"),
    [
        ("stat_object", "astat_object", ("media-assets", "clips/missing.txt"), "object"),
        (
            "get_object_download_url",
            "astat_object",
            ("media-assets", "clips/missing.txt"),
            "object",
        ),
        (
            "get_object_content",
            "astat_object",
            ("media-assets", "clips/missing.txt"),
            "object",
        ),
        (
            "create_upload_url",
            "abucket_exists",
            ("media-assets", "clips/new.txt"),
            "bucket",
        ),
        (
            "upload_base64_object",
            "abucket_exists",
            (
                "media-assets",
                "clips/new.txt",
                base64.b64encode(b"data").decode("ascii"),
                "text/plain",
            ),
            "object",
        ),
    ],
)
async def test_remaining_tools_map_storage_failures_without_sdk_details(
    resources,
    minio,
    tool_name,
    setup,
    args,
    resource,
):
    import mcp_adapter.minio_tools as tools

    getattr(minio, setup).side_effect = _s3_error("AccessDenied")

    response = await getattr(tools, tool_name)(resources, *args)

    assert response.error.code is ToolErrorCode.STORAGE_UNAVAILABLE
    assert "secret" not in response.model_dump_json()


def test_minio_tool_module_has_no_public_deletion_surface():
    import mcp_adapter.minio_tools as tools

    public_functions = {
        name for name, value in vars(tools).items() if inspect.iscoroutinefunction(value) and not name.startswith("_")
    }

    assert "remove_object" not in vars(tools)
    assert "remove_bucket" not in vars(tools)
    assert not {name for name in public_functions if "delete" in name}
