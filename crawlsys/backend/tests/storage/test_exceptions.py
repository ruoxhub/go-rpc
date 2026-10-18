"""Tests for extended storage exception hierarchy."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.exceptions import (
    StoreError,
    OperationError,
    BackendError,
    RedisOperationError,
    SQLOperationError,
    MongoOperationError,
    ElasticOperationError,
    MinioOperationError,
)


def test_backend_error_is_store_error():
    err = BackendError("test error", cause=ValueError("inner"))
    assert isinstance(err, StoreError)
    assert err.code == "BACKEND_ERROR"
    assert err.__cause__ is not None


def test_backend_error_without_cause():
    err = BackendError("no cause")
    assert err.__cause__ is None


def test_redis_operation_error():
    err = RedisOperationError("redis failed")
    assert isinstance(err, BackendError)
    assert isinstance(err, StoreError)
    assert "redis failed" in str(err)


def test_sql_operation_error():
    err = SQLOperationError("sql failed")
    assert isinstance(err, BackendError)


def test_mongo_operation_error():
    err = MongoOperationError("mongo failed")
    assert isinstance(err, BackendError)


def test_elastic_operation_error():
    err = ElasticOperationError("elastic failed")
    assert isinstance(err, BackendError)


def test_minio_operation_error():
    err = MinioOperationError("minio failed")
    assert isinstance(err, BackendError)
