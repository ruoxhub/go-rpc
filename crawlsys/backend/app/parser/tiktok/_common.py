import json
from typing import Dict, Any, Generator, Optional
from datetime import datetime, timezone
from .. import register
from utils.tools import generate_hash
from .getUserInfo import parse_user_data

def get_video_url(video_data: Dict[str, Any]) -> Optional[str]:
    """
    从视频数据中提取视频 URL

    Args:
        video_data: 视频数据字典

    Returns:
        视频 URL，如果未找到则返回 None
    """
    # 尝试获取 playAddr。PlayAddrStruct 可能缺失，需先以 {} 兜底，
    # 否则 video_data.get("PlayAddrStruct") 返回 None 后链式 .get 会抛
    # AttributeError: 'NoneType' object has no attribute 'get'。
    play_addr_struct = video_data.get("PlayAddrStruct") or {}
    url_list = play_addr_struct.get("UrlList", []) if isinstance(play_addr_struct, dict) else []
    if url_list:
        play_addr = url_list[-1]
    else:
        play_addr = video_data.get("playAddr")

    return play_addr



def _get_cover_url(video_data: Dict[str, Any]) -> Optional[str]:
    """
    从视频数据中提取封面 URL

    Args:
        video_data: 视频数据字典

    Returns:
        封面 URL，如果未找到则返回 None
    """
    return video_data.get("cover") or video_data.get("dynamicCover")


def _to_int(value: Any, default: int = 0) -> int:
    """
    将 TikTok 接口返回的计数字段安全地转为 int。

    TikTok 的 statsV2 字段以字符串形式返回（如 "903"），而数据库对应列为 INTEGER，
    直接写入会触发 asyncpg 的 DataError。此函数对 None / 空串 / 非数字做容错，
    保证批量插入不会因为个别字段类型不匹配而整体失败。
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_ecommerce_products(item: Dict[str, Any]) -> list[dict[str, Any]]:
    """从商品锚点的双层 JSON 中提取带货分析字段。"""
    product_fields = (
        "product_id",
        "title",
        "cover_url",
        "img_url",
        "price",
        "market_price",
        "currency",
        "seller_id",
        "source",
        "product_status",
        "in_shop",
        "is_platform_product",
        "skus",
        "categories",
        "detail_url",
        "seo_url",
    )
    products = []

    for anchor in item.get("anchors") or []:
        if not isinstance(anchor, dict) or not isinstance(anchor.get("extra"), str):
            continue
        try:
            anchor_items = json.loads(anchor["extra"])
        except (TypeError, ValueError):
            continue
        if not isinstance(anchor_items, list):
            continue

        for anchor_item in anchor_items:
            if not isinstance(anchor_item, dict) or not isinstance(anchor_item.get("extra"), str):
                continue
            try:
                product = json.loads(anchor_item["extra"])
            except (TypeError, ValueError):
                continue
            if not isinstance(product, dict) or product.get("product_id") is None:
                continue
            products.append({field: product.get(field) for field in product_fields})

    return products


def parse_item_dict(item: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析单条 TikTok 视频 item 并产出 content / media 数据字典。

    该函数对单条 item 做完整解析，从 video 列表与视频详情两条调用路径
    复用，避免重复逻辑。当 item 缺少 id 时直接跳过。

    Args:
        item: 单条视频数据字典（来自 itemList 或 itemInfo.itemStruct）

    Yields:
        dict: content 和 media 数据字典
    """
    video_id = item.get("id")
    if not video_id:
        return

    author = item.get("author", {})
    user_id = author.get("id")
    unique_id = author.get("uniqueId")
    nickname = author.get("nickname")

    video_info = item.get("video", {})
    music_info = item.get("music", {})
    stats = item.get("stats", {})
    stats_v2 = item.get("statsV2", {})

    create_time_ts = item.get("createTime")
    pub_time = (
        datetime.fromtimestamp(int(create_time_ts), tz=timezone.utc).replace(tzinfo=None)
        if create_time_ts
        else None
    )

    video_url = f"https://www.tiktok.com/@{unique_id}/video/{video_id}" if unique_id else ""
    desc = item.get("desc", "")
    # # 视频媒体
    video_play_addr = get_video_url(video_info)
    # if play_addr:
    #     yield {
    #         "datatype": "media",
    #         "media_id": f"{user_id}_{video_id}_1",
    #         "user_id": user_id,
    #         "content_id": video_id,
    #         "type": 1,
    #         "url": play_addr,
    #         "platform": "tiktok",
    #         "pub_time": pub_time,
    #     }

    # # 音频媒体
    music_play_addr = music_info.get("playUrl")
    # if play_url:
    #     yield {
    #         "datatype": "media",
    #         "media_id": f"{user_id}_{video_id}_4",
    #         "user_id": user_id,
    #         "content_id": video_id,
    #         "type": 4,
    #         "url": play_url,
    #         "platform": "tiktok",
    #         "pub_time": pub_time,
    #     }

    # 提取有用的扩展字段
    extend_data = {
        "aigcLabelType": item.get("aigcLabelType", 0),
        "aigc_description": item.get("AIGCDescription"),
        "category_type": item.get("CategoryType"),
        "text_language": item.get("textLanguage"),
        "diversification_id": item.get("diversificationId"),
        "item_comment_status": item.get("itemCommentStatus"),
        "item_control": item.get("item_control"),
        "offical_item": item.get("officalItem"),
        "original_item": item.get("originalItem"),
        "private_item": item.get("privateItem"),
        "secret": item.get("secret"),
        "collected": item.get("collected"),
        "digged": item.get("digged"),
        "duet_enabled": item.get("duetEnabled"),
        "stitch_enabled": item.get("stitchEnabled"),
        "share_enabled": item.get("shareEnabled"),
        "isECVideo": item.get("isECVideo"),
        "isAd": item.get("isAd"),
        "ecommerce_products": _extract_ecommerce_products(item),
        "video_url": video_play_addr,
        "music_url": music_play_addr,
        "pic_url": _get_cover_url(video_info),
    }

    video_dict = {
        "datatype": "content",
        "content_id": video_id,
        "user_id": user_id,
        "author": nickname or unique_id,
        "pic": video_info.get("cover"),
        "title": desc[:255] if desc else "",
        "description": desc,
        "url": video_url,
        "duration": _to_int(video_info.get("duration")),
        "pub_time": pub_time,
        "location": None,
        "share_count": _to_int(stats_v2.get("shareCount")),
        "repost_count": _to_int(stats_v2.get("repostCount")),
        "comment_count": _to_int(stats_v2.get("commentCount")),
        "like_count": _to_int(stats_v2.get("diggCount")),
        "view_count": _to_int(stats_v2.get("playCount")),
        "favorites": _to_int(stats_v2.get("collectCount")),
        "extend": json.dumps(extend_data, ensure_ascii=False),
        "platform": "tiktok",
    }
    yield video_dict

    yield from parse_user_data({"user": author})

@register("tiktok", "video")
def parse_video_data(data: Dict[str, Any]) -> Generator[dict, None, None]:
    """
    解析 TikTok 视频列表数据并提取主要内容

    Args:
        data: 包含 TikTok 视频列表数据的字典（含 itemList 字段）

    Yields:
        dict: 视频或媒体数据字典
    """
    if not data or "itemList" not in data:
        return

    for item in data["itemList"]:
        yield from parse_item_dict(item)
