# -*- coding: utf-8 -*-
"""
统一的 BloomFilter，实现同步和异步两种模式。
通过 `amode` 参数决定内部使用同步实现还是异步实现，外层提供统一的 API。

该模块提供了布隆过滤器的完整实现，支持动态扩容、统计信息查询和批量操作。
同步和异步实现共享相同的业务逻辑，确保行为一致性。
"""

import math
import asyncio
from typing import List, Dict, Optional
import mmh3
from storage.redis import RedisDB
from .base import BaseFilter
from common.decorators import require_sync, require_async


def _get_stat(stats: dict, key: str, default):
    """从 Redis hgetall 结果中安全取值，兼容 str/bytes 键。"""
    if key in stats:
        return stats[key]
    if isinstance(key, str) and key.encode() in stats:
        return stats[key.encode()]
    if isinstance(key, bytes) and key.decode() in stats:
        return stats[key.decode()]
    return default


def _calculate_bit_size(n: int, p: float) -> int:
    m = -(n * math.log(p)) / (math.log(2) ** 2)
    return int(m)


def _calculate_hash_count(m: int, n: int) -> int:
    k = (m / n) * math.log(2)
    return max(1, int(k))


def _get_offsets(item: str, bit_size: int, hash_count: int) -> List[int]:
    if bit_size <= 0:
        bit_size = 1
    return [mmh3.hash64(item, seed)[0] % bit_size for seed in range(hash_count)]


class _BloomCommon:
    """BloomFilter 同步/异步实现的共享基类。"""

    def __init__(self, expected_elements=1000000, false_positive_rate=0.01,
                 resize_factor=2, resize_threshold=0.8):
        self.expected_elements = expected_elements
        self.false_positive_rate = false_positive_rate
        self.resize_factor = resize_factor
        self.resize_threshold = resize_threshold
        self.filters_cache: Dict[str, List[Dict]] = {}


