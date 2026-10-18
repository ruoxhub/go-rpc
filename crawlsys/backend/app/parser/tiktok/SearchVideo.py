from typing import Dict, Any, Generator
from .. import register
from ._common import parse_item_dict, parse_video_data


@register("tiktok", "SearchVideo")
def parse_search_video(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析 TikTok 话题（挑战）下的视频列表数据。

    challengeItemList 接口返回的 itemList 与视频列表结构完全一致，
    因此直接复用视频解析逻辑，逐条产出 content 与 media 数据。

    Args:
        data: 包含 challengeItemList 接口返回数据的字典

    Yields:
        dict: 视频或媒体数据字典（content / media）
    """
    if not data or "item_list" not in data:
        return
    for item in data["item_list"]:
        yield from parse_item_dict(item)
