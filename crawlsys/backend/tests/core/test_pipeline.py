import pytest
from unittest.mock import AsyncMock, MagicMock

from pipeline import CrawlerPipeline
from models import Content, TkChallenge


def _stats():
    return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}


@pytest.mark.asyncio
async def test_update_items_uses_platform_and_unique_field_for_platform_models():
    store = MagicMock()
    store.abulk_update = AsyncMock(return_value=1)
    pipeline = CrawlerPipeline(filter=MagicMock(), store=store)

    await pipeline._update_items(
        [Content(datatype="content", platform="tiktok", content_id="123", title="new")],
        _stats(),
    )

    assert store.abulk_update.call_args.kwargs["key_fields"] == ["platform", "content_id"]


@pytest.mark.asyncio
async def test_update_items_uses_single_key_for_challenge_model():
    store = MagicMock()
    store.abulk_update = AsyncMock(return_value=1)
    pipeline = CrawlerPipeline(filter=MagicMock(), store=store)

    await pipeline._update_items(
        [TkChallenge(datatype="challenge", challenge_id="870345", title="menswear")],
        _stats(),
    )

    assert store.abulk_update.call_args.kwargs["key_fields"] == ["challenge_id"]


from datetime import datetime


@pytest.mark.asyncio
async def test_update_items_fills_updated_time_when_missing():
    store = MagicMock()
    store.abulk_update = AsyncMock(return_value=1)
    pipeline = CrawlerPipeline(filter=MagicMock(), store=store)

    await pipeline._update_items(
        [Content(datatype="content", platform="tiktok", content_id="123", view_count=9)],
        _stats(),
    )

    payload = store.abulk_update.call_args.kwargs["data"][0]
    assert "updated_time" in payload
    assert isinstance(payload["updated_time"], datetime)
    assert payload["updated_time"].tzinfo is None
    assert payload["view_count"] == 9


@pytest.mark.asyncio
async def test_update_items_preserves_explicit_updated_time():
    store = MagicMock()
    store.abulk_update = AsyncMock(return_value=1)
    pipeline = CrawlerPipeline(filter=MagicMock(), store=store)
    fixed = datetime(2026, 7, 1, 12, 0, 0)

    item = Content(
        datatype="content",
        platform="tiktok",
        content_id="123",
        view_count=9,
        updated_time=fixed,
    )
    await pipeline._update_items([item], _stats())

    payload = store.abulk_update.call_args.kwargs["data"][0]
    assert payload["updated_time"] == fixed


from datetime import timezone


@pytest.mark.asyncio
async def test_normalize_datetime_fields_strips_timezone():
    pipeline = CrawlerPipeline(filter=MagicMock(), store=MagicMock())
    aware_dt = datetime(2026, 10, 11, 8, 0, 0, tzinfo=timezone.utc)
    item = Content(
        datatype="content",
        platform="douyin",
        content_id="456",
        pub_time=aware_dt,
    )

    pipeline._normalize_datetime_fields(item)

    assert item.pub_time.tzinfo is None
    assert item.pub_time == datetime(2026, 10, 11, 8, 0, 0)