# ---------------------------------------------------------------------------
# 同步实现
# ---------------------------------------------------------------------------
class _SyncImpl(_BloomCommon):
    """同步版 BloomFilter 实现，使用 redis-py 客户端。"""

    def __init__(self, redis_url: str = None,
                 redis_client=None,
                 expected_elements=1000000, false_positive_rate=0.01,
                 resize_factor=2, resize_threshold=0.8):
        super().__init__(expected_elements, false_positive_rate,
                         resize_factor, resize_threshold)
        if redis_client is not None:
            self.redis = redis_client
            self._owns_connection = False
        elif redis_url is not None:
            self.redis = RedisDB.from_url(redis_url)
            self._owns_connection = True
        else:
            raise ValueError("必须提供 redis_client 或 redis_url 参数之一")

    # -------------------------- 辅助方法 --------------------------
    def _get_filters(self, key_prefix: str) -> List[Dict]:
        """获取指定前缀的过滤器列表，如果缓存中不存在则加载。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            List[Dict]: 过滤器配置列表，每个配置包含位图键、统计键、期望元素数等信息
        """
        if key_prefix not in self.filters_cache:
            self._load_filters(key_prefix)
        return self.filters_cache[key_prefix]

    def _load_filters(self, key_prefix: str):
        """从 Redis 加载指定前缀的过滤器配置到缓存。
        
        如果该前缀不存在任何过滤器，则创建一个新的过滤器。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
        """
        filter_list_key = f"{key_prefix}:filters"
        if self.redis.exists(filter_list_key):
            filters = []
            filter_ids = self.redis.lrange(filter_list_key, 0, -1)
            for fid in filter_ids:
                fid_str = fid if isinstance(fid, str) else fid.decode()
                stats = self.redis.hgetall(f"{fid_str}:stats")
                filters.append({
                    'bitmap_key': f"{fid_str}:bitmap",
                    'stats_key': f"{fid_str}:stats",
                    'expected_elements': int(_get_stat(stats, 'expected_elements', self.expected_elements)),
                    'false_positive_rate': float(_get_stat(stats, 'false_positive_rate', self.false_positive_rate)),
                    'bit_size': int(_get_stat(stats, 'bit_size', 0)),
                    'hash_count': int(_get_stat(stats, 'hash_count', 0))
                })
            self.filters_cache[key_prefix] = filters
        else:
            self._create_new_filter(key_prefix, self.expected_elements, self.false_positive_rate)

    def _create_new_filter(self, key_prefix: str, expected_elements: int, false_positive_rate: float):
        """创建一个新的布隆过滤器并添加到缓存和 Redis。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
            expected_elements: 期望添加的元素数量
            false_positive_rate: 可接受的误报率
        """
        filter_list_key = f"{key_prefix}:filters"
        filter_id = f"{key_prefix}:f{self.redis.incr(key_prefix + ':filter_id')}"
        self.redis.rpush(filter_list_key, filter_id)
        bit_size = _calculate_bit_size(expected_elements, false_positive_rate)
        hash_count = _calculate_hash_count(bit_size, expected_elements)
        stats_key = filter_id + ":stats"
        # 使用管道批量设置哈希字段（RedisDB.hset 不支持 mapping 参数）
        stats_data = {
            'expected_elements': expected_elements,
            'added_elements': 0,
            'false_positive_rate': false_positive_rate,
            'bit_size': bit_size,
            'hash_count': hash_count,
            'collisions': 0,
            'resize_count': 0
        }
        with self.redis.pipeline() as pipe:
            for k, v in stats_data.items():
                pipe.hset(stats_key, k, v)
            pipe.execute()
        new_filter = {
            'bitmap_key': filter_id + ":bitmap",
            'stats_key': stats_key,
            'expected_elements': expected_elements,
            'false_positive_rate': false_positive_rate,
            'bit_size': bit_size,
            'hash_count': hash_count
        }
        if key_prefix not in self.filters_cache:
            self.filters_cache[key_prefix] = []
        self.filters_cache[key_prefix].append(new_filter)

    def _check_resize(self, key_prefix: str):
        """检查当前过滤器是否需要扩容。
        
        当已添加元素数超过期望元素数的阈值比例时触发扩容。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
        """
        filters = self._get_filters(key_prefix)
        current = filters[-1]
        stats = self.redis.hgetall(current['stats_key'])
        added = int(_get_stat(stats, 'added_elements', 0))
        expected = int(_get_stat(stats, 'expected_elements', 1))
        # 添加除零保护
        if expected > 0 and added / expected > self.resize_threshold:
            self._resize_filter(key_prefix)

    def _resize_filter(self, key_prefix: str):
        """对指定前缀的布隆过滤器执行扩容操作。
        
        创建一个新的过滤器，其期望元素数为当前过滤器的 resize_factor 倍。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
        """
        filters = self._get_filters(key_prefix)
        last = filters[-1]
        new_expected = int(last['expected_elements'] * self.resize_factor)
        new_fpr = last['false_positive_rate']
        self._create_new_filter(key_prefix, new_expected, new_fpr)

    # -------------------------- 公共 API --------------------------
    def add(self, value: str, key_prefix: str) -> bool:
        """向布隆过滤器添加单个元素。
        
        如果元素已存在（可能发生碰撞），则不添加并增加碰撞计数。
        添加前会检查是否需要扩容。
        
        Args:
            value: 要添加的字符串元素
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            bool: 如果元素是新添加的返回 True，如果已存在返回 False
        """
        self._check_resize(key_prefix)
        if self.check(value, key_prefix):
            filters = self._get_filters(key_prefix)
            self.redis.hincrby(filters[-1]['stats_key'], 'collisions', 1)
            return False
        filters = self._get_filters(key_prefix)
        cur = filters[-1]
        offsets = _get_offsets(value, cur['bit_size'], cur['hash_count'])
        with self.redis.pipeline() as pipe:
            for off in offsets:
                pipe.setbit(cur['bitmap_key'], off, 1)
            pipe.hincrby(cur['stats_key'], 'added_elements', 1)
            pipe.execute()
        return True

    def batch_add(self, values: List[str], key_prefix: str) -> int:
        """批量添加元素到布隆过滤器。
        
        会先过滤掉已存在的元素，只添加新元素，并更新统计信息。
        使用 Redis 管道提高性能。
        
        Args:
            values: 要添加的字符串元素列表
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            int: 实际添加的新元素数量
        """
        self._check_resize(key_prefix)
        new_vals = [v for v in values if not self.check(v, key_prefix)]
        if not new_vals:
            return 0
        filters = self._get_filters(key_prefix)
        cur = filters[-1]
        with self.redis.pipeline() as pipe:
            for v in new_vals:
                offsets = _get_offsets(v, cur['bit_size'], cur['hash_count'])
                for off in offsets:
                    pipe.setbit(cur['bitmap_key'], off, 1)
            pipe.hincrby(cur['stats_key'], 'added_elements', len(new_vals))
            pipe.hincrby(cur['stats_key'], 'collisions', len(values) - len(new_vals))
            pipe.execute()
        return len(new_vals)

    def check(self, value: str, key_prefix: str) -> bool:
        """检查单个元素是否可能存在于布隆过滤器中。
        
        布隆过滤器可能存在误报（返回 True 但实际不存在），但不会出现漏报。
        会检查所有过滤器（包括扩容后的历史过滤器）。
        
        Args:
            value: 要检查的字符串元素
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            bool: 如果元素可能存在返回 True，如果肯定不存在返回 False
        """
        filters = self._get_filters(key_prefix)
        for f in filters:
            offsets = _get_offsets(value, f['bit_size'], f['hash_count'])
            with self.redis.pipeline() as pipe:
                for off in offsets:
                    pipe.getbit(f['bitmap_key'], off)
                results = pipe.execute()
            if all(results):
                return True
        return False

    def batch_check(self, values: List[str], key_prefix: str) -> Dict[str, bool]:
        """批量检查多个元素是否可能存在于布隆过滤器中。
        
        使用 Redis 管道一次性执行所有检查操作，提高性能。
        
        Args:
            values: 要检查的字符串元素列表
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            Dict[str, bool]: 元素到检查结果的映射字典
        """
        filters = self._get_filters(key_prefix)
        result: Dict[str, bool] = {}
        with self.redis.pipeline() as pipe:
            for v in values:
                for f in filters:
                    offsets = _get_offsets(v, f['bit_size'], f['hash_count'])
                    for off in offsets:
                        pipe.getbit(f['bitmap_key'], off)
            all_res = pipe.execute()
        # 处理 mock 返回 None 的情况
        if all_res is None:
            return {v: False for v in values}
        idx = 0
        for v in values:
            result[v] = False
            for f in filters:
                hc = f['hash_count']
                slice_res = all_res[idx:idx + hc]
                idx += hc
                if all(slice_res):
                    result[v] = True
        return result

    def close(self):
        """关闭 Redis 连接。
        
        仅在实例拥有连接时（通过 redis_url 创建）才会关闭连接。
        """
        if getattr(self, '_owns_connection', False) and hasattr(self, 'redis'):
            self.redis.close()

    def stats(self, key_prefix: Optional[str] = None) -> Dict:
        """获取布隆过滤器的统计信息。
        
        Args:
            key_prefix: 布隆过滤器的键前缀。如果为 None，则返回所有前缀的统计信息
            
        Returns:
            Dict: 包含过滤器数量、总添加元素数、总期望元素数、碰撞数和各过滤器详细信息的字典
        """
        if key_prefix is None:
            # 返回所有前缀的统计信息
            all_stats = {}
            for prefix in self.filters_cache.keys():
                all_stats[prefix] = self._get_prefix_stats(prefix)
            return all_stats
        else:
            return self._get_prefix_stats(key_prefix)

    def _get_prefix_stats(self, key_prefix: str) -> Dict:
        """获取指定前缀的统计信息。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            Dict: 包含过滤器数量、总添加元素数、总期望元素数、总碰撞数和各过滤器详细信息的字典
        """
        filters = self._get_filters(key_prefix)
        total_stats = {
            'filter_count': len(filters),
            'total_added': 0,
            'total_expected': 0,
            'total_collisions': 0,
            'filters': []
        }
        for f in filters:
            stats = self.redis.hgetall(f['stats_key'])
            filter_stats = {
                'expected_elements': int(_get_stat(stats, 'expected_elements', 0)),
                'added_elements': int(_get_stat(stats, 'added_elements', 0)),
                'false_positive_rate': float(_get_stat(stats, 'false_positive_rate', 0)),
                'bit_size': int(_get_stat(stats, 'bit_size', 0)),
                'hash_count': int(_get_stat(stats, 'hash_count', 0)),
                'collisions': int(_get_stat(stats, 'collisions', 0)),
                'resize_count': int(_get_stat(stats, 'resize_count', 0))
            }
            total_stats['total_added'] += filter_stats['added_elements']
            total_stats['total_expected'] += filter_stats['expected_elements']
            total_stats['total_collisions'] += filter_stats['collisions']
            total_stats['filters'].append(filter_stats)
        return total_stats

