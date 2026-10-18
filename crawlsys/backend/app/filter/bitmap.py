# -*- coding: utf-8 -*-
import hashlib
from typing import Dict, List, Union, Optional
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from .base import BaseFilter
from common.decorators import require_sync, require_async
try:
    from storage import RedisDB
except ImportError:
    RedisDB = None

from utils.log import get_logger
logger = get_logger("filter.bitmap")


def _format_bytes(bytes_size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} {unit}"


class _BitmapCommon:
    """Bitmap 通用逻辑封装"""
    def __init__(self, max_offset: int, use_hash: bool):
        self.max_offset = max_offset
        self.use_hash = use_hash
        
        # 内存使用估算和警告
        self._check_memory_usage()
        
    def _check_memory_usage(self):
        max_bytes = (self.max_offset + 1) // 8
        memory_str = _format_bytes(max_bytes)
        
        if max_bytes >= 1024**5:  # >= 1PB
            logger.error(f"⚠️ 极高内存使用警告: {memory_str}")
            logger.error("   这在实际生产环境中是不可行的！")
            logger.error("   强烈建议使用 HashBitmapDeduplicator")
        elif max_bytes >= 1024**4:  # >= 1TB
            logger.warning(f"⚠️ 高内存使用警告: {memory_str}")
            logger.warning("   需要大量内存，请谨慎使用")
            logger.warning("   建议考虑使用 HashBitmapDeduplicator")
        elif max_bytes >= 1024**3:  # >= 1GB
            logger.warning(f"⚠️ 中等内存使用: {memory_str}")
            logger.warning("   请确保Redis服务器有足够内存")
        elif max_bytes >= 1024**2:  # >= 1MB
            logger.info(f"内存使用: {memory_str}")
        
    def _hash_id(self, id_value: Union[str, int]) -> int:
        """将字符串ID哈希为整数"""
        hash_obj = hashlib.md5(str(id_value).encode())
        hash_int = int(hash_obj.hexdigest(), 16)
        return hash_int % self.max_offset

    def _validate_offset(self, id_value: Union[int, str]) -> int:
        """验证并转换位偏移量"""
        try:
            if isinstance(id_value, str):
                id_int = int(id_value)
            else:
                id_int = id_value
                
            if id_int < 0:
                raise ValueError(f"ID值必须是非负整数，当前值: {id_int}")
            if id_int > self.max_offset:
                raise ValueError(f"ID值 {id_int} 超出最大偏移量 {self.max_offset}")
                
            return id_int
        except (ValueError, TypeError) as e:
            logger.error(f"无效的ID值: {id_value}, 错误: {e}")
            raise ValueError(f"ID值必须是有效的非负整数，当前值: {id_value}")

    def _get_offset(self, id_value: Union[int, str]) -> int:
        """获取Bitmap偏移量"""
        if self.use_hash:
            return self._hash_id(id_value)
        return self._validate_offset(id_value)

    def get_memory_info(self) -> Dict[str, Union[int, str]]:
        max_bits = self.max_offset + 1
        max_bytes = max_bits // 8
        return {
            'max_offset': self.max_offset,
            'max_bits': max_bits,
            'max_bytes': max_bytes,
            'memory_human_readable': _format_bytes(max_bytes)
        }

