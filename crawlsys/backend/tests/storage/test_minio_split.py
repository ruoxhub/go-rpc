"""Tests for minio_store sub-package structure."""
import sys
import os
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.minio import MinioDB
from storage.minio.sync import SyncMinioImpl
from storage.minio._base import convert_minio_error, logger
from storage.exceptions import MinioOperationError

# 'async' is a Python keyword, so we use importlib to import it
_async_mod = importlib.import_module("storage.minio.async")
AsyncMinioImpl = _async_mod.AsyncMinioImpl


def test_minio_imports():
    assert MinioDB is not None
    assert SyncMinioImpl is not None
    assert AsyncMinioImpl is not None


def test_convert_minio_error_generic():
    err = convert_minio_error(ValueError("test"))
    assert isinstance(err, MinioOperationError)


def test_logger_exists():
    assert logger is not None


def test_miniodb_is_class():
    """MinioDB should be a class inheriting from BaseStore."""
    from storage.base import BaseStore
    assert issubclass(MinioDB, BaseStore)


def test_sync_impl_has_all_methods():
    """SyncMinioImpl should have all expected operation methods."""
    expected_methods = [
        "make_bucket", "bucket_exists", "list_buckets", "remove_bucket",
        "put_object", "fput_object", "get_object", "fget_object",
        "remove_object", "list_objects", "stat_object",
        "presigned_get_object", "presigned_put_object", "object_exists",
    ]
    for method_name in expected_methods:
        assert hasattr(SyncMinioImpl, method_name), f"SyncMinioImpl missing {method_name}"


def test_async_impl_has_all_methods():
    """AsyncMinioImpl should have all expected operation methods."""
    expected_methods = [
        "make_bucket", "bucket_exists", "list_buckets", "remove_bucket",
        "put_object", "fput_object", "get_object", "fget_object",
        "remove_object", "list_objects", "stat_object",
        "presigned_get_object", "presigned_put_object", "object_exists",
        "list_objects_stream",
    ]
    for method_name in expected_methods:
        assert hasattr(AsyncMinioImpl, method_name), f"AsyncMinioImpl missing {method_name}"


def test_miniodb_has_all_public_methods():
    """MinioDB should expose both sync and async public API methods."""
    expected_methods = [
        # BaseStore methods
        "connect", "aconnect", "close", "aclose", "ping", "aping",
        # Bucket operations
        "make_bucket", "amake_bucket", "bucket_exists", "abucket_exists",
        "list_buckets", "alist_buckets", "remove_bucket", "aremove_bucket",
        # Object operations
        "put_object", "aput_object", "fput_object", "afput_object",
        "get_object", "aget_object", "fget_object", "afget_object",
        "remove_object", "aremove_object",
        "list_objects", "alist_objects", "stat_object", "astat_object",
        # Presigned URL operations
        "presigned_get_object", "apresigned_get_object",
        "presigned_put_object", "apresigned_put_object",
        # Object existence check
        "object_exists", "aobject_exists",
        # Async streaming
        "alist_objects_stream",
    ]
    for method_name in expected_methods:
        assert hasattr(MinioDB, method_name), f"MinioDB missing {method_name}"


def test_convert_minio_error_with_s3error():
    """convert_minio_error should wrap S3Error into MinioOperationError."""
    try:
        from minio.error import S3Error
        # Create a minimal S3Error for testing
        err = S3Error("test", "test", "test", "test", "test", None)
        result = convert_minio_error(err)
        assert isinstance(result, MinioOperationError)
    except ImportError:
        # minio not installed, skip
        pass


def test_async_minio_response_class():
    """AsyncMinioResponse should be importable from the package."""
    from storage.minio import AsyncMinioResponse
    assert AsyncMinioResponse is not None
    assert hasattr(AsyncMinioResponse, "read")
    assert hasattr(AsyncMinioResponse, "close")
    assert hasattr(AsyncMinioResponse, "__aenter__")
    assert hasattr(AsyncMinioResponse, "__aexit__")


@pytest.mark.asyncio
async def test_aget_object_wraps_raw_response_in_public_async_context():
    """The async API owns runner usage and exposes only async response operations."""
    from storage.minio import AsyncMinioResponse

    minio = object.__new__(MinioDB)
    raw_response = SimpleNamespace(read=MagicMock(return_value=b"payload"), close=MagicMock())
    minio._impl = SimpleNamespace(get_object=AsyncMock(return_value=raw_response))

    async def run_sync(callable_):
        return callable_()

    minio._run_async = AsyncMock(side_effect=run_sync)

    response = await minio.aget_object("media-assets", "clips/video.txt", length=7)

    assert isinstance(response, AsyncMinioResponse)
    async with response as opened_response:
        assert await opened_response.read() == b"payload"
    raw_response.close.assert_called_once_with()
    assert minio._run_async.await_count == 2


@pytest.mark.asyncio
async def test_aget_object_context_closes_raw_response_when_reading_raises():
    minio = object.__new__(MinioDB)
    raw_response = SimpleNamespace(
        read=MagicMock(side_effect=OSError("read failed")),
        close=MagicMock(),
    )
    minio._impl = SimpleNamespace(get_object=AsyncMock(return_value=raw_response))

    async def run_sync(callable_):
        return callable_()

    minio._run_async = AsyncMock(side_effect=run_sync)

    with pytest.raises(OSError, match="read failed"):
        async with await minio.aget_object("media-assets", "clips/video.txt") as response:
            await response.read()

    raw_response.close.assert_called_once_with()