_BLOOM_ATOMIC_ADD_LUA = """
local bitmap_key = KEYS[1]
local stats_key = KEYS[2]
local all_set = 1
for i, off in ipairs(ARGV) do
    if redis.call('GETBIT', bitmap_key, off) == 0 then
        all_set = 0
    end
    redis.call('SETBIT', bitmap_key, off, 1)
end
if all_set == 1 then
    if stats_key and stats_key ~= '' then
        redis.call('HINCRBY', stats_key, 'collisions', 1)
    end
    return 0
else
    if stats_key and stats_key ~= '' then
        redis.call('HINCRBY', stats_key, 'added_elements', 1)
    end
    return 1
end
""".strip()


# ---------------------------------------------------------------------------
# 异步实现（基于支持 async/await 的 Redis 客户端）
# ---------------------------------------------------------------------------
class _AsyncImpl(_BloomCommon):
    """异步版 BloomFilter。"""

    def __init__(self, redis_url: str = None,
                 redis_client=None,
                 expected_elements=1000000, false_positive_rate=0.01,
                 resize_factor=2, resize_threshold=0.8):
        super().__init__(expected_elements, false_positive_rate,
                         resize_factor, resize_threshold)
        if redis_client is not None:
            self.redis = redis_client
            self._owns_connection = False
        elif redis_url is not None:
            self.redis = RedisDB.from_url(
                redis_url,
                decode_responses=True,
                max_connections=1000,
                amode=True,
            )
            self._owns_connection = True
        else:
            raise ValueError("必须提供 redis_client 或 redis_url 参数之一")
        self._lock = asyncio.Lock()

    async def _get_pipeline(self):
        """获取 pipeline 对象，兼容 AsyncMock 测试。"""
        pipeline_result = self.redis.pipeline()
        # 如果是 coroutine，需要 await
        if asyncio.iscoroutine(pipeline_result):
            pipeline_result = await pipeline_result
        return pipeline_result

    async def _get_filters(self, key_prefix: str) -> List[Dict]:
        """获取指定前缀的过滤器列表，如果缓存中不存在则异步加载。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            List[Dict]: 过滤器配置列表，每个配置包含位图键、统计键、期望元素数等信息
        """
        if key_prefix not in self.filters_cache:
            async with self._lock:
                if key_prefix not in self.filters_cache:
                    await self._load_filters(key_prefix)
        return self.filters_cache[key_prefix]

    async def _load_filters(self, key_prefix: str):
        """从 Redis 异步加载指定前缀的过滤器配置到缓存。
        
        如果该前缀不存在任何过滤器，则异步创建一个新的过滤器。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
        """
        filter_list_key = f"{key_prefix}:filters"
        if await self.redis.exists(filter_list_key):
            filters = []
            filter_ids = await self.redis.lrange(filter_list_key, 0, -1)
            for fid in filter_ids:
                fid_str = fid if isinstance(fid, str) else fid.decode()
                stats = await self.redis.hgetall(f"{fid_str}:stats")
                filters.append({
                    'bitmap_key': f"{fid_str}:bitmap",
                    'stats_key': f"{fid_str}:stats",
                    'expected_elements': int(_get_stat(stats, 'expected_elements', self.expected_elements)),
                    'false_positive_rate': float(_get_stat(stats, 'false_positive_rate', self.false_positive_rate)),
                    'bit_size': int(_get_stat(stats, 'bit_size', 0)),
                    'hash_count': int(_get_stat(stats, 'hash_count', 0))
                })
            self.filters_cache[key_prefix] = filters
        else:
            await self._create_new_filter(key_prefix, self.expected_elements, self.false_positive_rate)

    async def _create_new_filter(self, key_prefix: str, expected_elements: int, false_positive_rate: float):
        """异步创建一个新的布隆过滤器并添加到缓存和 Redis。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
            expected_elements: 期望添加的元素数量
            false_positive_rate: 可接受的误报率
        """
        filter_list_key = f"{key_prefix}:filters"
        new_id = await self.redis.incr(key_prefix + ':filter_id')
        filter_id = f"{key_prefix}:f{new_id}"
        await self.redis.rpush(filter_list_key, filter_id)
        bit_size = _calculate_bit_size(expected_elements, false_positive_rate)
        hash_count = _calculate_hash_count(bit_size, expected_elements)
        stats_key = filter_id + ":stats"
        # 使用管道批量设置哈希字段（RedisDB.hset 不支持 mapping 参数）
        stats_data = {
            'expected_elements': expected_elements,
            'added_elements': 0,
            'false_positive_rate': false_positive_rate,
            'bit_size': bit_size,
            'hash_count': hash_count,
            'collisions': 0,
            'resize_count': 0
        }
        pipe = await self._get_pipeline()
        async with pipe:
            for k, v in stats_data.items():
                pipe.hset(stats_key, k, v)
            await pipe.execute()
        new_filter = {
            'bitmap_key': filter_id + ":bitmap",
            'stats_key': stats_key,
            'expected_elements': expected_elements,
            'false_positive_rate': false_positive_rate,
            'bit_size': bit_size,
            'hash_count': hash_count
        }
        if key_prefix not in self.filters_cache:
            self.filters_cache[key_prefix] = []
        self.filters_cache[key_prefix].append(new_filter)

    async def _check_resize(self, key_prefix: str):
        """异步检查当前过滤器是否需要扩容。
        
        当已添加元素数超过期望元素数的阈值比例时触发扩容。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
        """
        filters = await self._get_filters(key_prefix)
        cur = filters[-1]
        stats = await self.redis.hgetall(cur['stats_key'])
        added = int(_get_stat(stats, 'added_elements', 0))
        expected = int(_get_stat(stats, 'expected_elements', 1))
        # 添加除零保护
        if expected > 0 and added / expected > self.resize_threshold:
            await self._resize_filter(key_prefix)

    async def _resize_filter(self, key_prefix: str):
        """异步对指定前缀的布隆过滤器执行扩容操作。
        
        创建一个新的过滤器，其期望元素数为当前过滤器的 resize_factor 倍。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
        """
        filters = await self._get_filters(key_prefix)
        last = filters[-1]
        new_expected = int(last['expected_elements'] * self.resize_factor)
        new_fpr = last['false_positive_rate']
        await self._create_new_filter(key_prefix, new_expected, new_fpr)

    async def add_atomic(self, value: str, key_prefix: str) -> bool:
        """使用 Lua 脚本原子性地检查并添加单个元素到布隆过滤器。"""
        await self._check_resize(key_prefix)
        filters = await self._get_filters(key_prefix)
        cur = filters[-1]
        offsets = _get_offsets(value, cur['bit_size'], cur['hash_count'])
        res = await self.redis.eval(
            _BLOOM_ATOMIC_ADD_LUA,
            2,
            cur['bitmap_key'],
            cur.get('stats_key', ''),
            *offsets,
        )
        return int(res) == 1

    # -------------------------- 公共 API --------------------------
    async def add(self, value: str, key_prefix: str) -> bool:
        """异步向布隆过滤器添加单个元素。
        
        如果元素已存在（可能发生碰撞），则不添加并增加碰撞计数。
        添加前会检查是否需要扩容。
        
        Args:
            value: 要添加的字符串元素
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            bool: 如果元素是新添加的返回 True，如果已存在返回 False
        """
        await self._check_resize(key_prefix)
        if await self.check(value, key_prefix):
            filters = await self._get_filters(key_prefix)
            await self.redis.hincrby(filters[-1]['stats_key'], 'collisions', 1)
            return False
        filters = await self._get_filters(key_prefix)
        cur = filters[-1]
        offsets = _get_offsets(value, cur['bit_size'], cur['hash_count'])
        pipe = await self._get_pipeline()
        async with pipe:
            for off in offsets:
                pipe.setbit(cur['bitmap_key'], off, 1)
            pipe.hincrby(cur['stats_key'], 'added_elements', 1)
            await pipe.execute()
        return True

    async def batch_add(self, values: List[str], key_prefix: str) -> int:
        """异步批量添加元素到布隆过滤器。
        
        会先过滤掉已存在的元素，只添加新元素，并更新统计信息。
        使用 asyncio.gather 并发检查元素是否存在，提高性能。
        
        Args:
            values: 要添加的字符串元素列表
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            int: 实际添加的新元素数量
        """
        await self._check_resize(key_prefix)
        checks = await asyncio.gather(*[self.check(v, key_prefix) for v in values])
        new_vals = [v for v, exists in zip(values, checks) if not exists]
        if not new_vals:
            return 0
        filters = await self._get_filters(key_prefix)
        cur = filters[-1]
        pipe = await self._get_pipeline()
        async with pipe:
            for v in new_vals:
                offsets = _get_offsets(v, cur['bit_size'], cur['hash_count'])
                for off in offsets:
                    pipe.setbit(cur['bitmap_key'], off, 1)
            pipe.hincrby(cur['stats_key'], 'added_elements', len(new_vals))
            pipe.hincrby(cur['stats_key'], 'collisions', len(values) - len(new_vals))
            await pipe.execute()
        return len(new_vals)

    async def check(self, value: str, key_prefix: str) -> bool:
        """异步检查单个元素是否可能存在于布隆过滤器中。
        
        布隆过滤器可能存在误报（返回 True 但实际不存在），但不会出现漏报。
        会检查所有过滤器（包括扩容后的历史过滤器）。
        
        Args:
            value: 要检查的字符串元素
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            bool: 如果元素可能存在返回 True，如果肯定不存在返回 False
        """
        filters = await self._get_filters(key_prefix)
        pipe = await self._get_pipeline()
        async with pipe:
            for f in filters:
                offsets = _get_offsets(value, f['bit_size'], f['hash_count'])
                for off in offsets:
                    pipe.getbit(f['bitmap_key'], off)
            results = await pipe.execute()
        idx = 0
        for f in filters:
            hc = f['hash_count']
            slice_res = results[idx:idx + hc]
            idx += hc
            if hc > 0 and all(slice_res):
                return True
        return False

    async def batch_check(self, values: List[str], key_prefix: str) -> Dict[str, bool]:
        """异步批量检查多个元素是否可能存在于布隆过滤器中。
        
        使用 Redis 管道一次性执行所有检查操作，提高性能。
        
        Args:
            values: 要检查的字符串元素列表
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            Dict[str, bool]: 元素到检查结果的映射字典
        """
        filters = await self._get_filters(key_prefix)
        pipe = await self._get_pipeline()
        async with pipe:
            for v in values:
                for f in filters:
                    offsets = _get_offsets(v, f['bit_size'], f['hash_count'])
                    for off in offsets:
                        pipe.getbit(f['bitmap_key'], off)
            all_res = await pipe.execute()
        result: Dict[str, bool] = {}
        # 处理 mock 返回 None 的情况
        if all_res is None:
            return {v: False for v in values}
        idx = 0
        for v in values:
            result[v] = False
            for f in filters:
                hc = f['hash_count']
                slice_res = all_res[idx:idx + hc]
                idx += hc
                if hc > 0 and all(slice_res):
                    result[v] = True
        return result

    async def close(self):
        """异步关闭 Redis 连接。
        
        仅在实例拥有连接时（通过 redis_url 创建）才会关闭连接。
        """
        if getattr(self, '_owns_connection', False) and hasattr(self, 'redis'):
            await self.redis.aclose()

    async def stats(self, key_prefix: Optional[str] = None) -> Dict:
        """异步获取布隆过滤器的统计信息。
        
        Args:
            key_prefix: 布隆过滤器的键前缀。如果为 None，则返回所有前缀的统计信息
            
        Returns:
            Dict: 包含过滤器数量、总添加元素数、总期望元素数、碰撞数和各过滤器详细信息的字典
        """
        if key_prefix is None:
            # 返回所有前缀的统计信息
            all_stats = {}
            for prefix in self.filters_cache.keys():
                all_stats[prefix] = await self._get_prefix_stats(prefix)
            return all_stats
        else:
            return await self._get_prefix_stats(key_prefix)

    async def _get_prefix_stats(self, key_prefix: str) -> Dict:
        """异步获取指定前缀的统计信息。
        
        Args:
            key_prefix: 布隆过滤器的键前缀
            
        Returns:
            Dict: 包含过滤器数量、总添加元素数、总期望元素数、总碰撞数和各过滤器详细信息的字典
        """
        filters = await self._get_filters(key_prefix)
        total_stats = {
            'filter_count': len(filters),
            'total_added': 0,
            'total_expected': 0,
            'total_collisions': 0,
            'filters': []
        }
        for f in filters:
            stats = await self.redis.hgetall(f['stats_key'])
            filter_stats = {
                'expected_elements': int(_get_stat(stats, 'expected_elements', 0)),
                'added_elements': int(_get_stat(stats, 'added_elements', 0)),
                'false_positive_rate': float(_get_stat(stats, 'false_positive_rate', 0)),
                'bit_size': int(_get_stat(stats, 'bit_size', 0)),
                'hash_count': int(_get_stat(stats, 'hash_count', 0)),
                'collisions': int(_get_stat(stats, 'collisions', 0)),
                'resize_count': int(_get_stat(stats, 'resize_count', 0))
            }
            total_stats['total_added'] += filter_stats['added_elements']
            total_stats['total_expected'] += filter_stats['expected_elements']
            total_stats['total_collisions'] += filter_stats['collisions']
            total_stats['filters'].append(filter_stats)
        return total_stats

