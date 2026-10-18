"""Bilibili parser implementations."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Generator

from .. import register

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str | None) -> str:
    """去除 B 站标题中的高亮 em 标签等 HTML 片段。"""
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


def _parse_duration(duration_str: Any) -> int:
    """解析时长，支持秒数数字或形如 '03:45' / '01:20:30' 的时间字符串。"""
    if isinstance(duration_str, (int, float)):
        return int(duration_str)
    if not duration_str or not isinstance(duration_str, str):
        return 0
    parts = duration_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(duration_str)
    except (ValueError, TypeError):
        return 0


def _parse_timestamp(val: Any) -> datetime | None:
    if not val:
        return None
    try:
        ts = int(val)
        return datetime.fromtimestamp(ts)
    except (ValueError, TypeError, OSError):
        return None


def parse_video_item(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """将一条 B 站视频项转换为统一 Content 字典和 User 字典。"""
    bvid = str(item.get("bvid") or item.get("id") or "")
    aid = str(item.get("aid") or "")
    content_id = bvid or aid

    mid = str(
        item.get("mid")
        or item.get("uid")
        or (item.get("owner", {}).get("mid") if isinstance(item.get("owner"), dict) else "")
        or ""
    )
    uname = (
        item.get("author")
        or item.get("uname")
        or (item.get("owner", {}).get("name") if isinstance(item.get("owner"), dict) else "")
        or ""
    )

    title = _clean_html(item.get("title"))
    description = item.get("description") or item.get("desc") or ""

    pic = item.get("pic") or item.get("cover") or ""
    if pic and pic.startswith("//"):
        pic = "https:" + pic

    upic = (
        item.get("upic")
        or item.get("uface")
        or (item.get("owner", {}).get("face") if isinstance(item.get("owner"), dict) else "")
        or ""
    )
    if upic and upic.startswith("//"):
        upic = "https:" + upic

    arcurl = item.get("arcurl") or (f"https://www.bilibili.com/video/{bvid}" if bvid else "")

    duration = _parse_duration(item.get("duration"))
    pub_time = _parse_timestamp(item.get("pubdate") or item.get("senddate") or item.get("ctime"))

    stat = item.get("stat") if isinstance(item.get("stat"), dict) else {}

    play = item.get("play") or stat.get("view") or 0
    view_count = int(play) if isinstance(play, (int, float)) else 0

    video_review = item.get("video_review") or item.get("review") or stat.get("reply") or 0
    comment_count = int(video_review) if isinstance(video_review, (int, float)) else 0

    favorites = item.get("favorites") or stat.get("favorite") or 0
    favorites_count = int(favorites) if isinstance(favorites, (int, float)) else 0

    like = item.get("like") or stat.get("like") or 0
    like_count = int(like) if isinstance(like, (int, float)) else 0

    share = stat.get("share") or 0
    share_count = int(share) if isinstance(share, (int, float)) else 0

    cid = str(item.get("cid") or "")
    if not cid and isinstance(item.get("pages"), list) and len(item["pages"]) > 0:
        cid = str(item["pages"][0].get("cid") or "")

    extend = {
        "aid": aid,
        "bvid": bvid,
        "cid": cid,
        "danmaku": item.get("danmaku") or stat.get("danmaku"),
        "tag": item.get("tag"),
        "typename": item.get("typename"),
        "typeid": item.get("typeid"),
    }

    content_dict = {
        "content_id": content_id,
        "user_id": mid,
        "author": uname,
        "title": title,
        "content": description,
        "description": description,
        "pic": pic,
        "thumbnail": pic,
        "url": arcurl,
        "duration": duration,
        "pub_time": pub_time,
        "view_count": view_count,
        "comment_count": comment_count,
        "favorites": favorites_count,
        "like_count": like_count,
        "share_count": share_count,
        "platform": "bilibili",
        "data_type": "3",  # 3: 视频
        "datatype": "content",
        "extend": json.dumps(extend, ensure_ascii=False),
    }

    user_dict = None
    if mid:
        user_dict = {
            "user_id": mid,
            "username": uname,
            "name": uname,
            "avatar": upic,
            "website": f"https://space.bilibili.com/{mid}",
            "platform": "bilibili",
            "datatype": "user",
        }

    return content_dict, user_dict


def parse_user_item(data: dict[str, Any]) -> dict[str, Any]:
    """将 getUserInfo 返回的数据转换为统一 User 字典。"""
    mid = str(data.get("mid") or "")
    name = data.get("name") or ""
    face = data.get("face") or ""
    if face and face.startswith("//"):
        face = "https:" + face
    sign = data.get("sign") or ""
    sex = data.get("sex") or ""
    gender = 1 if sex == "男" else (2 if sex == "女" else 0)

    extend = {
        "level": data.get("level"),
        "birthday": data.get("birthday"),
        "official": data.get("official"),
        "vip": data.get("vip"),
    }

    return {
        "user_id": mid,
        "username": name,
        "name": name,
        "avatar": face,
        "description": sign,
        "gender": gender,
        "website": f"https://space.bilibili.com/{mid}",
        "platform": "bilibili",
        "datatype": "user",
        "extend": json.dumps(extend, ensure_ascii=False),
    }


def parse_comment_item(item: dict[str, Any], content_id: str = "") -> dict[str, Any]:
    """将一条 B 站评论转换为统一 Comment 字典。"""
    rpid = str(item.get("rpid") or "")
    mid = str(item.get("mid") or "")
    member = item.get("member") if isinstance(item.get("member"), dict) else {}
    uname = member.get("uname") or ""

    content_msg = ""
    msg_obj = item.get("content")
    if isinstance(msg_obj, dict):
        content_msg = msg_obj.get("message") or ""
    elif isinstance(msg_obj, str):
        content_msg = msg_obj

    parent = str(item.get("parent") or "")
    root = str(item.get("root") or "")
    parent_comment_id = (
        parent if parent and parent != "0" else (root if root and root != "0" else None)
    )

    like = item.get("like") or 0
    like_count = int(like) if isinstance(like, (int, float)) else 0
    rcount = item.get("rcount") or item.get("count") or 0
    reply_count = int(rcount) if isinstance(rcount, (int, float)) else 0

    pub_time = _parse_timestamp(item.get("ctime"))

    extend = {
        "rpid": rpid,
        "oid": item.get("oid"),
        "type": item.get("type"),
        "action": item.get("action"),
    }

    return {
        "comment_id": rpid,
        "content_id": content_id or str(item.get("oid") or ""),
        "user_id": mid,
        "username": uname,
        "parent_comment_id": parent_comment_id,
        "content": content_msg,
        "like_count": like_count,
        "reply_count": reply_count,
        "pub_time": pub_time,
        "platform": "bilibili",
        "datatype": "comment",
        "extend": json.dumps(extend, ensure_ascii=False),
    }


@register("bilibili", "search")
def parse_search(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili search 动作返回的数据。"""
    if not isinstance(data, dict):
        return

    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    result = inner.get("result")
    if not result:
        return

    items: list[dict[str, Any]] = []
    if isinstance(result, list):
        for entry in result:
            if isinstance(entry, dict):
                if entry.get("result_type") == "video" and isinstance(entry.get("data"), list):
                    items.extend(entry["data"])
                elif "bvid" in entry or "aid" in entry:
                    items.append(entry)
    elif isinstance(result, dict) and isinstance(result.get("video"), list):
        items.extend(result["video"])

    for item in items:
        if isinstance(item, dict):
            content, user = parse_video_item(item)
            if content:
                yield content
            if user:
                yield user


