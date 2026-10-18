# -*- coding: utf-8 -*-
"""Elasticsearch backend — synchronous implementation."""

import time
from typing import Any, Dict, List, Optional, Union

from ._base import (
    Elasticsearch,
    ESNotFoundError,
    OperationError,
    NotFoundError,
    convert_elastic_error,
    logger,
)


class SyncElasticImpl:
    """Synchronous Elasticsearch operations."""

    def __init__(self, es_db: Elasticsearch):
        self._es_db = es_db

    def index(
        self,
        index: str,
        document: Dict[str, Any],
        id: Optional[str] = None,
        refresh: bool = False,
    ):
        """
        @summary: 索引文档
        ---------
        @param index: 索引名称
        @param document: 文档内容
        @param id: 文档ID,可选
        @param refresh: 是否立即刷新,默认False
        ---------
        @result: 索引结果
        """
        try:
            refresh_param = "true" if refresh else "false"
            return self._es_db.index(
                index=index, document=document, id=id, refresh=refresh_param
            )
        except Exception as e:
            raise convert_elastic_error(e)

    def get(self, index: str, id: str):
        """
        @summary: 获取文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 文档内容
        """
        try:
            return self._es_db.get(index=index, id=id)
        except ESNotFoundError as e:
            raise NotFoundError(f"Document {id} not found in {index}", original_error=e)
        except Exception as e:
            raise convert_elastic_error(e)

    def search(self, index: str, query: Dict[str, Any], size: int = 10, from_: int = 0):
        """
        @summary: 搜索文档
        ---------
        @param index: 索引名称
        @param query: 查询条件
        @param size: 返回结果数量,默认10
        @param from_: 起始偏移量,默认0
        ---------
        @result: 搜索结果
        """
        try:
            return self._es_db.search(index=index, query=query, size=size, from_=from_)
        except Exception as e:
            raise convert_elastic_error(e)

    def delete(self, index: str, id: str):
        """
        @summary: 删除文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 删除结果
        """
        try:
            return self._es_db.delete(index=index, id=id)
        except ESNotFoundError as e:
            raise NotFoundError(f"Document {id} not found in {index}", original_error=e)
        except Exception as e:
            raise convert_elastic_error(e)

    def update(self, index: str, id: str, document: Dict[str, Any]):
        """
        @summary: 更新文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        @param document: 更新的文档内容
        ---------
        @result: 更新结果
        """
        try:
            return self._es_db.update(index=index, id=id, doc=document)
        except ESNotFoundError as e:
            raise NotFoundError(f"Document {id} not found in {index}", original_error=e)
        except Exception as e:
            raise convert_elastic_error(e)

    def exists(self, index: str, id: str) -> bool:
        """
        @summary: 检查文档是否存在
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 是否存在
        """
        try:
            return self._es_db.exists(index=index, id=id)
        except Exception as e:
            logger.error(f"Exists check failed: {e}")
            return False

    def bulk(self, operations: List[Dict[str, Any]]):
        """
        @summary: 批量操作
        ---------
        @param operations: 操作列表
        ---------
        @result: 批量操作结果
        """
        try:
            return self._es_db.bulk(operations=operations)
        except Exception as e:
            raise convert_elastic_error(e)

    def count(self, index: str, query: Optional[Dict[str, Any]] = None) -> int:
        """
        @summary: 统计文档数量
        ---------
        @param index: 索引名称
        @param query: 查询条件,可选
        ---------
        @result: 文档数量
        """
        try:
            if query:
                return self._es_db.count(index=index, query=query)
            return self._es_db.count(index=index)
        except Exception as e:
            raise convert_elastic_error(e)

    def scroll(self, scroll_id: str, scroll: str = "1m"):
        """
        @summary: 滚动查询
        ---------
        @param scroll_id: 滚动ID
        @param scroll: 滚动保持时间,默认1分钟
        ---------
        @result: 滚动结果
        """
        try:
            return self._es_db.scroll(scroll_id=scroll_id, scroll=scroll)
        except Exception as e:
            raise convert_elastic_error(e)

    def clear_scroll(self, scroll_id: Optional[str] = None):
        """
        @summary: 清除滚动上下文
        ---------
        @param scroll_id: 滚动ID,可选,不传则清除所有
        ---------
        @result: 清除结果
        """
        try:
            return self._es_db.clear_scroll(scroll_id=scroll_id)
        except Exception as e:
            raise convert_elastic_error(e)

    def get_es_obj(self):
        """获取原始Elasticsearch对象"""
        return self._es_db

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查,返回Elasticsearch连接状态信息
        Returns:
            包含连接状态、延迟等信息的字典
        """
        try:
            start_time = time.time()
            cluster_info = self._es_db.cluster.health()
            latency = (time.time() - start_time) * 1000  # 转换为毫秒

            return {
                "status": cluster_info.get("status", "unknown"),
                "cluster_name": cluster_info.get("cluster_name", "unknown"),
                "number_of_nodes": cluster_info.get("number_of_nodes", 0),
                "active_shards": cluster_info.get("active_shards", 0),
                "latency_ms": round(latency, 2),
                "connected": True,
            }
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {"status": "error", "error": str(e), "connected": False}

    def close(self):
        """
        关闭Elasticsearch连接
        """
        if self._es_db:
            self._es_db.close()
