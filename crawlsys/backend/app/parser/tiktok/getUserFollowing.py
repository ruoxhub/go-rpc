import json
from typing import Dict, Any, Generator
from .. import register


@register("tiktok", "getUserFollowing")
def parse_user_following_data(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析 TikTok 用户关注列表数据（getUserFollowing 接口）

    接口返回的 userList 中每个元素包含 user / stats / statsV2 三部分，
    逐条解析为 BaseUser 模型对应的用户字典。

    Args:
        data: 包含 getUserFollowing 接口返回数据的字典

    Yields:
        dict: 用户数据字典 (datatype="user")
    """
    if not data:
        return

    user_list = data.get("userList") or []

    for entry in user_list:
        if not isinstance(entry, dict):
            continue

        user = entry.get("user", {})
        stats = entry.get("stats", {})
        stats_v2 = entry.get("statsV2", {})

        # 提取用户 ID
        user_id = user.get("id")
        if not user_id:
            continue

        # 提取用户名和昵称
        unique_id = user.get("uniqueId")
        nickname = user.get("nickname")

        # 构建用户主页链接
        user_url = f"https://www.tiktok.com/@{unique_id}" if unique_id else None

        # 提取头像 (使用最大尺寸)
        avatar = user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb")

        # 提取个人简介
        signature = user.get("signature")

        # 提取个人网站链接
        bio_link = user.get("bioLink", {})
        website = bio_link.get("link") if isinstance(bio_link, dict) else None

        # 提取统计数据 (优先使用 statsV2 的精确值，否则使用 stats)
        follower_count = int(stats_v2.get("followerCount", 0)) if stats_v2.get("followerCount") else stats.get("followerCount", 0)
        following_count = int(stats_v2.get("followingCount", 0)) if stats_v2.get("followingCount") else stats.get("followingCount", 0)
        content_count = int(stats_v2.get("videoCount", 0)) if stats_v2.get("videoCount") else stats.get("videoCount", 0)

        # 提取认证状态 (转换为字符串)
        verified = "verified" if user.get("verified") else "unverified"

        user_dict = {
            "datatype": "user",
            "user_id": str(user_id),
            "url": user_url,
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
            "extend": json.dumps(entry, ensure_ascii=False),
            "platform": "tiktok",
        }

        yield user_dict
