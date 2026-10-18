# -*- coding: utf-8 -*-
"""Redis storage backend — synchronous implementation."""

import time
from typing import Union, List, Any, Dict

from redis import Redis as SyncRedis

from ._base import (
    logger,
    convert_redis_error,
    SCAN_BATCH_SIZE,
    DELETE_CHUNK_SIZE,
    DEFAULT_MEMORY_FILTER,
)


class SyncRedisImpl:
    """同步实现类"""

    def __init__(self, redis_db):
        self._redis_db = redis_db

    def sadd(self, table, values):
        """
        @summary: 使用无序set集合存储数据， 去重
        ---------
        @param table:
        @param values: 值； 支持list 或 单个值
        ---------
        @result: 若库中存在 返回0，否则入库，返回1。 批量添加返回None
        """

        if isinstance(values, list):
            pipe = self._redis_db.pipeline()

            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.sadd(table, value)
            pipe.execute()

        else:
            return self._redis_db.sadd(table, values)

    def sget(self, table, count=1, is_pop=True):
        """
        返回 list 如 ['1'] 或 []
        @param table:
        @param count:
        @param is_pop:
        @return:
        """

        datas = []
        if is_pop:
            count = count if count <= self.sget_count(table) else self.sget_count(table)
            if count:
                if count > 1:
                    pipe = self._redis_db.pipeline()

                    if not self._redis_db._is_redis_cluster:
                        pipe.multi()
                    while count:
                        pipe.spop(table)
                        count -= 1
                    datas = pipe.execute()

                else:
                    datas.append(self._redis_db.spop(table))

        else:
            datas = self._redis_db.srandmember(table, count)

        return datas

    def srem(self, table, values):
        """
        @summary: 移除集合中的指定元素
        ---------
        @param table:
        @param values: 一个或者列表
        ---------
        @result:
        """

        if isinstance(values, list):
            pipe = self._redis_db.pipeline()

            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.srem(table, value)
            pipe.execute()
        else:
            self._redis_db.srem(table, values)

    def sget_count(self, table):
        return self._redis_db.scard(table)

    def sdelete(self, table, batch_size: int = 1000):
        """
        @summary: 删除set集合的大键（数据量大的表）
        删除大set键，使用sscan命令，每次扫描集合中500个元素，使用pipeline批量删除
        若直接用delete命令，会导致Redis阻塞，出现故障切换和应用程序崩溃的故障。
        ---------
        @param table:
        @param batch_size: 每批删除的数量，默认1000
        ---------
        @result:
        """

        # 当 SCAN 命令的游标参数被设置为 0 时， 服务器将开始一次新的迭代， 而当服务器向用户返回值为 0 的游标时， 表示迭代已结束
        cursor = 0
        while cursor != 0:
            cursor, data = self._redis_db.sscan(table, cursor=cursor, count=SCAN_BATCH_SIZE)

            # 使用pipeline批量删除，提高效率
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()

            for item in data:
                pipe.srem(table, item)

            pipe.execute()

    def sismember(self, table, key):
        "Return a boolean indicating if ``value`` is a member of set ``name``"
        return self._redis_db.sismember(table, key)

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
        if isinstance(values, list):
            if not isinstance(prioritys, list):
                prioritys = [prioritys] * len(values)
            else:
                assert len(values) == len(prioritys), "values值要与prioritys值一一对应"

            # 使用 mapping 参数优化批量插入性能
            try:
                # Redis 3.0.2+ 支持 mapping 参数
                mapping = {
                    value: priority for value, priority in zip(values, prioritys)
                }
                return self._redis_db.zadd(table, mapping)
            except (TypeError, AttributeError):
                # 降级到旧版本的实现方式 (Redis 版本不支持 mapping 参数)
                pipe = self._redis_db.pipeline()

                if not self._redis_db._is_redis_cluster:
                    pipe.multi()
                for value, priority in zip(values, prioritys):
                    pipe.execute_command(
                        "ZADD", table, priority, value
                    )  # 为了兼容2.x与3.x版本的redis
                return pipe.execute()

        else:
            return self._redis_db.execute_command(
                "ZADD", table, prioritys, values
            )  # 为了兼容2.x与3.x版本的redis

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

        start_pos = 0  # 包含
        end_pos = count - 1 if count > 0 else count

        pipe = self._redis_db.pipeline()

        if not self._redis_db._is_redis_cluster:
            pipe.multi()  # 标记事务的开始 参考 http://www.runoob.com/redis/redis-transactions.html
        pipe.zrange(table, start_pos, end_pos)  # 取值
        if is_pop:
            pipe.zremrangebyrank(table, start_pos, end_pos)  # 删除
        results, *count = pipe.execute()
        return results

    def zremrangebyscore(self, table, priority_min, priority_max):
        """
        根据分数移除成员 闭区间
        @param table:
        @param priority_min:
        @param priority_max:
        @return: 被移除的成员个数
        """
        return self._redis_db.zremrangebyscore(table, priority_min, priority_max)

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

        # 使用lua脚本， 保证操作的原子性
        lua = """
            -- local key = KEYS[1]
            local min_score = ARGV[2]
            local max_score = ARGV[3]
            local is_pop = ARGV[4]
            local count = ARGV[5]

            -- 取值
            local datas = nil
            if count then
                datas = redis.call('zrangebyscore', KEYS[1], min_score, max_score, 'limit', 0, count)
            else
                datas = redis.call('zrangebyscore', KEYS[1], min_score, max_score)
            end

            -- 删除redis中刚取到的值
            if (is_pop=='True' or is_pop=='1') then
                for i=1, #datas do
                    redis.call('zrem', KEYS[1], datas[i])
                end
            end


            return datas

        """
        cmd = self._redis_db.register_script(lua)
        if count:
            res = cmd(
                keys=[table], args=[table, priority_min, priority_max, is_pop, count]
            )
        else:
            res = cmd(keys=[table], args=[table, priority_min, priority_max, is_pop])

        return res

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

        # 使用lua脚本， 保证操作的原子性
        lua = """
            -- local key = KEYS[1]
            local min_score = ARGV[1]
            local max_score = ARGV[2]
            local increase_score = ARGV[3]
            local count = ARGV[4]

            -- 取值
            local datas = nil
            if count then
                datas = redis.call('zrangebyscore', KEYS[1], min_score, max_score, 'limit', 0, count)
            else
                datas = redis.call('zrangebyscore', KEYS[1], min_score, max_score)
            end

            --修改优先级
            for i=1, #datas do
                redis.call('zincrby', KEYS[1], increase_score, datas[i])
            end

            return datas

        """
        cmd = self._redis_db.register_script(lua)
        if count:
            res = cmd(
                keys=[table], args=[priority_min, priority_max, increase_score, count]
            )
        else:
            res = cmd(keys=[table], args=[priority_min, priority_max, increase_score])

        return res

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

        # 使用lua脚本， 保证操作的原子性
        lua = """
            -- local key = KEYS[1]
            local min_score = ARGV[1]
            local max_score = ARGV[2]
            local set_score = ARGV[3]
            local count = ARGV[4]

            -- 取值
            local datas = nil
            if count then
                datas = redis.call('zrangebyscore', KEYS[1], min_score, max_score, 'withscores','limit', 0, count)
            else
                datas = redis.call('zrangebyscore', KEYS[1], min_score, max_score, 'withscores')
            end

            local real_datas = {} -- 数据
            --修改优先级
            for i=1, #datas, 2 do
               local data = datas[i]
               local score = datas[i+1]

               table.insert(real_datas, data) -- 添加数据

               redis.call('zincrby', KEYS[1], set_score - score, datas[i])
            end

            return real_datas

        """
        cmd = self._redis_db.register_script(lua)
        if count:
            res = cmd(keys=[table], args=[priority_min, priority_max, score, count])
        else:
            res = cmd(keys=[table], args=[priority_min, priority_max, score])

        return res

    def zincrby(self, table, amount, value):
        return self._redis_db.zincrby(table, amount, value)

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

        if priority_min != None and priority_max != None:
            return self._redis_db.zcount(table, priority_min, priority_max)
        else:
            return self._redis_db.zcard(table)

    def zrem(self, table, values):
        """
        @summary: 移除集合中的指定元素
        ---------
        @param table:
        @param values: 一个或者列表
        ---------
        @result:
        """

        if isinstance(values, list):
            self._redis_db.zrem(table, *values)
        else:
            self._redis_db.zrem(table, values)

    def zexists(self, table, values):
        """
        利用zscore判断某元素是否存在
        @param values:
        @return:
        """

        is_exists = []

        if isinstance(values, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.zscore(table, value)
            is_exists_temp = pipe.execute()
            for is_exist in is_exists_temp:
                if is_exist != None:
                    is_exists.append(1)
                else:
                    is_exists.append(0)

        else:
            is_exists = self._redis_db.zscore(table, values)
            is_exists = 1 if is_exists != None else 0

        return is_exists

    def lpush(self, table, values):
        if isinstance(values, list):
            pipe = self._redis_db.pipeline()

            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.lpush(table, value)
            pipe.execute()

        else:
            return self._redis_db.lpush(table, values)

    def lpop(self, table, count=1):
        """
        @summary:
        ---------
        @param table:
        @param count:
        ---------
        @result: count>1时返回列表
        """

        datas = None
        lcount = self.lget_count(table)
        count = count if count <= lcount else lcount

        if count:
            if count > 1:
                pipe = self._redis_db.pipeline()

                if not self._redis_db._is_redis_cluster:
                    pipe.multi()
                while count:
                    pipe.lpop(table)
                    count -= 1
                datas = pipe.execute()

            else:
                datas = self._redis_db.lpop(table)

        return datas

    def rpoplpush(self, from_table, to_table=None):
        """
        将列表 from_table 中的最后一个元素(尾元素)弹出，并返回给客户端。
        将 from_table 弹出的元素插入到列表 to_table ，作为 to_table 列表的的头元素。
        如果 from_table 和 to_table 相同，则列表中的表尾元素被移动到表头，并返回该元素，可以把这种特殊情况视作列表的旋转(rotation)操作
        @param from_table:
        @param to_table:
        @return:
        """

        if not to_table:
            to_table = from_table

        return self._redis_db.rpoplpush(from_table, to_table)

    def lget_count(self, table):
        return self._redis_db.llen(table)

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
        return self._redis_db.lrem(table, num, value)

    def lrange(self, table, start=0, end=-1):
        return self._redis_db.lrange(table, start, end)

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
        return self._redis_db.hset(table, key, value)

    def hset_batch(self, table, datas):
        """
        批量插入
        Args:
            datas:
                [[key, value]]
        Returns:

        """
        pipe = self._redis_db.pipeline()

        if not self._redis_db._is_redis_cluster:
            pipe.multi()
        for key, value in datas:
            pipe.hset(table, key, value)
        return pipe.execute()

    def hincrby(self, table, key, increment):
        return self._redis_db.hincrby(table, key, increment)

    def hget(self, table, key, is_pop=False):
        if not is_pop:
            return self._redis_db.hget(table, key)
        else:
            lua = """
                -- local key = KEYS[1]
                local field = ARGV[1]

                -- 取值
                local datas = redis.call('hget', KEYS[1], field)
                -- 删除值
                redis.call('hdel', KEYS[1], field)

                return datas

                    """
            cmd = self._redis_db.register_script(lua)
            res = cmd(keys=[table], args=[key])

            return res

    def hgetall(self, table):
        return self._redis_db.hgetall(table)

    def hexists(self, table, key):
        return self._redis_db.hexists(table, key)

    def hdel(self, table, *keys):
        """
        @summary: 删除对应的key 可传多个
        ---------
        @param table:
        @param *keys:
        ---------
        @result:
        """
        self._redis_db.hdel(table, *keys)

    def hget_count(self, table):
        return self._redis_db.hlen(table)

    def hkeys(self, table):
        return self._redis_db.hkeys(table)

    def hvals(self, key):
        return self._redis_db.hvals(key)

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
        if isinstance(offsets, list):
            if isinstance(values, int):
                # 使用pipeline批量设置，避免lua脚本阻塞Redis
                pipe = self._redis_db.pipeline()
                if not self._redis_db._is_redis_cluster:
                    pipe.multi()

                for offset in offsets:
                    pipe.setbit(table, offset, values)

                return pipe.execute()
            else:
                assert len(offsets) == len(values), "offsets值要与values值一一对应"
                pipe = self._redis_db.pipeline()
                if not self._redis_db._is_redis_cluster:
                    pipe.multi()

                for offset, value in zip(offsets, values):
                    pipe.setbit(table, offset, value)

                return pipe.execute()

        else:
            return self._redis_db.setbit(table, offsets, values)

    def getbit(self, table, offsets):
        """
        取字符串数组某一位的值
        @param table:
        @param offsets: 支持列表
        @return: list / 单个值
        """
        if isinstance(offsets, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for offset in offsets:
                pipe.getbit(table, offset)

            return pipe.execute()

        else:
            return self._redis_db.getbit(table, offsets)

    def bitcount(self, table):
        return self._redis_db.bitcount(table)

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
        return self._redis_db.set(table, value, **kwargs)

    def str_incrby(self, table, value):
        return self._redis_db.incrby(table, value)

    def strget(self, table):
        return self._redis_db.get(table)

    def strlen(self, table):
        return self._redis_db.strlen(table)

    def getkeys(self, regex):
        return self._redis_db.keys(regex)

    def exists_key(self, key):
        return self._redis_db.exists(key)

    def set_expire(self, key, seconds):
        """
        @summary: 设置过期时间
        ---------
        @param key:
        @param seconds: 秒
        ---------
        @result:
        """
        self._redis_db.expire(key, seconds)

    def get_expire(self, key):
        """
        @summary: 查询过期时间
        ---------
        @param key:
        @param seconds: 秒
        ---------
        @result:
        """
        return self._redis_db.ttl(key)

    def clear(self, table):
        """删除指定的key"""
        try:
            self._redis_db.delete(table)
        except Exception as e:
            logger.error(f"删除key失败: {table}, 错误: {e}")

    def get_redis_obj(self):
        """获取原始Redis对象"""
        return self._redis_db

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查,返回Redis连接状态信息
        Returns:
            包含连接状态、延迟等信息的字典
        """
        try:
            start_time = time.time()
            ping_result = self._redis_db.ping()
            latency = (time.time() - start_time) * 1000  # 转换为毫秒

            info = self._redis_db.info()

            return {
                "status": "healthy" if ping_result else "unhealthy",
                "latency_ms": round(latency, 2),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "redis_version": info.get("redis_version", "unknown"),
            }
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {"status": "error", "error": str(e)}

    def get_connection_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态
        Returns:
            连接池状态信息
        """
        try:
            pool = self._redis_db.connection_pool
            return {
                "max_connections": self._redis_db._max_connections,
                "connection_class": str(pool.connection_class),
                "connection_kwargs": {
                    "host": self._redis_db._host,
                    "port": self._redis_db._port,
                    "db": self._redis_db._db,
                },
            }
        except Exception as e:
            logger.error(f"获取连接池状态失败: {e}")
            return {"error": str(e)}

    def current_status(self, show_key=True, filter_key_by_used_memory=DEFAULT_MEMORY_FILTER):
        """
        统计redis当前使用情况
        Args:
            show_key: 是否统计每个key的内存
            filter_key_by_used_memory: 根据内存的使用量过滤key 只显示使用量大于指定内存的key

        Returns:

        """
        from prettytable import PrettyTable
        from tqdm import tqdm

        status_msg = ""

        print("正在查询最大连接数...")
        clients_count = self._redis_db.execute_command("info clients")
        max_clients_count = self._redis_db.execute_command("config get maxclients")
        status_msg += ": ".join(max_clients_count) + "\n"
        status_msg += clients_count + "\n"

        print("正在查询整体内存使用情况...")
        total_status = self._redis_db.execute_command("info memory")
        status_msg += total_status + "\n"

        if show_key:
            print("正在查询每个key占用内存情况等信息...")
            table = PrettyTable(
                field_names=[
                    "type",
                    "key",
                    "value_count",
                    "used_memory_human",
                    "used_memory",
                ],
                sortby="used_memory",
                reversesort=True,
                header_style="title",
            )

            keys = self._redis_db.execute_command("keys *")
            for key in tqdm(keys):
                key_type = self._redis_db.execute_command("type {}".format(key))
                if key_type == "set":
                    value_count = self._redis_db.scard(key)
                elif key_type == "zset":
                    value_count = self._redis_db.zcard(key)
                elif key_type == "list":
                    value_count = self._redis_db.llen(key)
                elif key_type == "hash":
                    value_count = self._redis_db.hlen(key)
                elif key_type == "string":
                    value_count = self._redis_db.strlen(key)
                elif key_type == "none":
                    continue
                else:
                    raise TypeError("尚不支持 {} 类型的key".format(key_type))

                used_memory = self._redis_db.execute_command(
                    "memory usage {}".format(key)
                )
                if used_memory >= filter_key_by_used_memory:
                    used_memory_human = (
                        "%0.2fMB" % (used_memory / 1024 / 1024) if used_memory else 0
                    )

                    table.add_row(
                        [key_type, key, value_count, used_memory_human, used_memory]
                    )

            status_msg += str(table)

        return status_msg

    def batch_delete(self, keys: List[str], chunk_size: int = DELETE_CHUNK_SIZE) -> int:
        """
        批量删除keys
        Args:
            keys: 要删除的key列表
            chunk_size: 每批删除的数量
        Returns:
            删除的key数量
        """
        if not keys:
            return 0

        deleted_count = 0
        try:
            # 分批删除,避免一次性删除过多导致阻塞
            for i in range(0, len(keys), chunk_size):
                chunk = keys[i : i + chunk_size]
                deleted_count += self._redis_db.delete(*chunk)
            logger.info(f"批量删除完成,共删除 {deleted_count} 个key")
            return deleted_count
        except Exception as e:
            logger.error(f"批量删除失败: {e}")
            return deleted_count

    def delete_by_pattern(self, pattern: str, chunk_size: int = DELETE_CHUNK_SIZE) -> int:
        """
        根据模式删除keys
        Args:
            pattern: 匹配模式,如 "user:*"
            chunk_size: 每批删除的数量
        Returns:
            删除的key数量
        """
        try:
            keys = self._redis_db.keys(pattern)
            if not keys:
                logger.info(f"未找到匹配模式 '{pattern}' 的key")
                return 0

            logger.info(f"找到 {len(keys)} 个匹配 '{pattern}' 的key,开始删除...")
            return self.batch_delete(keys, chunk_size)
        except Exception as e:
            logger.error(f"按模式删除失败: {e}")
            return 0

    def mget_dict(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量获取多个key的值,返回字典格式
        Args:
            keys: key列表
        Returns:
            {key: value} 字典
        """
        try:
            values = self._redis_db.mget(keys)
            return {k: v for k, v in zip(keys, values) if v is not None}
        except Exception as e:
            logger.error(f"批量获取失败: {e}")
            return {}

    def mset_dict(self, mapping: Dict[str, Any]) -> bool:
        """
        批量设置多个key-value
        Args:
            mapping: {key: value} 字典
        Returns:
            是否成功
        """
        try:
            return self._redis_db.mset(mapping)
        except Exception as e:
            logger.error(f"批量设置失败: {e}")
            return False

    def expire_batch(self, keys: List[str], seconds: int) -> int:
        """
        批量设置过期时间
        Args:
            keys: key列表
            seconds: 过期秒数
        Returns:
            成功设置的数量
        """
        try:
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()

            for key in keys:
                pipe.expire(key, seconds)

            results = pipe.execute()
            success_count = sum(1 for r in results if r)
            logger.info(f"批量设置过期时间完成,成功 {success_count}/{len(keys)}")
            return success_count
        except Exception as e:
            logger.error(f"批量设置过期时间失败: {e}")
            return 0

    def close(self):
        """
        关闭Redis连接
        """
        if self._redis_db:
            self._redis_db.close()
