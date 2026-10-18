import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from services.video_download import VideoDownloadService
from worker import (
    CrawlerWorker,
    VideoAnalysisWorker,
    VideoCleanWorker,
    VideoDownloadWorker,
    registry,
)
from worker.registry import WORKER_TYPES, WorkerRuntime, create_workers


def test_registry_has_exactly_four_executor_types():
    assert WORKER_TYPES == {
        "rpc_crawl": CrawlerWorker,
        "video_clean": VideoCleanWorker,
        "video_download": VideoDownloadWorker,
        "video_analysis": VideoAnalysisWorker,
    }


@pytest.mark.asyncio
async def test_build_runtime_keeps_media_workers_outside_action_stream(
    monkeypatch, tmp_path
):
    raw_redis = object()
    bucket_calls = []

    class Resource:
        def __init__(self, *args, **kwargs):
            pass

        async def aconnect(self):
            pass

        async def ainit_db(self):
            pass

        async def amigrate_db(self):
            pass

        async def amake_bucket(self, bucket):
            bucket_calls.append(bucket)

        def get_redis_obj(self):
            return raw_redis

        async def close(self):
            pass

        async def aclose(self):
            pass

    for name in (
        "SQLAlchemyDB", "RedisDB", "Bloom", "CrawlerPipeline", "RpcClient", "MinioDB"
    ):
        monkeypatch.setattr(registry, name, Resource)
    monkeypatch.setattr(registry, "_http_client", lambda proxy=None: Resource())
    monkeypatch.setattr(
        registry,
        "build_runtime_config_defaults",
        lambda *args: SimpleNamespace(legacy_llm=object()),
    )
    monkeypatch.setattr(registry, "migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr(
        registry.SiteSource,
        "load_active_quotas",
        AsyncMock(return_value=[SimpleNamespace(platform="tiktok")]),
    )
    captured = {}

    def capture_workers(dependencies):
        captured.update(dependencies)
        return []

    monkeypatch.setattr(registry, "create_workers", capture_workers)
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    config = SimpleNamespace(
        postgresql=SimpleNamespace(
            username="u", password="p", host="h", port=1, database="d"
        ),
        redis=SimpleNamespace(url="redis://local"),
        rpc_base_url="http://rpc",
        rpc_token="",
        rpc_timeout=1,
        minio=SimpleNamespace(
            host="h", port=1, username="u", password="p", secure=False
        ),
        poll_interval=1,
        default_loop_interval_seconds=3600,
        zombie_reap_after_seconds=600,
    )

    runtime = await registry.build_runtime(config, str(config_path))
    await runtime.close()

    for executor in ("video_clean", "video_download", "video_analysis"):
        assert "stream_queue" not in captured[executor]
        assert "sink_router" not in captured[executor]
    assert bucket_calls == []


def test_registry_uses_canonical_flat_module_identity():
    assert registry.VideoDownloadService is VideoDownloadService


