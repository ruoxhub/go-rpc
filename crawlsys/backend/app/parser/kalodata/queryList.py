"""Parser for Kalodata's ``queryList`` action."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .. import register


@register("kalodata", "queryList")
def parse_query_list(data: Any) -> Iterator[dict[str, str]]:
    """Convert the upstream video-ID list into downstream stream parameters."""
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("queryList response.data must be a video ID list")

    seen: set[str] = set()
    for value in data["data"]:
        if not value:
            continue
        video_id = str(value)
        if video_id in seen:
            continue
        seen.add(video_id)
        yield {"content_id": video_id}