@register("bilibili", "getContent")
def parse_get_content(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili getContent (视频详情) 动作返回的数据。"""
    if not isinstance(data, dict):
        return
    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    if isinstance(inner, dict):
        content, user = parse_video_item(inner)
        if content:
            yield content
        if user:
            yield user


@register("bilibili", "getUserInfo")
def parse_get_user_info(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili getUserInfo 动作返回的数据。"""
    if not isinstance(data, dict):
        return
    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    if isinstance(inner, dict) and (inner.get("mid") or inner.get("name")):
        yield parse_user_item(inner)


@register("bilibili", "getComment")
def parse_get_comment(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili getComment 动作返回的数据。"""
    if not isinstance(data, dict):
        return
    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    if not isinstance(inner, dict):
        return

    replies = inner.get("replies") or []
    if isinstance(replies, list):
        for reply in replies:
            if isinstance(reply, dict):
                yield parse_comment_item(reply)
                # 解析二级回复
                sub_replies = reply.get("replies") or []
                if isinstance(sub_replies, list):
                    for sub in sub_replies:
                        if isinstance(sub, dict):
                            yield parse_comment_item(sub)


@register("bilibili", "getUserContents")
def parse_get_user_contents(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili getUserContents 动作返回的数据。"""
    if not isinstance(data, dict):
        return
    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    if not isinstance(inner, dict):
        return

    vlist = []
    list_obj = inner.get("list")
    if isinstance(list_obj, dict) and isinstance(list_obj.get("vlist"), list):
        vlist = list_obj["vlist"]
    elif isinstance(inner.get("vlist"), list):
        vlist = inner["vlist"]

    for item in vlist:
        if isinstance(item, dict):
            content, user = parse_video_item(item)
            if content:
                yield content
            if user:
                yield user


@register("bilibili", "getFeedRcmd")
def parse_get_feed_rcmd(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili getFeedRcmd (首页推荐) 动作返回的数据。"""
    if not isinstance(data, dict):
        return
    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    items = inner.get("item") or inner.get("items") or []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                content, user = parse_video_item(item)
                if content:
                    yield content
                if user:
                    yield user


@register("bilibili", "getVideoSubtitle")
def parse_get_video_subtitle(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """解析 Bilibili getVideoSubtitle 动作返回的字幕数据并转换为 Media 模型入库。"""
    if not isinstance(data, dict):
        return

    inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
    body = inner.get("body") if isinstance(inner, dict) and isinstance(inner.get("body"), list) else None
    if not body and isinstance(data.get("body"), list):
        body = data["body"]

    if not body:
        return

    # 提取字幕全文本
    lines = [str(line.get("content") or "").strip() for line in body if isinstance(line, dict) and line.get("content")]
    full_text = "\n".join(lines)

    extend = {
        "lines_count": len(lines),
        "stroke": inner.get("Stroke") or data.get("Stroke"),
        "raw_subtitles": body[:50],  # 保留前50句作为结构化对照
    }

    yield {
        "media_id": f"subtitle_{data.get('cid') or inner.get('cid') or hash(full_text)}",
        "content_id": str(data.get("aid") or inner.get("aid") or ""),
        "type": 4,  # 4: 音频/文字/字幕等衍生媒体
        "url": "",
        "platform": "bilibili",
        "datatype": "media",
        "extend": json.dumps({"text": full_text, **extend}, ensure_ascii=False),
    }