# ---------------------------------------------------------------------------
# 同步实现
# ---------------------------------------------------------------------------
class _SyncImpl(_BitmapCommon):
    def __init__(self, redis_url: str = None,
                 max_offset: int = 2**31 - 1, use_hash: bool = False):
        super().__init__(max_offset, use_hash)
        
        if redis_url is not None:
            self.redis = Redis.from_url(redis_url)
            self._owns_connection = True
        else:
            raise ValueError("必须提供 redis_url 参数")

    def add(self, value: str, key_prefix: str) -> bool:
        try:
            validated_id = self._get_offset(value)
            old_value = self.redis.setbit(key_prefix, validated_id, 1)
            return old_value == 0
        except RedisError as e:
            logger.error(f"Redis操作失败 (add): {e}")
            raise

    def batch_add(self, values: List[str], key_prefix: str) -> int:
        validated_ids = []
        for v in values:
            try:
                validated_ids.append(self._get_offset(v))
            except ValueError:
                continue # Skip invalid
        
        if not validated_ids:
            return 0
            
        try:
            with self.redis.pipeline() as pipe:
                for vid in validated_ids:
                    pipe.getbit(key_prefix, vid)
                old_values = pipe.execute()
                
                for vid in validated_ids:
                    pipe.setbit(key_prefix, vid, 1)
                pipe.execute()
                
            count = 0
            for old_v in old_values:
                if old_v == 0:
                    count += 1
            return count
        except RedisError as e:
            logger.error(f"Redis操作失败 (batch_add): {e}")
            raise

    def check(self, value: str, key_prefix: str) -> bool:
        try:
            validated_id = self._get_offset(value)
            return bool(self.redis.getbit(key_prefix, validated_id))
        except RedisError as e:
            logger.error(f"Redis操作失败 (check): {e}")
            raise

    def batch_check(self, values: List[str], key_prefix: str) -> Dict[str, bool]:
        validated_ids = []
        valid_values = []
        for v in values:
             try:
                 validated_ids.append(self._get_offset(v))
                 valid_values.append(v)
             except ValueError:
                 pass

        if not validated_ids:
            return {v: False for v in values} # Fallback for all invalid
            
        try:
            with self.redis.pipeline() as pipe:
                for vid in validated_ids:
                    pipe.getbit(key_prefix, vid)
                results = pipe.execute()
            
            result_map = {v: bool(res) for v, res in zip(valid_values, results)}
            # Fill missing (invalid) as False or handle appropriately
            for v in values:
                if v not in result_map:
                    result_map[v] = False
            return result_map
        except RedisError as e:
            logger.error(f"Redis操作失败 (batch_check): {e}")
            raise

    def close(self):
        if getattr(self, '_owns_connection', False) and hasattr(self, 'redis'):
            self.redis.close()

# ---------------------------------------------------------------------------
# 异步实现
# ---------------------------------------------------------------------------
class _AsyncImpl(_BitmapCommon):
    def __init__(self, redis_url: str = None,
                 max_offset: int = 2**31 - 1, use_hash: bool = False):
        super().__init__(max_offset, use_hash)
        
        if redis_url is not None:
            self.redis = AsyncRedis.from_url(redis_url)
            self._owns_connection = True
        else:
            raise ValueError("必须提供 redis_url 参数")

    async def add(self, value: str, key_prefix: str) -> bool:
        try:
            validated_id = self._get_offset(value)
            old_value = await self.redis.setbit(key_prefix, validated_id, 1)
            return old_value == 0
        except RedisError as e:
            logger.error(f"Redis操作失败 (add): {e}")
            raise

    async def batch_add(self, values: List[str], key_prefix: str) -> int:
        validated_ids = []
        for v in values:
             try:
                 validated_ids.append(self._get_offset(v))
             except ValueError:
                 continue
                 
        if not validated_ids:
            return 0
            
        try:
            async with self.redis.pipeline() as pipe:
                for vid in validated_ids:
                    pipe.getbit(key_prefix, vid)
                old_values = await pipe.execute()
                
                for vid in validated_ids:
                    pipe.setbit(key_prefix, vid, 1)
                await pipe.execute()
            
            count = sum(1 for old_v in old_values if old_v == 0)
            return count
        except RedisError as e:
            logger.error(f"Redis操作失败 (batch_add): {e}")
            raise

    async def check(self, value: str, key_prefix: str) -> bool:
        try:
            validated_id = self._get_offset(value)
            return bool(await self.redis.getbit(key_prefix, validated_id))
        except RedisError as e:
            logger.error(f"Redis操作失败 (check): {e}")
            raise

    async def batch_check(self, values: List[str], key_prefix: str) -> Dict[str, bool]:
        validated_ids = []
        valid_values = []
        for v in values:
             try:
                 validated_ids.append(self._get_offset(v))
                 valid_values.append(v)
             except ValueError:
                 pass
                 
        if not validated_ids:
            return {v: False for v in values}
        
        try:
            async with self.redis.pipeline() as pipe:
                for vid in validated_ids:
                    pipe.getbit(key_prefix, vid)
                results = await pipe.execute()
                
            result_map = {v: bool(res) for v, res in zip(valid_values, results)}
            for v in values:
                if v not in result_map:
                    result_map[v] = False
            return result_map
        except RedisError as e:
            logger.error(f"Redis操作失败 (batch_check): {e}")
            raise

    async def close(self):
        if getattr(self, '_owns_connection', False) and hasattr(self, 'redis'):
            await self.redis.aclose()


