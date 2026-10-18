# -*- coding: utf-8 -*-
"""Elasticsearch backend — shared constants, imports, and error conversion."""

from typing import Any, Dict, List, Optional, Union

try:
    from elasticsearch import Elasticsearch, AsyncElasticsearch
    from elasticsearch import NotFoundError as ESNotFoundError
    from elasticsearch import ConnectionError as ESConnectionError
except ImportError:
    Elasticsearch = None
    AsyncElasticsearch = None
    ESNotFoundError = None
    ESConnectionError = None

from utils.log import get_logger
from storage.exceptions import (
    ConnectionError as StoreConnectionError,
    OperationError,
    NotFoundError,
    ConfigurationError,
    ElasticOperationError,
)

logger = get_logger("storage.elastic")


def convert_elastic_error(exc: Exception) -> OperationError:
    """Convert elasticsearch native exceptions to StoreError subclasses."""
    if ESNotFoundError and isinstance(exc, ESNotFoundError):
        return NotFoundError(str(exc), original_error=exc)
    if ESConnectionError and isinstance(exc, ESConnectionError):
        return StoreConnectionError(str(exc), original_error=exc)
    return ElasticOperationError(str(exc), cause=exc)
