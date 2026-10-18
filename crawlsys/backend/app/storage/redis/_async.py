# -*- coding: utf-8 -*-
"""Redis storage backend — asynchronous implementation."""

from redis.asyncio import Redis as AsyncRedis

from ._base import logger, convert_redis_error


class AsyncRedisImpl:
    """异步实现类"""

    def __init__(self, redis_db):
        self._redis_db: AsyncRedis = redis_db

    # ==================== Set 操作 ====================
    async def asadd(self, table, values):
        """
        @summary: 异步使用无序set集合存储数据， 去重
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
            await pipe.execute()
        else:
            return await self._redis_db.sadd(table, values)

    async def asget(self, table, count=1, is_pop=True):
        """
        异步返回 list 如 ['1'] 或 []
        @param table:
        @param count:
        @param is_pop:
        @return:
        """
        datas = []
        if is_pop:
            sget_count = await self.asget_count(table)
            count = count if count <= sget_count else sget_count
            if count:
                if count > 1:
                    pipe = self._redis_db.pipeline()
                    if not self._redis_db._is_redis_cluster:
                        pipe.multi()
                    while count:
                        pipe.spop(table)
                        count -= 1
                    datas = await pipe.execute()
                else:
                    datas.append(await self._redis_db.spop(table))
        else:
            datas = await self._redis_db.srandmember(table, count)
        return datas

    async def asget_count(self, table):
        return await self._redis_db.scard(table)

    # 别名，保持向后兼容
    sadd = asadd
    sget = asget
    sget_count = asget_count

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
                return await self._redis_db.zadd(table, mapping)
            except (TypeError, AttributeError):
                # 降级到旧版本的实现方式 (Redis 版本不支持 mapping 参数)
                pipe = self._redis_db.pipeline()
                if not self._redis_db._is_redis_cluster:
                    pipe.multi()
                for value, priority in zip(values, prioritys):
                    pipe.execute_command("ZADD", table, priority, value)
                return await pipe.execute()
        else:
            return await self._redis_db.execute_command(
                "ZADD", table, prioritys, values
            )

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
        start_pos = 0  # 包含
        end_pos = count - 1 if count > 0 else count

        pipe = self._redis_db.pipeline()

        if not self._redis_db._is_redis_cluster:
            pipe.multi()  # 标记事务的开始 参考 http://www.runoob.com/redis/redis-transactions.html
        pipe.zrange(table, start_pos, end_pos)  # 取值
        if is_pop:
            pipe.zremrangebyrank(table, start_pos, end_pos)  # 删除
        results, *count = await pipe.execute()
        return results

    # 别名，保持向后兼容
    zadd = azadd
    zget = azget

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
        return await self._redis_db.hset(table, key, value)

    async def ahget(self, table, key, is_pop=False):
        if not is_pop:
            return await self._redis_db.hget(table, key)
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
            res = await cmd(keys=[table], args=[key])
            return res

    # 别名，保持向后兼容
    hset = ahset
    hget = ahget

    async def ahgetall(self, table):
        """异步获取哈希表所有字段和值"""
        return await self._redis_db.hgetall(table)

    # 别名，保持向后兼容
    hgetall = ahgetall

    async def ahexists(self, table, key):
        """异步检查哈希表字段是否存在"""
        return await self._redis_db.hexists(table, key)

    # 别名，保持向后兼容
    hexists = ahexists

    async def ahdel(self, table, *keys):
        """异步删除哈希表字段"""
        return await self._redis_db.hdel(table, *keys)

    # 别名，保持向后兼容
    hdel = ahdel

    async def ahget_count(self, table):
        """异步获取哈希表字段数量"""
        return await self._redis_db.hlen(table)

    # 别名，保持向后兼容
    hget_count = ahget_count

    async def ahkeys(self, table):
        """异步获取哈希表所有字段"""
        return await self._redis_db.hkeys(table)

    # 别名，保持向后兼容
    hkeys = ahkeys

    async def ahvals(self, table):
        """异步获取哈希表所有值"""
        return await self._redis_db.hvals(table)

    # 别名，保持向后兼容
    hvals = ahvals

    async def ahset_batch(self, table, datas):
        """
        异步批量插入哈希表
        Args:
            table:
            datas: [[key, value]]
        Returns:
        """
        pipe = self._redis_db.pipeline()
        if not self._redis_db._is_redis_cluster:
            pipe.multi()
        for key, value in datas:
            pipe.hset(table, key, value)
        return await pipe.execute()

    # 别名，保持向后兼容
    hset_batch = ahset_batch

    async def ahincrby(self, table, key, increment):
        """异步为哈希表字段增加整数值"""
        return await self._redis_db.hincrby(table, key, increment)

    # 别名，保持向后兼容
    hincrby = ahincrby

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
        return await self._redis_db.set(table, value, **kwargs)

    async def astrget(self, table):
        return await self._redis_db.get(table)

    async def amget(self, keys):
        return await self._redis_db.mget(keys)

    # 别名，保持向后兼容
    strset = astrset
    strget = astrget

    async def alrange(self, table, start=0, end=-1):
        """
        异步获取列表指定范围内的元素
        @param table:
        @param start: 起始位置，0 表示第一个元素，-1 表示最后一个元素
        @param end: 结束位置，-1 表示最后一个元素
        @return: 指定范围内的元素列表
        """
        return await self._redis_db.lrange(table, start, end)

    # 别名，保持向后兼容
    lrange = alrange

    async def alpush(self, table, values):
        """
        异步将值推入列表左侧
        @param table:
        @param values: 值，支持 list 或单个值
        @return:
        """
        if isinstance(values, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.lpush(table, value)
            await pipe.execute()
        else:
            return await self._redis_db.lpush(table, values)

    # 别名，保持向后兼容
    lpush = alpush

    async def alpop(self, table, count=1):
        """
        异步从列表左侧弹出元素
        @param table:
        @param count:
        @return: count>1 时返回列表
        """
        lcount = await self._redis_db.llen(table)
        count = count if count <= lcount else lcount

        datas = None
        if count:
            if count > 1:
                pipe = self._redis_db.pipeline()
                if not self._redis_db._is_redis_cluster:
                    pipe.multi()
                while count:
                    pipe.lpop(table)
                    count -= 1
                datas = await pipe.execute()
            else:
                datas = await self._redis_db.lpop(table)
        return datas

    # 别名，保持向后兼容
    lpop = alpop

    async def alget_count(self, table):
        """异步获取列表长度"""
        return await self._redis_db.llen(table)

    # 别名，保持向后兼容
    lget_count = alget_count

    async def alrem(self, table, value, num=0):
        """
        异步删除列表中的值
        @param table:
        @param value:
        @param num:
        @return: 删除的条数
        """
        return await self._redis_db.lrem(table, num, value)

    # 别名，保持向后兼容
    lrem = alrem

    async def asrem(self, table, values):
        """异步移除集合中的指定元素"""
        if isinstance(values, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.srem(table, value)
            await pipe.execute()
        else:
            await self._redis_db.srem(table, values)

    # 别名，保持向后兼容
    srem = asrem

    async def asismember(self, table, key):
        """异步检查成员是否在集合中"""
        return await self._redis_db.sismember(table, key)

    # 别名，保持向后兼容
    sismember = asismember

    async def azget_count(self, table, priority_min=None, priority_max=None):
        """异步获取有序集合数据数量"""
        if priority_min is not None and priority_max is not None:
            return await self._redis_db.zcount(table, priority_min, priority_max)
        else:
            return await self._redis_db.zcard(table)

    # 别名，保持向后兼容
    zget_count = azget_count

    async def azrem(self, table, values):
        """异步移除集合中的指定元素"""
        if isinstance(values, list):
            await self._redis_db.zrem(table, *values)
        else:
            await self._redis_db.zrem(table, values)

    # 别名，保持向后兼容
    zrem = azrem

    async def azexists(self, table, values):
        """异步检查元素是否存在"""
        if isinstance(values, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for value in values:
                pipe.zscore(table, value)
            is_exists_temp = await pipe.execute()
            is_exists = []
            for is_exist in is_exists_temp:
                if is_exist is not None:
                    is_exists.append(1)
                else:
                    is_exists.append(0)
            return is_exists
        else:
            is_exists = await self._redis_db.zscore(table, values)
            return 1 if is_exists is not None else 0

    # 别名，保持向后兼容
    zexists = azexists

    async def astr_incrby(self, table, value):
        """异步为字符串值增加整数"""
        return await self._redis_db.incrby(table, value)

    # 别名，保持向后兼容
    str_incrby = astr_incrby

    async def astrlen(self, table):
        """异步获取字符串长度"""
        return await self._redis_db.strlen(table)

    # 别名，保持向后兼容
    strlen = astrlen

    async def agetkeys(self, regex):
        """异步获取匹配模式的 keys"""
        return await self._redis_db.keys(regex)

    # 别名，保持向后兼容
    getkeys = agetkeys

    async def aexists_key(self, key):
        """异步检查 key 是否存在"""
        return await self._redis_db.exists(key)

    # 别名，保持向后兼容
    exists_key = aexists_key

    async def aset_expire(self, key, seconds):
        """异步设置过期时间"""
        await self._redis_db.expire(key, seconds)

    # 别名，保持向后兼容
    set_expire = aset_expire

    async def aget_expire(self, key):
        """异步获取过期时间"""
        return await self._redis_db.ttl(key)

    # 别名，保持向后兼容
    get_expire = aget_expire

    async def aclear(self, table):
        """异步删除指定的 key"""
        await self._redis_db.delete(table)

    # 别名，保持向后兼容
    clear = aclear

    async def asetbit(self, table, offsets, values):
        """异步设置字符串数组某一位的值"""
        if isinstance(offsets, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            if isinstance(values, int):
                for offset in offsets:
                    pipe.setbit(table, offset, values)
            else:
                assert len(offsets) == len(values), "offsets 值要与 values 值一一对应"
                for offset, value in zip(offsets, values):
                    pipe.setbit(table, offset, value)
            return await pipe.execute()
        else:
            return await self._redis_db.setbit(table, offsets, values)

    # 别名，保持向后兼容
    setbit = asetbit

    async def agetbit(self, table, offsets):
        """异步取字符串数组某一位的值"""
        if isinstance(offsets, list):
            pipe = self._redis_db.pipeline()
            if not self._redis_db._is_redis_cluster:
                pipe.multi()
            for offset in offsets:
                pipe.getbit(table, offset)
            return await pipe.execute()
        else:
            return await self._redis_db.getbit(table, offsets)

    # 别名，保持向后兼容
    getbit = agetbit

    async def abitcount(self, table):
        """异步计算字符串中 1 的数量"""
        return await self._redis_db.bitcount(table)

    # 别名，保持向后兼容
    bitcount = abitcount

    async def arpoplpush(self, from_table, to_table=None):
        """异步将列表尾元素弹出并推入另一个列表头部"""
        if not to_table:
            to_table = from_table
        return await self._redis_db.rpoplpush(from_table, to_table)

    # 别名，保持向后兼容
    rpoplpush = arpoplpush

    def get_redis_obj(self):
        """获取由 RedisDB 管理生命周期的原始异步 Redis 客户端。"""
        return self._redis_db

    async def aclose(self):
        """
        关闭Redis连接
        """
        if self._redis_db:
            await self._redis_db.aclose()
