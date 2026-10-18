# -*- coding: utf-8 -*-
"""Tests for mongo sub-package structure."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.mongo import MongoDB
from storage.mongo.sync import SyncMongoImpl
from storage.mongo._async import AsyncMongoImpl
from storage.mongo._base import convert_mongo_error, logger
from storage.exceptions import MongoOperationError


def test_mongo_imports():
    """All public symbols are importable from the mongo sub-package."""
    assert MongoDB is not None
    assert SyncMongoImpl is not None
    assert AsyncMongoImpl is not None


def test_convert_mongo_error_generic():
    """Non-pymongo exceptions are wrapped as MongoOperationError."""
    err = convert_mongo_error(ValueError("test"))
    assert isinstance(err, MongoOperationError)


def test_logger_exists():
    """Logger is configured via utils.log.get_logger."""
    assert logger is not None


def test_mongo_does_not_inherit_basestore():
    """MongoDB must NOT inherit from BaseStore."""
    from storage.base import BaseStore

    assert not issubclass(MongoDB, BaseStore)


def test_build_query_static():
    """MongoDB.build_query works as a static method."""
    assert MongoDB.build_query(None) == {}
    assert MongoDB.build_query({"name": "test"}) == {"name": "test"}
    assert MongoDB.build_query({"age__gt": 18}) == {"age": {"$gt": 18}}


def test_build_sort_static():
    """MongoDB.build_sort works as a static method."""
    assert MongoDB.build_sort(None) is None
    assert MongoDB.build_sort({"name": "asc"}) == [("name", 1)]
    assert MongoDB.build_sort({"age": "desc"}) == [("age", -1)]


def test_to_object_id_static():
    """MongoDB.to_object_id handles None and invalid values."""
    assert MongoDB.to_object_id(None) is None
    assert MongoDB.to_object_id("invalid_id_short") is None


def test_operator_mapping_present():
    """OPERATOR_MAPPING contains standard MongoDB operators."""
    from storage.mongo._base import OPERATOR_MAPPING

    assert OPERATOR_MAPPING["eq"] == "$eq"
    assert OPERATOR_MAPPING["gt"] == "$gt"
    assert OPERATOR_MAPPING["regex"] == "$regex"


def test_sync_impl_class_name():
    """SyncMongoImpl has the expected class name."""
    assert SyncMongoImpl.__name__ == "SyncMongoImpl"


def test_async_impl_class_name():
    """AsyncMongoImpl has the expected class name."""
    assert AsyncMongoImpl.__name__ == "AsyncMongoImpl"
