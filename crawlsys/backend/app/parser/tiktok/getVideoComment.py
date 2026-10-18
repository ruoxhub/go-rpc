import json
from typing import Dict, Any, Generator
from datetime import datetime
from .. import register


@register("tiktok", "getVideoComment")
def parse_comment_data(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析 TikTok 评论数据并提取主要内容

    Args:
        data: 包含 TikTok 评论数据的字典

    Yields:
        dict: 评论数据字典
    """
    if not data or "comments" not in data:
        return

    for comment in data["comments"]:
        user = comment.get("user", {})
        # 父评论信息
        parent_comment_id = comment.get("reply_id")
        if parent_comment_id == "0" or not parent_comment_id:
            parent_comment_id = None
        parent_user_id = None
        parent_name = None
        reply_comment = comment.get("reply_comment")
        if isinstance(reply_comment, dict):
            parent_user = reply_comment.get("user", {})
            parent_user_id = parent_user.get("uid")
            parent_name = parent_user.get("unique_id")
        # 用户主页链接
        unique_id = user.get("unique_id")
        user_url = f"https://www.tiktok.com/@{unique_id}" if unique_id else None

        parsed_comment = {
            "datatype": "comment",
            "comment_id": comment.get("cid"),
            "relation_id": comment.get("aweme_id"),
            "parent_user_id": parent_user_id,
            "parent_name": parent_name,
            "parent_comment_id": parent_comment_id,
            "user_id": user.get("uid"),
            "username": unique_id,
            "user_url": user_url,
            "location": None,
            "content": comment.get("text"),
            "like_count": comment.get("digg_count", 0),
            "reply_count": comment.get("reply_comment_total", 0),
            "pub_time": datetime.fromtimestamp(comment.get("create_time")) if comment.get("create_time") else None,
            "extend": json.dumps(comment, ensure_ascii=False),
            "platform": "tiktok",
        }
        yield parsed_comment
