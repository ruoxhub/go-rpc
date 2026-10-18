import pytest
from unittest.mock import AsyncMock
from app.filter.bloom import _AsyncImpl

@pytest.mark.asyncio
async def test_bloom_atomic_check_and_add_new_element():
    mock_redis = AsyncMock()
    # 模拟 filters_cache 加载
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.lrange = AsyncMock(return_value=[])
    mock_redis.hgetall = AsyncMock(return_value={})
    # 模拟 eval 返回 1 表示新元素写入成功
    mock_redis.eval = AsyncMock(return_value=1)

    bloom = _AsyncImpl(redis_client=mock_redis)
    result = await bloom.add_atomic("item123", "test_prefix")

    assert result is True
    assert mock_redis.eval.called

@pytest.mark.asyncio
async def test_bloom_atomic_check_and_add_existing_element():
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.lrange = AsyncMock(return_value=[])
    mock_redis.hgetall = AsyncMock(return_value={})
    # 模拟 eval 返回 0 表示所有位已存在
    mock_redis.eval = AsyncMock(return_value=0)

    bloom = _AsyncImpl(redis_client=mock_redis)
    result = await bloom.add_atomic("existing_item", "test_prefix")

    assert result is False
    assert mock_redis.eval.called
