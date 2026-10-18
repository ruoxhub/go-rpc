"""Tests for redis sub-package structure."""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.redis import RedisDB
from storage.redis.sync import SyncRedisImpl
from storage.redis._async import AsyncRedisImpl
from storage.redis._base import (
    convert_redis_error, logger, Encoder,
    SCAN_BATCH_SIZE, DELETE_CHUNK_SIZE,
)
from storage.exceptions import RedisOperationError


def test_redis_imports():
    assert RedisDB is not None
    assert SyncRedisImpl is not None
    assert AsyncRedisImpl is not None


@pytest.mark.asyncio
async def test_async_mget_delegates_one_call_to_redis_client():
    client = MagicMock(mget=AsyncMock(return_value=[b"one", b"two"]))

    result = await AsyncRedisImpl(client).amget(["first", "second"])

    assert result == [b"one", b"two"]
    client.mget.assert_awaited_once_with(["first", "second"])


@pytest.mark.asyncio
async def test_async_redis_db_exposes_owned_raw_client_without_double_close(monkeypatch):
    import storage.redis as redis_module

    raw_client = MagicMock(aclose=AsyncMock())
    monkeypatch.setattr(
        redis_module.AsyncRedis,
        "from_url",
        MagicMock(return_value=raw_client),
    )

    redis_db = RedisDB("redis://redis.internal:6379/4", amode=True)

    assert redis_db.get_redis_obj() is raw_client
    await redis_db.aclose()
    raw_client.aclose.assert_awaited_once_with()


def test_convert_redis_error_generic():
    err = convert_redis_error(ValueError("test"))
    assert isinstance(err, RedisOperationError)


def test_convert_redis_error_connection():
    import redis
    from storage.exceptions import ConnectionError as StoreConnErr
    err = convert_redis_error(redis.ConnectionError("conn failed"))
    assert isinstance(err, StoreConnErr)


def test_convert_redis_error_timeout():
    import redis
    from storage.exceptions import TimeoutError as StoreTimeout
    err = convert_redis_error(redis.TimeoutError("timed out"))
    assert isinstance(err, StoreTimeout)


def test_constants_preserved():
    assert SCAN_BATCH_SIZE == 500
    assert DELETE_CHUNK_SIZE == 100


def test_encoder_handles_list():
    import json
    enc = Encoder(encoding="utf-8", encoding_errors="strict", decode_responses=False)
    result = enc.encode([1, 2, 3])
    assert json.loads(result) == [1, 2, 3]


def test_encoder_handles_dict():
    import json
    enc = Encoder(encoding="utf-8", encoding_errors="strict", decode_responses=False)
    result = enc.encode({"key": "value"})
    assert json.loads(result) == {"key": "value"}


def test_logger_exists():
    assert logger is not None


def test_async_initialization_log_redacts_redis_credentials(monkeypatch):
    import storage.redis as redis_module

    fake_client = MagicMock()
    fake_logger = MagicMock()
    monkeypatch.setattr(redis_module.AsyncRedis, "from_url", MagicMock(return_value=fake_client))
    monkeypatch.setattr(redis_module, "logger", fake_logger)

    RedisDB(
        "redis://named-user:secret-password@redis.internal:6379/4?token=query-secret",
        amode=True,
    )

    rendered = " ".join(str(call) for call in fake_logger.info.call_args_list)
    assert "redis.internal:6379/4" in rendered
    assert "named-user" not in rendered
    assert "secret-password" not in rendered
    assert "query-secret" not in rendered


@pytest.mark.parametrize(
    "message, secret",
    [
        (
            "connection failed for redis://named-user:secret-password@redis.internal:6379/4",
            "secret-password",
        ),
        ("password=secret-password", "secret-password"),
    ],
)
def test_connection_error_log_redacts_credentials(monkeypatch, message, secret):
    import storage.redis as redis_module

    fake_client = MagicMock()
    fake_client.ping.side_effect = RuntimeError(message)
    fake_logger = MagicMock()
    monkeypatch.setattr(redis_module.SyncRedis, "from_url", MagicMock(return_value=fake_client))
    monkeypatch.setattr(redis_module, "logger", fake_logger)

    with pytest.raises(Exception):
        RedisDB("redis://redis.internal:6379/4", amode=False)

    rendered = " ".join(str(call) for call in fake_logger.error.call_args_list)
    assert secret not in rendered
    assert "RuntimeError" in rendered
