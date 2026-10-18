import json
from typing import Dict, Any, Generator
from datetime import datetime
from .. import register


@register("tiktok", "getUserInfo")
def parse_user_data(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析 TikTok 用户数据并提取主要内容

    Args:
        data: 包含 TikTok 用户数据的字典

    Yields:
        dict: 用户数据字典
    """
    # 提取用户信息路径
    user_info = data.get("userInfo", {}) or data

    if not user_info:
        return

    user = user_info.get("user", {})
    stats = user_info.get("stats", {})
    stats_v2 = user_info.get("statsV2", {})

    # 提取用户 ID
    user_id = user.get("id")
    if not user_id:
        return

    # 提取用户名和昵称
    unique_id = user.get("uniqueId")
    nickname = user.get("nickname")

    # 提取头像 (使用最大尺寸)
    avatar = user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb")
    if avatar and len(avatar) > 255:
        avatar = None

    # 提取个人简介
    signature = user.get("signature")

    # 提取个人网站链接
    bio_link = user.get("bioLink", {})
    website = bio_link.get("link") if isinstance(bio_link, dict) else None

    # 提取统计数据 (优先使用 stats_v2 的精确值，否则使用 stats)
    follower_count = int(stats_v2.get("followerCount", 0)) if stats_v2.get("followerCount") else stats.get("followerCount", 0)
    following_count = int(stats_v2.get("followingCount", 0)) if stats_v2.get("followingCount") else stats.get("followingCount", 0)
    content_count = int(stats_v2.get("videoCount", 0)) if stats_v2.get("videoCount") else stats.get("videoCount", 0)

    # 提取认证状态 (转换为字符串)
    verified = "verified" if user.get("verified") else "unverified"

    # 提取创建时间
    create_time_ts = user.get("createTime")
    created_at = datetime.fromtimestamp(create_time_ts) if create_time_ts else None

    # 构建用户字典，严格按照 BaseUser 模型字段
    user_dict = {
        "datatype": "user",
        "user_id": str(user_id),
        "avatar": avatar,
        "name": nickname,
        "username": unique_id,
        "gender": 0,  # TikTok API 未提供性别信息，使用默认值 0
        "website": website,
        "description": signature,
        "follower_count": follower_count,
        "following_count": following_count,
        "content_count": content_count,
        "verified": verified,
        "extend": json.dumps(user_info, ensure_ascii=False),
        "platform": "tiktok",
        "created_at": created_at,
    }

    yield user_dict
