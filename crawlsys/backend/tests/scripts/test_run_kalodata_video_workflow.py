from unittest.mock import AsyncMock

import pytest

from scripts.run_kalodata_video_workflow import build_parser, run


@pytest.mark.asyncio
async def test_workflow_runs_crawl_before_clean_and_download(monkeypatch):
    calls: list[str] = []
    crawl = AsyncMock(side_effect=lambda _args: calls.append("crawl"))
    clean_and_download = AsyncMock(
        side_effect=lambda **_kwargs: calls.append("clean_and_download")
    )
    monkeypatch.setattr(
        "scripts.run_kalodata_video_workflow.run_kalodata_crawl", crawl
    )
    monkeypatch.setattr(
        "scripts.run_kalodata_video_workflow.run_clean_and_download",
        clean_and_download,
    )
    args = build_parser().parse_args(["--page-count", "2", "--limit", "10"])

    await run(args)

    assert calls == ["crawl", "clean_and_download"]
    assert crawl.await_args.args[0].page_count == 2
    assert clean_and_download.await_args.kwargs["platform"] == "tiktok"
    assert clean_and_download.await_args.kwargs["limit"] == 10


@pytest.mark.asyncio
async def test_workflow_dry_run_skips_clean_and_download(monkeypatch):
    crawl = AsyncMock()
    clean_and_download = AsyncMock()
    monkeypatch.setattr(
        "scripts.run_kalodata_video_workflow.run_kalodata_crawl", crawl
    )
    monkeypatch.setattr(
        "scripts.run_kalodata_video_workflow.run_clean_and_download",
        clean_and_download,
    )
    args = build_parser().parse_args(["--dry-run"])

    await run(args)

    assert crawl.await_args.args[0].dry_run is True
    clean_and_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_does_not_process_old_data_when_rank_is_empty(monkeypatch):
    crawl = AsyncMock(side_effect=RuntimeError("榜单未返回可用视频 ID"))
    clean_and_download = AsyncMock()
    monkeypatch.setattr(
        "scripts.run_kalodata_video_workflow.run_kalodata_crawl", crawl
    )
    monkeypatch.setattr(
        "scripts.run_kalodata_video_workflow.run_clean_and_download",
        clean_and_download,
    )

    with pytest.raises(RuntimeError, match="榜单未返回可用视频 ID"):
        await run(build_parser().parse_args([]))

    clean_and_download.assert_not_awaited()
