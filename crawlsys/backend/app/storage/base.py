# -*- coding: utf-8 -*-
"""
Base Storage Interface
"""

import abc
from typing import List, Optional, Any, Dict

from .exceptions import ConfigurationError
from utils.log import get_logger

logger = get_logger("storage.base")


class BaseStore(abc.ABC):
    """
    Base storage class that defines the interface for all database managers.
    Supports both synchronous and asynchronous modes.
    """

    def __init__(self, amode: bool = False, **kwargs):
        """
        Initialize the storage backend.

        Args:
            amode: Whether to run in asynchronous mode.
            **kwargs: Additional driver-specific arguments.
        """
        self._amode = amode
        self._kwargs = kwargs
        self._connected = False

    @property
    def is_async(self) -> bool:
        """Return True if running in asynchronous mode."""
        return self._amode

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the backend."""
        return self._connected

    # ------------------- Connection Management -------------------

    @abc.abstractmethod
    def connect(self):
        """Establish connection to the backend (Sync)."""
        pass

    @abc.abstractmethod
    async def aconnect(self):
        """Establish connection to the backend (Async)."""
        pass

    @abc.abstractmethod
    def close(self):
        """Close synchronous connection."""
        pass

    @abc.abstractmethod
    async def aclose(self):
        """Close asynchronous connection."""
        pass

    @abc.abstractmethod
    def ping(self) -> bool:
        """Check synchronous connection status."""
        pass

    @abc.abstractmethod
    async def aping(self) -> bool:
        """Check asynchronous connection status."""
        pass

    # ------------------- Context Managers -------------------

    def __enter__(self):
        """Synchronous context manager entry."""
        if self.is_async:
            raise ConfigurationError(
                "Cannot use synchronous context manager with amode=True"
            )
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Synchronous context manager exit."""
        self.close()

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        if not self.is_async:
            raise ConfigurationError(
                "Cannot use asynchronous context manager with amode=False"
            )
        await self.aconnect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        await self.aclose()