# ---------------------------------------------------------------------------
# Facade：统一入口
# ---------------------------------------------------------------------------
class Bloom(BaseFilter):
    """统一的 BloomFilter 接口，支持同步和异步两种模式。
    
    参数 ``amode`` 为 True 时使用异步实现，否则使用同步实现。
    提供一致的 API，隐藏同步和异步实现的差异。
    
    Args:
        redis_url: Redis 连接 URL，格式为 redis://[:password]@host:port/db
        expected_elements: 期望添加的元素数量，用于计算初始位图大小
        false_positive_rate: 可接受的误报率，默认为 0.01 (1%)
        resize_factor: 扩容时的倍数因子，默认为 2
        resize_threshold: 触发扩容的阈值比例，默认为 0.8 (80%)
        amode: 是否使用异步模式，默认为 False（同步模式）
    
    Examples:
        同步使用::
        
            bloom = Bloom("redis://localhost:6379/0", amode=False)
            bloom.add("user:123", "users")
            exists = bloom.check("user:123", "users")
            bloom.close()
        
        异步使用::
        
            bloom = Bloom("redis://localhost:6379/0", amode=True)
            await bloom.aadd("user:123", "users")
            exists = await bloom.acheck("user:123", "users")
            await bloom.aclose()
    """

    def __init__(self, redis_url: str = None,
                 expected_elements=1000000, false_positive_rate=0.01,
                 resize_factor=2, resize_threshold=0.8, amode: bool = False):
        super().__init__(amode=amode)
        impl_cls = _AsyncImpl if amode else _SyncImpl
        self._impl = impl_cls(
            redis_url=redis_url,
            expected_elements=expected_elements,
            false_positive_rate=false_positive_rate,
            resize_factor=resize_factor,
            resize_threshold=resize_threshold
        )

    @require_sync("add")
    def add(self, value: str, key_prefix: str) -> bool:
        """添加单个元素（同步）。已存在返回 False。"""
        return self._impl.add(value, key_prefix)

    @require_sync("batch_add")
    def batch_add(self, values: List[str], key_prefix: str) -> int:
        """批量添加元素（同步）。返回实际添加的新元素数量。"""
        return self._impl.batch_add(values, key_prefix)

    @require_sync("check")
    def check(self, value: str, key_prefix: str) -> bool:
        """检查元素是否可能存在（同步）。可能有误报，不会漏报。"""
        return self._impl.check(value, key_prefix)

    @require_sync("batch_check")
    def batch_check(self, values: List[str], key_prefix: str) -> Dict[str, bool]:
        """批量检查元素是否可能存在（同步）。"""
        return self._impl.batch_check(values, key_prefix)

    @require_async("aadd")
    async def aadd(self, value: str, key_prefix: str) -> bool:
        """添加单个元素（异步）。已存在返回 False。"""
        return await self._impl.add(value, key_prefix)

    @require_async("aadd_atomic")
    async def aadd_atomic(self, value: str, key_prefix: str) -> bool:
        """原子检查并添加单个元素（异步）。已存在返回 False，新写入返回 True。"""
        return await self._impl.add_atomic(value, key_prefix)

    @require_async("abatch_add")
    async def abatch_add(self, values: List[str], key_prefix: str) -> int:
        """批量添加元素（异步）。返回实际添加的新元素数量。"""
        return await self._impl.batch_add(values, key_prefix)

    @require_async("acheck")
    async def acheck(self, value: str, key_prefix: str) -> bool:
        """检查元素是否可能存在（异步）。可能有误报，不会漏报。"""
        return await self._impl.check(value, key_prefix)

    @require_async("abatch_check")
    async def abatch_check(self, values: List[str], key_prefix: str) -> Dict[str, bool]:
        """批量检查元素是否可能存在（异步）。"""
        return await self._impl.batch_check(values, key_prefix)

    def close(self):
        if self.is_async:
            raise RuntimeError("异步实例请使用 await bloom.aclose() 关闭连接。")
        self._impl.close()

    async def aclose(self):
        if not self.is_async:
            raise RuntimeError("同步实例请使用 close() 方法。")
        await self._impl.close()

    async_close = aclose

    def connect(self):
        pass

    async def async_connect(self):
        pass

    def list_prefixes(self) -> List[str]:
        return list(self._impl.filters_cache.keys())

    @require_sync("stats")
    def stats(self, key_prefix: Optional[str] = None) -> Dict:
        """获取统计信息（同步）。key_prefix 为 None 时返回所有前缀。"""
        return self._impl.stats(key_prefix)

    @require_async("astats")
    async def astats(self, key_prefix: Optional[str] = None) -> Dict:
        """获取统计信息（异步）。key_prefix 为 None 时返回所有前缀。"""
        return await self._impl.stats(key_prefix)
