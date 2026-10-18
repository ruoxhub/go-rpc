"""Twitter/X 主页时间线 (Home Timeline) 解析器。"""
from __future__ import annotations

from typing import Generator
from .. import register
from ._common import _get_entries, tweet_from_data

_TWEET_ENTRY_PREFIXES = ("tweet-", "promoted-tweet-")


@register("twitter", "HomeTimeline")
def parse_home_timeline(response: dict) -> Generator[dict, None, None]:
    """解析 HomeTimeline 响应，逐条产出 content 与 user 字典。"""
    entries = _get_entries(response)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id: str = entry.get("entryId", "")

        if not entry_id.startswith(_TWEET_ENTRY_PREFIXES):
            continue

        content, user = tweet_from_data(entry)
        if content is None:
            continue

        yield content
        if user:
            yield user
