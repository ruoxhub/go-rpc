import pytest
from unittest.mock import AsyncMock

from api.crawler.schemas import TaskUpdate
from api.crawler.tasks import _config_from_payload
from core.task_config_merge import merge_task_config
from models.task_config import (
    RedisStreamSinkConfig,
    RedisStreamSourceConfig,
    SinkConfig,
    SourceConfig,
    TaskConfig,
    VideoAnalysisTaskConfig,
    VideoCleanTaskConfig,
    VideoDownloadTaskConfig,
)


def _common():
    return {
        "executor_explicit": True,
        "source": SourceConfig(table="new_items", key_column="id"),
        "sink": SinkConfig(mode="none"),
    }


def test_analysis_merge_preserves_nondefault_batch_settings():
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(
            batch_size=37,
            max_attempts=8,
            llm_model_id=11,
        ),
    )

    merged = merge_task_config(
        existing,
        executor="video_analysis",
        llm_model_id=29,
        llm_model_explicit=True,
        creating=False,
        **_common(),
    )

    assert merged.analysis == VideoAnalysisTaskConfig(
        batch_size=37,
        max_attempts=8,
        llm_model_id=29,
    )


def test_analysis_merge_explicit_none_clears_model_override():
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(llm_model_id=11),
    )

    merged = merge_task_config(
        existing,
        executor="video_analysis",
        llm_model_id=None,
        llm_model_explicit=True,
        creating=False,
        **_common(),
    )

    assert merged.analysis is not None
    assert merged.analysis.llm_model_id is None


def test_analysis_merge_omitted_model_keeps_override_and_executor():
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(
            batch_size=19,
            max_attempts=6,
            llm_model_id=11,
        ),
    )

    merged = merge_task_config(
        existing,
        executor="rpc_crawl",
        executor_explicit=False,
        llm_model_id=None,
        llm_model_explicit=False,
        source=None,
        sink=SinkConfig(),
        creating=False,
    )

    assert merged.executor == "video_analysis"
    assert merged.analysis == existing.analysis


@pytest.mark.asyncio
@pytest.mark.parametrize("review_route", ["R", "G"])
async def test_analysis_merge_updates_explicit_review_route(review_route):
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(review_route="R"),
    )

    merged = await _config_from_payload(
        object(),
        AsyncMock(),
        TaskUpdate(ba_id=1, review_route=review_route),
        existing=existing,
        creating=False,
    )

    assert merged.analysis.review_route == review_route


@pytest.mark.asyncio
async def test_analysis_merge_explicit_none_clears_review_route():
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(review_route="G"),
    )

    merged = await _config_from_payload(
        object(),
        AsyncMock(),
        TaskUpdate(ba_id=1, review_route=None),
        existing=existing,
        creating=False,
    )

    assert merged.analysis.review_route is None


@pytest.mark.asyncio
async def test_analysis_merge_omitted_review_route_preserves_existing_value():
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(review_route="G"),
    )

    merged = await _config_from_payload(
        object(),
        AsyncMock(),
        TaskUpdate(ba_id=1),
        existing=existing,
        creating=False,
    )

    assert merged.analysis.review_route == "G"


@pytest.mark.asyncio
async def test_switching_to_rpc_clears_analysis_review_route():
    existing = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(review_route="R"),
    )

    merged = await _config_from_payload(
        object(),
        AsyncMock(),
        TaskUpdate(ba_id=1, executor="rpc_crawl"),
        existing=existing,
        creating=False,
    )

    assert merged.executor == "rpc_crawl"
    assert merged.analysis.review_route is None


@pytest.mark.parametrize(
    ("executor", "existing"),
    [
        (
            "video_clean",
            TaskConfig(
                executor="video_clean",
                clean=VideoCleanTaskConfig(platforms=["tiktok"], batch_size=41),
            ),
        ),
        (
            "video_download",
            TaskConfig(
                executor="video_download",
                download=VideoDownloadTaskConfig(
                    batch_size=73,
                    min_grade=2,
                    use_proxy=False,
                    rps=1.5,
                ),
            ),
        ),
    ],
)
def test_specialized_executor_merge_preserves_its_config(executor, existing):
    merged = merge_task_config(
        existing,
        executor=executor,
        llm_model_id=None,
        llm_model_explicit=False,
        creating=False,
        **_common(),
    )

    assert merged.clean == existing.clean
    assert merged.download == existing.download


def test_download_merge_replaces_explicit_config_and_preserves_omitted_config():
    existing = TaskConfig(
        executor="video_download",
        download=VideoDownloadTaskConfig(max_attempts=7),
    )
    replacement = VideoDownloadTaskConfig(max_attempts=9)

    replaced = merge_task_config(
        existing,
        executor="video_download",
        llm_model_id=None,
        llm_model_explicit=False,
        download=replacement,
        download_explicit=True,
        creating=False,
        **_common(),
    )
    preserved = merge_task_config(
        replaced,
        executor="video_download",
        llm_model_id=None,
        llm_model_explicit=False,
        creating=False,
        **_common(),
    )

    assert replaced.download == replacement
    assert preserved.download == replacement


