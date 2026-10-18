import asyncio
import time
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.errors import NodeCancelledError

import agents.tiktok_video_analysis as analysis
import tools.media as media_tools
from models.results import (
    AnalysisArtifacts,
    AnalysisRequest,
    AnalysisStage,
    ContentClassification,
    ContentType,
    DownloadedVideo,
    EvaluationDraft,
    InputMode,
    MediaProbe,
    ObservationResult,
    ProgressEvent,
    Topology,
    VideoMetadata,
)
from models.video_analysis_runtime import MediaCoverage, MediaTimeRange


def observation():
    return ObservationResult(
        content_classification=ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            topology=Topology.ONE_TAKE,
        )
    )


def evaluation(route=None):
    return EvaluationDraft(review_route=route)


def make_artifacts(path: Path):
    return AnalysisArtifacts(
        local_video_path=path,
        downloaded=False,
        mime_type="video/mp4",
        metadata=VideoMetadata(10.0, 1080, 1920, 30.0, True),
        media_probe=MediaProbe(10.0, "mp4", 1234, 8000, 2, "aac", 48000, 2),
        content_blocks=[
            {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,dmlkZW8="}}
        ],
        evidence_text="safe deterministic evidence",
        source_sha256="a" * 64,
        source_id=f"sha256:{'a' * 64}",
        coverage=MediaCoverage(
            input_mode=InputMode.FULL_VIDEO,
            sampled_timestamps=(),
            observed_ranges=(MediaTimeRange(0.0, 10.0),),
            unobserved_ranges=(),
            limitations=(),
        ),
    )


class RecordingMedia:
    def __init__(self, prepared, error=None):
        self.prepared = prepared
        self.error = error
        self.requests = []
        self.progress_callbacks = []
        self.cancellation_callbacks = []

    async def prepare(self, request, on_progress, check_cancelled):
        self.requests.append(request)
        self.progress_callbacks.append(on_progress)
        self.cancellation_callbacks.append(check_cancelled)
        check_cancelled()
        if on_progress is not None:
            on_progress(ProgressEvent(AnalysisStage.PROBING_MEDIA, "fake probe"))
        if self.error:
            raise self.error
        return self.prepared


class ScriptedModel:
    def __init__(self, observation_script=None, evaluation_script=None):
        self.scripts = {
            ObservationResult: list(observation_script or [observation()]),
            EvaluationDraft: list(evaluation_script or [evaluation()]),
        }
        self.invocations = []
        self.schema_calls = []

    def with_structured_output(self, schema):
        self.schema_calls.append(schema)

        async def invoke(messages):
            self.invocations.append(schema)
            outcome = self.scripts[schema].pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        return RunnableLambda(invoke)


class ConnectionConfigurationError(RuntimeError):
    pass


class RateLimitPolicyError(RuntimeError):
    pass


class NetworkSchemaError(RuntimeError):
    pass


def retryable_errors():
    request = httpx.Request("POST", "https://provider.test/model")
    return [
        TimeoutError("timeout body secret"),
        httpx.ConnectError("network body secret", request=request),
        httpx.HTTPStatusError(
            "rate limit body secret",
            request=request,
            response=httpx.Response(429, request=request),
        ),
    ]


def invalid_rate_limit_errors():
    request = httpx.Request("POST", "https://provider.test/model")

    class FakeResponse:
        status_code = 429

    return [
        httpx.HTTPStatusError(
            "fake response body secret",
            request=request,
            response=FakeResponse(),
        ),
        httpx.HTTPStatusError(
            "missing response body secret",
            request=request,
            response=None,
        ),
    ]


def make_service(path, *, model=None, media=None, store=None, prompt_loader=None):
    prepared = make_artifacts(path)
    media = media or RecordingMedia(prepared)
    model = model or ScriptedModel()
    store = store or Mock()
    service = analysis.AnalysisService(
        media=media,
        model=model,
        store=store,
        prompt_loader=prompt_loader or (lambda path: f"prompt:{path.name}"),
    )
    return service, media, model, store


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", [None, 0.0, -1.0])
async def test_invalid_media_never_reaches_structured_model(tmp_path, monkeypatch, duration):
    video = tmp_path / "invalid.mp4"
    if duration is not None:
        video.write_bytes(b"video")
        metadata = VideoMetadata(duration, 16, 9, 30.0, False)
        probe = MediaProbe(duration, "mp4", 5, None, 1, None, None, None)
        monkeypatch.setattr(media_tools, "require_executable", lambda name: name)
        monkeypatch.setattr(media_tools, "probe_video", lambda *args: metadata)
        monkeypatch.setattr(media_tools, "probe_media", lambda *args: probe)
    model = ScriptedModel()
    service = analysis.AnalysisService(
        media=analysis.MediaBoundary(),
        model=model,
        store=Mock(),
        prompt_loader=lambda path: "prompt",
    )

    expected = analysis.InputResolutionError if duration is None else analysis.MediaProcessingError
    with pytest.raises(expected):
        await service.run(AnalysisRequest(source=video))
    assert model.invocations == []


@pytest.mark.asyncio
async def test_success_records_stage_attempts_durations_and_saves_only_final_result(tmp_path):
    video = tmp_path / "local.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "result.json"
    events = []
    service, media, model, store = make_service(video)

    result = await service.run(
        AnalysisRequest(source=video, output_path=output), on_progress=events.append
    )

    assert media.requests[0].source == video.resolve()
    assert model.invocations == [ObservationResult, EvaluationDraft]
    store.save.assert_called_once_with(result, output)
    assert result.meta.timings.observation_attempts == 1
    assert result.meta.timings.evaluation_attempts == 1
    assert result.meta.timings.observation_duration_ms is not None
    assert result.meta.timings.evaluation_duration_ms is not None
    assert result.meta.timings.total_duration_ms is not None
    assert [(event.stage, event.attempt) for event in events] == [
        (AnalysisStage.RESOLVING_INPUT, None),
        (AnalysisStage.PROBING_MEDIA, None),
        (AnalysisStage.CALLING_MODEL, 1),
        (AnalysisStage.VALIDATING_RESULT, 1),
        (AnalysisStage.CALLING_MODEL, 1),
        (AnalysisStage.VALIDATING_RESULT, 1),
        (AnalysisStage.SAVING_RESULT, None),
        (AnalysisStage.COMPLETED, None),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("observation_script", "evaluation_script", "expected_invocations", "attempts"),
    [
        (
            [TimeoutError("provider body secret"), observation()],
            [evaluation()],
            [ObservationResult, ObservationResult, EvaluationDraft],
            (2, 1),
        ),
        (
            [observation()],
            [ConnectionError("api-key=secret"), evaluation()],
            [ObservationResult, EvaluationDraft, EvaluationDraft],
            (1, 2),
        ),
    ],
)
async def test_transient_retry_repeats_only_active_stage(
    tmp_path, observation_script, evaluation_script, expected_invocations, attempts
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    model = ScriptedModel(observation_script, evaluation_script)
    service, _, _, _ = make_service(video, model=model)

    result = await service.run(AnalysisRequest(source=video))

    assert model.invocations == expected_invocations
    assert result.meta.timings.observation_attempts == attempts[0]
    assert result.meta.timings.evaluation_attempts == attempts[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["observation", "evaluation"])
@pytest.mark.parametrize("retryable_error", retryable_errors())
async def test_explicit_transient_types_retry_each_active_stage_once(
    tmp_path, stage, retryable_error
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    observation_script = [observation()]
    evaluation_script = [evaluation()]
    if stage == "observation":
        observation_script = [retryable_error, observation()]
    else:
        evaluation_script = [retryable_error, evaluation()]
    model = ScriptedModel(observation_script, evaluation_script)
    service, _, _, _ = make_service(video, model=model)

    result = await service.run(AnalysisRequest(source=video))

    expected_attempts = (2, 1) if stage == "observation" else (1, 2)
    assert result.meta.timings.observation_attempts == expected_attempts[0]
    assert result.meta.timings.evaluation_attempts == expected_attempts[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "misleading_error",
    [
        ConnectionConfigurationError("provider body secret"),
        RateLimitPolicyError("provider body secret"),
        NetworkSchemaError("provider body secret"),
    ],
)
async def test_misleading_exception_names_are_not_retried(tmp_path, misleading_error):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    model = ScriptedModel([misleading_error, observation()], [evaluation()])
    service, _, _, _ = make_service(video, model=model)

    with pytest.raises(analysis.LLMRequestError) as caught:
        await service.run(AnalysisRequest(source=video))

    assert model.invocations == [ObservationResult]
    assert str(caught.value) == "模型请求失败"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize("rate_limit_error", invalid_rate_limit_errors())
async def test_fake_or_missing_429_response_is_not_retried_or_leaked(
    tmp_path, rate_limit_error
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    model = ScriptedModel([rate_limit_error, observation()], [evaluation()])
    service, _, _, store = make_service(video, model=model)

    with pytest.raises(analysis.LLMRequestError) as caught:
        await service.run(AnalysisRequest(source=video))

    assert model.invocations == [ObservationResult]
    assert str(caught.value) == "模型请求失败"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    store.save.assert_not_called()


@pytest.mark.asyncio
async def test_structured_output_binding_failure_is_sanitized_and_not_retried(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    class BindingFailureModel:
        calls = 0

        def with_structured_output(self, schema):
            self.calls += 1
            raise RuntimeError("provider response body api-key=secret")

    model = BindingFailureModel()
    service, _, _, store = make_service(video, model=model)

    with pytest.raises(analysis.LLMRequestError) as caught:
        await service.run(AnalysisRequest(source=video))

    assert model.calls == 1
    assert str(caught.value) == "模型结构化输出绑定失败"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    store.save.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("observation_script", "evaluation_script", "expected_invocations"),
    [
        ([RuntimeError("provider response: secret")], [evaluation()], [ObservationResult]),
        (
            [observation()],
            [RuntimeError("provider response: secret")],
            [ObservationResult, EvaluationDraft],
        ),
        ([{"invalid": True}], [evaluation()], [ObservationResult]),
        (
            [observation()],
            [{"review_route": "R", "specialized_score_r": None}],
            [ObservationResult, EvaluationDraft],
        ),
    ],
)
async def test_stage_failure_is_sanitized_not_retried_and_never_saves_partial(
    tmp_path, observation_script, evaluation_script, expected_invocations
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    store = Mock()
    model = ScriptedModel(observation_script, evaluation_script)
    service, _, _, _ = make_service(video, model=model, store=store)

    with pytest.raises(analysis.LLMRequestError) as caught:
        await service.run(AnalysisRequest(source=video, output_path=tmp_path / "out.json"))

    assert str(caught.value) in {"模型请求失败", "模型结构化输出校验失败"}
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert model.invocations == expected_invocations
    store.save.assert_not_called()


@pytest.mark.asyncio
async def test_pre_media_prompt_failure_does_not_prepare_or_invoke_or_save(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    media = RecordingMedia(make_artifacts(video))
    model = ScriptedModel()
    store = Mock()
    service, _, _, _ = make_service(
        video,
        media=media,
        model=model,
        store=store,
        prompt_loader=lambda path: (_ for _ in ()).throw(OSError("token=secret")),
    )

    with pytest.raises(analysis.InputResolutionError, match="无法读取分析提示词"):
        await service.run(AnalysisRequest(source=video))
    assert media.requests == []
    assert model.invocations == []
    store.save.assert_not_called()


@pytest.mark.asyncio
async def test_media_failure_is_not_retried_and_never_invokes_or_saves(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    media = RecordingMedia(make_artifacts(video), analysis.MediaProcessingError("secret"))
    model = ScriptedModel()
    store = Mock()
    service, _, _, _ = make_service(video, media=media, model=model, store=store)

    with pytest.raises(analysis.MediaProcessingError) as caught:
        await service.run(AnalysisRequest(source=video))
    assert str(caught.value) == "媒体证据准备失败"
    assert caught.value.__context__ is None
    assert len(media.requests) == 1
    assert model.invocations == []
    store.save.assert_not_called()


@pytest.mark.asyncio
async def test_assembly_failure_is_not_retried_and_never_saves(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    model = ScriptedModel()
    store = Mock()
    service, _, _, _ = make_service(video, model=model, store=store)

    def fail_assembly(**kwargs):
        raise ValueError("deterministic assembly failure")

    monkeypatch.setattr(analysis, "assemble_analysis_result", fail_assembly)
    with pytest.raises(ValueError, match="deterministic assembly failure"):
        await service.run(AnalysisRequest(source=video))
    assert model.invocations == [ObservationResult, EvaluationDraft]
    store.save.assert_not_called()


@pytest.mark.asyncio
async def test_total_duration_includes_slow_assembly_but_saves_once(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    store = Mock()
    service, _, _, _ = make_service(video, store=store)
    real_assemble = analysis.assemble_analysis_result

    def slow_assemble(**kwargs):
        time.sleep(0.03)
        return real_assemble(**kwargs)

    monkeypatch.setattr(analysis, "assemble_analysis_result", slow_assemble)
    result = await service.run(
        AnalysisRequest(source=video, output_path=tmp_path / "result.json")
    )

    assert result.meta.timings.total_duration_ms >= 30
    store.save.assert_called_once_with(result, tmp_path / "result.json")


@pytest.mark.asyncio
async def test_save_failure_is_sanitized_and_cleanup_still_runs(tmp_path, monkeypatch):
    events = []
    real_directory = analysis.tempfile.TemporaryDirectory

    class RecordingDirectory:
        def __init__(self):
            self.delegate = real_directory()
            self.name = self.delegate.name

        def cleanup(self):
            events.append("cleanup")
            self.delegate.cleanup()

    class FailingStore:
        def save(self, result, output_path):
            raise OSError(f"private path={output_path}; token=secret")

    monkeypatch.setattr(analysis.tempfile, "TemporaryDirectory", RecordingDirectory)
    monkeypatch.setattr(analysis, "is_video_url", lambda source: True)

    def download(source, target):
        path = Path(target) / "downloaded.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "tiktok", "title", 1.0, source)

    monkeypatch.setattr(analysis, "download_video", download)
    service, _, _, _ = make_service(tmp_path / "placeholder.mp4", store=FailingStore())

    with pytest.raises(analysis.ResultStorageError) as caught:
        await service.run(
            AnalysisRequest(
                source="https://example.test/video",
                output_path=tmp_path / "private-result.json",
            )
        )

    assert str(caught.value) == "无法保存分析结果"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert events == ["cleanup"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cancelled_node",
    [
        "resolve_input",
        "load_prompts",
        "prepare_evidence",
        "observe_video",
        "review_and_score",
        "assemble_result",
        "save_result",
    ],
)
async def test_cancelled_error_is_checked_at_each_node_entry_without_partial_save(
    tmp_path, monkeypatch, cancelled_node
):
    node_order = [
        "resolve_input",
        "load_prompts",
        "prepare_evidence",
        "observe_video",
        "review_and_score",
        "assemble_result",
        "save_result",
    ]
    paths = configure_remote_with_cleanup_tracking(monkeypatch)
    trace = []
    bindings = []
    control = {"armed": cancelled_node == "resolve_input"}
    cancelled = asyncio.CancelledError(f"cancel before {cancelled_node}")
    real_assemble = analysis.assemble_analysis_result

    def is_cancelled():
        if control["armed"]:
            raise cancelled
        return False

    def on_progress(event):
        if event.stage is AnalysisStage.RESOLVING_INPUT:
            trace.append("resolve_input")
            if cancelled_node == "load_prompts":
                control["armed"] = True

    prompt_calls = 0

    def load_prompt(path):
        nonlocal prompt_calls
        prompt_calls += 1
        if prompt_calls == 1:
            trace.append("load_prompts")
            if cancelled_node == "prepare_evidence":
                control["armed"] = True
        return path.name

    class NodeAwareMedia:
        async def prepare(self, request, on_progress, check_cancelled):
            trace.append("prepare_evidence")
            check_cancelled()
            prepared = make_artifacts(Path(request.source))
            if cancelled_node == "observe_video":
                control["armed"] = True
            return prepared

    class NodeAwareModel:
        def with_structured_output(self, schema):
            bindings.append(
                (
                    "observe_video"
                    if schema is ObservationResult
                    else "review_and_score",
                    schema,
                )
            )

            async def invoke(messages):
                if schema is ObservationResult:
                    trace.append("observe_video")
                    if cancelled_node == "review_and_score":
                        control["armed"] = True
                    return observation()
                trace.append("review_and_score")
                if cancelled_node == "assemble_result":
                    control["armed"] = True
                return evaluation()

            return RunnableLambda(invoke)

    def assemble_then_arm(**kwargs):
        trace.append("assemble_result")
        result = real_assemble(**kwargs)
        if cancelled_node == "save_result":
            control["armed"] = True
        return result

    monkeypatch.setattr(analysis, "assemble_analysis_result", assemble_then_arm)
    store = Mock()
    service = analysis.AnalysisService(
        media=NodeAwareMedia(),
        model=NodeAwareModel(),
        store=store,
        prompt_loader=load_prompt,
    )

    with pytest.raises(asyncio.CancelledError) as caught:
        await service.run(
            AnalysisRequest(
                source="https://example.test/video",
                output_path=tmp_path / "out.json",
            ),
            on_progress=on_progress,
            is_cancelled=is_cancelled,
        )

    assert caught.value is cancelled
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert trace == node_order[: node_order.index(cancelled_node)]
    expected_bindings = []
    if node_order.index(cancelled_node) > node_order.index("observe_video"):
        expected_bindings.append(("observe_video", ObservationResult))
    if node_order.index(cancelled_node) > node_order.index("review_and_score"):
        expected_bindings.append(("review_and_score", EvaluationDraft))
    assert bindings == expected_bindings
    store.save.assert_not_called()
    assert paths and not paths[0].exists()


@pytest.mark.asyncio
async def test_media_fake_records_and_respects_progress_and_cancellation(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    events = []
    service, media, _, _ = make_service(video)

    await service.run(AnalysisRequest(source=video), on_progress=events.append)

    assert media.progress_callbacks[0] is not None
    assert media.cancellation_callbacks[0] is not None
    assert any(event.stage is AnalysisStage.PROBING_MEDIA for event in events)


def configure_remote_with_cleanup_tracking(monkeypatch):
    paths = []
    real_directory = analysis.tempfile.TemporaryDirectory

    class TrackingDirectory:
        def __init__(self):
            self.delegate = real_directory()
            self.name = self.delegate.name
            paths.append(Path(self.name))

        def cleanup(self):
            self.delegate.cleanup()

    def download(source, target):
        path = Path(target) / "downloaded.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "tiktok", "title", 1.0, source)

    monkeypatch.setattr(analysis.tempfile, "TemporaryDirectory", TrackingDirectory)
    monkeypatch.setattr(analysis, "is_video_url", lambda source: True)
    monkeypatch.setattr(analysis, "download_video", download)
    return paths


@pytest.mark.asyncio
async def test_cancellation_during_retry_sleep_stops_retry_save_and_cleans(
    tmp_path, monkeypatch
):
    paths = configure_remote_with_cleanup_tracking(monkeypatch)
    first_failed = asyncio.Event()

    class RetrySleepModel(ScriptedModel):
        def with_structured_output(self, schema):
            async def invoke(messages):
                self.invocations.append(schema)
                if schema is ObservationResult:
                    first_failed.set()
                    raise TimeoutError("retry timeout")
                return evaluation()

            return RunnableLambda(invoke)

    model = RetrySleepModel()
    store = Mock()
    service, _, _, _ = make_service(
        tmp_path / "placeholder.mp4", model=model, store=store
    )
    task = asyncio.create_task(
        service.run(AnalysisRequest(source="https://example.test/video"))
    )
    await first_failed.wait()
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert model.invocations == [ObservationResult]
    store.save.assert_not_called()
    assert paths and not paths[0].exists()


@pytest.mark.asyncio
async def test_cancellation_during_second_attempt_stops_save_and_cleans(
    tmp_path, monkeypatch
):
    paths = configure_remote_with_cleanup_tracking(monkeypatch)
    second_started = asyncio.Event()
    blocker = asyncio.Event()

    class SecondAttemptModel(ScriptedModel):
        def with_structured_output(self, schema):
            attempts = 0

            async def invoke(messages):
                nonlocal attempts
                attempts += 1
                self.invocations.append(schema)
                if schema is ObservationResult and attempts == 1:
                    raise TimeoutError("retry timeout")
                if schema is ObservationResult:
                    second_started.set()
                    await blocker.wait()
                    return observation()
                return evaluation()

            return RunnableLambda(invoke)

    model = SecondAttemptModel()
    store = Mock()
    service, _, _, _ = make_service(
        tmp_path / "placeholder.mp4", model=model, store=store
    )
    task = asyncio.create_task(
        service.run(AnalysisRequest(source="https://example.test/video"))
    )
    await second_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert model.invocations == [ObservationResult, ObservationResult]
    store.save.assert_not_called()
    assert paths and not paths[0].exists()


@pytest.mark.asyncio
async def test_asyncio_cancelled_error_propagates_unchanged(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    cancelled = asyncio.CancelledError("cancel identity")
    model = ScriptedModel([cancelled], [evaluation()])
    service, _, _, _ = make_service(video, model=model)

    with pytest.raises(asyncio.CancelledError) as caught:
        await service.run(AnalysisRequest(source=video))
    assert caught.value is cancelled
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.asyncio
async def test_non_cancel_node_cancelled_error_is_not_misidentified(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    service, _, _, _ = make_service(video)
    node_error = NodeCancelledError("observe_video")

    async def fail_graph(state):
        raise node_error

    monkeypatch.setattr(service.graph, "ainvoke", fail_graph)
    with pytest.raises(NodeCancelledError) as caught:
        await service.run(AnalysisRequest(source=video))
    assert caught.value is node_error


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
async def test_remote_temporary_directory_is_cleaned_for_every_outcome(
    tmp_path, monkeypatch, outcome
):
    events = []
    paths = []
    real_directory = analysis.tempfile.TemporaryDirectory

    class RecordingDirectory:
        def __init__(self):
            self.delegate = real_directory()
            self.name = self.delegate.name
            self.cleaned = False
            paths.append(Path(self.name))

        def cleanup(self):
            if self.cleaned:
                return
            events.append(("cleanup-start", Path(self.name).is_dir()))
            self.delegate.cleanup()
            self.cleaned = True
            events.append(("cleanup-end", Path(self.name).exists()))

    monkeypatch.setattr(analysis.tempfile, "TemporaryDirectory", RecordingDirectory)
    monkeypatch.setattr(analysis, "is_video_url", lambda source: True)

    def download(source, target):
        path = Path(target) / "downloaded.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "tiktok", "title", 1.0, source)

    monkeypatch.setattr(analysis, "download_video", download)
    placeholder = tmp_path / "placeholder.mp4"
    model = ScriptedModel(
        [RuntimeError("provider body secret")] if outcome == "failure" else None
    )
    service, _, _, _ = make_service(placeholder, model=model)

    if outcome == "success":
        await service.run(AnalysisRequest(source="https://example.test/video"))
    elif outcome == "failure":
        with pytest.raises(analysis.LLMRequestError):
            await service.run(AnalysisRequest(source="https://example.test/video"))
    else:
        checks = iter([False, True])
        with pytest.raises(analysis.AnalysisCancelled):
            await service.run(
                AnalysisRequest(source="https://example.test/video"),
                is_cancelled=lambda: next(checks),
            )

    assert paths
    assert events[-2:] == [("cleanup-start", True), ("cleanup-end", False)]
    assert not paths[0].exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
async def test_cleanup_failure_never_replaces_primary_outcome(
    tmp_path, monkeypatch, outcome
):
    class FailingCleanupDirectory:
        def __init__(self):
            self.name = str(tmp_path / "remote-temp")
            Path(self.name).mkdir()

        def cleanup(self):
            raise OSError("cleanup token=secret")

    def download(source, target):
        path = Path(target) / "downloaded.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "tiktok", "title", 1.0, source)

    monkeypatch.setattr(analysis.tempfile, "TemporaryDirectory", FailingCleanupDirectory)
    monkeypatch.setattr(analysis, "is_video_url", lambda source: True)
    monkeypatch.setattr(analysis, "download_video", download)
    cancelled = asyncio.CancelledError("original cancel")
    model = ScriptedModel(
        [RuntimeError("provider body secret")]
        if outcome == "failure"
        else [cancelled]
        if outcome == "cancelled"
        else None
    )
    service, _, _, _ = make_service(tmp_path / "placeholder.mp4", model=model)

    with pytest.warns(RuntimeWarning, match="分析临时目录清理失败"):
        if outcome == "success":
            result = await service.run(AnalysisRequest(source="https://example.test/video"))
            assert result.meta.schema_version == "v4.0"
        elif outcome == "failure":
            with pytest.raises(analysis.LLMRequestError, match="模型请求失败"):
                await service.run(AnalysisRequest(source="https://example.test/video"))
        else:
            with pytest.raises(asyncio.CancelledError) as caught:
                await service.run(AnalysisRequest(source="https://example.test/video"))
            assert caught.value is cancelled
            assert caught.value.__cause__ is None
            assert caught.value.__context__ is None


class StatelessMedia:
    async def prepare(self, request, on_progress, check_cancelled):
        check_cancelled()
        if on_progress is not None:
            on_progress(ProgressEvent(AnalysisStage.PROBING_MEDIA, str(request.source)))
        return make_artifacts(Path(request.source))


class StatelessModel:
    def with_structured_output(self, schema):
        async def invoke(messages):
            return observation() if schema is ObservationResult else evaluation()

        return RunnableLambda(invoke)


@pytest.mark.asyncio
async def test_concurrent_service_calls_isolate_and_reset_contextvars(tmp_path):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"video")
    second.write_bytes(b"video")
    service = analysis.AnalysisService(
        media=StatelessMedia(),
        model=StatelessModel(),
        store=Mock(),
        prompt_loader=lambda path: path.name,
    )
    first_events = []
    second_events = []

    first_result, second_result = await asyncio.gather(
        service.run(
            AnalysisRequest(source=first),
            on_progress=lambda event: first_events.append(("first", event)),
            is_cancelled=lambda: False,
        ),
        service.run(
            AnalysisRequest(source=second),
            on_progress=lambda event: second_events.append(("second", event)),
            is_cancelled=lambda: False,
        ),
    )

    assert first_result.meta.schema_version == second_result.meta.schema_version == "v4.0"
    assert first_events and all(label == "first" for label, _ in first_events)
    assert second_events and all(label == "second" for label, _ in second_events)
    assert service.graph._analysis_progress_var.get() is None
    assert service.graph._analysis_cancellation_var.get() is None
    assert service.graph._analysis_started_var.get() is None


@pytest.mark.asyncio
async def test_nested_service_call_restores_outer_context(tmp_path):
    outer = tmp_path / "outer.mp4"
    nested = tmp_path / "nested.mp4"
    outer.write_bytes(b"video")
    nested.write_bytes(b"video")
    outer_events = []
    nested_events = []

    class NestedModel:
        service = None
        nested_started = False

        def with_structured_output(self, schema):
            async def invoke(messages):
                if schema is ObservationResult and not self.nested_started:
                    self.nested_started = True
                    await self.service.run(
                        AnalysisRequest(source=nested),
                        on_progress=nested_events.append,
                        is_cancelled=lambda: False,
                    )
                return observation() if schema is ObservationResult else evaluation()

            return RunnableLambda(invoke)

    model = NestedModel()
    service = analysis.AnalysisService(
        media=StatelessMedia(),
        model=model,
        store=Mock(),
        prompt_loader=lambda path: path.name,
    )
    model.service = service

    await service.run(
        AnalysisRequest(source=outer),
        on_progress=outer_events.append,
        is_cancelled=lambda: False,
    )

    assert sum(event.stage is AnalysisStage.COMPLETED for event in outer_events) == 1
    assert sum(event.stage is AnalysisStage.COMPLETED for event in nested_events) == 1
    assert outer_events[-1].stage is AnalysisStage.COMPLETED
    assert service.graph._analysis_progress_var.get() is None
    assert service.graph._analysis_cancellation_var.get() is None
    assert service.graph._analysis_started_var.get() is None
