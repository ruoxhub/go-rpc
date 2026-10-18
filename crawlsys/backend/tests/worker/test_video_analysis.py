import logging
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from services.video_analysis.batch import BatchSummary, ModelSnapshot
from llm.model_factory import (
    BatchModelResolution,
    ModelResolution,
    TranscriptionResolution,
)
from models.task_config import TaskConfig, VideoAnalysisTaskConfig
from runtime_config.models import AnalysisVideoSettings, LlmSettings
from runtime_config.store import VideoAnalysisSnapshot
from tools.frame_sampling import FrameSamplingOptions, FrameSamplingStrategy
from worker.result import WorkerResult
from worker.video_analysis import VideoAnalysisWorker, build_analysis_service


def test_main_prioritizes_local_agents_package(tmp_path):
    third_party = tmp_path / "third_party"
    fake_agents = third_party / "agents"
    fake_agents.mkdir(parents=True)
    (fake_agents / "__init__.py").write_text(
        '"""Simulated third-party agents package."""\n', encoding="utf-8"
    )
    backend_dir = Path(__file__).resolve().parents[2]
    command = textwrap.dedent(
        f"""
        import importlib.util
        import sys
        sys.path.insert(0, {str(third_party)!r})
        spec = importlib.util.spec_from_file_location(
            "crawler_main", {str(backend_dir / 'main.py')!r}
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import agents.tiktok_video_analysis as analysis
        print(analysis.__file__)
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert str(backend_dir / "app" / "agents") in completed.stdout


def make_resolution(name="provider/model"):
    return ModelResolution(Mock(), name, 7)


def test_build_analysis_service_uses_langchain_model_and_optional_transcription(monkeypatch):
    resolution = make_resolution()
    target = SimpleNamespace(model="audio/model", api_key="secret", base_url="https://api.test")
    service = object()
    constructor = Mock(return_value=service)
    monkeypatch.setattr("worker.video_analysis.AnalysisService", constructor)
    result = build_analysis_service(
        resolution,
        LlmSettings(max_tokens=123, temperature=0.25, enable_thinking=True),
        AnalysisVideoSettings(
            is_base64=True,
            frame_sampling_strategy="timestamps",
            max_frames=6,
            frame_interval_seconds=2.5,
            frame_timestamps=(1.0, 3.5),
        ),
        transcription_target=target,
        transcriber=object(),
    )

    assert result is service
    kwargs = constructor.call_args.kwargs
    assert kwargs["model"] is resolution.model
    assert kwargs["media"].transcription_target is target
    assert kwargs["media"].frame_sampling == FrameSamplingOptions(
        strategy=FrameSamplingStrategy.TIMESTAMPS,
        max_frames=6,
        interval_seconds=2.5,
        timestamps=(1.0, 3.5),
    )


def test_build_analysis_service_omits_transcriber_when_unconfigured(monkeypatch):
    constructor = Mock(return_value=object())
    monkeypatch.setattr("worker.video_analysis.AnalysisService", constructor)
    build_analysis_service(
        make_resolution(), LlmSettings(), AnalysisVideoSettings()
    )

    media = constructor.call_args.kwargs["media"]
    assert media.transcriber is None
    assert media.transcription_target is None


def make_worker(batch, **overrides):
    values = dict(
        platform="video_analysis", repo=object(), db=object(), quota=object(),
        source=SimpleNamespace(bucket="videos"), analysis_service=object(),
        model="model-a", stale_timeout_seconds=90, analysis_repo=object(),
        clock=lambda: datetime(2026, 8, 1), batch_runner=batch,
    )
    values.update(overrides)
    return VideoAnalysisWorker(**values)


@pytest.mark.asyncio
async def test_static_run_batch_passes_options_and_maps_summary():
    batch = AsyncMock(return_value=BatchSummary(3, 1, 1, 1))
    worker = make_worker(batch)

    result = await worker.run_batch(
        VideoAnalysisTaskConfig(batch_size=4, max_attempts=7, review_route="G")
    )

    assert result == WorkerResult(total=3, succeeded=1, failed=1, skipped=1)
    assert batch.await_args.kwargs["model"] == ModelSnapshot(None, "model-a")
    assert batch.await_args.kwargs["batch_size"] == 4
    assert batch.await_args.kwargs["max_attempts"] == 7
    assert batch.await_args.kwargs["review_route"] == "G"


@pytest.mark.asyncio
async def test_analysis_still_delegates_claim_and_recovery_to_batch_runner():
    batch = AsyncMock(return_value=BatchSummary(0, 0, 0, 0))
    worker = make_worker(batch)

    await worker.run_batch(VideoAnalysisTaskConfig(batch_size=3, max_attempts=4))

    assert batch.await_args.kwargs["repository"] is worker.analysis_repo
    assert batch.await_args.kwargs["source"] is worker.source
    assert batch.await_args.kwargs["batch_size"] == 3
    assert batch.await_args.kwargs["max_attempts"] == 4


@pytest.mark.asyncio
async def test_batch_runner_failure_uses_safe_media_log_boundary(caplog):
    error = RuntimeError(
        "download https://private.invalid/video token=full-secret failed"
    )
    worker = make_worker(AsyncMock(side_effect=error))

    with caplog.at_level(logging.ERROR, logger="worker.video_analysis"):
        with pytest.raises(RuntimeError) as caught:
            await worker.run_batch(task_id=41)

    assert caught.value is error
    record = caplog.records[-1]
    assert record.task_id == 41
    assert record.consumer_key == "task:41"
    assert record.platform == "video_analysis"
    assert record.outcome == "failed"
    assert record.exception_type == "RuntimeError"
    assert "https://" not in record.getMessage()
    assert "private.invalid" not in record.getMessage()
    assert "full-secret" not in record.getMessage()


@pytest.mark.asyncio
async def test_execute_business_parses_model_override():
    worker = make_worker(AsyncMock())
    worker.run_batch = AsyncMock(return_value=WorkerResult())

    await worker.execute_business(SimpleNamespace(config={
        "executor": "video_analysis",
        "analysis": {"llm_model_id": 22, "review_route": "R"},
    }))

    assert worker.run_batch.await_args.args == (
        VideoAnalysisTaskConfig(llm_model_id=22, review_route="R"),
    )
    assert worker.run_batch.await_args.kwargs == {"task_id": None}


@pytest.mark.asyncio
async def test_dynamic_worker_resolves_analysis_and_transcription_models():
    settings = LlmSettings(
        default_analysis_model_id=7,
        default_transcription_model_id=8,
        max_tokens=321,
        temperature=0.5,
        enable_thinking=True,
    )
    store = SimpleNamespace(
        get_video_analysis_snapshot=AsyncMock(return_value=VideoAnalysisSnapshot(
            settings, AnalysisVideoSettings()
        )),
    )
    transcription = TranscriptionResolution(
        "audio/model", "secret", "https://provider.test"
    )
    model_factory = SimpleNamespace(
        resolve_batch=AsyncMock(return_value=BatchModelResolution(
            make_resolution("analysis/model"), transcription
        )),
    )
    service = SimpleNamespace(aclose=AsyncMock())
    service_factory = Mock(return_value=service)
    batch = AsyncMock(return_value=BatchSummary(0, 0, 0, 0))
    worker = VideoAnalysisWorker(
        platform="video_analysis", repo=object(), db=object(), quota=object(),
        config_store=store, source=object(), model_factory=model_factory,
        analysis_service_factory=service_factory, transcriber="transcriber",
        analysis_repo=object(), batch_runner=batch,
    )

    await worker.run_batch()

    store.get_video_analysis_snapshot.assert_awaited_once_with()
    model_factory.resolve_batch.assert_awaited_once_with(
        7, 8, temperature=0.5, max_tokens=321, enable_thinking=True
    )
    assert batch.await_args.kwargs["model"] == ModelSnapshot(7, "analysis/model")
    kwargs = service_factory.call_args.kwargs
    assert kwargs["transcription_target"].model == "audio/model"
    assert kwargs["transcription_target"].api_key == "secret"
    assert kwargs["transcriber"] == "transcriber"
    service.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_model_id_overrides_default_and_transcription_is_optional():
    settings = LlmSettings(default_analysis_model_id=7)
    store = SimpleNamespace(
        get_video_analysis_snapshot=AsyncMock(return_value=VideoAnalysisSnapshot(
            settings, AnalysisVideoSettings()
        )),
    )
    factory = SimpleNamespace(
        resolve_batch=AsyncMock(return_value=BatchModelResolution(
            make_resolution(), None
        )),
    )
    worker = VideoAnalysisWorker(
        platform="video_analysis", repo=object(), db=object(), quota=object(),
        config_store=store, source=object(), model_factory=factory,
        analysis_service_factory=Mock(return_value=SimpleNamespace()),
        analysis_repo=object(), batch_runner=AsyncMock(return_value=BatchSummary(0, 0, 0, 0)),
    )

    await worker.run_batch(VideoAnalysisTaskConfig(llm_model_id=22))

    factory.resolve_batch.assert_awaited_once_with(
        22, None, temperature=0.0, max_tokens=8192, enable_thinking=False
    )


@pytest.mark.asyncio
async def test_dynamic_worker_preserves_unspecified_thinking_setting():
    settings = SimpleNamespace(
        default_analysis_model_id=7,
        default_transcription_model_id=None,
        max_tokens=8192,
        temperature=0.0,
        enable_thinking=None,
    )
    store = SimpleNamespace(
        get_video_analysis_snapshot=AsyncMock(
            return_value=VideoAnalysisSnapshot(settings, AnalysisVideoSettings())
        )
    )
    factory = SimpleNamespace(
        resolve_batch=AsyncMock(
            return_value=BatchModelResolution(make_resolution(), None)
        )
    )
    worker = VideoAnalysisWorker(
        platform="video_analysis",
        repo=object(),
        db=object(),
        quota=object(),
        config_store=store,
        source=object(),
        model_factory=factory,
        analysis_service_factory=Mock(return_value=SimpleNamespace()),
        analysis_repo=object(),
        batch_runner=AsyncMock(return_value=BatchSummary(0, 0, 0, 0)),
    )

    await worker.run_batch()

    factory.resolve_batch.assert_awaited_once_with(
        7, None, temperature=0.0, max_tokens=8192, enable_thinking=None
    )


@pytest.mark.asyncio
async def test_missing_analysis_model_id_fails_before_batch():
    store = SimpleNamespace(
        get_video_analysis_snapshot=AsyncMock(return_value=VideoAnalysisSnapshot(
            LlmSettings(), AnalysisVideoSettings()
        )),
    )
    batch = AsyncMock()
    worker = VideoAnalysisWorker(
        platform="video_analysis", repo=object(), db=object(), quota=object(),
        config_store=store, source=object(), model_factory=SimpleNamespace(),
        analysis_repo=object(), batch_runner=batch,
    )

    with pytest.raises(ValueError, match="default_analysis_model_id"):
        await worker.run_batch()
    batch.assert_not_awaited()


def test_analysis_rejects_missing_or_conflicting_mode_dependencies():
    base = dict(platform="video_analysis", repo=object(), db=object(), quota=object(), source=object())
    with pytest.raises(ValueError, match="dynamic analysis"):
        VideoAnalysisWorker(**base)
    with pytest.raises(ValueError, match="static analysis"):
        VideoAnalysisWorker(**base, analysis_service=object())
