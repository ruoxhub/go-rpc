from __future__ import annotations

import pytest

from services.parser_configuration.rate_limit import (
    ParserRateLimitExceeded,
    RedisParserRateLimiter,
)


class FakeRedis:
    def __init__(self) -> None:
        self.eval_result = [1, 1, 60]
        self.eval_calls: list[tuple] = []

    async def eval(self, *args):
        self.eval_calls.append(args)
        result = self.eval_result
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.mark.asyncio
async def test_global_and_action_limits_are_checked_in_one_eval(fake_redis):
    fake_redis.eval_result = [3, 2, 41]
    limiter = RedisParserRateLimiter(fake_redis)

    await limiter.require(
        operation="sample",
        ba_id=9,
        global_limit=30,
        action_limit=5,
    )

    assert len(fake_redis.eval_calls) == 1
    assert fake_redis.eval_calls[0][1] == 2
    assert fake_redis.eval_calls[0][2:4] == (
        "parser-config:sample:global",
        "parser-config:sample:action:9",
    )
    assert fake_redis.eval_calls[0][4:] == (30, 5)


@pytest.mark.asyncio
async def test_limit_error_exposes_retry_after_only(fake_redis):
    fake_redis.eval_result = [31, 1, 37]

    with pytest.raises(ParserRateLimitExceeded) as caught:
        await RedisParserRateLimiter(fake_redis).require(
            operation="sample", ba_id=9, global_limit=30, action_limit=5
        )

    assert caught.value.retry_after_seconds == 37
    assert "9" not in str(caught.value)


@pytest.mark.asyncio
async def test_action_limit_uses_minimum_retry_after_when_ttl_is_missing(fake_redis):
    fake_redis.eval_result = [1, 6, -1]

    with pytest.raises(ParserRateLimitExceeded) as caught:
        await RedisParserRateLimiter(fake_redis).require(
            operation="sample", ba_id=9, global_limit=30, action_limit=5
        )

    assert caught.value.retry_after_seconds == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["Sample", "sample-raw", "sample:raw", ""])
async def test_invalid_operation_fails_before_redis(operation, fake_redis):
    with pytest.raises(ValueError, match="operation"):
        await RedisParserRateLimiter(fake_redis).require(
            operation=operation, ba_id=9, global_limit=30, action_limit=5
        )

    assert fake_redis.eval_calls == []


@pytest.mark.asyncio
async def test_redis_failure_is_fail_closed(fake_redis):
    fake_redis.eval_result = RuntimeError("redis unavailable")

    with pytest.raises(RuntimeError, match="redis unavailable"):
        await RedisParserRateLimiter(fake_redis).require(
            operation="assist", ba_id=9, global_limit=10, action_limit=2
        )
