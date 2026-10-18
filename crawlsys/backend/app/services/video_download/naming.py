from __future__ import annotations

from urllib.parse import quote


def encode_object_segment(value: str, field: str) -> str:
    """Encode one logical identifier as a reversible MinIO path segment."""
    if not value or value in {".", ".."}:
        raise ValueError(f"{field} must be non-empty and cannot be '.' or '..'")
    return quote(value, safe="-_.~", encoding="utf-8", errors="strict")


def video_object_stem(platform: str, content_id: str) -> str:
    encoded_id = encode_object_segment(content_id, "content_id")
    if not platform:
        return encoded_id
    return f"{encode_object_segment(platform, 'platform')}/{encoded_id}"


def video_object_name(content_id: str) -> str:
    return f"{encode_object_segment(content_id, 'content_id')}/video"


def cover_object_name(content_id: str) -> str:
    encoded_id = encode_object_segment(content_id, "content_id")
    return f"{encoded_id}/pic"


def audio_object_stem(content_id: str) -> str:
    encoded_id = encode_object_segment(content_id, "content_id")
    return f"{encoded_id}/audio"


def image_object_name(content_id: str, number: int) -> str:
    if number < 1:
        raise ValueError("image number must be greater than zero")
    encoded_id = encode_object_segment(content_id, "content_id")
    return f"{encoded_id}/image_{number}"