class Bitmap(BaseFilter):
    """
    Bitmap 去重器，支持同步和异步模式。
    如果 use_hash=False，value 必须是整数字符串或整数，且在 max_offset 范围内。
    如果 use_hash=True，value 可以是任意字符串，会被 hash 到 max_offset 范围内。
    """
    
    def __init__(self, redis_url: str = None,
                 max_offset: int = 2**31 - 1, use_hash: bool = False,
                 amode: bool = False, key_prefix: str = None):
        """
        初始化 Bitmap

        Args:
            redis_url: Redis 连接 URL
            max_offset: 最大偏移量 (默认 2^31 - 1)
            use_hash: 是否启用 Hash (将任意字符串映射到 Bitmap)
            amode: 是否启用异步模式
            key_prefix: (兼容性参数) 默认 key 前缀，如果方法调用时不传 key_prefix 可能用到
        """
        # 调用父类初始化
        super().__init__(amode=amode)
        self._default_key_prefix = key_prefix
        self._impl = None

        # 构造参数
        kwargs = {
            'redis_url': redis_url,
            'max_offset': max_offset,
            'use_hash': use_hash
        }

        if amode:
            self._impl = _AsyncImpl(**kwargs)
        else:
            self._impl = _SyncImpl(**kwargs)
            
    # -----------------------------------------------------------------------
    # Sync Interface
    # -----------------------------------------------------------------------
    @require_sync("add")
    def add(self, value: Union[str, int], key_prefix: str = None) -> bool:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return self._impl.add(value, prefix)

    @require_sync("batch_add")
    def batch_add(self, values: List[Union[str, int]], key_prefix: str = None) -> int:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return self._impl.batch_add(values, prefix)

    @require_sync("check")
    def check(self, value: Union[str, int], key_prefix: str = None) -> bool:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return self._impl.check(value, prefix)

    @require_sync("batch_check")
    def batch_check(self, values: List[Union[str, int]], key_prefix: str = None) -> Dict[str, bool]:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return self._impl.batch_check(values, prefix)

    def close(self):
        if self.is_async:
            raise RuntimeError("异步实例请使用 await bitmap.aclose() 关闭")
        self._impl.close()

    def connect(self):
        pass

    async def async_connect(self):
        pass

    async def async_close(self):
        if not self.is_async:
            raise RuntimeError("同步实例请使用 close() 方法。")
        await self._impl.close()

    # -----------------------------------------------------------------------
    # Async Interface
    # -----------------------------------------------------------------------
    @require_async("aadd")
    async def aadd(self, value: Union[str, int], key_prefix: str = None) -> bool:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return await self._impl.add(value, prefix)

    @require_async("abatch_add")
    async def abatch_add(self, values: List[Union[str, int]], key_prefix: str = None) -> int:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return await self._impl.batch_add(values, prefix)

    @require_async("acheck")
    async def acheck(self, value: Union[str, int], key_prefix: str = None) -> bool:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return await self._impl.check(value, prefix)

    @require_async("abatch_check")
    async def abatch_check(self, values: List[Union[str, int]], key_prefix: str = None) -> Dict[str, bool]:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix must be provided")
        return await self._impl.batch_check(values, prefix)

    async def aclose(self):
        if not self.is_async:
            raise RuntimeError("同步实例请使用 close()")
        await self._impl.close()

    def get_memory_info(self):
        return self._impl.get_memory_info()

    # -----------------------------------------------------------------------
    # Extra helper methods
    # -----------------------------------------------------------------------
    @require_sync("get_count")
    def get_count(self, key_prefix: str = None) -> int:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix is required")
        return self._impl.redis.bitcount(prefix)

    @require_async("aget_count")
    async def aget_count(self, key_prefix: str = None) -> int:
        prefix = key_prefix or self._default_key_prefix
        if prefix is None:
            raise ValueError("key_prefix is required")
        return await self._impl.redis.bitcount(prefix)
