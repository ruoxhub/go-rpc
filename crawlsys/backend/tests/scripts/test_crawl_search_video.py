from unittest.mock import AsyncMock, Mock

import pytest

from scripts import crawl_search_video as search_script
from scripts.crawl_search_video import crawl_search_video


@pytest.mark.asyncio
async def test_crawl_search_video_accepts_snake_case_response(monkeypatch):
    rpc = AsyncMock()
    rpc.invoke.side_effect = [
        {
            "item_list": [{"id": "1"}],
            "has_more": 1,
            "cursor": 12,
        },
        {
            "item_list": [{"id": "2"}],
            "has_more": 0,
            "cursor": 24,
        },
    ]
    pipeline = AsyncMock()
    pipeline.process_items.return_value = {
        "inserted": 1,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    monkeypatch.setattr(
        "scripts.crawl_search_video.general_parser.parse",
        lambda *args, **kwargs: iter(
            [
                {
                    "datatype": "content",
                    "platform": "tiktok",
                    "content_id": args[1]["itemList"][0]["id"],
                }
            ]
        ),
    )

    pages, items = await crawl_search_video(
        rpc,
        pipeline,
        "tiktok",
        "menswear",
        rps=0,
        max_pages=50,
        dry_run=False,
    )

    assert (pages, items) == (2, 2)
    assert rpc.invoke.await_count == 2
    assert pipeline.process_items.await_count == 2
    assert rpc.invoke.await_args_list[1].args[2]["cursor"] == 12


@pytest.mark.asyncio
async def test_crawl_search_video_dry_run_counts_parsed_items_without_writing(monkeypatch):
    rpc = AsyncMock()
    rpc.invoke.return_value = {
        "itemList": [{"id": "1"}, {"id": "2"}],
        "hasMore": False,
    }
    pipeline = AsyncMock()
    monkeypatch.setattr(
        "scripts.crawl_search_video.general_parser.parse",
        lambda *args, **kwargs: iter([{"datatype": "content"}] * 3),
    )

    pages, items = await crawl_search_video(
        rpc,
        pipeline,
        "tiktok",
        "menswear",
        rps=0,
        max_pages=0,
        dry_run=True,
    )

    assert (pages, items) == (1, 3)
    pipeline.process_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_crawl_search_video_surfaces_worker_failure():
    rpc = AsyncMock()
    rpc.invoke.side_effect = RuntimeError("rpc failed")
    pipeline = AsyncMock()

    with pytest.raises(RuntimeError, match="CrawlerWorker failed 1/1"):
        await crawl_search_video(
            rpc,
            pipeline,
            "tiktok",
            "menswear",
            rps=0,
            max_pages=1,
            dry_run=True,
        )


def test_search_failure_log_redacts_error_and_hashes_keyword(monkeypatch):
    keyword = "private search keyword with account details"
    token = "secret-token-value"
    error = RuntimeError(
        f"request https://private.example/path token={token} {'x' * 600}"
    )
    mock_logger = Mock()
    monkeypatch.setattr(search_script, "logger", mock_logger)

    search_script._log_failure(keyword, error)

    args = mock_logger.error.call_args.args
    rendered = args[0] % args[1:]
    assert len(args[1]) == len("sha256:") + 12
    assert len(args[2]) == 500
    assert keyword not in rendered
    assert "private.example" not in rendered
    assert token not in rendered
    assert "[REDACTED_URL]" in rendered
    assert "token=***" in rendered
    assert args[1].startswith("sha256:")