def test_switching_away_from_video_download_clears_download_config():
    merged = merge_task_config(
        TaskConfig(
            executor="video_download",
            download=VideoDownloadTaskConfig(max_attempts=7),
        ),
        executor="rpc_crawl",
        llm_model_id=None,
        llm_model_explicit=False,
        creating=False,
        **_common(),
    )

    assert merged.download is None


@pytest.mark.parametrize("download", [None, VideoDownloadTaskConfig()])
def test_download_config_rejects_null_or_non_download_executor(download):
    executor = "video_download" if download is None else "rpc_crawl"
    with pytest.raises(ValueError):
        merge_task_config(
            TaskConfig(),
            executor=executor,
            llm_model_id=None,
            llm_model_explicit=False,
            download=download,
            download_explicit=True,
            creating=False,
            **_common(),
        )


def test_rpc_merge_keeps_legacy_public_field_behavior():
    merged = merge_task_config(
        TaskConfig(
            executor="rpc_crawl",
            source=SourceConfig(table="old_items", key_column="old_id"),
            sink=SinkConfig(mode="standard"),
        ),
        executor="rpc_crawl",
        llm_model_id=None,
        llm_model_explicit=False,
        creating=False,
        **_common(),
    )

    assert merged.executor == "rpc_crawl"
    assert merged.source == SourceConfig(table="new_items", key_column="id")
    assert merged.sink == SinkConfig(mode="none")


def test_update_switches_database_source_to_stream_without_stale_fields():
    merged = merge_task_config(
        TaskConfig(source=SourceConfig(table="seed", key_column="id")),
        executor="rpc_crawl",
        executor_explicit=False,
        execution_mode="invoke_action",
        execution_mode_explicit=True,
        llm_model_id=None,
        llm_model_explicit=False,
        source=RedisStreamSourceConfig(
            stream="crawler:{detail}:stream",
            group="detail",
            dead_letter_stream="crawler:{detail}:dlq",
        ),
        sink=SinkConfig(),
        creating=False,
    )

    assert merged.source.type == "redis_stream"
    assert "table" not in merged.source.model_dump()


def test_merge_preserves_omitted_execution_mode():
    existing = TaskConfig(
        execution_mode="publish_source",
        source=SourceConfig(
            table="seed",
            key_column="id",
            completion={"column": "published"},
        ),
        sink=RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={"id": "id"},
        ),
    )

    merged = merge_task_config(
        existing,
        executor="rpc_crawl",
        executor_explicit=False,
        execution_mode="invoke_action",
        execution_mode_explicit=False,
        llm_model_id=None,
        llm_model_explicit=False,
        source=existing.source,
        sink=existing.sink,
        creating=False,
    )

    assert merged.execution_mode == "publish_source"


def test_update_switches_stream_sink_to_database_without_stale_fields():
    existing = TaskConfig(
        source=RedisStreamSourceConfig(
            stream="crawler:{detail}:stream",
            group="detail",
            dead_letter_stream="crawler:{detail}:dlq",
        ),
        sink=RedisStreamSinkConfig(
            stream="crawler:{result}:stream",
            param_map={"id": "id"},
        ),
    )

    merged = merge_task_config(
        existing,
        executor="rpc_crawl",
        executor_explicit=False,
        execution_mode="invoke_action",
        execution_mode_explicit=False,
        llm_model_id=None,
        llm_model_explicit=False,
        source=existing.source,
        sink=SinkConfig(mode="standard"),
        creating=False,
    )

    assert merged.sink.type == "database"
    assert "stream" not in merged.sink.model_dump()


def test_explicit_publish_source_mode_validates_io_combination():
    with pytest.raises(ValueError, match="publish_source requires"):
        merge_task_config(
            TaskConfig(),
            executor="rpc_crawl",
            executor_explicit=False,
            execution_mode="publish_source",
            execution_mode_explicit=True,
            llm_model_id=None,
            llm_model_explicit=False,
            source=SourceConfig(table="seed", key_column="id"),
            sink=SinkConfig(),
            creating=False,
        )


@pytest.mark.parametrize(
    ("executor", "message"),
    [("video_clean", "无法创建"), ("video_download", "缺少 download 配置")],
)
def test_create_rejects_executor_without_form_config(executor, message):
    with pytest.raises(ValueError, match=message):
        merge_task_config(
            None,
            executor=executor,
            executor_explicit=True,
            llm_model_id=None,
            llm_model_explicit=False,
            source=None,
            sink=SinkConfig(),
            creating=True,
        )
