"""清洗后视频分析 Worker。"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agents.tiktok_video_analysis import AnalysisService, JsonResultStore, MediaBoundary
from services.video_analysis.batch import BatchSummary, ModelSnapshot, run_analysis_batch
from services.video_analysis.repository import VideoAnalysisRepository
from llm.model_factory import LitellmModelFactory, ModelResolution
from llm.transcription import LiteLlmTranscriber, TranscriptionTarget
from models import BusTask
from models.task_config import TaskConfig, VideoAnalysisTaskConfig
from runtime_config.models import AnalysisVideoSettings, LlmSettings
from tools.frame_sampling import FrameSamplingOptions, FrameSamplingStrategy

from .base import BaseWorker
from .media_logging import log_media_event
from .result import WorkerResult


logger = logging.getLogger(__name__)


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_analysis_service(
    resolution: ModelResolution,
    settings: LlmSettings,
    video: AnalysisVideoSettings,
    *,
    transcription_target: TranscriptionTarget | None = None,
    transcriber: Any = None,
) -> AnalysisService:
    """从已解析的 LangChain 模型构造分析服务。"""
    return AnalysisService(
        media=MediaBoundary(
            is_base64=video.is_base64,
            frame_sampling=FrameSamplingOptions(
                strategy=FrameSamplingStrategy(video.frame_sampling_strategy),
                max_frames=video.max_frames,
                interval_seconds=video.frame_interval_seconds,
                timestamps=video.frame_timestamps,
            ),
            transcriber=(transcriber or LiteLlmTranscriber()) if transcription_target else None,
            transcription_target=transcription_target,
        ),
        model=resolution.model,
        store=JsonResultStore(),
        prompt_loader=load_prompt,
    )


class VideoAnalysisWorker(BaseWorker):
    executor = "video_analysis"

    def __init__(
        self,
        *args: Any,
        source: Any,
        analysis_service: AnalysisService | None = None,
        model: str | None = None,
        analysis_service_factory: Callable[..., AnalysisService] = build_analysis_service,
        catalog: Any = None,
        model_factory: LitellmModelFactory | None = None,
        transcriber: Any = None,
        stale_timeout_seconds: float = 7200,
        analysis_repo: VideoAnalysisRepository | None = None,
        clock: Callable[[], datetime] | None = None,
        batch_runner: Callable[..., Any] = run_analysis_batch,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        dynamic = analysis_service is None
        if dynamic and (
            self.config_store is None
            or (catalog is None and model_factory is None)
            or not callable(analysis_service_factory)
        ):
            raise ValueError("dynamic analysis requires config_store and service factory")
        if not dynamic and (model is None or self.config_store is not None):
            raise ValueError("static analysis requires analysis_service and model only")
        self.source = source
        self.analysis_service = analysis_service
        self.model = model
        self._analysis_service_factory = analysis_service_factory
        self._model_factory = model_factory or (LitellmModelFactory(catalog) if catalog else None)
        self._transcriber = transcriber
        self.stale_timeout_seconds = stale_timeout_seconds
        self.analysis_repo = analysis_repo or VideoAnalysisRepository(self.db)
        self._clock = clock or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))
        self._batch_runner = batch_runner

    async def execute_business(self, task: BusTask) -> WorkerResult:
        config = task.config if isinstance(task.config, TaskConfig) else TaskConfig.model_validate(task.config or {})
        return await self.run_batch(config.analysis, task_id=getattr(task, "task_id", None))

    async def run_batch(
        self,
        options: VideoAnalysisTaskConfig | None = None,
        *,
        task_id: int | None = None,
    ) -> WorkerResult:
        options = options or VideoAnalysisTaskConfig()
        batch_id = uuid.uuid4().hex
        started_at = time.monotonic()
        service = self.analysis_service
        model = self.model
        model_id = None
        dynamic = service is None
        if dynamic:
            snapshot = await self.config_store.get_video_analysis_snapshot()
            settings = snapshot.llm
            model_id = options.llm_model_id or settings.default_analysis_model_id
            if model_id is None:
                raise ValueError("LLM default_analysis_model_id 未配置")
            resolutions = await self._model_factory.resolve_batch(
                model_id,
                settings.default_transcription_model_id,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                enable_thinking=settings.enable_thinking,
            )
            resolution = resolutions.analysis
            transcription_target = None
            if resolutions.transcription is not None:
                transcription = resolutions.transcription
                transcription_target = TranscriptionTarget(
                    model=transcription.name,
                    api_key=transcription.api_key,
                    base_url=transcription.base_url,
                )
            service = self._analysis_service_factory(
                resolution,
                settings,
                snapshot.video,
                transcription_target=transcription_target,
                transcriber=self._transcriber,
            )
            model = resolution.name
            model_id = resolution.model_id
        try:
            summary = await self._batch_runner(
                repository=self.analysis_repo, source=self.source,
                analysis_service=service, model=ModelSnapshot(model_id, model),
                review_route=options.review_route,
                batch_size=options.batch_size, max_attempts=options.max_attempts,
                stale_timeout_seconds=self.stale_timeout_seconds, now=self._clock(),
            )
        except BaseException as primary_error:
            if dynamic:
                try:
                    close = getattr(service, "aclose", None)
                    if close is not None:
                        await close()
                except BaseException as cleanup_error:
                    primary_error.add_note(
                        f"analysis service cleanup failed: {type(cleanup_error).__name__}"
                    )
            if isinstance(primary_error, Exception):
                log_media_event(
                    logger,
                    logging.ERROR,
                    task_id=task_id,
                    consumer_key=f"task:{task_id}" if task_id is not None else None,
                    platform=self.platform,
                    batch_id=batch_id,
                    outcome="failed",
                    latency_ms=max(0, int((time.monotonic() - started_at) * 1000)),
                    exception_type=type(primary_error).__name__,
                    error=primary_error,
                )
            raise
        if dynamic:
            close = getattr(service, "aclose", None)
            if close is not None:
                await close()
        return self.result_from_summary(summary)

    @staticmethod
    def result_from_summary(summary: BatchSummary) -> WorkerResult:
        return WorkerResult(
            total=summary.claimed,
            succeeded=summary.succeeded,
            failed=summary.failed,
            skipped=summary.skipped,
        )
