# -*- coding: utf-8 -*-
"""Base Filter Interface"""

import abc

from utils.log import get_logger
logger = get_logger("filter.base")


class BaseFilter(abc.ABC):
    """Base class for all filters (Bloom, Bitmap, etc.)"""

    def __init__(self, amode: bool = False, **kwargs):
        """
        Initialize the filter.

        Args:
            amode: Whether to run in asynchronous mode.
            **kwargs: Additional arguments.
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

    @abc.abstractmethod
    def connect(self):
        """Establish connection to the backend (Sync)."""
        pass

    @abc.abstractmethod
    async def async_connect(self):
        """Establish connection to the backend (Async)."""
        pass

    @abc.abstractmethod
    def close(self):
        """Close connection (Sync)."""
        pass

    @abc.abstractmethod
    async def async_close(self):
        """Close connection (Async)."""
        pass
