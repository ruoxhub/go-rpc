import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import main as entrypoint
from worker.registry import WorkerRuntime


def config():
    return SimpleNamespace(
        validate=Mock(),
        web=SimpleNamespace(host="127.0.0.1", port=8080),
    )


@pytest.mark.asyncio
async def test_main_starts_each_global_worker_once_even_without_quotas(monkeypatch):
    executors = ("rpc_crawl", "video_clean", "video_download", "video_analysis")
    workers = [SimpleNamespace(executor=name, run=AsyncMock(), stop=Mock()) for name in executors]
    runtime = SimpleNamespace(workers=workers, active_quota_count=0, close=AsyncMock())
    cfg = config()
    monkeypatch.setattr(entrypoint.SchedulerConfig, "from_toml", Mock(return_value=cfg))
    build = AsyncMock(return_value=runtime)
    monkeypatch.setattr(entrypoint, "build_runtime", build)
    monkeypatch.setattr(entrypoint, "_start_web_server", Mock(return_value=SimpleNamespace(name="web")))
    monkeypatch.setattr(entrypoint.sys, "platform", "win32")

    await entrypoint.main("test.toml")

    build.assert_awaited_once_with(cfg, "test.toml")
    assert [worker.run.await_count for worker in workers] == [1, 1, 1, 1]
    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_closes_runtime_when_worker_fails(monkeypatch):
    failed = AsyncMock(side_effect=RuntimeError("boom"))
    waiting = AsyncMock(side_effect=lambda: None)
    workers = [
        SimpleNamespace(executor="rpc_crawl", run=failed, stop=Mock()),
        *(SimpleNamespace(executor=name, run=waiting, stop=Mock()) for name in
          ("video_clean", "video_download", "video_analysis")),
    ]
    runtime = SimpleNamespace(workers=workers, active_quota_count=1, close=AsyncMock())
    cfg = config()
    monkeypatch.setattr(entrypoint.SchedulerConfig, "from_toml", Mock(return_value=cfg))
    monkeypatch.setattr(entrypoint, "build_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(entrypoint, "_start_web_server", Mock(return_value=SimpleNamespace(name="web")))
    monkeypatch.setattr(entrypoint.sys, "platform", "win32")

    with pytest.raises(RuntimeError, match="boom"):
        await entrypoint.main()

    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_workers_cancels_and_awaits_long_running_siblings():
    cancelled = [False, False, False]

    async def fail():
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    def sibling(index):
        async def run():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled[index] = True
                raise
        return run

    workers = [
        SimpleNamespace(run=fail),
        *(SimpleNamespace(run=sibling(index)) for index in range(3)),
    ]

    with pytest.raises(RuntimeError, match="boom"):
        await entrypoint._run_workers(workers)

    assert cancelled == [True, True, True]


@pytest.mark.asyncio
async def test_main_propagates_cancellation_and_closes_runtime(monkeypatch):
    worker = SimpleNamespace(
        executor="rpc_crawl", run=AsyncMock(side_effect=asyncio.CancelledError())
    )
    runtime = SimpleNamespace(
        workers=[worker], active_quota_count=1, close=AsyncMock()
    )
    cfg = config()
    monkeypatch.setattr(entrypoint.SchedulerConfig, "from_toml", Mock(return_value=cfg))
    monkeypatch.setattr(entrypoint, "build_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(entrypoint, "_start_web_server", Mock(return_value=SimpleNamespace(name="web")))
    monkeypatch.setattr(entrypoint.sys, "platform", "win32")

    with pytest.raises(asyncio.CancelledError):
        await entrypoint.main()

    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_closes_runtime_if_web_start_fails(monkeypatch):
    runtime = SimpleNamespace(workers=[], active_quota_count=1, close=AsyncMock())
    cfg = config()
    monkeypatch.setattr(entrypoint.SchedulerConfig, "from_toml", Mock(return_value=cfg))
    monkeypatch.setattr(entrypoint, "build_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(entrypoint, "_start_web_server", Mock(side_effect=RuntimeError("web")))

    with pytest.raises(RuntimeError, match="web"):
        await entrypoint.main()

    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_signals_and_finally_stop_and_close_once(monkeypatch):
    worker = SimpleNamespace(executor="rpc_crawl", run=AsyncMock(), stop=Mock())
    stack = SimpleNamespace(aclose=AsyncMock())
    runtime = WorkerRuntime([worker], stack, active_quota_count=1)
    cfg = config()
    loop = Mock()
    loop.add_signal_handler.side_effect = lambda signal, callback: callback()
    monkeypatch.setattr(entrypoint.SchedulerConfig, "from_toml", Mock(return_value=cfg))
    monkeypatch.setattr(entrypoint, "build_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(entrypoint, "_start_web_server", Mock(return_value=SimpleNamespace(name="web")))
    monkeypatch.setattr(entrypoint.sys, "platform", "linux")
    monkeypatch.setattr(entrypoint.asyncio, "get_event_loop", Mock(return_value=loop))

    await entrypoint.main()

    assert loop.add_signal_handler.call_count == 2
    worker.stop.assert_called_once_with()
    stack.aclose.assert_awaited_once()
