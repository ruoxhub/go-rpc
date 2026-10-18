"""Twitter/X 解析公用函数与数据映射。

提供推文、用户、媒体、日期的解析与统一字典格式化。
所有输入均为原始 GraphQL / API 返回的 dict。
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

try:
    from email.utils import parsedate_to_datetime as _parsedate
except Exception:
    _parsedate = None


def _parse_twitter_datetime(s: str | None) -> datetime | None:
    """将 Twitter created_at (RFC2822 或常见格式) 转为 naive datetime。"""
    if not s:
        return None
    ss = s.strip()
    if _parsedate:
        try:
            dt = _parsedate(ss)
            return dt.replace(tzinfo=None)
        except Exception:
            pass
    try:
        dt = datetime.strptime(ss, "%a %b %d %H:%M:%S %z %Y")
        return dt.replace(tzinfo=None)
    except Exception:
        return None


PLATFORM = "twitter"


def find_dict(obj: list | dict, key: str | int, find_one: bool = False) -> list[Any]:
    """在嵌套字典/列表中查找指定 key 的所有值。"""
    results: list[Any] = []
    if isinstance(obj, dict):
        if key in obj:
            results.append(obj.get(key))
            if find_one:
                return results
    if isinstance(obj, (list, dict)):
        for elem in (obj if isinstance(obj, list) else obj.values()):
            r = find_dict(elem, key, find_one)
            results += r
            if r and find_one:
                return results
    return results


def _extract_media(tweet_data: dict) -> list[dict]:
    """从 tweet_data 中提取媒体列表，优先用 extended_entities。"""
    legacy = tweet_data.get("legacy", {}) if isinstance(tweet_data.get("legacy"), dict) else {}
    ext = legacy.get("extended_entities", {}) if isinstance(legacy.get("extended_entities"), dict) else {}
    raw_media = ext.get("media") or (legacy.get("entities", {}).get("media") if isinstance(legacy.get("entities"), dict) else []) or []
    result = []
    for m in raw_media:
        if not isinstance(m, dict):
            continue
        media_type = m.get("type", "")
        if media_type in ("video", "animated_gif"):
            variants = m.get("video_info", {}).get("variants", [])
            mp4_variants = [v for v in variants if isinstance(v, dict) and v.get("content_type") == "video/mp4"]
            url = ""
            if mp4_variants:
                url = max(mp4_variants, key=lambda v: v.get("bitrate", 0)).get("url", "")
            duration_ms = m.get("video_info", {}).get("duration_millis", 0)
            result.append({
                "type": 1,  # video
                "url": url,
                "duration": duration_ms / 1000 if duration_ms else 0,
                "thumbnail": m.get("media_url_https", ""),
            })
        else:
            result.append({
                "type": 2,  # image
                "url": m.get("media_url_https", ""),
            })
    return result


def _first_video(media_list: list[dict]) -> tuple[str, float]:
    for m in media_list:
        if m.get("type") == 1:
            return m.get("url", ""), m.get("duration", 0)
    return "", 0


def _first_image_url(media_list: list[dict]) -> str:
    for m in media_list:
        if m.get("type") == 2:
            return m.get("url", "")
    return ""


def _media_extend(media_list: list[dict]) -> list[dict]:
    result = []
    for m in media_list:
        entry: dict[str, Any] = {"type": m.get("type"), "url": m.get("url")}
        if m.get("duration"):
            entry["duration"] = m["duration"]
        if m.get("thumbnail"):
            entry["thumbnail"] = m["thumbnail"]
        result.append(entry)
    return result


def _get_user_info(user_result: dict) -> tuple[str, str]:
    """返回 (user_id, screen_name)。兼容 core 与 legacy。"""
    user_id = user_result.get("rest_id", "")
    core = user_result.get("core") if isinstance(user_result.get("core"), dict) else {}
    legacy = user_result.get("legacy") if isinstance(user_result.get("legacy"), dict) else {}
    screen_name = core.get("screen_name") or legacy.get("screen_name") or ""
    return user_id, screen_name


def _place_name(tweet_data: dict) -> str:
    place = tweet_data.get("place")
    if isinstance(place, dict):
        return place.get("full_name") or place.get("name") or ""
    return ""


def tweet_to_content(tweet_data: dict, user_result: dict) -> dict:
    """将原始 tweet_data dict 和 user_result dict 转换为统一 Content 字典。"""
    legacy = tweet_data.get("legacy", {}) if isinstance(tweet_data.get("legacy"), dict) else {}
    media_list = _extract_media(tweet_data)

    user_id, screen_name = _get_user_info(user_result)

    is_retweet = "retweeted_status_result" in legacy or "retweeted_status_result" in tweet_data
    is_quote = legacy.get("is_quote_status", False)
    in_reply_to_post_id = legacy.get("in_reply_to_status_id_str", "")
    is_reply = bool(in_reply_to_post_id)

    entities = legacy.get("entities", {}) if isinstance(legacy.get("entities"), dict) else {}
    hashtags = [h.get("text", "") for h in entities.get("hashtags", []) if isinstance(h, dict)]
    user_mentions = [
        {"id": u.get("id_str", ""), "screen_name": u.get("screen_name", "")}
        for u in entities.get("user_mentions", [])
        if isinstance(u, dict)
    ]
    urls = [u.get("expanded_url", "") for u in entities.get("urls", []) if isinstance(u, dict) and u.get("expanded_url")]

    extend_data: dict[str, Any] = {
        "lang": legacy.get("lang", ""),
        "is_retweet": int(is_retweet),
        "is_quote": int(is_quote),
        "is_reply": int(is_reply),
        "hashtags": hashtags,
        "user_mentions": user_mentions,
        "conversation_id": legacy.get("conversation_id_str", ""),
    }

    if media_list:
        extend_data["media"] = _media_extend(media_list)

    if is_reply:
        extend_data["in_reply_to_post_id"] = in_reply_to_post_id
        extend_data["in_reply_to_user_id"] = legacy.get("in_reply_to_user_id_str", "")

    if urls:
        extend_data["urls"] = urls

    video_url, duration = _first_video(media_list)
    image_url = _first_image_url(media_list)

    views = tweet_data.get("views", {}) if isinstance(tweet_data.get("views"), dict) else {}
    view_count = int(views.get("count", 0) or 0)

    tweet_id = legacy.get("id_str", "") or tweet_data.get("rest_id", "")
    note_tweet = tweet_data.get("note_tweet", {}) if isinstance(tweet_data.get("note_tweet"), dict) else {}
    note_results = note_tweet.get("note_tweet_results", {}) if isinstance(note_tweet.get("note_tweet_results"), dict) else {}
    note_text = note_results.get("result", {}).get("text", "") if isinstance(note_results.get("result"), dict) else ""
    full_text = note_text or legacy.get("full_text", "")
    tweet_url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""

    return {
        "content_id": tweet_id,
        "user_id": user_id,
        "author": screen_name,
        "pic": image_url,
        "thumbnail": video_url,
        "title": "",
        "content": full_text,
        "description": full_text,
        "url": tweet_url,
        "duration": int(duration),
        "pub_time": _parse_twitter_datetime(legacy.get("created_at")),
        "location": _place_name(tweet_data),
        "share_count": 0,
        "repost_count": legacy.get("retweet_count", 0) or 0,
        "comment_count": legacy.get("reply_count", 0) or 0,
        "like_count": legacy.get("favorite_count", 0) or 0,
        "view_count": view_count,
        "favorites": legacy.get("bookmark_count", 0) or 0,
        "platform": PLATFORM,
        "datatype": "content",
        "extend": json.dumps(extend_data, ensure_ascii=False),
    }


def tweet_from_data(data: dict) -> tuple[dict, dict] | tuple[None, None]:
    """从 entry/item dict 中提取 tweet_data 和 user_result，

    返回 (content_dict, user_dict) 或 (None, None)。
    """
    tweet_data_ = find_dict(data, "result", True)
    if not tweet_data_:
        return None, None
    tweet_data = tweet_data_[0]

    if not isinstance(tweet_data, dict):
        return None, None
    if tweet_data.get("__typename") == "TweetTombstone":
        return None, None
    if "tweet" in tweet_data and isinstance(tweet_data["tweet"], dict):
        tweet_data = tweet_data["tweet"]
    if "core" not in tweet_data:
        return None, None
    if "legacy" not in tweet_data:
        return None, None

    user_results = tweet_data.get("core", {}).get("user_results", {})
    if not isinstance(user_results, dict) or "result" not in user_results:
        return None, None

    user_result = user_results["result"]
    if not isinstance(user_result, dict):
        return None, None

    content = tweet_to_content(tweet_data, user_result)
    user = parse_user_data(user_result)
    return content, user


def _get_entries(response: dict) -> list:
    """从 response 中提取 entries 列表。"""
    instructions_ = find_dict(response, "instructions", True)
    if not instructions_:
        return []
    instructions = instructions_[0]
    if not isinstance(instructions, list):
        return []
    for instr in reversed(instructions):
        if isinstance(instr, dict) and "entries" in instr:
            return instr["entries"]
    if instructions and isinstance(instructions[0], dict) and "moduleItems" in instructions[0]:
        return instructions[0]["moduleItems"]
    return []


def parse_user_data(data: dict) -> dict:
    """将用户数据解析为统一 User 字典。兼容完整 JSON 或 result 字典。"""
    user_data = data
    if isinstance(data, dict):
        if (
            "data" in data
            and isinstance(data["data"], dict)
            and "user" in data["data"]
            and isinstance(data["data"]["user"], dict)
            and "result" in data["data"]["user"]
        ):
            user_data = data["data"]["user"]["result"]
        elif "result" in data and isinstance(data["result"], dict):
            user_data = data["result"]

    if not isinstance(user_data, dict):
        user_data = {}

    legacy = user_data.get("legacy") if isinstance(user_data.get("legacy"), dict) else {}
    core = user_data.get("core") if isinstance(user_data.get("core"), dict) else {}
    location_info = user_data.get("location") if isinstance(user_data.get("location"), dict) else {}

    # 提取 username 和 name (兼容 core 与 legacy)
    screen_name = core.get("screen_name") or legacy.get("screen_name") or ""
    name = core.get("name") or legacy.get("name") or ""

    extend = {
        "is_blue_verified": user_data.get("is_blue_verified", False),
        "profile_banner_url": legacy.get("profile_banner_url", "") or user_data.get("profile_banner_url", ""),
        "profile_image_shape": user_data.get("profile_image_shape", ""),
        "possibly_sensitive": legacy.get("possibly_sensitive", False),
        "default_profile": legacy.get("default_profile", False),
        "default_profile_image": legacy.get("default_profile_image", False),
        "has_custom_timelines": legacy.get("has_custom_timelines", False),
        "is_translator": legacy.get("is_translator", False),
        "translator_type": legacy.get("translator_type", ""),
        "want_retweets": legacy.get("want_retweets", False),
        "has_graduated_access": user_data.get("has_graduated_access", False),
        "premium_gifting_eligible": user_data.get("premium_gifting_eligible", False),
        "creator_subscriptions_count": user_data.get("creator_subscriptions_count", 0),
        "affiliates_highlighted_label": user_data.get("affiliates_highlighted_label", {}),
        "highlights_info": user_data.get("highlights_info", {}),
        "tipjar_settings": user_data.get("tipjar_settings", {}),
        "business_account": user_data.get("business_account", {}),
        "legacy_extended_profile": user_data.get("legacy_extended_profile", {}),
        "verification_info": user_data.get("verification_info", {}),
        "relationship_perspectives": user_data.get("relationship_perspectives", {}),
    }

    verification = user_data.get("verification")
    verified_type = verification.get("verified_type", "") if isinstance(verification, dict) else ""
    is_blue_verified = user_data.get("is_blue_verified", False)
    if verified_type == "Business":
        verified = "gold"
    elif is_blue_verified:
        verified = "blue"
    else:
        verified = "none"

    created_at_str = core.get("created_at") or legacy.get("created_at") or ""
    created_at = None
    if created_at_str:
        dt = _parse_twitter_datetime(created_at_str)
        if dt:
            created_at = dt.strftime("%Y-%m-%d %H:%M:%S")

    avatar_info = user_data.get("avatar")
    avatar_url = avatar_info.get("image_url", "") if isinstance(avatar_info, dict) else legacy.get("profile_image_url_https", "")

    return {
        "user_id": user_data.get("rest_id", ""),
        "url": f"https://x.com/{screen_name}" if screen_name else "",
        "avatar": avatar_url,
        "name": name,
        "username": screen_name,
        "gender": 0,
        "website": legacy.get("url", ""),
        "description": legacy.get("description", ""),
        "location": location_info.get("location", "") or legacy.get("location", ""),
        "follower_count": legacy.get("followers_count", 0) or 0,
        "following_count": legacy.get("friends_count", 0) or 0,
        "content_count": legacy.get("statuses_count", 0) or 0,
        "verified": verified,
        "extend": json.dumps(extend, ensure_ascii=False),
        "platform": PLATFORM,
        "datatype": "user",
        "created_at": created_at,
    }
