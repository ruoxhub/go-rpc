# -*- coding: utf-8 -*-
"""装饰器模块 - 提供模式检查装饰器（require_sync / require_async）"""
import asyncio
from functools import wraps
from typing import Callable, Any


def _is_async_mode(instance: Any) -> bool:
    """统一检测实例是否处于异步模式。"""
    if hasattr(instance, "is_async"):
        return bool(instance.is_async)
    if hasattr(instance, "amode"):
        return bool(instance.amode)
    return False


def require_sync(method_name: str) -> Callable:
    """装饰器：确保实例在同步模式下运行。如果是异步模式则抛出异常。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> Any:
            if _is_async_mode(self):
                raise RuntimeError(
                    f"方法 '{func.__name__}' 只能在同步模式下调用 (当前为异步模式)"
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def require_async(method_name: str) -> Callable:
    """装饰器：确保实例在异步模式下运行。如果是同步模式则抛出异常。"""
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(self, *args, **kwargs) -> Any:
                if not _is_async_mode(self):
                    raise RuntimeError(
                        f"方法 '{func.__name__}' 只能在异步模式下调用 (当前为同步模式)"
                    )
                return await func(self, *args, **kwargs)
            return async_wrapper

        @wraps(func)
        def wrapper(self, *args, **kwargs) -> Any:
            if not _is_async_mode(self):
                raise RuntimeError(
                    f"方法 '{func.__name__}' 只能在异步模式下调用 (当前为同步模式)"
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
