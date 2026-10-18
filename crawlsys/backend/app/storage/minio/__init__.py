# -*- coding: utf-8 -*-
"""MinIO storage backend — unified MinioDB factory class.

This sub-package splits the original monolithic minio.py into:
  - _base.py: shared imports, logger, error conversion
  - sync.py: SyncMinioImpl (synchronous operations)
  - async.py: AsyncMinioImpl (asynchronous operations)
  - __init__.py: MinioDB (factory + connection management)
"""

import asyncio
import io
from typing import Any, Dict, List, Optional, Generator, AsyncGenerator
from functools import partial

from minio import Minio
from minio.error import S3Error
from minio.datatypes import Object, Bucket

from storage.base import BaseStore
from common.decorators import require_sync, require_async
from ._base import (
    StoreConnectionError,
    OperationError,
    logger,
)
import importlib as _importlib

from .sync import SyncMinioImpl

_async_mod = _importlib.import_module(".async", package=__name__)
AsyncMinioImpl = _async_mod.AsyncMinioImpl


class MinioDB(BaseStore):
    """Unified Minio manager supporting both sync and async operations.

    For async operations, it wraps blocking Minio calls in a thread pool executor.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = True,
        region: Optional[str] = None,
        session_token: Optional[str] = None,
        amode: bool = False,
        **kwargs,
    ):
        """Initialize MinioManager.

        Args:
            endpoint: Minio server endpoint (e.g. 'play.min.io')
            access_key: Access key
            secret_key: Secret key
            secure: Use HTTPS if True
            region: Region name
            session_token: Session token
            amode: Enable async mode
            **kwargs: Additional arguments for Minio client
        """
        super().__init__(amode=amode, **kwargs)
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._secure = secure
        self._region = region
        self._session_token = session_token

        # Initialize Minio client
        try:
            self._client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
                region=region,
                session_token=session_token,
                **kwargs,
            )
            self._connected = True
            logger.info(f"Minio client initialized: {endpoint} (async={amode})")
        except (S3Error, ValueError) as e:
            logger.error(f"Failed to initialize Minio client: {e}")
            self._connected = False
            raise StoreConnectionError(
                f"Failed to initialize Minio client: {e}", original_error=e
            ) from e

        # Initialize implementation based on mode
        if amode:
            self._impl = AsyncMinioImpl(self._client, self._run_async)
        else:
            self._impl = SyncMinioImpl(self._client)

    @property
    def client(self) -> Minio:
        return self._client

    # ------------------- BaseStore Abstract Methods -------------------

    @require_sync("connect")
    def connect(self):
        """Establish connection to Minio (Sync).

        Minio client is stateless and connects on each request.
        This method validates the connection by listing buckets.
        """
        try:
            self._client.list_buckets()
            self._connected = True
            logger.info(f"Minio connection verified [mode=sync]: {self._endpoint}")
        except S3Error as e:
            self._connected = False
            logger.error(f"Failed to connect to Minio: {e}")
            raise StoreConnectionError(
                f"Failed to connect to Minio: {e}", original_error=e
            )

    @require_async("connect")
    async def aconnect(self):
        """Establish connection to Minio (Async).

        Minio client is stateless and connects on each request.
        This method validates the connection by listing buckets.
        """
        try:
            await self._run_async(self._client.list_buckets)
            self._connected = True
            logger.info(f"Minio connection verified [mode=async]: {self._endpoint}")
        except S3Error as e:
            self._connected = False
            logger.error(f"Failed to connect to Minio: {e}")
            raise StoreConnectionError(
                f"Failed to connect to Minio: {e}", original_error=e
            )

    @require_sync("close")
    def close(self):
        """Close Minio connection (Sync).

        Minio client is stateless and doesn't require explicit closing.
        This method just updates the connection status.
        """
        self._connected = False
        logger.info(f"Minio connection closed [mode=sync]: {self._endpoint}")

    @require_async("close")
    async def aclose(self):
        """Close Minio connection (Async).

        Minio client is stateless and doesn't require explicit closing.
        This method just updates the connection status.
        """
        self._connected = False
        logger.info(f"Minio connection closed [mode=async]: {self._endpoint}")

    @require_sync("ping")
    def ping(self) -> bool:
        """Check Minio connection status (Sync).

        Returns:
            True if connection is healthy, False otherwise.
        """
        try:
            self._client.list_buckets()
            return True
        except Exception as e:
            logger.error(f"Minio ping failed: {e}")
            self._connected = False
            return False

    @require_async("ping")
    async def aping(self) -> bool:
        """Check Minio connection status (Async).

        Returns:
            True if connection is healthy, False otherwise.
        """
        try:
            await self._run_async(self._client.list_buckets)
            return True
        except Exception as e:
            logger.error(f"Minio async ping failed: {e}")
            self._connected = False
            return False

    async def _run_async(self, func, *args, **kwargs):
        """Run blocking function in executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # ------------------- Bucket Operations -------------------

    def make_bucket(
        self, bucket_name: str, location: str = None, object_lock: bool = False
    ):
        """Create a new bucket."""
        return self._impl.make_bucket(bucket_name, location, object_lock)

    async def amake_bucket(
        self, bucket_name: str, location: str = None, object_lock: bool = False
    ):
        """Asynchronously create a new bucket."""
        return await self._impl.make_bucket(bucket_name, location, object_lock)

    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists."""
        return self._impl.bucket_exists(bucket_name)

    async def abucket_exists(self, bucket_name: str) -> bool:
        """Asynchronously check if bucket exists."""
        return await self._impl.bucket_exists(bucket_name)

    def list_buckets(self) -> List[Bucket]:
        """List all buckets."""
        return self._impl.list_buckets()

    async def alist_buckets(self) -> List[Bucket]:
        """Asynchronously list all buckets."""
        return await self._impl.list_buckets()

    def remove_bucket(self, bucket_name: str):
        """Remove an empty bucket."""
        return self._impl.remove_bucket(bucket_name)

    async def aremove_bucket(self, bucket_name: str):
        """Asynchronously remove an empty bucket."""
        return await self._impl.remove_bucket(bucket_name)

    # ------------------- Object Operations -------------------

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: io.BytesIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, str] = None,
        **kwargs,
    ):
        """Upload an object."""
        return self._impl.put_object(
            bucket_name, object_name, data, length, content_type, metadata, **kwargs
        )

    async def aput_object(
        self,
        bucket_name: str,
        object_name: str,
        data: io.BytesIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, str] = None,
        **kwargs,
    ):
        """Asynchronously upload an object."""
        return await self._impl.put_object(
            bucket_name, object_name, data, length, content_type, metadata, **kwargs
        )

    def fput_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, str] = None,
        **kwargs,
    ):
        """Upload a file as an object."""
        return self._impl.fput_object(
            bucket_name, object_name, file_path, content_type, metadata, **kwargs
        )

    async def afput_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, str] = None,
        **kwargs,
    ):
        """Asynchronously upload a file as an object."""
        return await self._impl.fput_object(
            bucket_name, object_name, file_path, content_type, metadata, **kwargs
        )

    def get_object(
        self,
        bucket_name: str,
        object_name: str,
        offset: int = 0,
        length: int = 0,
        **kwargs,
    ):
        """Get an object."""
        return self._impl.get_object(
            bucket_name, object_name, offset, length, **kwargs
        )

    async def aget_object(
        self,
        bucket_name: str,
        object_name: str,
        offset: int = 0,
        length: int = 0,
        **kwargs,
    ):
        """Asynchronously get an object.

        Returns an async context manager that closes the raw response on exit.
        Recommended usage:

        async with await manager.aget_object(...) as response:
            data = await response.read()
        """
        response = await self._impl.get_object(
            bucket_name, object_name, offset, length, **kwargs
        )
        return AsyncMinioResponse(response, self._run_async)

    def fget_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        request_headers: Dict[str, str] = None,
        **kwargs,
    ):
        """Download an object to a file."""
        return self._impl.fget_object(
            bucket_name, object_name, file_path, request_headers, **kwargs
        )

    async def afget_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        request_headers: Dict[str, str] = None,
        **kwargs,
    ):
        """Asynchronously download an object to a file."""
        return await self._impl.fget_object(
            bucket_name, object_name, file_path, request_headers, **kwargs
        )

    def remove_object(self, bucket_name: str, object_name: str, version_id: str = None):
        """Remove an object."""
        return self._impl.remove_object(bucket_name, object_name, version_id)

    async def aremove_object(
        self, bucket_name: str, object_name: str, version_id: str = None
    ):
        """Asynchronously remove an object."""
        return await self._impl.remove_object(bucket_name, object_name, version_id)

    def list_objects(
        self,
        bucket_name: str,
        prefix: str = None,
        recursive: bool = False,
        start_after: str = None,
        include_user_meta: bool = False,
        include_version: bool = False,
    ) -> Generator[Object, None, None]:
        """List objects in a bucket."""
        return self._impl.list_objects(
            bucket_name,
            prefix=prefix,
            recursive=recursive,
            start_after=start_after,
            include_user_meta=include_user_meta,
            include_version=include_version,
        )

    async def alist_objects(
        self,
        bucket_name: str,
        prefix: str = None,
        recursive: bool = False,
        start_after: str = None,
        include_user_meta: bool = False,
        include_version: bool = False,
    ) -> List[Object]:
        """Asynchronously list objects.

        Returns a list instead of generator to ensure non-blocking behavior.
        """
        return await self._impl.list_objects(
            bucket_name,
            prefix=prefix,
            recursive=recursive,
            start_after=start_after,
            include_user_meta=include_user_meta,
            include_version=include_version,
        )

    def stat_object(
        self,
        bucket_name: str,
        object_name: str,
        ssec: Any = None,
        version_id: str = None,
        extra_headers: Dict[str, str] = None,
        extra_query_params: Dict[str, str] = None,
    ):
        """Get object metadata."""
        return self._impl.stat_object(
            bucket_name,
            object_name,
            ssec=ssec,
            version_id=version_id,
            extra_headers=extra_headers,
            extra_query_params=extra_query_params,
        )

    async def astat_object(
        self,
        bucket_name: str,
        object_name: str,
        ssec: Any = None,
        version_id: str = None,
        extra_headers: Dict[str, str] = None,
        extra_query_params: Dict[str, str] = None,
    ):
        """Asynchronously get object metadata."""
        return await self._impl.stat_object(
            bucket_name,
            object_name,
            ssec=ssec,
            version_id=version_id,
            extra_headers=extra_headers,
            extra_query_params=extra_query_params,
        )

    # ------------------- Presigned URL Operations -------------------

    def presigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: Any = None,
        response_headers: Dict[str, str] = None,
        request_date: Any = None,
        version_id: str = None,
        extra_query_params: Dict[str, str] = None,
    ) -> str:
        """Get presigned URL for GET."""
        return self._impl.presigned_get_object(
            bucket_name,
            object_name,
            expires=expires,
            response_headers=response_headers,
            request_date=request_date,
            version_id=version_id,
            extra_query_params=extra_query_params,
        )

    async def apresigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: Any = None,
        response_headers: Dict[str, str] = None,
        request_date: Any = None,
        version_id: str = None,
        extra_query_params: Dict[str, str] = None,
    ) -> str:
        """Asynchronously get presigned URL for GET."""
        return await self._impl.presigned_get_object(
            bucket_name,
            object_name,
            expires=expires,
            response_headers=response_headers,
            request_date=request_date,
            version_id=version_id,
            extra_query_params=extra_query_params,
        )

    def presigned_put_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: Any = None,
    ) -> str:
        """Get presigned URL for PUT."""
        return self._impl.presigned_put_object(bucket_name, object_name, expires=expires)

    async def apresigned_put_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: Any = None,
    ) -> str:
        """Asynchronously get presigned URL for PUT."""
        return await self._impl.presigned_put_object(
            bucket_name, object_name, expires=expires
        )

    # ------------------- Object Existence Check -------------------

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """Check if object exists in bucket."""
        return self._impl.object_exists(bucket_name, object_name)

    async def aobject_exists(self, bucket_name: str, object_name: str) -> bool:
        """Asynchronously check if object exists in bucket."""
        return await self._impl.object_exists(bucket_name, object_name)

    # ------------------- Async Streaming Support -------------------

    async def alist_objects_stream(
        self,
        bucket_name: str,
        prefix: str = None,
        recursive: bool = False,
        start_after: str = None,
        include_user_meta: bool = False,
        include_version: bool = False,
    ) -> AsyncGenerator[Object, None]:
        """Asynchronously stream objects using async generator.

        Yields objects one by one without loading all into memory.
        """
        async for obj in self._impl.list_objects_stream(
            bucket_name,
            prefix=prefix,
            recursive=recursive,
            start_after=start_after,
            include_user_meta=include_user_meta,
            include_version=include_version,
        ):
            yield obj


class AsyncMinioResponse:
    """异步友好的 Minio 响应上下文管理器"""

    def __init__(self, response, run_afunc):
        self._response = response
        self._run_async = run_afunc

    async def read(self):
        return await self._run_async(self._response.read)

    async def close(self):
        return await self._run_async(self._response.close)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
