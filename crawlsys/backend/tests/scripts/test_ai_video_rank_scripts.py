from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts._ai_video_rank_common import (
    crawl_rank_video_details,
    extract_video_ids,
    run_rank_video_details,
)
from scripts.crawl_fastmoss_ai_video_rank import fetch_fastmoss_video_ids
from scripts.crawl_kalodata_query_list import fetch_kalodata_video_pages


def test_extract_video_ids_deduplicates_and_rejects_invalid_payload():
    assert extract_video_ids({"data": ["1", "2", "1"]}, "fastmoss") == ["1", "2"]
    with pytest.raises(ValueError, match="video ID list"):
        extract_video_ids({"data": None}, "kalodata")


@pytest.mark.asyncio
async def test_crawl_rank_video_details_persists_ids(monkeypatch):
    rpc = AsyncMock()
    rpc.invoke.return_value = {"id": "1"}
    pipeline = AsyncMock()
    monkeypatch.setattr(
        "scripts._ai_video_rank_common.parse_video_detail",
        lambda detail: iter([{"datatype": "content"}]),
    )

    result = await crawl_rank_video_details(
        rpc,
        pipeline,
        video_ids=["1"],
        dry_run=True,
    )

    assert result == (1, 1, 0)
    assert rpc.invoke.await_args.args == (
        "tiktok", "videoDetail", {"itemId": "1"}
    )
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_fastmoss_fetches_pages_until_empty_and_deduplicates():
    rpc = AsyncMock()
    rpc.invoke.side_effect = [
        {"data": ["1", "2"]},
        {"data": ["2", "3"]},
        {"data": []},
    ]

    ids = await fetch_fastmoss_video_ids(
        rpc, region="US", date_value="2026-08-01"
    )

    assert ids == ["1", "2", "3"]
    assert [call.args[2]["page"] for call in rpc.invoke.await_args_list] == [1, 2, 3]


@pytest.mark.asyncio
async def test_fastmoss_stops_when_page_has_no_new_ids():
    rpc = AsyncMock()
    rpc.invoke.side_effect = [{"data": ["1"]}, {"data": ["1"]}]

    assert await fetch_fastmoss_video_ids(
        rpc, region="US", date_value="2026-08-01"
    ) == ["1"]
    assert rpc.invoke.await_count == 2


@pytest.mark.asyncio
async def test_kalodata_yields_each_page_with_categories():
    rpc = AsyncMock()
    rpc.invoke.side_effect = [
        {"data": ["1", "2"]},
        {"data": ["2", "3"]},
    ]

    pages = [
        page
        async for page in fetch_kalodata_video_pages(
            rpc,
            country="US",
            start_date="2026-08-05",
            end_date="2026-08-05",
            cate_ids=["840072", "839944"],
            page_count=2,
            page_size=2,
        )
    ]

    assert pages == [(1, ["1", "2"]), (2, ["3"])]
    assert [call.args[2] for call in rpc.invoke.await_args_list] == [
        {
            "country": "US",
            "startDate": "2026-08-05",
            "endDate": "2026-08-05",
            "cateIds": ["840072", "839944"],
            "showCateIds": ["840072", "839944"],
            "pageNo": 1,
            "pageSize": 2,
        },
        {
            "country": "US",
            "startDate": "2026-08-05",
            "endDate": "2026-08-05",
            "cateIds": ["840072", "839944"],
            "showCateIds": ["840072", "839944"],
            "pageNo": 2,
            "pageSize": 2,
        },
    ]


@pytest.mark.parametrize("terminal_data", [None, []])
@pytest.mark.asyncio
async def test_kalodata_stops_at_terminal_page(terminal_data):
    rpc = AsyncMock()
    rpc.invoke.side_effect = [
        {"data": ["1"]},
        {"data": terminal_data},
        {"data": ["stale"]},
    ]

    pages = [
        page
        async for page in fetch_kalodata_video_pages(
            rpc,
            country="US",
            start_date="2026-08-05",
            end_date="2026-08-05",
            cate_ids=["840072"],
            page_count=3,
            page_size=50,
        )
    ]

    assert pages == [(1, ["1"])]
    assert rpc.invoke.await_count == 2


@pytest.mark.asyncio
async def test_paginated_rank_run_fails_when_all_pages_are_empty(monkeypatch):
    from scripts import _ai_video_rank_common as common

    config = SimpleNamespace(
        postgresql=SimpleNamespace(
            username="u", password="p", host="h", port=5432, database="d"
        ),
        redis=SimpleNamespace(url="redis://test"),
        rpc_base_url="http://rpc",
        rpc_token="token",
        rpc_timeout=10,
    )
    db = AsyncMock()
    bloom = AsyncMock()
    pipeline = AsyncMock()
    rpc = AsyncMock()
    monkeypatch.setattr(common.SchedulerConfig, "from_toml", lambda _path: config)
    monkeypatch.setattr(common, "SQLAlchemyDB", lambda **_kwargs: db)
    monkeypatch.setattr(common, "Bloom", lambda **_kwargs: bloom)
    monkeypatch.setattr(common, "CrawlerPipeline", lambda **_kwargs: pipeline)
    monkeypatch.setattr(common, "RpcClient", lambda **_kwargs: rpc)

    async def empty_pages(_rpc):
        yield 1, []

    with pytest.raises(RuntimeError, match="榜单未返回可用视频 ID"):
        await run_rank_video_details(
            label="kalodata/queryList",
            fetch_video_pages=empty_pages,
            config_path="config.toml",
            dry_run=False,
        )

    rpc.close.assert_awaited_once()
    pipeline.close.assert_awaited_once()
    bloom.aclose.assert_awaited_once()
    db.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_kalodata_rejects_different_start_and_end_dates():
    rpc = AsyncMock()

    with pytest.raises(ValueError, match="start_date must be equal to end_date"):
        async for _page in fetch_kalodata_video_pages(
            rpc,
            country="US",
            start_date="2026-08-04",
            end_date="2026-08-05",
            cate_ids=["840072"],
            page_count=1,
            page_size=50,
        ):
            pass

    rpc.invoke.assert_not_awaited()
