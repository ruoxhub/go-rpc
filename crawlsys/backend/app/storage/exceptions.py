# -*- coding: utf-8 -*-
"""
Storetool Exception Hierarchy
"""

from typing import Optional, Any


class StoreError(Exception):
    """Base exception for all storetool errors."""

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        original_error: Optional[Exception] = None,
    ):
        self.message = message
        self.code = code
        self.original_error = original_error
        super().__init__(f"[{code}] {message}")


class ConfigurationError(StoreError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, code="CONFIG_ERROR", original_error=original_error)


class ConnectionError(StoreError):
    """Raised when connection to the backend fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message, code="CONNECTION_ERROR", original_error=original_error
        )


class AuthenticationError(StoreError):
    """Raised when authentication fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, code="AUTH_ERROR", original_error=original_error)


class OperationError(StoreError):
    """Raised when a storage operation fails."""

    def __init__(
        self,
        message: str,
        code: str = "OPERATION_ERROR",
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message, code=code, original_error=original_error)


class NotFoundError(OperationError):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, code="NOT_FOUND", original_error=original_error)


class AlreadyExistsError(OperationError):
    """Raised when creating a resource that already exists."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, code="ALREADY_EXISTS", original_error=original_error)


class ValidationError(OperationError):
    """Raised when data validation fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message, code="VALIDATION_ERROR", original_error=original_error
        )


class TimeoutError(OperationError):
    """Raised when an operation times out."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, code="TIMEOUT", original_error=original_error)


class BackendError(StoreError):
    """Backend-specific error base class."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message, code="BACKEND_ERROR", original_error=cause)
        if cause:
            self.__cause__ = cause


class RedisOperationError(BackendError):
    """Redis backend operation failure."""
    pass


class SQLOperationError(BackendError):
    """SQLAlchemy backend operation failure."""
    pass


class MongoOperationError(BackendError):
    """MongoDB backend operation failure."""
    pass


class ElasticOperationError(BackendError):
    """Elasticsearch backend operation failure."""
    pass


class MinioOperationError(BackendError):
    """MinIO backend operation failure."""
    pass
