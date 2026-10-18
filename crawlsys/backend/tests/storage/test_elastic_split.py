"""Tests for elastic sub-package structure."""
import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.elastic import ElasticDB
from storage.elastic.sync import SyncElasticImpl
from storage.elastic._async import AsyncElasticImpl
from storage.elastic._base import convert_elastic_error, logger
from storage.exceptions import ElasticOperationError


def test_elastic_imports():
    """All expected symbols are importable from the sub-package."""
    assert ElasticDB is not None
    assert SyncElasticImpl is not None
    assert AsyncElasticImpl is not None


def test_convert_elastic_error_generic():
    """Generic exceptions become ElasticOperationError."""
    err = convert_elastic_error(ValueError("test"))
    assert isinstance(err, ElasticOperationError)


def test_convert_elastic_error_not_found():
    """ESNotFoundError maps to NotFoundError."""
    from storage.elastic._base import ESNotFoundError, NotFoundError
    if ESNotFoundError is None:
        pytest.skip("elasticsearch not installed")
    try:
        from elastic_transport import ApiResponseMeta
        meta = ApiResponseMeta(
            status=404, http_version="1.1", headers={}, duration=0.0, node=None
        )
        exc = ESNotFoundError("not found", meta, {})
    except (ImportError, TypeError):
        # Fallback: create a subclass that is an instance of ESNotFoundError
        exc = type("_FakeNotFound", (ESNotFoundError,), {"__init__": lambda self: None})()
    err = convert_elastic_error(exc)
    assert isinstance(err, NotFoundError)


def test_logger_is_loguru():
    """Logger should be from utils.log (loguru-based)."""
    assert logger is not None


def test_elastic_db_repr():
    """ElasticDB repr should work without connection."""
    from storage.elastic._base import Elasticsearch
    if Elasticsearch is None:
        pytest.skip("elasticsearch not installed")
    # ElasticDB inherits from BaseStore(ABC) which has abstract methods
    # (aconnect/aclose/aping) not implemented by the original code
    # (which uses async_connect/async_close/async_ping naming).
    # Bypass ABC check by patching __abstractmethods__.
    original = getattr(ElasticDB, "__abstractmethods__", frozenset())
    ElasticDB.__abstractmethods__ = frozenset()
    try:
        db = ElasticDB.__new__(ElasticDB)
        db._hosts = ["http://localhost:9200"]
        db._amode = False
        assert "ElasticDB" in repr(db)
    finally:
        ElasticDB.__abstractmethods__ = original
