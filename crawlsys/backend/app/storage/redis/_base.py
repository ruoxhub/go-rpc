# -*- coding: utf-8 -*-
"""Redis storage backend — shared base: Encoder, constants, error conversion."""

import json

import redis as _redis_lib
from redis.connection import Encoder as _Encoder
from redis.exceptions import ConnectionError, TimeoutError, DataError

from utils.log import get_logger
from storage.exceptions import (
    ConnectionError as StoreConnectionError,
    OperationError,
    TimeoutError as StoreTimeoutError,
    RedisOperationError,
)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = get_logger("storage.redis")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCAN_BATCH_SIZE = 500  # SCAN命令默认批次大小
DELETE_CHUNK_SIZE = 100  # 批量删除默认批次大小
DEFAULT_MEMORY_FILTER = 10 * 1024 * 1024  # 默认内存过滤阈值: 10MB

# ---------------------------------------------------------------------------
# Custom Encoder (supports JSON-serialisable types)
# ---------------------------------------------------------------------------

class Encoder(_Encoder):
    def encode(self, value):
        "Return a bytestring or bytes-like representation of the value"
        if isinstance(value, (bytes, memoryview)):
            return value
        # elif isinstance(value, bool):
        #     # special case bool since it is a subclass of int
        #     raise DataError(
        #         "Invalid input of type: 'bool'. Convert to a "
        #         "bytes, string, int or float first."
        #     )
        elif isinstance(value, float):
            value = repr(value).encode()
        elif isinstance(value, int):
            # python 2 repr() on longs is '123L', so use str() instead
            value = str(value).encode()
        elif isinstance(value, (list, dict, tuple)):
            value = json.dumps(value, ensure_ascii=False)
        elif not isinstance(value, str):
            # a value we don't know how to deal with. throw an error
            typename = type(value).__name__
            raise DataError(
                "Invalid input of type: '%s'. Convert to a "
                "bytes, string, int or float first." % typename
            )
        if isinstance(value, str):
            value = value.encode(self.encoding, self.encoding_errors)
        return value


# Apply monkey-patch so redis-py uses our Encoder globally.
_redis_lib.connection.Encoder = Encoder

# ---------------------------------------------------------------------------
# Exception mapping / conversion
# ---------------------------------------------------------------------------

REDIS_EXCEPTION_MAP = {
    _redis_lib.ConnectionError: StoreConnectionError,
    _redis_lib.TimeoutError: StoreTimeoutError,
    _redis_lib.DataError: OperationError,
    _redis_lib.RedisError: OperationError,
}


def convert_redis_error(exc: Exception) -> OperationError:
    """Convert redis native exceptions to StoreError subclasses."""
    for native_type, store_type in REDIS_EXCEPTION_MAP.items():
        if isinstance(exc, native_type):
            return store_type(str(exc), original_error=exc)
    return RedisOperationError(str(exc), cause=exc)
