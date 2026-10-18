# -*- coding: utf-8 -*-
"""Elasticsearch backend — asynchronous implementation."""

from typing import Any, Dict, List, Optional, Union

from ._base import (
    AsyncElasticsearch,
    ESNotFoundError,
    OperationError,
    NotFoundError,
    convert_elastic_error,
    logger,
)


class AsyncElasticImpl:
    """Asynchronous Elasticsearch operations."""

    def __init__(self, es_db):
        self._es_db: AsyncElasticsearch = es_db

    async def aindex(
        self,
        index: str,
        document: Dict[str, Any],
        id: Optional[str] = None,
        refresh: bool = False,
    ):
        """
        @summary: 异步索引文档
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
            return await self._es_db.index(
                index=index, document=document, id=id, refresh=refresh_param
            )
        except Exception as e:
            raise convert_elastic_error(e)

    async def aget(self, index: str, id: str):
        """
        @summary: 异步获取文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 文档内容
        """
        try:
            return await self._es_db.get(index=index, id=id)
        except ESNotFoundError as e:
            raise NotFoundError(f"Document {id} not found in {index}", original_error=e)
        except Exception as e:
            raise convert_elastic_error(e)

    async def asearch(
        self, index: str, query: Dict[str, Any], size: int = 10, from_: int = 0
    ):
        """
        @summary: 异步搜索文档
        ---------
        @param index: 索引名称
        @param query: 查询条件
        @param size: 返回结果数量,默认10
        @param from_: 起始偏移量,默认0
        ---------
        @result: 搜索结果
        """
        try:
            return await self._es_db.search(
                index=index, query=query, size=size, from_=from_
            )
        except Exception as e:
            raise convert_elastic_error(e)

    async def adelete(self, index: str, id: str):
        """
        @summary: 异步删除文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 删除结果
        """
        try:
            return await self._es_db.delete(index=index, id=id)
        except ESNotFoundError as e:
            raise NotFoundError(f"Document {id} not found in {index}", original_error=e)
        except Exception as e:
            raise convert_elastic_error(e)

    async def aupdate(self, index: str, id: str, document: Dict[str, Any]):
        """
        @summary: 异步更新文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        @param document: 更新的文档内容
        ---------
        @result: 更新结果
        """
        try:
            return await self._es_db.update(index=index, id=id, doc=document)
        except ESNotFoundError as e:
            raise NotFoundError(f"Document {id} not found in {index}", original_error=e)
        except Exception as e:
            raise convert_elastic_error(e)

    async def aexists(self, index: str, id: str) -> bool:
        """
        @summary: 异步检查文档是否存在
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 是否存在
        """
        try:
            return await self._es_db.exists(index=index, id=id)
        except Exception as e:
            logger.error(f"Async exists check failed: {e}")
            return False

    async def abulk(self, operations: List[Dict[str, Any]]):
        """
        @summary: 异步批量操作
        ---------
        @param operations: 操作列表
        ---------
        @result: 批量操作结果
        """
        try:
            return await self._es_db.bulk(operations=operations)
        except Exception as e:
            raise convert_elastic_error(e)

    async def aclose(self):
        """
        关闭Elasticsearch异步连接
        """
        if self._es_db:
            await self._es_db.aclose()
