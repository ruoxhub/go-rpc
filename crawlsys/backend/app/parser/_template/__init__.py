"""<platform_name> 平台解析器 — 模板文件，复制此目录为新平台起点。

用法：
1. 复制 _template/ 到新目录并重命名
2. 修改 platform 和 selectors
3. 实现 transform() 方法
"""

from typing import Iterator

from ..base import BasePlatformParser
from ...web import Metadata


class NewPlatform(BasePlatformParser):
    platform = "new_platform"  # TODO: 修改为新平台的标识名
    selectors = {
        "author": "",
        "published": "",
        "content": "",
    }

    def transform(self, metadata: Metadata) -> Iterator[dict]:
        yield {
            "datatype": "content",
            "platform": self.platform,
            "title": metadata.title,
            "author": metadata.author,
            "pub_time": metadata.published,
            "content": metadata.content,
            "url": metadata.url,
            "domain": metadata.domain,
        }
