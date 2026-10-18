from __future__ import annotations

import hashlib
import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from minio.sse import SseS3

from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.storage import ParserSampleObjectStore


class _S3Error(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _ResponseContext:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.exited = True

    async def read(self) -> bytes:
        return self.payload


def _minio(*, bucket_exists: bool = True) -> MagicMock:
    minio = MagicMock()
    minio.abucket_exists = AsyncMock(return_value=bucket_exists)
    minio.amake_bucket = AsyncMock()
    minio.aput_object = AsyncMock(return_value=object())
    minio.aget_object = AsyncMock()
    minio.aremove_object = AsyncMock()
    minio.client = MagicMock()
    minio.client.get_bucket_policy.side_effect = _S3Error("NoSuchBucketPolicy")
    return minio


def _store(minio: MagicMock, **kwargs) -> ParserSampleObjectStore:
    return ParserSampleObjectStore(
        minio,
        bucket="parser-samples",
        sse_enabled=False,
        storage_ready=True,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_write_pair_compensates_first_object_when_second_fails():
    sensitive = "TASK9_SECRET_SENTINEL_token"
    minio = _minio()
    minio.aput_object.side_effect = [
        object(),
        RuntimeError(f"write failed: {sensitive}"),
    ]
    store = _store(minio)

    with pytest.raises(ParserConfigurationError) as caught:
        await store.write_pair(
            ba_id=7,
            raw=f'{{"secret":"{sensitive}"}}'.encode(),
            redacted=b'{"secret":"x"}',
        )

    assert caught.value.code == "sample_storage_failed"
    raw_key = minio.aput_object.await_args_list[0].args[1]
    exposed = f"{caught.value} {json.dumps(caught.value.details)}"
    assert sensitive not in exposed
    assert "write failed" not in exposed
    assert raw_key not in exposed
    minio.aremove_object.assert_awaited_once_with("parser-samples", raw_key)


@pytest.mark.asyncio
async def test_write_pair_preserves_retry_evidence_when_compensation_fails():
    sensitive = "TASK9_CLEANUP_SENTINEL_token"
    minio = _minio()
    minio.aput_object.side_effect = [
        object(),
        RuntimeError(f"upload failed: {sensitive}"),
    ]
    minio.aremove_object.side_effect = RuntimeError(f"cleanup failed: {sensitive}")
    store = _store(minio)

    with pytest.raises(ParserConfigurationError) as caught:
        await store.write_pair(
            ba_id=7,
            raw=f'{{"secret":"{sensitive}"}}'.encode(),
            redacted=b'{"secret":"x"}',
        )

    raw_key = minio.aput_object.await_args_list[0].args[1]
    assert getattr(caught.value, "cleanup_retryable_object_keys") == (raw_key,)
    assert caught.value.details == {
        "cleanup_retryable": True,
        "cleanup_failure_count": 1,
    }
    exposed = f"{caught.value} {json.dumps(caught.value.details)}"
    assert sensitive not in exposed
    assert "upload failed" not in exposed
    assert "cleanup failed" not in exposed
    assert raw_key not in exposed


@pytest.mark.asyncio
async def test_release_not_ready_never_touches_minio():
    minio = _minio()
    store = ParserSampleObjectStore(
        minio,
        bucket="parser-samples",
        sse_enabled=False,
        storage_ready=False,
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await store.write_pair(ba_id=7, raw=b"{}", redacted=b"{}")

    assert caught.value.code == "parser_storage_not_ready"
    minio.abucket_exists.assert_not_awaited()
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("ba_id", [0, -1, True, "../7"])
async def test_invalid_ba_id_never_reaches_minio(ba_id):
    minio = _minio()
    store = _store(minio)

    with pytest.raises(ValueError, match="ba_id"):
        await store.write_pair(ba_id=ba_id, raw=b"{}", redacted=b"{}")

    minio.abucket_exists.assert_not_awaited()
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_bucket_is_created_only_once_for_repeated_writes():
    minio = _minio(bucket_exists=False)
    store = _store(minio)

    await store.write_pair(ba_id=7, raw=b"{}", redacted=b"{}")
    await store.write_pair(ba_id=7, raw=b"{}", redacted=b"{}")

    minio.abucket_exists.assert_awaited_once_with("parser-samples")
    minio.amake_bucket.assert_awaited_once_with("parser-samples")


@pytest.mark.asyncio
async def test_existing_bucket_with_anonymous_policy_fails_closed():
    minio = _minio()
    minio.client.get_bucket_policy.side_effect = None
    minio.client.get_bucket_policy.return_value = '{"Statement":[{}]}'
    store = _store(minio)

    with pytest.raises(ParserConfigurationError) as caught:
        await store.write_pair(ba_id=7, raw=b"{}", redacted=b"{}")

    assert caught.value.code == "parser_storage_not_private"
    minio.aput_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_sse_uploads_canonical_bytes_and_returns_integrity_metadata():
    minio = _minio()
    store = ParserSampleObjectStore(
        minio,
        bucket="parser-samples",
        sse_enabled=True,
        storage_ready=True,
    )
    raw = b'{"secret":1}'
    redacted = b'{"secret":"x"}'

    stored = await store.write_pair(ba_id=7, raw=raw, redacted=redacted)

    assert stored.response_bytes == len(raw)
    assert stored.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert re.fullmatch(r"actions/7/[0-9a-f]{32}/raw\.json", stored.raw_object_key)
    assert stored.redacted_object_key == stored.raw_object_key.replace(
        "/raw.json", "/redacted.json"
    )
    for call, payload in zip(minio.aput_object.await_args_list, (raw, redacted)):
        assert call.args[:2] == (
            "parser-samples",
            stored.raw_object_key if payload is raw else stored.redacted_object_key,
        )
        assert call.args[2].getvalue() == payload
        assert call.args[3] == len(payload)
        assert call.kwargs["content_type"] == "application/json"
        assert isinstance(call.kwargs["sse"], SseS3)


@pytest.mark.asyncio
async def test_read_raw_uses_response_context_manager():
    minio = _minio()
    response = _ResponseContext(b'{"ok":true}')
    minio.aget_object.return_value = response
    store = _store(minio)

    payload = await store.read_raw("actions/7/id/raw.json")

    assert payload == b'{"ok":true}'
    assert response.entered
    assert response.exited


@pytest.mark.asyncio
async def test_read_redacted_uses_response_context_manager():
    minio = _minio()
    response = _ResponseContext(b'{"secret":"x"}')
    minio.aget_object.return_value = response
    store = _store(minio)

    payload = await store.read_redacted("actions/7/id/redacted.json")

    assert payload == b'{"secret":"x"}'
    assert response.exited


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reader", "object_key"),
    [
        ("read_raw", "actions/7/id/raw.json"),
        ("read_redacted", "actions/7/id/redacted.json"),
    ],
)
async def test_read_missing_object_maps_s3_not_found_to_stable_404(
    reader, object_key
):
    minio = _minio()
    minio.aget_object.side_effect = _S3Error("NoSuchKey")
    store = _store(minio)

    with pytest.raises(ParserConfigurationError) as caught:
        await getattr(store, reader)(object_key)

    assert caught.value.code == "sample_object_missing"
    assert caught.value.status_code == 404
    assert object_key not in str(caught.value)


@pytest.mark.asyncio
async def test_delete_pair_treats_not_found_as_idempotent_success():
    minio = _minio()
    minio.aremove_object.side_effect = [_S3Error("NoSuchKey"), None]
    store = _store(minio)

    await store.delete_pair("actions/7/id/raw.json", "actions/7/id/redacted.json")

    assert minio.aremove_object.await_count == 2


@pytest.mark.asyncio
async def test_delete_pair_keeps_failed_keys_internal_and_continues_cleanup():
    sensitive = "TASK9_DELETE_SENTINEL_token"
    minio = _minio()
    minio.aremove_object.side_effect = [
        RuntimeError(f"backend unavailable: {sensitive}"),
        None,
    ]
    store = _store(minio)

    with pytest.raises(ParserConfigurationError) as caught:
        await store.delete_pair("actions/7/id/raw.json", "actions/7/id/redacted.json")

    assert caught.value.code == "sample_cleanup_failed"
    assert minio.aremove_object.await_count == 2
    assert getattr(caught.value, "cleanup_retryable_object_keys") == (
        "actions/7/id/raw.json",
    )
    assert caught.value.details == {
        "cleanup_retryable": True,
        "cleanup_failure_count": 1,
    }
    exposed = f"{caught.value} {json.dumps(caught.value.details)}"
    assert sensitive not in exposed
    assert "backend unavailable" not in exposed
    assert "actions/7/id/raw.json" not in exposed
