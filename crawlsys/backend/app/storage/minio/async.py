# -*- coding: utf-8 -*-
"""Asynchronous MinIO implementation."""

from typing import Any, Dict, List, Optional, AsyncGenerator
import asyncio
import io

from minio import Minio
from minio.error import S3Error
from minio.datatypes import Object, Bucket

from ._base import (
    OperationError,
    NotFoundError,
    convert_minio_error,
    logger,
)


class AsyncMinioImpl:
    """Asynchronous MinIO storage implementation."""

    def __init__(self, client: Minio, run_afunc):
        self._client = client
        self._run_async = run_afunc

    # ------------------- Bucket Operations -------------------

    async def make_bucket(
        self, bucket_name: str, location: str = None, object_lock: bool = False
    ):
        """Asynchronously create a new bucket."""
        try:
            exists = await self._run_async(self._client.bucket_exists, bucket_name)
            if not exists:
                await self._run_async(
                    self._client.make_bucket,
                    bucket_name,
                    location=location,
                    object_lock=object_lock,
                )
        except S3Error as e:
            logger.error(f"Failed to create bucket {bucket_name}: {e}")
            raise

    async def bucket_exists(self, bucket_name: str) -> bool:
        """Asynchronously check if bucket exists."""
        return await self._run_async(self._client.bucket_exists, bucket_name)

    async def list_buckets(self) -> List[Bucket]:
        """Asynchronously list all buckets."""
        return await self._run_async(self._client.list_buckets)

    async def remove_bucket(self, bucket_name: str):
        """Asynchronously remove an empty bucket."""
        try:
            await self._run_async(self._client.remove_bucket, bucket_name)
        except S3Error as e:
            logger.error(f"Failed to remove bucket {bucket_name}: {e}")
            raise

    # ------------------- Object Operations -------------------

    async def put_object(
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
        return await self._run_async(
            self._client.put_object,
            bucket_name,
            object_name,
            data,
            length,
            content_type=content_type,
            metadata=metadata,
            **kwargs,
        )

    async def fput_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, str] = None,
        **kwargs,
    ):
        """Asynchronously upload a file as an object."""
        return await self._run_async(
            self._client.fput_object,
            bucket_name,
            object_name,
            file_path,
            content_type=content_type,
            metadata=metadata,
            **kwargs,
        )

    async def get_object(
        self,
        bucket_name: str,
        object_name: str,
        offset: int = 0,
        length: int = 0,
        **kwargs,
    ):
        """Asynchronously get an object.

        Warning: The returned response object MUST be closed after use to prevent resource leaks.
        Recommended usage:

        # 方式1: 手动关闭
        response = await manager.aget_object(...)
        try:
            data = await manager._run_async(response.read)
        finally:
            await manager._run_async(response.close)

        # 方式2: 使用上下文管理器（推荐）
        response = await manager.aget_object(...)
        async with AsyncMinioResponse(response, manager._run_async) as resp:
            data = await resp.read()
        """
        return await self._run_async(
            self._client.get_object, bucket_name, object_name, offset, length, **kwargs
        )

    async def fget_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        request_headers: Dict[str, str] = None,
        **kwargs,
    ):
        """Asynchronously download an object to a file."""
        return await self._run_async(
            self._client.fget_object,
            bucket_name,
            object_name,
            file_path,
            request_headers,
            **kwargs,
        )

    async def remove_object(
        self, bucket_name: str, object_name: str, version_id: str = None
    ):
        """Asynchronously remove an object."""
        return await self._run_async(
            self._client.remove_object, bucket_name, object_name, version_id=version_id
        )

    async def list_objects(
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

        def _list():
            return list(
                self._client.list_objects(
                    bucket_name,
                    prefix=prefix,
                    recursive=recursive,
                    start_after=start_after,
                    include_user_meta=include_user_meta,
                    include_version=include_version,
                )
            )

        return await self._run_async(_list)

    async def stat_object(
        self,
        bucket_name: str,
        object_name: str,
        ssec: Any = None,
        version_id: str = None,
        extra_headers: Dict[str, str] = None,
        extra_query_params: Dict[str, str] = None,
    ):
        """Asynchronously get object metadata."""
        return await self._run_async(
            self._client.stat_object,
            bucket_name,
            object_name,
            ssec=ssec,
            version_id=version_id,
            extra_headers=extra_headers,
            extra_query_params=extra_query_params,
        )

    # ------------------- Presigned URL Operations -------------------

    async def presigned_get_object(
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
        return await self._run_async(
            self._client.get_presigned_url,
            "GET",
            bucket_name,
            object_name,
            expires=expires,
            response_headers=response_headers,
            request_date=request_date,
            version_id=version_id,
            extra_query_params=extra_query_params,
        )

    async def presigned_put_object(
        self,
        bucket_name: str,
        object_name: str,
        expires: Any = None,
    ) -> str:
        """Asynchronously get presigned URL for PUT."""
        return await self._run_async(
            self._client.get_presigned_url,
            "PUT",
            bucket_name,
            object_name,
            expires=expires,
        )

    # ------------------- Object Existence Check -------------------

    async def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """Asynchronously check if object exists in bucket."""
        try:
            await self.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise

    # ------------------- Async Streaming Support -------------------

    async def list_objects_stream(
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
        # 获取生成器
        gen = await self._run_async(
            self._client.list_objects,
            bucket_name,
            prefix=prefix,
            recursive=recursive,
            start_after=start_after,
            include_user_meta=include_user_meta,
            include_version=include_version,
        )

        # 异步迭代
        for obj in gen:
            yield obj
            # 让出控制权
            await asyncio.sleep(0)
