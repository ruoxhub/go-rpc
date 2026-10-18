# -*- coding: utf-8 -*-
"""MongoDB backend — shared constants, imports, and error conversion."""

from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Callable, Tuple
from contextlib import contextmanager, asynccontextmanager
from functools import wraps
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from common.decorators import require_sync, require_async

from utils.log import get_logger
from storage.exceptions import (
    ConnectionError as StoreConnectionError,
    OperationError,
    NotFoundError,
    AlreadyExistsError,
    MongoOperationError,
)

logger = get_logger("storage.mongo")


# ------------------- Operator Mapping -------------------
# MongoDB 查询操作符映射表
OPERATOR_MAPPING: Dict[str, str] = {
    "eq": "$eq",
    "ne": "$ne",
    "gt": "$gt",
    "lt": "$lt",
    "gte": "$gte",
    "lte": "$lte",
    "in": "$in",
    "nin": "$nin",
    "exists": "$exists",
    "regex": "$regex",
    "elemMatch": "$elemMatch",
    "size": "$size",
    "all": "$all",
    "type": "$type",
}


def convert_mongo_error(exc: Exception) -> OperationError:
    """Convert pymongo exceptions to StoreError subclasses."""
    try:
        from pymongo.errors import (
            ConnectionFailure,
            OperationFailure,
            DuplicateKeyError,
            PyMongoError,
        )

        if isinstance(exc, DuplicateKeyError):
            return AlreadyExistsError(str(exc), original_error=exc)
        if isinstance(exc, ConnectionFailure):
            return StoreConnectionError(str(exc), original_error=exc)
        if isinstance(exc, OperationFailure):
            return MongoOperationError(str(exc), cause=exc)
        if isinstance(exc, PyMongoError):
            return MongoOperationError(str(exc), cause=exc)
    except ImportError:
        pass
    return MongoOperationError(str(exc), cause=exc)
