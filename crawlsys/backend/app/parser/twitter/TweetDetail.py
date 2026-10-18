"""Twitter/X TweetDetail 与对话线程解析器。"""
from __future__ import annotations

from typing import Generator
from .. import register
from ._common import _get_entries, find_dict, tweet_from_data, tweet_to_content, parse_user_data


@register("twitter", "TweetDetail")
def parse_tweet_detail(response: dict) -> Generator[dict, None, None]:
    """解析 TweetDetail 响应，逐条产出 content 与 user 字典。

    包含 focal tweet 和 threaded_conversation 中的回复推文。
    """
    seen_ids: set[str] = set()

    # 1. 尝试直接从 instructions/entries 中提取推文
    entries = _get_entries(response)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        content, user = tweet_from_data(entry)
        if content and content.get("content_id"):
            cid = content["content_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                yield content
                if user:
                    yield user

        # 检查 itemContent 中的 items (针对 conversationThread 模块)
        items = find_dict(entry, "items", True)
        if items and isinstance(items[0], list):
            for it in items[0]:
                if not isinstance(it, dict):
                    continue
                c, u = tweet_from_data(it)
                if c and c.get("content_id"):
                    cid = c["content_id"]
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        yield c
                        if u:
                            yield u

    # 2. 如果 entries 未提取到任何数据，回退扫描 tweetResult
    if not seen_ids:
        tweet_results = find_dict(response, "tweetResult", True)
        if tweet_results and isinstance(tweet_results[0], dict):
            res = tweet_results[0].get("result")
            if isinstance(res, dict):
                tw = res.get("tweet") if "tweet" in res and isinstance(res["tweet"], dict) else res
                core = tw.get("core", {}) if isinstance(tw.get("core"), dict) else {}
                u_res = core.get("user_results", {}).get("result", {})
                if isinstance(u_res, dict):
                    content = tweet_to_content(tw, u_res)
                    user = parse_user_data(u_res)
                    if content and content.get("content_id"):
                        seen_ids.add(content["content_id"])
                        yield content
                        if user:
                            yield user
