from unittest.mock import AsyncMock, Mock

import pytest

from scripts import crawl_challenge_item_list as challenge_script
from scripts.crawl_challenge_item_list import crawl_challenge_item_list


@pytest.mark.asyncio
async def test_challenge_uses_max_cursor_first_and_counts_parser_items(monkeypatch):
    rpc = AsyncMock()
    rpc.invoke.side_effect = [
        {
            "itemList": [{"id": "wire-item"}],
            "hasMore": True,
            "maxCursor": "20",
            "cursor": "10",
        },
        {"itemList": [{"id": "last"}], "hasMore": False},
    ]
    pipeline = AsyncMock()
    monkeypatch.setattr(
        "app.core.sink_handlers.general_parser.parse",
        lambda *args, **kwargs: iter([{"datatype": "content"}] * 2),
    )

    pages, items = await crawl_challenge_item_list(
        rpc,
        pipeline,
        "tiktok",
        "challenge-1",
        rps=0,
        max_pages=0,
        dry_run=True,
        count=30,
        region="TW",
        locale="zh-Hans",
    )

    assert (pages, items) == (2, 4)
    assert rpc.invoke.await_args_list[1].args[2]["cursor"] == 20
    pipeline.process_items.assert_not_awaited()


def test_challenge_failure_log_redacts_error_and_hashes_identifier(monkeypatch):
    challenge_id = "private-challenge-id-123456789"
    token = "secret-token-value"
    error = RuntimeError(
        f"request https://private.example/path token={token} {'x' * 600}"
    )
    mock_logger = Mock()
    monkeypatch.setattr(challenge_script, "logger", mock_logger)

    challenge_script._log_failure(challenge_id, error)

    args = mock_logger.error.call_args.args
    rendered = args[0] % args[1:]
    assert len(args[1]) == len("sha256:") + 12
    assert len(args[2]) == 500
    assert challenge_id not in rendered
    assert "private.example" not in rendered
    assert token not in rendered
    assert "[REDACTED_URL]" in rendered
    assert "token=***" in rendered
    assert args[1].startswith("sha256:")
