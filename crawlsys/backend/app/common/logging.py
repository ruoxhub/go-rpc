# -*- coding: utf-8 -*-
"""
Logging shim — delegates to utils/log.py (loguru-based).
Existing callers using `from common.logging import get_logger` continue to work.
"""
from utils.log import get_logger as _get_logger


def get_logger(name: str):
    """Backward-compatible logger factory. Delegates to utils.log."""
    return _get_logger(name)
