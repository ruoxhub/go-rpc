"""Offline latest-model contract fixtures parsed through the real models and assembler."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from app.services.video_analysis.assembly import assemble_analysis_result
from models.results import (
    AnalysisArtifacts,
    AnalysisRequest,
    AnalysisResult,
    AnalysisTimings,
    EvaluationDraft,
    InputMode,
    ObservationResult,
    VideoMetadata,
)
from models.video_analysis_runtime import MediaCoverage, MediaTimeRange


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "latest"

FIXTURE_NAMES = (
    "normal_r.json",
    "g0_product_failure.json",
    "missing_release_phase.json",
    "sampled_frames_insufficient.json",
    "evidence_conflict.json",
    "missing_route.json",
)

FORBIDDEN_FIELDS = ("recommended_grade", "ai_video_prompt", "iteration", "post_production")
ABSOLUTE_PATH_MARKERS = ("C:\\", "c:\\", ":/", "\\private\\", "/private/", "file://")
SECRET_PATTERNS = ("sk-", "api_key", "api-key", "bearer ", "token=")
LOW_CONFIDENCE_THRESHOLD = 0.5


def _iter_json_keys(node) -> object:
    if isinstance(node, dict):
        yield from node
        for value in node.values():
            yield from _iter_json_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_keys(item)


def _iter_json_strings(node) -> object:
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_strings(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_json_strings(value)


def _coverage(payload: dict) -> MediaCoverage:
    return MediaCoverage(
        input_mode=InputMode(payload["input_mode"]),
        sampled_timestamps=tuple(payload.get("sampled_timestamps", [])),
        observed_ranges=tuple(
            MediaTimeRange(**range_payload) for range_payload in payload["observed_ranges"]
        ),
        unobserved_ranges=tuple(
            MediaTimeRange(**range_payload) for range_payload in payload["unobserved_ranges"]
        ),
        limitations=tuple(payload.get("limitations", [])),
    )


def _artifacts(payload: dict) -> AnalysisArtifacts:
    return AnalysisArtifacts(
        local_video_path=Path(payload["local_video_path"]),
        downloaded=payload.get("downloaded", False),
        mime_type=payload.get("mime_type", "video/mp4"),
        metadata=VideoMetadata(**payload["metadata"]),
        timestamps=list(payload.get("timestamps", [])),
        frames=[base64.b64decode(frame) for frame in payload.get("frames", [])],
        source_sha256=payload["source_sha256"],
        source_id=payload["source_id"],
        coverage=_coverage(payload["coverage"]),
        transcript=payload.get("transcript"),
        detected_voice=payload.get("detected_voice"),
        evidence_text=payload.get("evidence_text", ""),
    )


def _assemble(payload: dict) -> AnalysisResult:
    request = AnalysisRequest(**payload["request"])
    artifacts = _artifacts(payload["artifacts"])
    observation = ObservationResult.model_validate(payload["observation"])
    evaluation = EvaluationDraft.model_validate(payload["evaluation"])
    timings = AnalysisTimings.model_validate(payload["timings"])
    return assemble_analysis_result(
        request=request,
        artifacts=artifacts,
        observation=observation,
        evaluation=evaluation,
        timings=timings,
    )


def _selected_dimensions(result: AnalysisResult) -> list:
    evaluation = result.evaluation
    selected = list(evaluation.common_score_c.dimensions)
    if evaluation.review_route == "R":
        selected.extend(evaluation.specialized_score_r.dimensions)
    elif evaluation.review_route == "G":
        selected.extend(evaluation.specialized_score_g.dimensions)
    return selected


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_contract(fixture_name: str) -> None:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    expected = payload["expected"]
    result = _assemble(payload)

    assert result.meta.schema_version == "v4.0"
    assert result.decision.gate_status.value == expected["gate"]
    assert result.decision.scoring_status.value == expected["scoring_status"]
    assert result.evaluation.review_route == expected["route"]
    if expected["diagnostic_total"] == "available":
        assert result.evaluation.diagnostic_total is not None
    else:
        assert result.evaluation.diagnostic_total is None
    assert len(result.evaluation.evidence_conflicts) == expected["conflict_count"]
    assert result.decision.recommended_grade is None
    assert result.evidence_card.official_scoring_ready is False

    reparsed = AnalysisResult.model_validate(result.model_dump(mode="json"))
    assert reparsed == result


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_contains_no_forbidden_or_sensitive_content(fixture_name: str) -> None:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))

    forbidden = [key for key in _iter_json_keys(payload) if key in FORBIDDEN_FIELDS]
    assert forbidden == []

    for value in _iter_json_strings(payload):
        assert not any(marker in value for marker in ABSOLUTE_PATH_MARKERS)
        assert not any(pattern in value.lower() for pattern in SECRET_PATTERNS)


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_governance_and_route_invariants(fixture_name: str) -> None:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    result = _assemble(payload)
    evaluation = result.evaluation

    assert not (
        evaluation.specialized_score_r is not None
        and evaluation.specialized_score_g is not None
    )
    if evaluation.review_route is None:
        assert evaluation.specialized_score_r is None
        assert evaluation.specialized_score_g is None
        assert evaluation.diagnostic_total is None

    g0_hit = any(
        finding.triggered
        and any(
            reference.positive
            and (reference.timestamp is not None or reference.time_range is not None)
            for reference in finding.evidence_timestamps
        )
        for finding in evaluation.g0_assessment.findings
    )
    if g0_hit:
        assert result.decision.gate_status.value == "BLOCK"
        assert result.decision.system_disposition.value == "REJECT"

    if any(
        conflict.confidence is not None
        and conflict.confidence < LOW_CONFIDENCE_THRESHOLD
        for conflict in evaluation.evidence_conflicts
    ):
        assert result.decision.gate_status.value == "INSUFFICIENT_EVIDENCE"

    if not evaluation.evidence_review.evidence_complete:
        assert result.decision.gate_status.value == "INSUFFICIENT_EVIDENCE"

    dimensions = _selected_dimensions(result)
    all_scorable = all(dimension.scorable for dimension in dimensions)
    if evaluation.review_route is not None and all_scorable:
        assert evaluation.diagnostic_total == evaluation.partial_points
    if not all_scorable:
        assert evaluation.diagnostic_total is None


