from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
from dataclasses import dataclass
from typing import Any

from minio.sse import SseS3

from services.parser_configuration.errors import ParserConfigurationError
from storage.minio import MinioDB


@dataclass(frozen=True)
class StoredSampleObjects:
    raw_object_key: str
    redacted_object_key: str
    response_sha256: str
    response_bytes: int


class _ParserSampleStorageError(ParserConfigurationError):
    def __init__(
        self, code: str, message: str, *, cleanup_retryable_object_keys: tuple[str, ...]
    ) -> None:
        self.cleanup_retryable_object_keys = cleanup_retryable_object_keys
        details = (
            {
                "cleanup_retryable": True,
                "cleanup_failure_count": len(cleanup_retryable_object_keys),
            }
            if cleanup_retryable_object_keys
            else None
        )
        super().__init__(code, message, details=details)


class ParserSampleObjectStore:
    def __init__(
        self,
        minio: MinioDB,
        *,
        bucket: str,
        sse_enabled: bool,
        storage_ready: bool,
    ) -> None:
        self._minio = minio
        self._bucket = bucket
        self._sse_enabled = sse_enabled
        self._storage_ready = storage_ready
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()

    async def write_pair(
        self, *, ba_id: int, raw: bytes, redacted: bytes
    ) -> StoredSampleObjects:
        if isinstance(ba_id, bool) or not isinstance(ba_id, int) or ba_id <= 0:
            raise ValueError("ba_id must be a positive integer")
        self._require_storage_ready()
        await self._ensure_private_bucket()
        object_prefix = f"actions/{ba_id}/{uuid.uuid4().hex}"
        raw_key = f"{object_prefix}/raw.json"
        redacted_key = f"{object_prefix}/redacted.json"
        written: list[str] = []
        try:
            await self._put(raw_key, raw)
            written.append(raw_key)
            await self._put(redacted_key, redacted)
            written.append(redacted_key)
        except Exception:
            cleanup_failures = await self._remove_objects(reversed(written))
            raise _ParserSampleStorageError(
                "sample_storage_failed",
                "Failed to store parser sample",
                cleanup_retryable_object_keys=cleanup_failures,
            ) from None

        return StoredSampleObjects(
            raw_object_key=raw_key,
            redacted_object_key=redacted_key,
            response_sha256=hashlib.sha256(raw).hexdigest(),
            response_bytes=len(raw),
        )

    async def read_raw(self, object_key: str) -> bytes:
        return await self._read(object_key)

    async def read_redacted(self, object_key: str) -> bytes:
        return await self._read(object_key)

    async def delete_pair(self, raw_object_key: str, redacted_object_key: str) -> None:
        self._require_storage_ready()
        cleanup_failures = await self._remove_objects(
            (raw_object_key, redacted_object_key)
        )
        if cleanup_failures:
            raise _ParserSampleStorageError(
                "sample_cleanup_failed",
                "Failed to delete parser sample",
                cleanup_retryable_object_keys=cleanup_failures,
            ) from None

    async def _remove_objects(self, object_keys: Any) -> tuple[str, ...]:
        cleanup_failures: list[str] = []
        for object_key in object_keys:
            try:
                await self._minio.aremove_object(self._bucket, object_key)
            except Exception as error:
                if _is_not_found(error):
                    continue
                cleanup_failures.append(object_key)
        return tuple(cleanup_failures)

    async def _ensure_private_bucket(self) -> None:
        if self._bucket_ready:
            return
        async with self._bucket_lock:
            if self._bucket_ready:
                return
            try:
                if not await self._minio.abucket_exists(self._bucket):
                    await self._minio.amake_bucket(self._bucket)
                else:
                    await self._check_existing_bucket_policy()
            except ParserConfigurationError:
                raise
            except Exception:
                raise ParserConfigurationError(
                    "sample_storage_failed", "Failed to prepare parser sample storage"
                ) from None
            self._bucket_ready = True

    async def _check_existing_bucket_policy(self) -> None:
        try:
            policy = await asyncio.to_thread(
                self._minio.client.get_bucket_policy, bucket_name=self._bucket
            )
        except Exception as error:
            if _error_code(error) == "NoSuchBucketPolicy":
                return
            raise
        if policy:
            raise ParserConfigurationError(
                "parser_storage_not_private",
                "Parser sample bucket must not have an anonymous policy",
            )

    async def _put(self, object_key: str, payload: bytes) -> None:
        kwargs: dict[str, Any] = {"content_type": "application/json"}
        if self._sse_enabled:
            kwargs["sse"] = SseS3()
        await self._minio.aput_object(
            self._bucket,
            object_key,
            io.BytesIO(payload),
            len(payload),
            **kwargs,
        )

    async def _read(self, object_key: str) -> bytes:
        self._require_storage_ready()
        try:
            async with await self._minio.aget_object(
                self._bucket, object_key
            ) as response:
                return await response.read()
        except Exception as error:
            if _is_not_found(error):
                raise ParserConfigurationError(
                    "sample_object_missing",
                    "Parser sample object is missing",
                    status_code=404,
                ) from None
            raise ParserConfigurationError(
                "sample_storage_failed", "Failed to read parser sample"
            ) from None

    def _require_storage_ready(self) -> None:
        if not self._storage_ready:
            raise ParserConfigurationError(
                "parser_storage_not_ready", "Parser sample storage is not ready"
            )


def _error_code(error: BaseException) -> str | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, str):
            return code
        current = getattr(current, "original_error", None) or current.__cause__
    return None


def _is_not_found(error: BaseException) -> bool:
    return _error_code(error) in {
        "NoSuchKey",
        "NoSuchObject",
        "NoSuchVersion",
        "NOT_FOUND",
    }


__all__ = ["ParserSampleObjectStore", "StoredSampleObjects"]
