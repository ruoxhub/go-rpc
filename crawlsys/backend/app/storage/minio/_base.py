# -*- coding: utf-8 -*-
"""Shared imports, logger, and error conversion for minio_store sub-package."""

from typing import Any, Dict, List, Optional, Generator, AsyncGenerator
from functools import partial
import asyncio
import io

from minio import Minio, __version__
from minio.error import S3Error
from minio.datatypes import Object, Bucket

from utils.log import get_logger
from storage.exceptions import (
    ConnectionError as StoreConnectionError,
    OperationError,
    NotFoundError,
    MinioOperationError,
)

logger = get_logger("storage.minio")


def convert_minio_error(exc: Exception) -> OperationError:
    """Convert minio native exceptions to StoreError subclasses."""
    try:
        from minio.error import S3Error
        if isinstance(exc, S3Error):
            return MinioOperationError(str(exc), cause=exc)
    except ImportError:
        pass
    return MinioOperationError(str(exc), cause=exc)
