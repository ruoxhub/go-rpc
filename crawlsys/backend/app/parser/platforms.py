"""BasePlatformParser — ABC template for HTML-based platform parsers."""

from abc import ABC, abstractmethod
from typing import ClassVar, Iterator, Any

from web import Metadata, WebExtractor


class BasePlatformParser(ABC):
    platform: ClassVar[str]
    selectors: ClassVar[dict[str, str]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "platform") and cls.platform:
            from parser import register
            # 实例化并将其包装方法注册为平台解析函数（统一类型为 'content'）
            instance = cls()
            register(cls.platform, "content")(instance.parse_wrapper)

    def parse(self, html: str, url: str) -> Iterator[dict]:
        extractor = WebExtractor(html, url, selectors=self.selectors)
        metadata = extractor.extract()
        yield from self.transform(metadata)

    def parse_wrapper(self, data: Any) -> Iterator[dict]:
        # 兼容 dict (含 html & url) 和纯 str 的调用
        if isinstance(data, dict):
            html = data.get("html", "")
            url = data.get("url", "")
        else:
            html = str(data)
            url = ""
        yield from self.parse(html, url)

    @abstractmethod
    def transform(self, metadata: Metadata) -> Iterator[dict]:
        """子类实现：将 Metadata 转换为含 datatype 的 dict 序列。"""
        pass
