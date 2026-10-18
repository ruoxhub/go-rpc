# -*- coding: utf-8 -*-
"""MongoDB backend — synchronous implementation."""

from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, timezone

from bson import ObjectId

from ._base import logger, OPERATOR_MAPPING, convert_mongo_error


class SyncMongoImpl:
    """同步实现类 - 封装所有同步 MongoDB 操作"""

    def __init__(self, manager):
        """初始化同步实现

        Args:
            manager: MongoDB 管理器实例
        """
        self._manager = manager
        self._client = None
        self._db = None

    def connect(self) -> None:
        """建立同步 MongoDB 连接"""
        try:
            from pymongo import MongoClient

            self._client = MongoClient(
                self._manager._database_url,
                **self._manager._connection_options
            )
            # 验证连接
            self._client.server_info()

            # 获取数据库
            if self._manager._database_name:
                self._db = self._client[self._manager._database_name]
            else:
                self._db = self._client.get_default_database()

            logger.info(
                f"同步MongoDB连接已建立: {self._manager._database_url} "
                f"(pool: {self._manager._connection_options['minPoolSize']}-"
                f"{self._manager._connection_options['maxPoolSize']})"
            )
        except Exception as e:
            logger.error(f"同步MongoDB连接失败: {e}")
            raise

    def close(self) -> None:
        """关闭同步 MongoDB 连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("同步MongoDB连接已关闭")

    def ping(self) -> bool:
        """检测同步连接状态"""
        try:
            self._client.admin.command('ping')
            return True
        except Exception as e:
            logger.warning(f"MongoDB ping 失败: {e}")
            return False

    def _get_collection(self, collection_name: str):
        """获取集合对象"""
        if self._db is None:
            self.connect()
        return self._db[collection_name]

    # CRUD 操作
    def insert_one(
        self,
        collection_name: str,
        document: Dict[str, Any],
        add_timestamp: bool = False,
    ) -> str:
        """同步插入单个文档"""
        try:
            if add_timestamp:
                now = datetime.now(timezone.utc)
                document = {**document, 'created_at': now, 'updated_at': now}

            collection = self._get_collection(collection_name)
            result = collection.insert_one(document)
            logger.debug(f"成功插入文档到 {collection_name}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"插入文档失败: {e}")
            raise convert_mongo_error(e) from e

    def insert_many(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        ordered: bool = True,
        add_timestamp: bool = False,
    ) -> List[str]:
        """同步插入多个文档"""
        if not documents:
            return []
        try:
            if add_timestamp:
                now = datetime.now(timezone.utc)
                documents = [
                    {**doc, 'created_at': now, 'updated_at': now}
                    for doc in documents
                ]

            collection = self._get_collection(collection_name)
            result = collection.insert_many(documents, ordered=ordered)
            logger.debug(
                f"成功插入 {len(documents)} 个文档到 {collection_name}"
            )
            return [str(id) for id in result.inserted_ids]
        except Exception as e:
            logger.error(f"批量插入文档失败: {e}")
            raise convert_mongo_error(e) from e

    def find_one(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步查找单个文档"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            return collection.find_one(query, projection)
        except Exception as e:
            logger.error(f"查找文档失败: {e}")
            raise convert_mongo_error(e) from e

    def find_many(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """同步查找多个文档"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)

            cursor = collection.find(query, projection)

            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)

            sort_list = MongoDB.build_sort(order_by)
            if sort_list:
                cursor = cursor.sort(sort_list)

            return list(cursor)
        except Exception as e:
            logger.error(f"查找文档失败: {e}")
            raise convert_mongo_error(e) from e

    def find_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步根据 ID 查找文档"""
        try:
            from . import MongoDB
            oid = MongoDB.to_object_id(doc_id)
            if oid is None:
                return None
            collection = self._get_collection(collection_name)
            return collection.find_one({"_id": oid}, projection)
        except Exception as e:
            logger.error(f"根据ID查找文档失败: {e}")
            raise convert_mongo_error(e) from e

    def update_one(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
    ) -> int:
        """同步更新单个文档"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)

            # 确保使用 $set 操作符（不修改原始参数）
            final_update = update
            if not any(key.startswith('$') for key in update.keys()):
                final_update = {"$set": update}

            # 添加更新时间
            if add_timestamp:
                if '$set' not in final_update:
                    final_update['$set'] = {}
                final_update['$set']['updated_at'] = datetime.now(timezone.utc)

            collection = self._get_collection(collection_name)
            result = collection.update_one(query, final_update, upsert=upsert)
            return result.modified_count
        except Exception as e:
            logger.error(f"更新文档失败: {e}")
            raise convert_mongo_error(e) from e

    def update_many(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        add_timestamp: bool = True,
    ) -> int:
        """同步更新多个文档"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)

            # 确保使用 $set 操作符（不修改原始参数）
            final_update = update
            if not any(key.startswith('$') for key in update.keys()):
                final_update = {"$set": update}

            # 添加更新时间
            if add_timestamp:
                if '$set' not in final_update:
                    final_update['$set'] = {}
                final_update['$set']['updated_at'] = datetime.now(timezone.utc)

            collection = self._get_collection(collection_name)
            result = collection.update_many(query, final_update, upsert=upsert)
            return result.modified_count
        except Exception as e:
            logger.error(f"批量更新文档失败: {e}")
            raise convert_mongo_error(e) from e

    def update_by_id(
        self,
        collection_name: str,
        doc_id: Union[str, ObjectId],
        update: Dict[str, Any],
        add_timestamp: bool = True,
    ) -> int:
        """同步根据 ID 更新文档"""
        from . import MongoDB
        oid = MongoDB.to_object_id(doc_id)
        if oid is None:
            return 0
        return self.update_one(
            collection_name,
            {"_id": oid},
            update,
            add_timestamp=add_timestamp,
        )

    def delete_one(self, collection_name: str, filter: Dict[str, Any]) -> int:
        """同步删除单个文档"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            result = collection.delete_one(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            raise convert_mongo_error(e) from e

    def delete_many(self, collection_name: str, filter: Dict[str, Any]) -> int:
        """同步删除多个文档"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            result = collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"批量删除文档失败: {e}")
            raise convert_mongo_error(e) from e

    def delete_by_id(
        self, collection_name: str, doc_id: Union[str, ObjectId]
    ) -> int:
        """同步根据 ID 删除文档"""
        from . import MongoDB
        oid = MongoDB.to_object_id(doc_id)
        if oid is None:
            return 0
        return self.delete_one(collection_name, {"_id": oid})

    def count(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """同步统计文档数量"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            return collection.count_documents(query)
        except Exception as e:
            logger.error(f"统计文档失败: {e}")
            raise convert_mongo_error(e) from e

    def exists(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """同步检查文档是否存在"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            return collection.find_one(query, projection={"_id": 1}) is not None
        except Exception as e:
            logger.error(f"检查文档存在性失败: {e}")
            raise convert_mongo_error(e) from e

    def distinct(
        self,
        collection_name: str,
        field: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """同步获取字段的唯一值列表"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            return collection.distinct(field, query)
        except Exception as e:
            logger.error(f"获取唯一值失败: {e}")
            raise convert_mongo_error(e) from e

    def aggregate(
        self,
        collection_name: str,
        pipeline: List[Dict[str, Any]],
        allow_disk_use: bool = True,
    ) -> List[Dict[str, Any]]:
        """同步执行聚合查询"""
        try:
            collection = self._get_collection(collection_name)
            cursor = collection.aggregate(
                pipeline, allowDiskUse=allow_disk_use
            )
            return list(cursor)
        except Exception as e:
            logger.error(f"聚合查询失败: {e}")
            raise convert_mongo_error(e) from e

    def paginate(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """同步分页查询"""
        try:
            total = self.count(collection_name, filter)
            skip = (page - 1) * page_size
            items = self.find_many(
                collection_name,
                filter=filter,
                projection=projection,
                order_by=order_by,
                limit=page_size,
                skip=skip,
            )
            return items, total
        except Exception as e:
            logger.error(f"分页查询失败: {e}")
            raise convert_mongo_error(e) from e

    def bulk_write(
        self,
        collection_name: str,
        operations: List[Any],
        ordered: bool = True,
    ) -> Dict[str, int]:
        """同步批量写入操作"""
        try:
            collection = self._get_collection(collection_name)
            result = collection.bulk_write(operations, ordered=ordered)
            return {
                "inserted": result.inserted_count,
                "matched": result.matched_count,
                "modified": result.modified_count,
                "deleted": result.deleted_count,
                "upserted": result.upserted_count,
            }
        except Exception as e:
            logger.error(f"批量写入失败: {e}")
            raise convert_mongo_error(e) from e

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
        """同步查找并更新文档（原子操作）"""
        try:
            from pymongo import ReturnDocument
            from . import MongoDB

            query = MongoDB.build_query(filter)

            # 确保使用 $set 操作符（不修改原始参数）
            final_update = update
            if not any(key.startswith('$') for key in update.keys()):
                final_update = {"$set": update}

            # 添加更新时间
            if add_timestamp:
                if '$set' not in final_update:
                    final_update['$set'] = {}
                final_update['$set']['updated_at'] = datetime.now(timezone.utc)

            return_doc = (
                ReturnDocument.AFTER
                if return_document == "after"
                else ReturnDocument.BEFORE
            )

            collection = self._get_collection(collection_name)
            return collection.find_one_and_update(
                query,
                final_update,
                upsert=upsert,
                return_document=return_doc,
                projection=projection,
            )
        except Exception as e:
            logger.error(f"查找并更新失败: {e}")
            raise convert_mongo_error(e) from e

    def find_one_and_delete(
        self,
        collection_name: str,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """同步查找并删除文档（原子操作）"""
        try:
            from . import MongoDB
            query = MongoDB.build_query(filter)
            collection = self._get_collection(collection_name)
            return collection.find_one_and_delete(query, projection=projection)
        except Exception as e:
            logger.error(f"查找并删除失败: {e}")
            raise convert_mongo_error(e) from e

    # 索引管理
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
        """同步创建索引"""
        try:
            collection = self._get_collection(collection_name)

            options = {
                "unique": unique,
                "background": background,
                "sparse": sparse,
            }

            if expire_after_seconds is not None:
                options["expireAfterSeconds"] = expire_after_seconds
            if name:
                options["name"] = name

            return collection.create_index(keys, **options)
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            raise convert_mongo_error(e) from e

    def create_indexes(
        self,
        collection_name: str,
        indexes: List[Dict[str, Any]],
    ) -> List[str]:
        """同步批量创建索引"""
        try:
            from pymongo import IndexModel

            collection = self._get_collection(collection_name)
            index_models = [
                IndexModel(idx["keys"], **idx.get("options", {}))
                for idx in indexes
            ]
            return collection.create_indexes(index_models)
        except Exception as e:
            logger.error(f"批量创建索引失败: {e}")
            raise convert_mongo_error(e) from e

    def drop_index(self, collection_name: str, index_name: str) -> None:
        """同步删除索引"""
        try:
            collection = self._get_collection(collection_name)
            collection.drop_index(index_name)
            logger.info(f"成功删除索引 {index_name}")
        except Exception as e:
            logger.error(f"删除索引失败: {e}")
            raise convert_mongo_error(e) from e

    def list_indexes(
        self, collection_name: str
    ) -> List[Dict[str, Any]]:
        """同步列出所有索引"""
        try:
            collection = self._get_collection(collection_name)
            return list(collection.list_indexes())
        except Exception as e:
            logger.error(f"列出索引失败: {e}")
            raise convert_mongo_error(e) from e

    # 集合管理
    def list_collections(self) -> List[str]:
        """同步列出所有集合名称"""
        try:
            return self._db.list_collection_names()
        except Exception as e:
            logger.error(f"列出集合失败: {e}")
            raise convert_mongo_error(e) from e

    def drop_collection(self, collection_name: str) -> None:
        """同步删除集合"""
        try:
            self._db.drop_collection(collection_name)
            logger.info(f"成功删除集合 {collection_name}")
        except Exception as e:
            logger.error(f"删除集合失败: {e}")
            raise convert_mongo_error(e) from e

    def rename_collection(
        self,
        collection_name: str,
        new_name: str,
        drop_target: bool = False,
    ) -> None:
        """同步重命名集合"""
        try:
            collection = self._get_collection(collection_name)
            collection.rename(new_name, dropTarget=drop_target)
            logger.info(
                f"成功将集合 {collection_name} 重命名为 {new_name}"
            )
        except Exception as e:
            logger.error(f"重命名集合失败: {e}")
            raise convert_mongo_error(e) from e
