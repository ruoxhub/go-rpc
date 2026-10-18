# -*- coding: utf-8 -*-
"""Redis storage backend — RedisDB factory + connection management + delegation."""

import asyncio
import os
import time
import threading
from typing import Union, List, Optional, Any, Dict, Tuple
from urllib.parse import urlsplit

from dotenv import load_dotenv
from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as _RedisConnectionError
from redis.exceptions import TimeoutError as _RedisTimeoutError

from storage.base import BaseStore
from common.errors import format_error
from .sync import SyncRedisImpl
from ._async import AsyncRedisImpl
from ._base import (
    logger,
    convert_redis_error,
    Encoder,
    SCAN_BATCH_SIZE,
    DELETE_CHUNK_SIZE,
    DEFAULT_MEMORY_FILTER,
)

load_dotenv()


def _safe_redis_target(database_url: str) -> str:
    """Return a diagnostic Redis target without credentials or query values."""
    try:
        parsed = urlsplit(database_url)
        scheme = parsed.scheme or "redis"
        host = parsed.hostname or "<unknown>"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        database = parsed.path if parsed.path.lstrip("/").isdigit() else ""
        return f"{scheme}://{host}{port}{database}"
    except (TypeError, ValueError):
        return "redis://<redacted>"


class RedisDB(BaseStore):
    def __init__(
        self,
        database_url: str,
        decode_responses: bool = True,
        max_connections: int = 1000,
        amode: bool = False,
        **kwargs,
    ):
        """
        redis的封装
        Args:
            database_url: redis的连接地址
            decode_responses: 是否解码响应
            max_connections: 同一个redis对象使用的并发数(连接池的最大连接数),超过这个数量会抛出redis.ConnectionError
            amode: 是否使用异步模式
            **kwargs: 其他redis连接参数
        """

        # 从环境变量加载配置,优先使用传入的参数
        self._database_url = database_url
        self._log_target = _safe_redis_target(database_url)
        self._decode_responses = decode_responses
        self._max_connections = max_connections
        self._amode = amode
        self._kwargs = kwargs or {}

        self._is_redis_cluster = False

        # 初始化连接状态
        self._connected = False

        # 添加重连锁,防止并发重连
        self._reconnect_lock = threading.RLock()

        # 初始化Redis连接
        try:
            if amode:
                self.__redis = AsyncRedis.from_url(
                    self._database_url,
                    decode_responses=decode_responses,
                    max_connections=max_connections,
                    **self._kwargs,
                )
                self._impl = AsyncRedisImpl(self.__redis)
                # 异步模式下的连接测试将在首次使用时进行
                logger.info(f"Redis异步客户端初始化完成: {self._log_target}")
                self._connected = True
            else:
                self.__redis = SyncRedis.from_url(
                    self._database_url,
                    decode_responses=decode_responses,
                    max_connections=max_connections,
                    **self._kwargs,
                )
                # 测试同步连接
                self._impl = SyncRedisImpl(self.__redis)
                self.__redis.ping()
                self._connected = True
                logger.info(f"Redis连接成功: {self._log_target}")
        except Exception as e:
            logger.error(f"Redis初始化失败: {format_error(e, max_length=500)}")
            raise convert_redis_error(e)

    # BaseStore 抽象方法实现
    def connect(self):
        """建立同步连接"""
        try:
            self.__redis.ping()
            self._connected = True
            logger.info(f"Redis同步连接建立成功: {self._log_target}")
        except Exception as e:
            logger.error(f"Redis同步连接失败: {format_error(e, max_length=500)}")
            raise convert_redis_error(e)

    async def aconnect(self):
        """建立异步连接"""
        try:
            # 使用 ping 命令测试连接
            await self.__redis.ping()
            self._connected = True
            logger.info(f"Redis异步连接建立成功: {self._log_target}")
        except Exception as e:
            logger.error(f"Redis异步连接失败: {format_error(e, max_length=500)}")
            raise convert_redis_error(e)

    def close(self):
        """关闭同步连接"""
        try:
            if self.__redis:
                self.__redis.close()
                self._connected = False
                logger.info("Redis同步连接已关闭")
        except Exception as e:
            logger.error(f"关闭Redis同步连接失败: {format_error(e, max_length=500)}")

    async def aclose(self):
        """关闭异步连接"""
        try:
            if self.__redis:
                await self.__redis.aclose()
                self._connected = False
                logger.info("Redis异步连接已关闭")
        except Exception as e:
            logger.error(f"关闭Redis异步连接失败: {format_error(e, max_length=500)}")

    def ping(self) -> bool:
        """检查同步连接状态"""
        try:
            result = self.__redis.ping()
            return result
        except Exception as e:
            logger.error(f"Redis ping 失败: {format_error(e, max_length=500)}")
            self._connected = False
            return False

    async def aping(self) -> bool:
        """检查异步连接状态"""
        try:
            result = await self.__redis.ping()
            return result
        except Exception as e:
            logger.error(f"Redis async ping 失败: {format_error(e, max_length=500)}")
            self._connected = False
            return False

    def __repr__(self):
        return (
            f"<RedisDB database_url={self._log_target} amode={self._amode}>"
        )

    @property
    def _redis(self):
        """获取Redis连接对象,不进行主动健康检查,依靠连接池自动处理"""
        return self.__redis

    @_redis.setter
    def _redis(self, val):
        self.__redis = val

    @classmethod
    def from_url(
        cls,
        database_url: str,
        decode_responses: bool = True,
        max_connections: int = 1000,
        amode: bool = False,
        **kwargs,
    ):
        """

        Args:
            database_url: redis url

        Returns:

        """
        return cls(
            database_url=database_url,
            decode_responses=decode_responses,
            max_connections=max_connections,
            amode=amode,
            **kwargs,
        )

    async def asadd(self, table, values):
        """
        @summary: 异步使用无序set集合存储数据， 去重
        ---------
        @param table:
        @param values: 值； 支持list 或 单个值
        ---------
        @result: 若库中存在 返回0，否则入库，返回1。 批量添加返回None
        """
        return await self._impl.asadd(table, values)

    def sadd(self, table, values):
        """
        @summary: 使用无序set集合存储数据， 去重
        ---------
        @param table:
        @param values: 值； 支持list 或 单个值
        ---------
        @result: 若库中存在 返回0，否则入库，返回1。 批量添加返回None
        """
        return self._impl.sadd(table, values)

    async def asget(self, table, count=1, is_pop=True):
        """
        异步返回 list 如 ['1'] 或 []
        @param table:
        @param count:
        @param is_pop:
        @return:
        """
        return await self._impl.asget(table, count, is_pop)

    def sget(self, table, count=1, is_pop=True):
        """
        返回 list 如 ['1'] 或 []
        @param table:
        @param count:
        @param is_pop:
        @return:
        """
        return self._impl.sget(table, count, is_pop)

    def srem(self, table, values):
        """
        @summary: 移除集合中的指定元素
        ---------
        @param table:
        @param values: 一个或者列表
        ---------
        @result:
        """
        return self._impl.srem(table, values)

    async def asget_count(self, table):
        return await self._impl.asget_count(table)

    def sget_count(self, table):
        return self._impl.sget_count(table)

    def sdelete(self, table):
        """
        @summary: 删除set集合的大键（数据量大的表）
        删除大set键，使用sscan命令，每次扫描集合中500个元素，再用srem命令每次删除一个键
        若直接用delete命令，会导致Redis阻塞，出现故障切换和应用程序崩溃的故障。
        ---------
        @param table:
        ---------
        @result:
        """
        return self._impl.sdelete(table)

    def sismember(self, table, key):
        "Return a boolean indicating if ``value`` is a member of set ``name``"
        return self._impl.sismember(table, key)

    async def azadd(self, table, values, prioritys=0):
        """
        @summary: 异步使用有序set集合存储数据， 去重(值存在更新)
        ---------
        @param table:
        @param values: 值； 支持list 或 单个值
        @param prioritys: 优先级； double类型，支持list 或 单个值。 根据此字段的值来排序, 值越小越优先。 可不传值，默认value的优先级为0
        ---------
        @result:若库中存在 返回0，否则入库，返回1。 批量添加返回 [0, 1 ...]
        """
        return await self._impl.azadd(table, values, prioritys)

    def zadd(self, table, values, prioritys=0):
        """
        @summary: 使用有序set集合存储数据， 去重(值存在更新)
        ---------
        @param table:
        @param values: 值； 支持list 或 单个值
        @param prioritys: 优先级； double类型，支持list 或 单个值。 根据此字段的值来排序, 值越小越优先。 可不传值，默认value的优先级为0
        ---------
        @result:若库中存在 返回0，否则入库，返回1。 批量添加返回 [0, 1 ...]
        """
        return self._impl.zadd(table, values, prioritys)

    async def azget(self, table, count=1, is_pop=True):
        """
        @summary: 异步从有序set集合中获取数据 优先返回分数小的（优先级高的）
        ---------
        @param table:
        @param count: 数量 -1 返回全部数据
        @param is_pop:获取数据后，是否在原set集合中删除，默认是
        ---------
        @result: 列表
        """
        return await self._impl.azget(table, count, is_pop)

    def zget(self, table, count=1, is_pop=True):
        """
        @summary: 从有序set集合中获取数据 优先返回分数小的（优先级高的）
        ---------
        @param table:
        @param count: 数量 -1 返回全部数据
        @param is_pop:获取数据后，是否在原set集合中删除，默认是
        ---------
        @result: 列表
        """
        return self._impl.zget(table, count, is_pop)

    def zremrangebyscore(self, table, priority_min, priority_max):
        """
        根据分数移除成员 闭区间
        @param table:
        @param priority_min:
        @param priority_max:
        @return: 被移除的成员个数
        """
        return self._impl.zremrangebyscore(table, priority_min, priority_max)

    def zrangebyscore(self, table, priority_min, priority_max, count=None, is_pop=True):
        """
        @summary: 返回指定分数区间的数据 闭区间
        ---------
        @param table:
        @param priority_min: 优先级越小越优先
        @param priority_max:
        @param count: 获取的数量，为空则表示分数区间内的全部数据
        @param is_pop: 是否删除
        ---------
        @result:
        """
        return self._impl.zrangebyscore(
            table, priority_min, priority_max, count, is_pop
        )

    def zrangebyscore_increase_score(
        self, table, priority_min, priority_max, increase_score, count=None
    ):
        """
        @summary: 返回指定分数区间的数据 闭区间， 同时修改分数
        ---------
        @param table:
        @param priority_min: 最小分数
        @param priority_max: 最大分数
        @param increase_score: 分数值增量 正数则在原有的分数上叠加，负数则相减
        @param count: 获取的数量，为空则表示分数区间内的全部数据
        ---------
        @result:
        """
        return self._impl.zrangebyscore_increase_score(
            table, priority_min, priority_max, increase_score, count
        )

    def zrangebyscore_set_score(
        self, table, priority_min, priority_max, score, count=None
    ):
        """
        @summary: 返回指定分数区间的数据 闭区间， 同时修改分数
        ---------
        @param table:
        @param priority_min: 最小分数
        @param priority_max: 最大分数
        @param score: 分数值
        @param count: 获取的数量，为空则表示分数区间内的全部数据
        ---------
        @result:
        """
        return self._impl.zrangebyscore_set_score(
            table, priority_min, priority_max, score, count
        )

    def zincrby(self, table, amount, value):
        return self._impl.zincrby(table, amount, value)

    def zget_count(self, table, priority_min=None, priority_max=None):
        """
        @summary: 获取表数据的数量
        ---------
        @param table:
        @param priority_min:优先级范围 最小值（包含）
        @param priority_max:优先级范围 最大值（包含）
        ---------
        @result:
        """
        return self._impl.zget_count(table, priority_min, priority_max)

    def zrem(self, table, values):
        """
        @summary: 移除集合中的指定元素
        ---------
        @param table:
        @param values: 一个或者列表
        ---------
        @result:
        """
        return self._impl.zrem(table, values)

    def zexists(self, table, values):
        """
        利用zscore判断某元素是否存在
        @param values:
        @return:
        """
        return self._impl.zexists(table, values)

    def lpush(self, table, values):
        return self._impl.lpush(table, values)

    def lpop(self, table, count=1):
        """
        @summary:
        ---------
        @param table:
        @param count:
        ---------
        @result: count>1时返回列表
        """
        return self._impl.lpop(table, count)

    def rpoplpush(self, from_table, to_table=None):
        """
        将列表 from_table 中的最后一个元素(尾元素)弹出，并返回给客户端。
        将 from_table 弹出的元素插入到列表 to_table ，作为 to_table 列表的的头元素。
        如果 from_table 和 to_table 相同，则列表中的表尾元素被移动到表头，并返回该元素，可以把这种特殊情况视作列表的旋转(rotation)操作
        @param from_table:
        @param to_table:
        @return:
        """
        return self._impl.rpoplpush(from_table, to_table)

    def lget_count(self, table):
        return self._impl.lget_count(table)

    def lrem(self, table, value, num=0):
        """
        @summary:
        删除value
        ---------
        @param table:
        @param value:
        @param num:
        ---------
        @result: 删除的条数
        """
        return self._impl.lrem(table, value, num)

    def lrange(self, table, start=0, end=-1):
        return self._impl.lrange(table, start, end)

    async def alrange(self, table, start=0, end=-1):
        """
        异步获取列表指定范围内的元素
        @param table:
        @param start: 起始位置，0 表示第一个元素，-1 表示最后一个元素
        @param end: 结束位置，-1 表示最后一个元素
        @return: 指定范围内的元素列表
        """
        return await self._impl.alrange(table, start, end)

    async def alpush(self, table, values):
        """异步将值推入列表左侧"""
        return await self._impl.alpush(table, values)

    async def alpop(self, table, count=1):
        """异步从列表左侧弹出元素"""
        return await self._impl.alpop(table, count)

    async def alget_count(self, table):
        """异步获取列表长度"""
        return await self._impl.alget_count(table)

    async def alrem(self, table, value, num=0):
        """异步删除列表中的值"""
        return await self._impl.alrem(table, value, num)

    async def ahset(self, table, key, value):
        """
        @summary: 异步设置哈希表字段的值
        如果 key 不存在，一个新的哈希表被创建并进行 HSET 操作。
        如果域 field 已经存在于哈希表中，旧值将被覆盖
        ---------
        @param table:
        @param key:
        @param value:
        ---------
        @result: 1 新插入； 0 覆盖
        """
        return await self._impl.ahset(table, key, value)

    def hset(self, table, key, value):
        """
        @summary:
        如果 key 不存在，一个新的哈希表被创建并进行 HSET 操作。
        如果域 field 已经存在于哈希表中，旧值将被覆盖
        ---------
        @param table:
        @param key:
        @param value:
        ---------
        @result: 1 新插入； 0 覆盖
        """
        return self._impl.hset(table, key, value)

    def hset_batch(self, table, datas):
        """
        批量插入
        Args:
            datas:
                [[key, value]]
        Returns:

        """
        return self._impl.hset_batch(table, datas)

    def hincrby(self, table, key, increment):
        return self._impl.hincrby(table, key, increment)

    async def ahget(self, table, key, is_pop=False):
        return await self._impl.ahget(table, key, is_pop)

    async def ahgetall(self, table):
        """异步获取哈希表所有字段和值"""
        return await self._impl.ahgetall(table)

    async def ahexists(self, table, key):
        """异步检查哈希表字段是否存在"""
        return await self._impl.ahexists(table, key)

    async def ahdel(self, table, *keys):
        """异步删除哈希表字段"""
        return await self._impl.ahdel(table, *keys)

    async def ahget_count(self, table):
        """异步获取哈希表字段数量"""
        return await self._impl.ahget_count(table)

    async def ahkeys(self, table):
        """异步获取哈希表所有字段"""
        return await self._impl.ahkeys(table)

    async def ahvals(self, table):
        """异步获取哈希表所有值"""
        return await self._impl.ahvals(table)

    async def ahset_batch(self, table, datas):
        """异步批量插入哈希表"""
        return await self._impl.ahset_batch(table, datas)

    async def ahincrby(self, table, key, increment):
        """异步为哈希表字段增加整数值"""
        return await self._impl.ahincrby(table, key, increment)

    async def asrem(self, table, values):
        """异步移除集合中的指定元素"""
        return await self._impl.asrem(table, values)

    async def asismember(self, table, key):
        """异步检查成员是否在集合中"""
        return await self._impl.asismember(table, key)

    async def azget_count(self, table, priority_min=None, priority_max=None):
        """异步获取有序集合数据数量"""
        return await self._impl.azget_count(table, priority_min, priority_max)

    async def azrem(self, table, values):
        """异步移除集合中的指定元素"""
        return await self._impl.azrem(table, values)

    async def azexists(self, table, values):
        """异步检查元素是否存在"""
        return await self._impl.azexists(table, values)

    async def astr_incrby(self, table, value):
        """异步为字符串值增加整数"""
        return await self._impl.astr_incrby(table, value)

    async def astrlen(self, table):
        """异步获取字符串长度"""
        return await self._impl.astrlen(table)

    async def agetkeys(self, regex):
        """异步获取匹配模式的 keys"""
        return await self._impl.agetkeys(regex)

    async def aexists_key(self, key):
        """异步检查 key 是否存在"""
        return await self._impl.aexists_key(key)

    async def aset_expire(self, key, seconds):
        """异步设置过期时间"""
        return await self._impl.aset_expire(key, seconds)

    async def aget_expire(self, key):
        """异步获取过期时间"""
        return await self._impl.aget_expire(key)

    async def aclear(self, table):
        """异步删除指定的 key"""
        return await self._impl.aclear(table)

    async def asetbit(self, table, offsets, values):
        """异步设置字符串数组某一位的值"""
        return await self._impl.asetbit(table, offsets, values)

    async def agetbit(self, table, offsets):
        """异步取字符串数组某一位的值"""
        return await self._impl.agetbit(table, offsets)

    async def abitcount(self, table):
        """异步计算字符串中 1 的数量"""
        return await self._impl.abitcount(table)

    async def arpoplpush(self, from_table, to_table=None):
        """异步将列表尾元素弹出并推入另一个列表头部"""
        return await self._impl.arpoplpush(from_table, to_table)

    def hget(self, table, key, is_pop=False):
        return self._impl.hget(table, key, is_pop)

    def hgetall(self, table):
        return self._impl.hgetall(table)

    def hexists(self, table, key):
        return self._impl.hexists(table, key)

    def hdel(self, table, *keys):
        """
        @summary: 删除对应的key 可传多个
        ---------
        @param table:
        @param *keys:
        ---------
        @result:
        """
        return self._impl.hdel(table, *keys)

    def hget_count(self, table):
        return self._impl.hget_count(table)

    def hkeys(self, table):
        return self._impl.hkeys(table)

    def hvals(self, key):
        return self._impl.hvals(key)

    def setbit(
        self, table, offsets: Union[int, List[int]], values: Union[int, List[int]]
    ):
        """
        设置字符串数组某一位的值，返回之前的值
        @param table: Redis key
        @param offsets: 支持列表或单个值
        @param values: 支持列表或单个值
        @return: list / 单个值
        """
        return self._impl.setbit(table, offsets, values)

    def getbit(self, table, offsets):
        """
        取字符串数组某一位的值
        @param table:
        @param offsets: 支持列表
        @return: list / 单个值
        """
        return self._impl.getbit(table, offsets)

    def bitcount(self, table):
        return self._impl.bitcount(table)

    async def astrset(self, table, value, **kwargs):
        """
        异步设置键值
        Args:
            table:
            value:
            **kwargs:
                ex: Union[None, int, timedelta] = ..., 设置键的过期时间为 second 秒
                px: Union[None, int, timedelta] = ..., 设置键的过期时间为 millisecond 毫秒
                nx: bool = ..., 只有键不存在时，才对键进行设置操作
                xx: bool = ..., 只有键已经存在时，才对键进行设置操作
                keepttl: bool = ..., 保留键的过期时间
        Returns:

        """
        return await self._impl.astrset(table, value, **kwargs)

    def strset(self, table, value, **kwargs):
        """
        设置键值
        Args:
            table:
            value:
            **kwargs:
                ex: Union[None, int, timedelta] = ..., 设置键的过期时间为 second 秒
                px: Union[None, int, timedelta] = ..., 设置键的过期时间为 millisecond 毫秒
                nx: bool = ..., 只有键不存在时，才对键进行设置操作
                xx: bool = ..., 只有键已经存在时，才对键进行设置操作
                keepttl: bool = ..., 保留键的过期时间
        Returns:

        """
        return self._impl.strset(table, value, **kwargs)

    def str_incrby(self, table, value):
        return self._impl.str_incrby(table, value)

    async def astrget(self, table):
        return await self._impl.astrget(table)

    async def amget(self, keys):
        return await self._impl.amget(keys)

    def strget(self, table):
        return self._impl.strget(table)

    def strlen(self, table):
        return self._impl.strlen(table)

    def getkeys(self, regex):
        return self._impl.getkeys(regex)

    def exists_key(self, key):
        return self._impl.exists_key(key)

    def set_expire(self, key, seconds):
        """
        @summary: 设置过期时间
        ---------
        @param key:
        @param seconds: 秒
        ---------
        @result:
        """
        return self._impl.set_expire(key, seconds)

    def get_expire(self, key):
        """
        @summary: 查询过期时间
        ---------
        @param key:
        @param seconds: 秒
        ---------
        @result:
        """
        return self._impl.get_expire(key)

    def clear(self, table):
        """删除指定的key"""
        return self._impl.clear(table)

    def get_redis_obj(self):
        """获取原始Redis对象"""
        return self._impl.get_redis_obj()

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查,返回Redis连接状态信息
        Returns:
            包含连接状态、延迟等信息的字典
        """
        return self._impl.health_check()

    def get_connection_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态
        Returns:
            连接池状态信息
        """
        return self._impl.get_connection_pool_status()

    def _reconnect(self, max_retries: int = 5):
        """
        重新连接Redis
        Args:
            max_retries: 最大重试次数,默认5次
        """
        # 使用锁防止并发重连
        with self._reconnect_lock:
            # 再次检查连接状态,避免重复重连
            try:
                if not self._amode:
                    if self.__redis.ping():
                        logger.info("Redis连接正常,无需重连")
                        return True
            except:
                pass

            retry_count = 0
            while retry_count < max_retries:
                try:
                    retry_count += 1
                    logger.warning(
                        f"Redis连接断开,正在尝试第 {retry_count}/{max_retries} 次重连..."
                    )

                    # 重新创建连接
                    if self._amode:
                        self.__redis = AsyncRedis.from_url(
                            self._database_url,
                            decode_responses=self._decode_responses,
                            max_connections=self._max_connections,
                            **self._kwargs,
                        )
                    else:
                        self.__redis = SyncRedis.from_url(
                            self._database_url,
                            decode_responses=self._decode_responses,
                            max_connections=self._max_connections,
                            **self._kwargs,
                        )

                    # 测试连接
                    if not self._amode:
                        if self.__redis.ping():
                            logger.info(f"Redis重连成功: {self._log_target}")
                            return True
                    else:
                        # 异步模式不进行ping测试
                        logger.info(f"Redis异步客户端重连成功: {self._log_target}")
                        return True

                except (_RedisConnectionError, _RedisTimeoutError) as e:
                    logger.error(
                        f"Redis重连失败 (尝试 {retry_count}/{max_retries}): "
                        f"{format_error(e, max_length=500)}"
                    )
                    if retry_count < max_retries:
                        time.sleep(2)
                except Exception as e:
                    logger.error(
                        f"Redis重连出现未知错误: {format_error(e, max_length=500)}"
                    )
                    if retry_count < max_retries:
                        time.sleep(2)

            # 超过最大重试次数
            error_msg = f"Redis重连失败,已达到最大重试次数 {max_retries}"
            logger.error(error_msg)
            raise _RedisConnectionError(error_msg)

    def __getattr__(self, name):
        return getattr(self._redis, name)

    def current_status(self, show_key=True, filter_key_by_used_memory=DEFAULT_MEMORY_FILTER):
        """
        统计redis当前使用情况
        Args:
            show_key: 是否统计每个key的内存
            filter_key_by_used_memory: 根据内存的使用量过滤key 只显示使用量大于指定内存的key

        Returns:

        """
        return self._impl.current_status(show_key, filter_key_by_used_memory)

    def batch_delete(self, keys: List[str], chunk_size: int = DELETE_CHUNK_SIZE) -> int:
        """
        批量删除keys
        Args:
            keys: 要删除的key列表
            chunk_size: 每批删除的数量
        Returns:
            删除的key数量
        """
        return self._impl.batch_delete(keys, chunk_size)

    def delete_by_pattern(self, pattern: str, chunk_size: int = DELETE_CHUNK_SIZE) -> int:
        """
        根据模式删除keys
        Args:
            pattern: 匹配模式,如 "user:*"
            chunk_size: 每批删除的数量
        Returns:
            删除的key数量
        """
        return self._impl.delete_by_pattern(pattern, chunk_size)

    def mget_dict(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量获取多个key的值,返回字典格式
        Args:
            keys: key列表
        Returns:
            {key: value} 字典
        """
        return self._impl.mget_dict(keys)

    def mset_dict(self, mapping: Dict[str, Any]) -> bool:
        """
        批量设置多个key-value
        Args:
            mapping: {key: value} 字典
        Returns:
            是否成功
        """
        return self._impl.mset_dict(mapping)

    def expire_batch(self, keys: List[str], seconds: int) -> int:
        """
        批量设置过期时间
        Args:
            keys: key列表
            seconds: 过期秒数
        Returns:
            成功设置的数量
        """
        return self._impl.expire_batch(keys, seconds)
