# -*- coding: utf-8 -*-
"""
MongoDB backend — MongoDB factory and public API.

Public API:
    MongoDB  — main entry point (does NOT inherit from BaseStore)
"""

from typing import Any, Dict, List, Optional, Union, Tuple

from bson import ObjectId
from bson.errors import InvalidId

from common.decorators import require_sync, require_async

from ._base import (
    logger,
    OPERATOR_MAPPING,
    convert_mongo_error,
)
from .sync import SyncMongoImpl
from ._async import AsyncMongoImpl


class MongoDB:
    """Unified MongoDB manager supporting both sync and async operations."""

    def __init__(
        self,
        database_url: str,
        database_name: str = None,
        *,
        amode: bool = False,
        min_pool_size: int = 5,
        max_pool_size: int = 50,
        max_idle_time_ms: int = 30000,
        connect_timeout_ms: int = 20000,
        socket_timeout_ms: int = 20000,
        server_selection_timeout_ms: int = 20000,
        wait_queue_timeout_ms: int = 50000,
        retry_writes: bool = True,
        retry_reads: bool = True,
        auto_connect: bool = True,
    ):
        """初始化 MongoManager.

        Args:
            database_url: MongoDB 数据库 URL
            database_name: 数据库名称，如果 URL 中未指定则使用此参数
            amode: 是否使用异步模式
            min_pool_size: 连接池保持的最小连接数
            max_pool_size: 连接池允许的最大连接数
            max_idle_time_ms: 连接在池中的最大空闲时间(毫秒)
            connect_timeout_ms: 连接超时时间(毫秒)
            socket_timeout_ms: socket 超时时间(毫秒)
            server_selection_timeout_ms: 服务器选择超时时间(毫秒)
            wait_queue_timeout_ms: 连接池队列等待超时时间(毫秒)
            retry_writes: 是否自动重试写操作
            retry_reads: 是否自动重试读操作
            auto_connect: 是否自动建立连接

        Examples:
            >>> # 同步模式
            >>> manager = MongoDB("mongodb://localhost:27017/mydb")

            >>> # 异步模式
            >>> manager = MongoDB("mongodb://localhost:27017/mydb", amode=True)
        """
        self._async = amode
        self._database_url = database_url
        self._database_name = database_name

        # 连接池配置
        self._connection_options = {
            "minPoolSize": min_pool_size,
            "maxPoolSize": max_pool_size,
            "maxIdleTimeMS": max_idle_time_ms,
            "connectTimeoutMS": connect_timeout_ms,
            "socketTimeoutMS": socket_timeout_ms,
            "serverSelectionTimeoutMS": server_selection_timeout_ms,
            "waitQueueTimeoutMS": wait_queue_timeout_ms,
            "retryWrites": retry_writes,
            "retryReads": retry_reads,
        }

        # 创建对应的实现类实例
        if amode:
            self._impl = AsyncMongoImpl(self)
        else:
            self._impl = SyncMongoImpl(self)

        if auto_connect:
            self._impl.connect()

    @staticmethod
    def _apply_operator(
        field: str, op: str, value: Any
    ) -> Optional[Dict[str, Any]]:
        """应用操作符到字段上，返回查询条件。

        Args:
            field: 字段名称
            op: 操作符名称
            value: 比较值

        Returns:
            查询条件字典，如果操作符不支持则返回 None
        """
        if op == "eq" or op == "":
            return {field: value}
        if op in OPERATOR_MAPPING:
            return {field: {OPERATOR_MAPPING[op]: value}}
        return None

    @staticmethod
    def build_query(
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """动态构建查询条件。

        支持 AND 逻辑（默认）和 OR 逻辑（当键以 or__ 开头时）。

        Args:
            filters: 过滤条件字典，支持格式:
                - ``{"field": value}`` - 等于
                - ``{"field__op": value}`` - 使用指定操作符
                - ``{"or__": {"field__op": value, ...}}`` - OR 逻辑

        Returns:
            MongoDB 查询条件字典

        Examples:
            >>> MongoDB.build_query({"name": "test"})
            {"name": "test"}

            >>> MongoDB.build_query({"age__gt": 18})
            {"age": {"$gt": 18}}

            >>> MongoDB.build_query({"or__": {"status": "active", "role": "admin"}})
            {"$or": [{"status": "active"}, {"role": "admin"}]}
        """
        if not filters:
            return {}

        query: Dict[str, Any] = {}
        and_conditions: List[Dict[str, Any]] = []
        or_conditions: List[Dict[str, Any]] = []

        for key, value in filters.items():
            if key.startswith("or__"):
                # OR 逻辑: value 应该是一个 {field__op: value} 的字典
                if isinstance(value, dict):
                    for or_key, or_value in value.items():
                        field_name, _, op = or_key.partition("__")
                        op = op or "eq"
                        cond = MongoDB._apply_operator(
                            field_name, op, or_value
                        )
                        if cond:
                            or_conditions.append(cond)
            else:
                field_name, _, op = key.partition("__")
                op = op or "eq"
                cond = MongoDB._apply_operator(field_name, op, value)
                if cond:
                    and_conditions.append(cond)

        # 构建最终查询
        if and_conditions:
            for cond in and_conditions:
                query.update(cond)

        if or_conditions:
            query["$or"] = or_conditions

        return query

    @staticmethod
    def build_sort(
        order_by: Optional[Dict[str, str]] = None,
    ) -> Optional[List[Tuple[str, int]]]:
        """构建排序表达式。

        Args:
            order_by: 排序字典 {field: direction}，direction 为 "asc" 或 "desc"

        Returns:
            MongoDB 排序列表 [(field, direction), ...]
        """
        if not order_by:
            return None
        sort_list = []
        for field, direction in order_by.items():
            sort_dir = -1 if direction.lower() == "desc" else 1
            sort_list.append((field, sort_dir))
        return sort_list

    @staticmethod
    def to_object_id(
        id_value: Union[str, ObjectId, None],
    ) -> Optional[ObjectId]:
        """将字符串 ID 转换为 ObjectId。

        Args:
            id_value: 字符串 ID 或 ObjectId

        Returns:
            ObjectId 对象，如果转换失败则返回 None
        """
        if id_value is None:
            return None
        if isinstance(id_value, ObjectId):
            return id_value
        try:
            return ObjectId(id_value)
        except InvalidId:
            logger.warning(f"无效的 ObjectId: {id_value}")
            return None

    def _get_collection(self, collection_name: str):
        """获取集合对象。

        Args:
            collection_name: 集合名称

        Returns:
            Collection 对象
        """
        return self._impl._get_collection(collection_name)

    # ------------------- 连接管理 -------------------
    async def async_ping(self) -> bool:
        """异步检测连接状态。"""
        if not self._async:
            raise RuntimeError("async_ping 仅在异步模式下可用")
        return await self._impl.ping()

    def ping(self) -> bool:
        """同步检测连接状态。"""
        if self._async:
            raise RuntimeError("ping 仅在同步模式下可用，请使用 async_ping")
        return self._impl.ping()

    def close(self) -> None:
        """关闭 MongoDB 连接。"""
        self._impl.close()

    async def async_close(self) -> None:
        """异步关闭 MongoDB 连接。"""
        if self._async:
            await self._impl.close()
        else:
            self._impl.close()

    # ------------------- 同步 CRUD 操作 -------------------
    @require_sync("insert_one")
    def insert_one(
        self,
        collection_name: str,
        document: Dict[str, Any],
        add_timestamp: bool = False,
    ) -> str:
        """同步插入单个文档。

        Args:
            collection_name: 集合名称
            document: 要插入的文档
            add_timestamp: 是否自动添加时间戳字段

        Returns:
            插入文档的 ID
        """
        return self._impl.insert_one(
            collection_name, document, add_timestamp
        )

    @require_sync("insert_many")
    def insert_many(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        ordered: bool = True,
        add_timestamp: bool = False,
    ) -> List[str]:
        """同步插入多个文档。

        Args:
            collection_name: 集合名称
            documents: 要插入的文档列表
            ordered: 是否按顺序插入（出错时停止）
            add_timestamp: 是否自动添加时间戳字段

        Returns:
            插入文档的 ID 列表
        """
        return self._impl.insert_many(
            collection_name, documents, ordered, add_timestamp
        )

    @require_sync("find_one")
    def find_one(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步查找单个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件（支持操作符语法）
            projection: 投影字段

        Returns:
            查找到的文档，未找到返回 None
        """
        return self._impl.find_one(collection_name, filter, projection)

    @require_sync("find_many")
    def find_many(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """同步查找多个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件（支持操作符语法）
            projection: 投影字段
            order_by: 排序条件 {field: "asc"|"desc"}
            limit: 限制返回数量
            skip: 跳过文档数量

        Returns:
            查找到的文档列表
        """
        return self._impl.find_many(
            collection_name, filter, projection, order_by, limit, skip
        )

    @require_sync("find_by_id")
    def find_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步根据 ID 查找文档。

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID
            projection: 投影字段

        Returns:
            查找到的文档，未找到返回 None
        """
        return self._impl.find_by_id(collection_name, doc_id, projection)

    @require_sync("update_one")
    def update_one(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
    ) -> int:
        """同步更新单个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            update: 更新内容
            upsert: 不存在时是否插入
            add_timestamp: 是否自动更新 updated_at 字段

        Returns:
            更新的文档数量
        """
        return self._impl.update_one(
            collection_name, filter, update, upsert, add_timestamp
        )

    @require_sync("update_many")
    def update_many(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
    ) -> int:
        """同步更新多个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            update: 更新内容
            upsert: 不存在时是否插入
            add_timestamp: 是否自动更新 updated_at 字段

        Returns:
            更新的文档数量
        """
        return self._impl.update_many(
            collection_name, filter, update, upsert, add_timestamp
        )

    @require_sync("update_by_id")
    def update_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
        update: Dict[str, Any],
        add_timestamp: bool = True,
    ) -> int:
        """同步根据 ID 更新文档。

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID
            update: 更新内容
            add_timestamp: 是否自动更新 updated_at 字段

        Returns:
            更新的文档数量
        """
        return self._impl.update_by_id(
            collection_name, doc_id, update, add_timestamp
        )

    @require_sync("delete_one")
    def delete_one(
        self, collection_name: str, filter: Dict[str, Any]
    ) -> int:
        """同步删除单个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            删除的文档数量
        """
        return self._impl.delete_one(collection_name, filter)

    @require_sync("delete_many")
    def delete_many(
        self, collection_name: str, filter: Dict[str, Any]
    ) -> int:
        """同步删除多个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            删除的文档数量
        """
        return self._impl.delete_many(collection_name, filter)

    @require_sync("delete_by_id")
    def delete_by_id(
        self, collection_name: str, doc_id: Union[str, ObjectId]
    ) -> int:
        """同步根据 ID 删除文档。

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID

        Returns:
            删除的文档数量
        """
        return self._impl.delete_by_id(collection_name, doc_id)

    @require_sync("count")
    def count(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """同步统计文档数量。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            文档数量
        """
        return self._impl.count(collection_name, filter)

    @require_sync("exists")
    def exists(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """同步检查文档是否存在。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            是否存在
        """
        return self._impl.exists(collection_name, filter)

    @require_sync("distinct")
    def distinct(
        self,
        collection_name: str,
        field: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """同步获取字段的唯一值列表。

        Args:
            collection_name: 集合名称
            field: 字段名称
            filter: 查询条件

        Returns:
            唯一值列表
        """
        return self._impl.distinct(collection_name, field, filter)

    @require_sync("aggregate")
    def aggregate(
        self,
        collection_name: str,
        pipeline: List[Dict[str, Any]],
        allow_disk_use: bool = True,
    ) -> List[Dict[str, Any]]:
        """同步执行聚合查询。

        Args:
            collection_name: 集合名称
            pipeline: 聚合管道
            allow_disk_use: 是否允许使用磁盘进行排序

        Returns:
            聚合结果列表
        """
        return self._impl.aggregate(
            collection_name, pipeline, allow_disk_use
        )

    @require_sync("paginate")
    def paginate(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """同步分页查询。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            projection: 投影字段
            order_by: 排序条件
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            (数据列表, 总数) 元组
        """
        return self._impl.paginate(
            collection_name, filter, projection, order_by, page, page_size
        )

    @require_sync("bulk_write")
    def bulk_write(
        self,
        collection_name: str,
        operations: List[Any],
        ordered: bool = True,
    ) -> Dict[str, int]:
        """同步批量写入操作。

        Args:
            collection_name: 集合名称
            operations: 批量操作列表
            ordered: 是否按顺序执行

        Returns:
            操作结果统计
        """
        return self._impl.bulk_write(collection_name, operations, ordered)

    @require_sync("find_one_and_update")
    def find_one_and_update(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
        return_document: str = "after",
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步查找并更新文档（原子操作）。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            update: 更新内容
            upsert: 不存在时是否插入
            add_timestamp: 是否自动更新 updated_at 字段
            return_document: 返回更新前的文档("before")还是更新后的文档("after")
            projection: 投影字段

        Returns:
            查找到的文档
        """
        return self._impl.find_one_and_update(
            collection_name,
            filter,
            update,
            upsert,
            add_timestamp,
            return_document,
            projection,
        )

    @require_sync("find_one_and_delete")
    def find_one_and_delete(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步查找并删除文档（原子操作）。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            projection: 投影字段

        Returns:
            被删除的文档
        """
        return self._impl.find_one_and_delete(
            collection_name, filter, projection
        )

    # ------------------- 索引管理 -------------------
    @require_sync("create_index")
    def create_index(
        self,
        collection_name: str,
        keys: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        background: bool = True,
        sparse: bool = False,
        expire_after_seconds: Optional[int] = None,
        name: Optional[str] = None,
    ) -> str:
        """同步创建索引。

        Args:
            collection_name: 集合名称
            keys: 索引键，可以是单个字段名或 [(field, direction), ...] 列表
            unique: 是否唯一索引
            background: 是否后台创建
            sparse: 是否稀疏索引
            expire_after_seconds: TTL 索引的过期时间（秒）
            name: 索引名称

        Returns:
            索引名称
        """
        return self._impl.create_index(
            collection_name,
            keys,
            unique,
            background,
            sparse,
            expire_after_seconds,
            name,
        )

    @require_sync("create_indexes")
    def create_indexes(
        self,
        collection_name: str,
        indexes: List[Dict[str, Any]],
    ) -> List[str]:
        """同步批量创建索引。

        Args:
            collection_name: 集合名称
            indexes: 索引配置列表，每个元素为 {"keys": ..., "options": {...}}

        Returns:
            创建的索引名称列表
        """
        return self._impl.create_indexes(collection_name, indexes)

    @require_sync("drop_index")
    def drop_index(
        self, collection_name: str, index_name: str
    ) -> None:
        """同步删除索引。

        Args:
            collection_name: 集合名称
            index_name: 索引名称
        """
        return self._impl.drop_index(collection_name, index_name)

    @require_sync("list_indexes")
    def list_indexes(
        self, collection_name: str
    ) -> List[Dict[str, Any]]:
        """同步列出所有索引。

        Args:
            collection_name: 集合名称

        Returns:
            索引信息列表
        """
        return self._impl.list_indexes(collection_name)

    # ------------------- 集合管理 -------------------
    @require_sync("list_collections")
    def list_collections(self) -> List[str]:
        """同步列出所有集合名称。

        Returns:
            集合名称列表
        """
        return self._impl.list_collections()

    @require_sync("drop_collection")
    def drop_collection(self, collection_name: str) -> None:
        """同步删除集合。

        Args:
            collection_name: 集合名称
        """
        return self._impl.drop_collection(collection_name)

    @require_sync("rename_collection")
    def rename_collection(
        self,
        collection_name: str,
        new_name: str,
        drop_target: bool = False,
    ) -> None:
        """同步重命名集合。

        Args:
            collection_name: 原集合名称
            new_name: 新集合名称
            drop_target: 如果目标集合存在是否删除
        """
        return self._impl.rename_collection(
            collection_name, new_name, drop_target
        )

    # ------------------- 异步 CRUD 操作 -------------------
    @require_async("insert_one")
    async def async_insert_one(
        self,
        collection_name: str,
        document: Dict[str, Any],
        add_timestamp: bool = False,
    ) -> str:
        """异步插入单个文档。

        Args:
            collection_name: 集合名称
            document: 要插入的文档
            add_timestamp: 是否自动添加时间戳字段

        Returns:
            插入文档的 ID
        """
        return await self._impl.insert_one(
            collection_name, document, add_timestamp
        )

    @require_async("insert_many")
    async def async_insert_many(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        ordered: bool = True,
        add_timestamp: bool = False,
    ) -> List[str]:
        """异步插入多个文档。

        Args:
            collection_name: 集合名称
            documents: 要插入的文档列表
            ordered: 是否按顺序插入
            add_timestamp: 是否自动添加时间戳字段

        Returns:
            插入文档的 ID 列表
        """
        return await self._impl.insert_many(
            collection_name, documents, ordered, add_timestamp
        )

    @require_async("find_one")
    async def async_find_one(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """异步查找单个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            projection: 投影字段

        Returns:
            查找到的文档，未找到返回 None
        """
        return await self._impl.find_one(collection_name, filter, projection)

    @require_async("find_many")
    async def async_find_many(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """异步查找多个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            projection: 投影字段
            order_by: 排序条件
            limit: 限制返回数量
            skip: 跳过文档数量

        Returns:
            查找到的文档列表
        """
        return await self._impl.find_many(
            collection_name, filter, projection, order_by, limit, skip
        )

    @require_async("find_by_id")
    async def async_find_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """异步根据 ID 查找文档。

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID
            projection: 投影字段

        Returns:
            查找到的文档，未找到返回 None
        """
        return await self._impl.find_by_id(
            collection_name, doc_id, projection
        )

    @require_async("update_one")
    async def async_update_one(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
    ) -> int:
        """异步更新单个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            update: 更新内容
            upsert: 不存在时是否插入
            add_timestamp: 是否自动更新 updated_at 字段

        Returns:
            更新的文档数量
        """
        return await self._impl.update_one(
            collection_name, filter, update, upsert, add_timestamp
        )

    @require_async("update_many")
    async def async_update_many(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
    ) -> int:
        """异步更新多个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            update: 更新内容
            upsert: 不存在时是否插入
            add_timestamp: 是否自动更新 updated_at 字段

        Returns:
            更新的文档数量
        """
        return await self._impl.update_many(
            collection_name, filter, update, upsert, add_timestamp
        )

    @require_async("update_by_id")
    async def async_update_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
        update: Dict[str, Any],
        add_timestamp: bool = True,
    ) -> int:
        """异步根据 ID 更新文档。

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID
            update: 更新内容
            add_timestamp: 是否自动更新 updated_at 字段

        Returns:
            更新的文档数量
        """
        return await self._impl.update_by_id(
            collection_name, doc_id, update, add_timestamp
        )

    @require_async("delete_one")
    async def async_delete_one(
        self,
        collection_name: str,
        filter: Dict[str, Any],
    ) -> int:
        """异步删除单个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            删除的文档数量
        """
        return await self._impl.delete_one(collection_name, filter)

    @require_async("delete_many")
    async def async_delete_many(
        self,
        collection_name: str,
        filter: Dict[str, Any],
    ) -> int:
        """异步删除多个文档。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            删除的文档数量
        """
        return await self._impl.delete_many(collection_name, filter)

    @require_async("delete_by_id")
    async def async_delete_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
    ) -> int:
        """异步根据 ID 删除文档。

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID

        Returns:
            删除的文档数量
        """
        return await self._impl.delete_by_id(collection_name, doc_id)

    @require_async("count")
    async def async_count(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """异步统计文档数量。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            文档数量
        """
        return await self._impl.count(collection_name, filter)

    @require_async("exists")
    async def async_exists(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """异步检查文档是否存在。

        Args:
            collection_name: 集合名称
            filter: 查询条件

        Returns:
            是否存在
        """
        return await self._impl.exists(collection_name, filter)

    @require_async("distinct")
    async def async_distinct(
        self,
        collection_name: str,
        field: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """异步获取字段的唯一值列表。

        Args:
            collection_name: 集合名称
            field: 字段名称
            filter: 查询条件

        Returns:
            唯一值列表
        """
        return await self._impl.distinct(collection_name, field, filter)

    @require_async("aggregate")
    async def async_aggregate(
        self,
        collection_name: str,
        pipeline: List[Dict[str, Any]],
        allow_disk_use: bool = True,
    ) -> List[Dict[str, Any]]:
        """异步执行聚合查询。

        Args:
            collection_name: 集合名称
            pipeline: 聚合管道
            allow_disk_use: 是否允许使用磁盘进行排序

        Returns:
            聚合结果列表
        """
        return await self._impl.aggregate(
            collection_name, pipeline, allow_disk_use
        )

    @require_async("paginate")
    async def async_paginate(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """异步分页查询。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            projection: 投影字段
            order_by: 排序条件
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            (数据列表, 总数) 元组
        """
        return await self._impl.paginate(
            collection_name, filter, projection, order_by, page, page_size
        )

    @require_async("bulk_write")
    async def async_bulk_write(
        self,
        collection_name: str,
        operations: List[Any],
        ordered: bool = True,
    ) -> Dict[str, int]:
        """异步批量写入操作。

        Args:
            collection_name: 集合名称
            operations: 批量操作列表
            ordered: 是否按顺序执行

        Returns:
            操作结果统计
        """
        return await self._impl.bulk_write(
            collection_name, operations, ordered
        )

    @require_async("find_one_and_update")
    async def async_find_one_and_update(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
        return_document: str = "after",
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """异步查找并更新文档（原子操作）。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            update: 更新内容
            upsert: 不存在时是否插入
            add_timestamp: 是否自动更新 updated_at 字段
            return_document: 返回更新前("before")还是更新后("after")的文档
            projection: 投影字段

        Returns:
            查找到的文档
        """
        return await self._impl.find_one_and_update(
            collection_name,
            filter,
            update,
            upsert,
            add_timestamp,
            return_document,
            projection,
        )

    @require_async("find_one_and_delete")
    async def async_find_one_and_delete(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """异步查找并删除文档（原子操作）。

        Args:
            collection_name: 集合名称
            filter: 查询条件
            projection: 投影字段

        Returns:
            被删除的文档
        """
        return await self._impl.find_one_and_delete(
            collection_name, filter, projection
        )

    # ------------------- 异步索引管理 -------------------
    @require_async("create_index")
    async def async_create_index(
        self,
        collection_name: str,
        keys: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        background: bool = True,
        sparse: bool = False,
        expire_after_seconds: Optional[int] = None,
        name: Optional[str] = None,
    ) -> str:
        """异步创建索引。

        Args:
            collection_name: 集合名称
            keys: 索引键
            unique: 是否唯一索引
            background: 是否后台创建
            sparse: 是否稀疏索引
            expire_after_seconds: TTL 索引的过期时间（秒）
            name: 索引名称

        Returns:
            索引名称
        """
        return await self._impl.create_index(
            collection_name,
            keys,
            unique,
            background,
            sparse,
            expire_after_seconds,
            name,
        )

    @require_async("drop_index")
    async def async_drop_index(
        self, collection_name: str, index_name: str
    ) -> None:
        """异步删除索引。

        Args:
            collection_name: 集合名称
            index_name: 索引名称
        """
        return await self._impl.drop_index(collection_name, index_name)

    @require_async("create_indexes")
    async def async_create_indexes(
        self,
        collection_name: str,
        indexes: List[Dict[str, Any]],
    ) -> List[str]:
        """异步批量创建索引。

        Args:
            collection_name: 集合名称
            indexes: 索引配置列表，每个元素为 {"keys": ..., "options": {...}}

        Returns:
            创建的索引名称列表
        """
        return await self._impl.create_indexes(collection_name, indexes)

    @require_async("list_indexes")
    async def async_list_indexes(
        self, collection_name: str
    ) -> List[Dict[str, Any]]:
        """异步列出所有索引。

        Args:
            collection_name: 集合名称

        Returns:
            索引信息列表
        """
        return await self._impl.list_indexes(collection_name)

    # ------------------- 异步集合管理 -------------------
    @require_async("list_collections")
    async def async_list_collections(self) -> List[str]:
        """异步列出所有集合名称。

        Returns:
            集合名称列表
        """
        return await self._impl.list_collections()

    @require_async("drop_collection")
    async def async_drop_collection(
        self, collection_name: str
    ) -> None:
        """异步删除集合。

        Args:
            collection_name: 集合名称
        """
        return await self._impl.drop_collection(collection_name)