@pytest.mark.asyncio
async def test_build_runtime_injects_stream_queue_from_config_redis(
    monkeypatch, tmp_path
):
    created_redis = MagicMock()
    created_redis.aconnect = AsyncMock()
    created_redis.aclose = AsyncMock()
    raw_redis = MagicMock()
    created_redis.get_redis_obj.return_value = raw_redis
    queue_factory = MagicMock(return_value=object())
    router_factory = MagicMock(return_value=object())

    class Resource:
        def __init__(self, *args, **kwargs):
            pass

        async def aconnect(self):
            pass

        async def ainit_db(self):
            pass

        async def amigrate_db(self):
            pass

        async def amake_bucket(self, bucket):
            pass

        async def close(self):
            pass

        async def aclose(self):
            pass

    db = Resource()
    pipeline = Resource()
    monkeypatch.setattr(registry, "SQLAlchemyDB", MagicMock(return_value=db))
    monkeypatch.setattr(registry, "RedisDB", MagicMock(return_value=created_redis))
    monkeypatch.setattr(registry, "Bloom", Resource)
    monkeypatch.setattr(registry, "CrawlerPipeline", MagicMock(return_value=pipeline))
    monkeypatch.setattr(registry, "RpcClient", Resource)
    monkeypatch.setattr(registry, "MinioDB", Resource)
    monkeypatch.setattr(registry, "_http_client", lambda proxy=None: Resource())
    monkeypatch.setattr(registry, "StreamQueue", queue_factory)
    monkeypatch.setattr(registry, "ResultSinkRouter", router_factory)
    monkeypatch.setattr(
        registry,
        "build_runtime_config_defaults",
        lambda *args: SimpleNamespace(legacy_llm=object()),
    )
    monkeypatch.setattr(registry, "migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr(registry.SiteSource, "load_active_quotas", AsyncMock(return_value=[]))

    captured_dependencies = None

    def create_test_workers(dependencies):
        nonlocal captured_dependencies
        captured_dependencies = dependencies
        return [
            SimpleNamespace(executor=executor, **worker_dependencies)
            for executor, worker_dependencies in dependencies.items()
        ]

    monkeypatch.setattr(registry, "create_workers", create_test_workers)
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    config = SimpleNamespace(
        postgresql=SimpleNamespace(
            username="u", password="p", host="h", port=1, database="d"
        ),
        redis=SimpleNamespace(url="redis://local"),
        rpc_token="",
        minio=SimpleNamespace(
            host="h", port=1, username="u", password="p", secure=False
        ),
        poll_interval=1,
        default_loop_interval_seconds=3600,
        zombie_reap_after_seconds=600,
    )

    runtime = await registry.build_runtime(config, str(config_path))
    crawler = next(worker for worker in runtime.workers if worker.executor == "rpc_crawl")

    created_redis.get_redis_obj.assert_called_once_with()
    queue_factory.assert_called_once_with(raw_redis)
    router_factory.assert_called_once_with(
        db=db,
        pipeline=pipeline,
        parser=registry.general_parser,
        stream_queue=queue_factory.return_value,
        persist_results=True,
    )
    assert crawler.stream_queue is queue_factory.return_value
    assert crawler.sink_router is router_factory.return_value
    for worker in runtime.workers:
        if worker.executor != "rpc_crawl":
            assert not hasattr(worker, "stream_queue")
            assert not hasattr(worker, "sink_router")
    assert captured_dependencies is not None
    assert captured_dependencies["rpc_crawl"]["stream_queue"] is queue_factory.return_value
    assert captured_dependencies["rpc_crawl"]["sink_router"] is router_factory.return_value
    for executor in ("video_clean", "video_download", "video_analysis"):
        assert "stream_queue" not in captured_dependencies[executor]
        assert "sink_router" not in captured_dependencies[executor]
    await runtime.close()
    await runtime.close()
    created_redis.aclose.assert_awaited_once_with()
    raw_redis.aclose.assert_not_called()


def test_create_workers_constructs_one_instance_per_executor():
    calls = []

    class FakeWorker:
        def __init__(self, *, executor):
            calls.append(executor)

    original = dict(WORKER_TYPES)
    try:
        WORKER_TYPES.clear()
        WORKER_TYPES.update({name: FakeWorker for name in original})
        workers = create_workers({name: {"executor": name} for name in original})
    finally:
        WORKER_TYPES.clear()
        WORKER_TYPES.update(original)

    assert len(workers) == 4
    assert calls == list(original)


@pytest.mark.parametrize("failure_index", [1, 2])
def test_create_workers_stops_partial_construction_in_reverse(failure_index):
    events = []

    class FakeWorker:
        def __init__(self, *, index):
            if index == failure_index:
                raise RuntimeError(f"construct:{index}")
            self.index = index

        def stop(self):
            events.append(self.index)

    original = dict(WORKER_TYPES)
    try:
        WORKER_TYPES.clear()
        WORKER_TYPES.update({name: FakeWorker for name in original})
        dependencies = {
            name: {"index": index} for index, name in enumerate(original)
        }
        with pytest.raises(RuntimeError, match=f"construct:{failure_index}"):
            create_workers(dependencies)
    finally:
        WORKER_TYPES.clear()
        WORKER_TYPES.update(original)

    assert events == list(reversed(range(failure_index)))


def test_create_workers_stop_error_does_not_hide_construction_error():
    class FakeWorker:
        def __init__(self, *, index):
            if index == 1:
                raise RuntimeError("construction error")

        def stop(self):
            raise ValueError("stop error")

    original = dict(WORKER_TYPES)
    try:
        WORKER_TYPES.clear()
        WORKER_TYPES.update({name: FakeWorker for name in original})
        dependencies = {
            name: {"index": index} for index, name in enumerate(original)
        }
        with pytest.raises(RuntimeError, match="construction error"):
            create_workers(dependencies)
    finally:
        WORKER_TYPES.clear()
        WORKER_TYPES.update(original)


@pytest.mark.asyncio
async def test_runtime_stops_workers_in_reverse_order_before_closing_resources():
    events = []
    workers = [
        SimpleNamespace(stop=lambda name=name: events.append(f"stop:{name}"))
        for name in ("crawler", "clean", "download", "analysis")
    ]
    stack = Mock()

    async def close_stack():
        events.append("resources")

    stack.aclose = close_stack
    runtime = WorkerRuntime(workers, stack)
    runtime.request_stop()
    runtime.request_stop()
    await runtime.close()
    await runtime.close()

    assert events == [
        "stop:analysis", "stop:download", "stop:clean", "stop:crawler",
        "resources",
    ]


@pytest.mark.asyncio
async def test_concurrent_close_survives_cancelled_waiter_and_closes_once():
    started = asyncio.Event()
    release = asyncio.Event()
    stack = SimpleNamespace(aclose=AsyncMock())

    async def close_resources():
        started.set()
        await release.wait()

    stack.aclose.side_effect = close_resources
    worker = SimpleNamespace(stop=Mock())
    runtime = WorkerRuntime([worker], stack)

    first = asyncio.create_task(runtime.close())
    await started.wait()
    second = asyncio.create_task(runtime.close())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    await second
    await runtime.close()

    worker.stop.assert_called_once_with()
    stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_task_error_is_shared_by_all_callers():
    stack = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    runtime = WorkerRuntime([], stack)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="close failed"):
            await runtime.close()

    stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_error", [RuntimeError("quota load failed"), asyncio.CancelledError()]
)
async def test_build_runtime_closes_constructed_resources_on_failure(
    monkeypatch, tmp_path, primary_error
):
    events = []
    raw_redis = MagicMock(aclose=AsyncMock())

    class Resource:
        def __init__(self, name):
            self.name = name

        async def aconnect(self):
            pass

        async def ainit_db(self):
            pass

        async def amigrate_db(self):
            pass

        async def amake_bucket(self, bucket):
            pass

        def get_redis_obj(self):
            return raw_redis

        async def close(self):
            events.append(self.name)
            raise ValueError("secret cleanup detail")

        async def aclose(self):
            events.append(self.name)
            raise ValueError("secret cleanup detail")

    monkeypatch.setattr(registry, "SQLAlchemyDB", lambda *args, **kwargs: Resource("db"))
    monkeypatch.setattr(
        registry, "RedisDB", lambda *args, **kwargs: Resource("config_redis")
    )
    monkeypatch.setattr(registry, "Bloom", lambda *args, **kwargs: Resource("bloom"))
    monkeypatch.setattr(
        registry, "CrawlerPipeline", lambda *args, **kwargs: Resource("pipeline")
    )
    monkeypatch.setattr(registry, "RpcClient", lambda *args, **kwargs: Resource("rpc"))
    monkeypatch.setattr(registry, "MinioDB", lambda *args, **kwargs: Resource("minio"))
    monkeypatch.setattr(
        registry, "_http_client", lambda proxy=None: Resource("direct_http")
    )
    monkeypatch.setattr(
        registry,
        "build_runtime_config_defaults",
        lambda *args: SimpleNamespace(legacy_llm=object()),
    )
    monkeypatch.setattr(registry, "migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr(
        registry.SiteSource,
        "load_active_quotas",
        AsyncMock(side_effect=primary_error),
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    config = SimpleNamespace(
        postgresql=SimpleNamespace(username="u", password="p", host="h", port=1, database="d"),
        redis=SimpleNamespace(url="redis://local"),
        rpc_base_url="http://rpc", rpc_token="", rpc_timeout=1,
        minio=SimpleNamespace(host="h", port=1, username="u", password="p", secure=False),
    )

    with pytest.raises(type(primary_error)) as caught:
        await registry.build_runtime(config, str(config_path))

    assert events == [
        "direct_http",
        "minio",
        "rpc",
        "pipeline",
        "bloom",
        "config_redis",
        "db",
    ]
    raw_redis.aclose.assert_not_awaited()
    assert caught.value is primary_error
    assert caught.value.__notes__ == ["Worker 资源清理失败: ValueError"]
    assert "secret cleanup detail" not in caught.value.__notes__[0]
