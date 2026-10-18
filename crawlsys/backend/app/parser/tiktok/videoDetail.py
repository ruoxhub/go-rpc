from typing import Dict, Any, Generator

from .. import register
from ._common import parse_item_dict


@register("tiktok", "videoDetail")
def parse_video_detail(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析 TikTok 视频详情数据（videoDetail 接口）。

    该接口返回结构与视频列表不同：视频主体位于 ``itemInfo.itemStruct``，
    而非 ``itemList``。本函数优先从此路径提取单条 item，再复用
    ``parse_item_dict`` 产出 content / media 数据，保持与视频列表解析
    完全一致的输出字段。

    同时为兼容以 itemList 形式返回（或其他平台复用接口）的输入，
    若检测到 ``itemList`` 字段则逐条解析，保证调用方无需关心接口差异。

    Args:
        data: videoDetail 接口返回的字典

    Yields:
        dict: 视频或媒体数据字典（datatype=content / media）
    """
    if not data:
        return

    # 路径 1：详情接口标准返回 — itemInfo.itemStruct 单条视频
    item_info = data.get("itemInfo")
    if isinstance(item_info, dict):
        item_struct = item_info.get("itemStruct")
        if isinstance(item_struct, dict):
            yield from parse_item_dict(item_struct)
            return

    # 路径 2：兼容 itemList 形式（列表 / 单元素）
    item_list = data.get("itemList")
    if isinstance(item_list, list):
        for item in item_list:
            if isinstance(item, dict):
                yield from parse_item_dict(item)
                return

    # 路径 3：根级即为单条 item（兜底）
    if "id" in data:
        yield from parse_item_dict(data)
