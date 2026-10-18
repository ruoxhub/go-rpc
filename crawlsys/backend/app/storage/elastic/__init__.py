# -*- coding: utf-8 -*-
"""
Elasticsearch backend — ElasticDB factory and connection management.

Public API:
    ElasticDB   — main entry point (subclass of BaseStore)
"""

from typing import Any, Dict, List, Optional, Union

from storage.base import BaseStore
from storage.exceptions import ConfigurationError

from ._base import (
    Elasticsearch,
    AsyncElasticsearch,
    convert_elastic_error,
    logger,
)
from .sync import SyncElasticImpl
from ._async import AsyncElasticImpl


class ElasticDB(BaseStore):
    """
    Elasticsearch的封装
    """

    def __init__(
        self,
        hosts: Union[str, List[str]],
        *,
        amode: bool = False,
        **kwargs,
    ):
        """
        初始化Elasticsearch客户端
        Args:
            hosts: Elasticsearch主机地址,可以是字符串或列表
            amode: 是否使用异步模式
            **kwargs: 其他Elasticsearch连接参数
        """
        super().__init__(amode=amode, **kwargs)

        if not Elasticsearch:
            raise ConfigurationError(
                "elasticsearch is not installed. Run: pip install elasticsearch"
            )

        self._hosts = hosts
        self._kwargs = kwargs or {}
        self._amode = amode

        # 初始化连接状态
        self._connected = False

        # 初始化Elasticsearch连接
        try:
            if amode:
                if not AsyncElasticsearch:
                    raise ConfigurationError(
                        "AsyncElasticsearch is not available. Please install elasticsearch>=8.0"
                    )
                self.__client = AsyncElasticsearch(hosts=self._hosts, **self._kwargs)
                self._impl = AsyncElasticImpl(self.__client)
                # 异步模式下的连接测试将在首次使用时进行
                logger.info(f"Elasticsearch异步客户端初始化完成: {self._hosts}")
                self._connected = True
            else:
                self.__client = Elasticsearch(hosts=self._hosts, **self._kwargs)
                self._impl = SyncElasticImpl(self.__client)
                # 测试同步连接
                self.__client.ping()
                self._connected = True
                logger.info(f"Elasticsearch连接成功: {self._hosts}")
        except Exception as e:
            logger.error(f"Elasticsearch初始化失败: {e}")
            raise

    # BaseStore 抽象方法实现
    def connect(self):
        """建立同步连接"""
        try:
            self.__client.ping()
            self._connected = True
            logger.info(f"Elasticsearch同步连接建立成功: {self._hosts}")
        except Exception as e:
            logger.error(f"Elasticsearch同步连接失败: {e}")
            raise

    async def async_connect(self):
        """建立异步连接"""
        try:
            # 使用 ping 命令测试连接
            await self.__client.ping()
            self._connected = True
            logger.info(f"Elasticsearch异步连接建立成功: {self._hosts}")
        except Exception as e:
            logger.error(f"Elasticsearch异步连接失败: {e}")
            raise

    def close(self):
        """关闭同步连接"""
        try:
            if self.__client:
                self.__client.close()
                self._connected = False
                logger.info("Elasticsearch同步连接已关闭")
        except Exception as e:
            logger.error(f"关闭Elasticsearch同步连接失败: {e}")

    async def async_close(self):
        """关闭异步连接"""
        try:
            if self.__client:
                await self.__client.aclose()
                self._connected = False
                logger.info("Elasticsearch异步连接已关闭")
        except Exception as e:
            logger.error(f"关闭Elasticsearch异步连接失败: {e}")

    def ping(self) -> bool:
        """检查同步连接状态"""
        try:
            result = self.__client.ping()
            return result
        except Exception as e:
            logger.error(f"Elasticsearch ping 失败: {e}")
            self._connected = False
            return False

    async def async_ping(self) -> bool:
        """检查异步连接状态"""
        try:
            result = await self.__client.ping()
            return result
        except Exception as e:
            logger.error(f"Elasticsearch async ping 失败: {e}")
            self._connected = False
            return False

    def __repr__(self):
        return f"<ElasticDB hosts={self._hosts} amode={self._amode}>"

    @property
    def _client(self):
        """获取Elasticsearch连接对象"""
        return self.__client

    @classmethod
    def from_url(
        cls,
        hosts: Union[str, List[str]],
        amode: bool = False,
        **kwargs,
    ):
        """
        从URL创建Elasticsearch实例
        Args:
            hosts: Elasticsearch主机地址
            amode: 是否使用异步模式
            **kwargs: 其他Elasticsearch连接参数
        Returns:
            ElasticDB实例
        """
        return cls(hosts=hosts, amode=amode, **kwargs)

    # ------------------- CRUD Operations -------------------

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
        return await self._impl.aindex(index, document, id, refresh)

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
        return self._impl.index(index, document, id, refresh)

    async def aget(self, index: str, id: str):
        """
        @summary: 异步获取文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 文档内容
        """
        return await self._impl.aget(index, id)

    def get(self, index: str, id: str):
        """
        @summary: 获取文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 文档内容
        """
        return self._impl.get(index, id)

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
        return await self._impl.asearch(index, query, size, from_)

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
        return self._impl.search(index, query, size, from_)

    async def adelete(self, index: str, id: str):
        """
        @summary: 异步删除文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 删除结果
        """
        return await self._impl.adelete(index, id)

    def delete(self, index: str, id: str):
        """
        @summary: 删除文档
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 删除结果
        """
        return self._impl.delete(index, id)

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
        return await self._impl.aupdate(index, id, document)

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
        return self._impl.update(index, id, document)

    async def aexists(self, index: str, id: str) -> bool:
        """
        @summary: 异步检查文档是否存在
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 是否存在
        """
        return await self._impl.aexists(index, id)

    def exists(self, index: str, id: str) -> bool:
        """
        @summary: 检查文档是否存在
        ---------
        @param index: 索引名称
        @param id: 文档ID
        ---------
        @result: 是否存在
        """
        return self._impl.exists(index, id)

    async def abulk(self, operations: List[Dict[str, Any]]):
        """
        @summary: 异步批量操作
        ---------
        @param operations: 操作列表
        ---------
        @result: 批量操作结果
        """
        return await self._impl.abulk(operations)

    def bulk(self, operations: List[Dict[str, Any]]):
        """
        @summary: 批量操作
        ---------
        @param operations: 操作列表
        ---------
        @result: 批量操作结果
        """
        return self._impl.bulk(operations)

    def count(self, index: str, query: Optional[Dict[str, Any]] = None) -> int:
        """
        @summary: 统计文档数量
        ---------
        @param index: 索引名称
        @param query: 查询条件,可选
        ---------
        @result: 文档数量
        """
        return self._impl.count(index, query)

    def scroll(self, scroll_id: str, scroll: str = "1m"):
        """
        @summary: 滚动查询
        ---------
        @param scroll_id: 滚动ID
        @param scroll: 滚动保持时间,默认1分钟
        ---------
        @result: 滚动结果
        """
        return self._impl.scroll(scroll_id, scroll)

    def clear_scroll(self, scroll_id: Optional[str] = None):
        """
        @summary: 清除滚动上下文
        ---------
        @param scroll_id: 滚动ID,可选,不传则清除所有
        ---------
        @result: 清除结果
        """
        return self._impl.clear_scroll(scroll_id)

    def get_es_obj(self):
        """获取原始Elasticsearch对象"""
        return self._impl.get_es_obj()

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查,返回Elasticsearch连接状态信息
        Returns:
            包含连接状态、延迟等信息的字典
        """
        return self._impl.health_check()

    def __getattr__(self, name):
        """委托到底层Elasticsearch客户端"""
        return getattr(self.__client, name)
