# -*- coding: utf-8 -*-
"""
核心重试工具库 - 提供针对异步方法的可定制重试装饰器。
"""

import asyncio
import functools
from typing import Any, Callable, Tuple, Type
from sqlalchemy.exc import OperationalError, DBAPIError
from common.backoff import full_jitter_delay
from utils.log import get_logger

# 定义可以重试的数据库及网络瞬时异常
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    OperationalError,
    DBAPIError,
    TimeoutError,
    asyncio.TimeoutError,
)


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    exceptions: Tuple[Type[Exception], ...] = RETRYABLE_EXCEPTIONS,
):
    """异步方法的重试装饰器。

    使用指数退避策略，并引入随机抖动 (Jitter) 以防止惊群效应。
    """
    def decorator(func: Callable) -> Callable:
        logger = get_logger(func.__module__)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            delay = base_delay
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(
                            "方法 %s 已达到最大重试次数 %d，抛出异常: %s",
                            func.__name__, max_attempts, e,
                        )
                        raise e

                    sleep_time = full_jitter_delay(
                        attempt,
                        base_delay=delay,
                        max_delay=max_delay,
                    )
                    logger.warning(
                        "方法 %s 执行时捕获可重试异常 %s: %s，将在 %.2f 秒后进行第 %d 次重试...",
                        func.__name__, e.__class__.__name__, e, sleep_time, attempt,
                    )
                    await asyncio.sleep(sleep_time)
        return wrapper
    return decorator
