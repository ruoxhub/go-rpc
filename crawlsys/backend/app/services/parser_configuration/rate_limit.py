from __future__ import annotations

import re
from typing import Any


_OPERATION_PATTERN = re.compile(r"[a-z_]+\Z")
_RATE_LIMIT_SCRIPT = """
local global_count = redis.call('INCR', KEYS[1])
if global_count == 1 then
    redis.call('EXPIRE', KEYS[1], 60)
end

local action_count = redis.call('INCR', KEYS[2])
if action_count == 1 then
    redis.call('EXPIRE', KEYS[2], 60)
end

local global_ttl = redis.call('TTL', KEYS[1])
local action_ttl = redis.call('TTL', KEYS[2])
return {global_count, action_count, math.max(global_ttl, action_ttl)}
""".strip()


class ParserRateLimitExceeded(RuntimeError):
    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Parser configuration rate limit exceeded")


class RedisParserRateLimiter:
    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def require(
        self,
        *,
        operation: str,
        ba_id: int,
        global_limit: int,
        action_limit: int,
    ) -> None:
        if _OPERATION_PATTERN.fullmatch(operation) is None:
            raise ValueError(
                "operation must contain only lowercase letters and underscores"
            )

        global_key = f"parser-config:{operation}:global"
        action_key = f"parser-config:{operation}:action:{ba_id}"
        global_count, action_count, ttl = await self._redis.eval(
            _RATE_LIMIT_SCRIPT,
            2,
            global_key,
            action_key,
            global_limit,
            action_limit,
        )
        if int(global_count) > global_limit or int(action_count) > action_limit:
            raise ParserRateLimitExceeded(retry_after_seconds=max(1, int(ttl)))


__all__ = ["ParserRateLimitExceeded", "RedisParserRateLimiter"]
