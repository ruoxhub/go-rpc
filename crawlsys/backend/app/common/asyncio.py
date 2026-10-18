"""Cancellation-safe asyncio helpers."""

import asyncio
from collections.abc import Callable
from typing import Any


async def to_thread_and_drain(func: Callable[..., Any], /, *args, **kwargs):
    """Run sync work without releasing its resources before cancellation drains."""
    task = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        try:
            task.result()
        except BaseException:
            pass
        raise
