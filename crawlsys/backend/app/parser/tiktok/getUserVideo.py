from typing import Any, Dict, Generator

from .. import register
from ._common import parse_video_data


@register("tiktok", "getUserVideo")
def parse_get_user_video(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """解析 TikTok 用户视频列表数据。"""
    yield from parse_video_data(data)
