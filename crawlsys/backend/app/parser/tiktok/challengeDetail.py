from typing import Dict, Any, Generator
from .. import register


@register("tiktok", "challengeDetail")
def parse_challenge_detail(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """解析 TikTok 话题（挑战）详情数据。

    challengeDetail 接口返回结构形如:
    {
        "challengeInfo": {
            "challenge": {"id": "870345", "title": "menswear", "desc": "...", "isCommerce": false, ...},
            "statsV2": {"videoCount": "2415148", "viewCount": "24459979345"}
        },
        ...
    }
    产出 challenge 类型数据，经 standard sink 路由到 tk_challenge 表。
    """
    if not data:
        return

    challenge_info = data.get("challengeInfo") or {}
    challenge = challenge_info.get("challenge") or {}
    challenge_id = challenge.get("id")
    if not challenge_id:
        return

    # statsV2 为字符串计数；challenge 顶层 stats 为数值，优先采用 statsV2
    stats_v2 = challenge_info.get("statsV2") or challenge.get("statsV2") or {}
    video_count = stats_v2.get("videoCount")
    view_count = stats_v2.get("viewCount")

    yield {
        "datatype": "challenge",
        "challenge_id": str(challenge_id),
        "title": challenge.get("title"),
        "desc": challenge.get("desc"),
        "is_commerce": bool(challenge.get("isCommerce", False)),
        "video_count": str(video_count) if video_count is not None else None,
        "view_count": str(view_count) if view_count is not None else None,
    }
