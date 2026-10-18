"""Safely merge public task fields into typed worker configuration."""
from __future__ import annotations

from typing import Literal

from models.task_config import (
    ExecutorType,
    TaskConfig,
    VideoAnalysisTaskConfig,
    VideoDownloadTaskConfig,
    WorkItemSinkConfig,
    WorkItemSourceConfig,
)


def merge_task_config(
    existing: TaskConfig | None,
    *,
    executor: ExecutorType,
    executor_explicit: bool,
    execution_mode: Literal["invoke_action", "publish_source"] = "invoke_action",
    execution_mode_explicit: bool = False,
    llm_model_id: int | None,
    llm_model_explicit: bool,
    source: WorkItemSourceConfig | None,
    sink: WorkItemSinkConfig,
    creating: bool,
    download: VideoDownloadTaskConfig | None = None,
    download_explicit: bool = False,
) -> TaskConfig:
    """Merge editable public fields without discarding executor-owned options."""
    config = existing.model_copy(deep=True) if existing else TaskConfig()
    target_executor = executor if executor_explicit else config.executor

    if creating and target_executor == "video_clean":
        raise ValueError(f"当前任务表单无法创建 {target_executor} 任务")
    if target_executor == "video_clean" and config.clean is None:
        raise ValueError("视频清洗任务缺少 clean 配置")
    if download_explicit:
        if target_executor != "video_download":
            raise ValueError("只有视频下载任务可以指定 download 配置")
        config.download = download
    if target_executor == "video_download" and config.download is None:
        raise ValueError("视频下载任务缺少 download 配置")
    if target_executor != "video_download":
        config.download = None

    config.executor = target_executor
    if execution_mode_explicit:
        config.execution_mode = execution_mode
    config.source = source
    config.sink = sink
    if target_executor == "video_analysis":
        analysis = (
            config.analysis.model_copy(deep=True)
            if config.analysis is not None
            else VideoAnalysisTaskConfig()
        )
        if llm_model_explicit:
            analysis.llm_model_id = llm_model_id
        config.analysis = analysis
    return TaskConfig.model_validate(config.model_dump())
