"""crawl_user_videos.py 单元测试：secuid 解析、getUserInfo 入库、媒体下载回写、用户列表读取。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from scripts.crawl_user_videos import (
    download_item_media,
    extract_secuid,
    extract_secuid_from_data,
    fetch_user_info,
    read_user_list,
    _media_urls_from_extend,
    _parse_extend,
)
from models.results import DownloadedVideo
from services.video_download import VideoDownloadResult


class _FakeResult:
    def __init__(self, object_name: str):
        self.object_name = object_name


# ---------- extract_secuid ----------


def test_extract_secuid_from_data_reads_secUid():
    data = {"user": {"secUid": "sec-123", "id": "1"}, "stats": {}}
    assert extract_secuid_from_data(data) == "sec-123"


def test_extract_secuid_from_data_accepts_userInfo_wrapper():
    data = {"userInfo": {"user": {"secuid": "sec-456"}}}
    assert extract_secuid_from_data(data) == "sec-456"


def test_extract_secuid_from_data_missing_returns_none():
    assert extract_secuid_from_data({"user": {}}) is None
    assert extract_secuid_from_data({"userInfo": {}}) is None
    assert extract_secuid_from_data([]) is None
    assert extract_secuid_from_data(None) is None


def test_extract_secuid_from_orm_user():
    user = type("User", (), {"extend": json.dumps({"user": {"secUid": "sec-9"}}), "user_id": "1", "username": "u"})()
    assert extract_secuid(user) == "sec-9"


def test_extract_secuid_from_orm_user_bad_extend():
    user = type("User", (), {"extend": "not-json", "user_id": "1", "username": "u"})()
    assert extract_secuid(user) is None


# ---------- fetch_user_info ----------


@pytest.mark.asyncio
async def test_fetch_user_info_parses_and_stores():
    rpc = AsyncMock()
    rpc.invoke.return_value = {"userInfo": {"user": {"id": "1", "secUid": "sec-1"}, "stats": {}}}
    pipeline = AsyncMock()
    pipeline.process_items.return_value = {"inserted": 1, "updated": 0, "skipped": 0, "errors": 0}

    with patch("scripts.crawl_user_videos.general_parser.parse") as mock_parse:
        mock_parse.return_value = iter([{"datatype": "user", "user_id": "1", "extend": "{}"}])
        secuid = await fetch_user_info(
            rpc, pipeline, "tiktok", "user-t", user_param="uniqueId", dry_run=False,
        )

    assert secuid == "sec-1"
    rpc.invoke.assert_awaited_once_with("tiktok", "getUserInfo", {"uniqueId": "user-t"})
    pipeline.process_items.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_user_info_no_secuid_returns_none():
    rpc = AsyncMock()
    rpc.invoke.return_value = {"userInfo": {"user": {"id": "1"}}}
    pipeline = AsyncMock()

    with patch(
        "scripts.crawl_user_videos.general_parser.parse",
        return_value=iter([{"datatype": "user", "user_id": "1"}]),
    ):
        sec = await fetch_user_info(
            rpc, pipeline, "tiktok", "u1", user_param="uniqueId", dry_run=False,
        )

    assert sec is None


@pytest.mark.asyncio
async def test_fetch_user_info_dry_run_skips_pipeline():
    rpc = AsyncMock()
    rpc.invoke.return_value = {"userInfo": {"user": {"id": "1", "secUid": "sec"}}}
    pipeline = AsyncMock()

    with patch(
        "scripts.crawl_user_videos.general_parser.parse",
        return_value=iter([{"datatype": "user"}]),
    ):
        sec = await fetch_user_info(
            rpc, pipeline, "tiktok", "u1", user_param="uniqueId", dry_run=True,
        )

    assert sec == "sec"
    pipeline.process_items.assert_not_awaited()


# ---------- read_user_list ----------


def test_read_user_list_ignores_comments_and_blank(tmp_path: Path):
    f = tmp_path / "users.txt"
    f.write_text("# users\nuser1\n\nuser2  \n", encoding="utf-8")
    assert read_user_list(f) == ["user1", "user2"]


def test_read_user_list_empty_raises(tmp_path: Path):
    f = tmp_path / "empty.txt"
    f.write_text("# only comment\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        read_user_list(f)


# ---------- extend helpers ----------


def test_parse_extend_handles_json_and_junk():
    assert _parse_extend({"extend": '{"a": 1}'}) == {"a": 1}
    assert _parse_extend({"extend": "junk"}) == {}
    assert _parse_extend({"extend": None}) == {}
    assert _parse_extend({}) == {}


def test_media_urls_from_extend():
    ext = {"video_url": "v", "music_url": "m"}
    assert _media_urls_from_extend(ext, {"pic": "p"}) == ("v", "m", "p")
    assert _media_urls_from_extend({}, {"pic": "p"}) == ("", "", "p")
    assert _media_urls_from_extend({"pic_url": "p2"}, {}) == ("", "", "p2")


# ---------- download_item_media ----------


@pytest.mark.asyncio
async def test_download_item_media_full_media_writes_extend_and_flag():
    item = {
        "datatype": "content",
        "content_id": "c1",
        "pic": "cover",
        "extend": json.dumps({"video_url": "v1", "music_url": "m1", "pic_url": "p1"}),
    }
    service = AsyncMock()
    service.download_media.return_value = (
        _FakeResult("c1/video"),
        _FakeResult("c1/audio"),
        _FakeResult("c1/pic"),
    )
    sem = asyncio.Semaphore(2)

    ok = await download_item_media(service, "tiktok", item, sem)

    assert ok is True
    service.download_media.assert_awaited_once_with("v1", "m1", "p1", "tiktok", "c1")
    service.download.assert_not_awaited()
    assert item["is_download"] is True
    ext = json.loads(item["extend"])
    assert ext["minio_video"] == "c1/video"
    assert ext["minio_audio"] == "c1/audio"
    assert ext["minio_pic"] == "c1/pic"
    assert ext["video_url"] == "v1"  # 原字段保留


@pytest.mark.asyncio
async def test_download_item_media_missing_audio_degrades_to_video_only():
    item = {
        "datatype": "content",
        "content_id": "c2",
        "extend": json.dumps({"video_url": "v2"}),
    }
    service = AsyncMock()
    service.download.return_value = _FakeResult("c2/video")
    sem = asyncio.Semaphore(1)

    ok = await download_item_media(service, "tiktok", item, sem)

    assert ok is True
    service.download.assert_awaited_once_with("v2", "tiktok", "c2")
    service.download_media.assert_not_awaited()
    ext = json.loads(item["extend"])
    assert ext == {"video_url": "v2", "minio_video": "c2/video"}
    assert "minio_audio" not in ext


@pytest.mark.asyncio
async def test_download_item_media_failure_returns_false_without_flag():
    item = {
        "datatype": "content",
        "content_id": "c3",
        "extend": json.dumps({"video_url": "v3", "music_url": "m3", "pic_url": "p3"}),
    }
    service = AsyncMock()
    service.download_media.side_effect = RuntimeError("boom")
    sem = asyncio.Semaphore(1)

    ok = await download_item_media(service, "tiktok", item, sem)

    assert ok is False
    assert item.get("is_download") is None
    assert "minio_video" not in json.loads(item["extend"])


@pytest.mark.asyncio
async def test_download_item_media_skips_non_content():
    service = AsyncMock()
    sem = asyncio.Semaphore(1)
    ok = await download_item_media(service, "tiktok", {"datatype": "user"}, sem)
    assert ok is False
    service.download_media.assert_not_awaited()
    service.download.assert_not_awaited()