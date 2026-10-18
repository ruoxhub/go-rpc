from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.runnables import RunnableLambda

from agents.tiktok_video_analysis import build_analysis_graph
from models.results import (
    AnalysisArtifacts,
    AnalysisRequest,
    ContentClassification,
    ContentType,
    EvaluationDraft,
    InputMode,
    ObservationResult,
    Topology,
    VideoMetadata,
)
from models.video_analysis_runtime import MediaCoverage, MediaTimeRange


@pytest.mark.asyncio
async def test_gemini_compatible_multimodal_content_stays_provider_neutral(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    captured = []
    schemas = []
    blocks = [
        {"type": "text", "text": "before"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,aW1hZ2U="},
        },
        {
            "type": "video_url",
            "video_url": {"url": "data:video/mp4;base64,dmlkZW8="},
        },
    ]

    class CompatibleChatModel:
        def with_structured_output(self, schema):
            schemas.append(schema)

            async def invoke(messages):
                captured.append(messages[-1].content)
                if schema is ObservationResult:
                    return ObservationResult(
                        content_classification=ContentClassification(
                            primary_type=ContentType.FUNCTIONAL_PROOF,
                            topology=Topology.ONE_TAKE,
                        )
                    )
                return EvaluationDraft(review_route=None)

            return RunnableLambda(invoke)

    class Media:
        async def prepare(self, request, on_progress, check_cancelled):
            check_cancelled()
            return AnalysisArtifacts(
                local_video_path=Path(request.source),
                downloaded=False,
                mime_type="video/mp4",
                metadata=VideoMetadata(10.0, 1080, 1920, 30.0, True),
                content_blocks=blocks,
                evidence_text="after",
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

    graph = build_analysis_graph(
        media=Media(),
        model=CompatibleChatModel(),
        store=Mock(),
        prompt_loader=lambda path: "prompt",
    )
    state = await graph.ainvoke({"request": AnalysisRequest(source=video)})

    assert schemas == [ObservationResult, EvaluationDraft]
    assert state["final_result"].meta.schema_version == "v4.0"
    assert captured[0][0] == {"type": "text", "text": "ORIGINAL MEDIA"}
    assert captured[1][0] == {"type": "text", "text": "ORIGINAL MEDIA"}
    assert captured[0][1:4] == blocks
    assert captured[1][1:4] == blocks
    assert "after" in captured[0][4]["text"]
    assert "after" in captured[1][4]["text"]
