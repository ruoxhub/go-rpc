# -*- coding: utf-8 -*-
"""Synchronous MinIO implementation."""

from typing import Any, Dict, List, Optional, Generator
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


class SyncMinioImpl:
    """Synchronous MinIO storage implementation."""

    def __init__(self, client: Minio):
        self._client = client

    # ------------------- Bucket Operations -------------------

    def make_bucket(
        self, bucket_name: str, location: str = None, object_lock: bool = False
    ):
        """Create a new bucket."""
        try:
            if not self._client.bucket_exists(bucket_name):
                self._client.make_bucket(
                    bucket_name, location=location, object_lock=object_lock
                )
        except S3Error as e:
            logger.error(f"Failed to create bucket {bucket_name}: {e}")
            raise

    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists."""
        return self._client.bucket_exists(bucket_name)

    def list_buckets(self) -> List[Bucket]:
        """List all buckets."""
        return self._client.list_buckets()

    def remove_bucket(self, bucket_name: str):
        """Remove an empty bucket."""
        try:
            self._client.remove_bucket(bucket_name)
        except S3Error as e:
            logger.error(f"Failed to remove bucket {bucket_name}: {e}")
            raise

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
        return self._client.put_object(
            bucket_name,
            object_name,
            data,
            length,
            content_type=content_type,
            metadata=metadata,
            **kwargs,
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
        return self._client.fput_object(
            bucket_name,
            object_name,
            file_path,
            content_type=content_type,
            metadata=metadata,
            **kwargs,
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
        return self._client.get_object(
            bucket_name, object_name, offset, length, **kwargs
        )

    def fget_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        request_headers: Dict[str, str] = None,
        **kwargs,
    ):
        """Download an object to a file."""
        return self._client.fget_object(
            bucket_name, object_name, file_path, request_headers, **kwargs
        )

    def remove_object(self, bucket_name: str, object_name: str, version_id: str = None):
        """Remove an object."""
        return self._client.remove_object(
            bucket_name, object_name, version_id=version_id
        )

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
        return self._client.list_objects(
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
        return self._client.stat_object(
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
        return self._client.get_presigned_url(
            "GET",
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
        return self._client.get_presigned_url(
            "PUT",
            bucket_name,
            object_name,
            expires=expires,
        )

    # ------------------- Object Existence Check -------------------

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """Check if object exists in bucket."""
        try:
            self._client.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise
