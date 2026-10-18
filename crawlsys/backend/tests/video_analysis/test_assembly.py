from dataclasses import replace
from pathlib import Path

import pytest

from app.services.video_analysis import assembly
from app.services.video_analysis.assembly import (
    InvalidEvaluationStructureError,
    assemble_analysis_result,
)
from models.results import (
    AnalysisArtifacts,
    AnalysisRequest,
    AnalysisTimings,
    CommonScoreC,
    ContentClassification,
    ContentType,
    DefectCategory,
    EvaluationDraft,
    EvaluationResult,
    EvidenceConflict,
    EvidenceReference,
    EvidenceReview,
    EvidenceSource,
    G0Assessment,
    G0Finding,
    GateStatus,
    GeneratedScoreG,
    InputMode,
    ObservationResult,
    ReferenceScoreR,
    ScoreDimension,
    ScoringStatus,
    SystemDisposition,
    Topology,
    VideoMetadata,
)
from models.video_analysis_runtime import MediaCoverage, MediaTimeRange


SPECS = {
    "C": (
        ("C1", "受众与购买需求", 6),
        ("C2", "钩子停留能力", 10),
        ("C3", "商品识别与曝光", 6),
        ("C4", "卖点选择", 8),
        ("C5", "可见证据链", 12),
        ("C6", "节奏与信息密度", 8),
        ("C7", "记忆点与商品绑定", 6),
        ("C8", "信任、顾虑与行动", 4),
    ),
    "R": (
        ("R1", "时间线与结构可拆解性", 8),
        ("R2", "AI 复刻友好度", 10),
        ("R3", "可迁移变量丰富度", 8),
        ("R4", "换成我方商品的安全性", 6),
        ("R5", "生产成本与稳定性", 4),
        ("R6", "差异化潜力", 4),
    ),
    "G": (
        ("G1", "商品一致性", 12),
        ("G2", "人物身份与服装层级", 5),
        ("G3", "动作完整性与力量感", 8),
        ("G4", "物理、接触与回弹", 6),
        ("G5", "镜头与构图连续性", 4),
        ("G6", "技术画质", 3),
        ("G7", "背景、灯光与声音联动", 2),
    ),
}


def _dimension(dimension_id: str, name: str, max_points: float) -> ScoreDimension:
    return ScoreDimension(
        dimension_id=dimension_id,
        name=name,
        awarded_points=max_points / 2,
        max_points=max_points,
        reason="hand-checked",
        scorable=True,
        confidence=0.9,
    )


def _section(route: str):
    dimensions = [_dimension(*spec) for spec in SPECS[route]]
    return {"C": CommonScoreC, "R": ReferenceScoreR, "G": GeneratedScoreG}[
        route
    ](dimensions=dimensions)


def _draft(route: str | None = "R", **updates) -> EvaluationDraft:
    values = {
        "review_route": route,
        "evidence_review": EvidenceReview(evidence_complete=True, confidence=0.9),
        "common_score_c": _section("C"),
        "specialized_score_r": _section("R") if route == "R" else None,
        "specialized_score_g": _section("G") if route == "G" else None,
    }
    values.update(updates)
    return EvaluationDraft(**values)


@pytest.fixture
def analysis_request() -> AnalysisRequest:
    return AnalysisRequest(
        source=Path("input.mp4"),
        model="deterministic-test-model",
        api_key="must-never-leak",
        output_path=Path("C:/private/result.json"),
    )


@pytest.fixture
def artifacts() -> AnalysisArtifacts:
    return AnalysisArtifacts(
        local_video_path=Path("C:/private/tmp/video.mp4"),
        downloaded=True,
        mime_type="video/mp4",
        metadata=VideoMetadata(
            duration=10.0,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio_stream=True,
        ),
        timestamps=[1.0, 9.0],
        frames=[b"a", b"b"],
        source_sha256="a" * 64,
        source_id=f"sha256:{'a' * 64}",
        coverage=MediaCoverage(
            input_mode=InputMode.SAMPLED_FRAMES,
            sampled_timestamps=(1.0, 9.0),
            observed_ranges=(MediaTimeRange(1.0, 1.0), MediaTimeRange(9.0, 9.0)),
            unobserved_ranges=(
                MediaTimeRange(0.0, 1.0, end_inclusive=False),
                MediaTimeRange(1.0, 9.0, False, False),
                MediaTimeRange(9.0, 10.0, False, True),
            ),
            limitations=("sampled coverage",),
        ),
    )


@pytest.fixture
def observation() -> ObservationResult:
    return ObservationResult(
        content_classification=ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            topology=Topology.ONE_TAKE,
        )
    )


def _assemble(analysis_request, artifacts, observation, evaluation):
    return assemble_analysis_result(
        request=analysis_request,
        artifacts=artifacts,
        observation=observation,
        evaluation=evaluation,
        timings=AnalysisTimings(
            observation_duration_ms=100,
            evaluation_duration_ms=50,
            total_duration_ms=150,
        ),
    )


def _request_for_route(analysis_request, route):
    return replace(analysis_request, review_route=route)


def _use_full_video_coverage(artifacts):
    artifacts.coverage = MediaCoverage(
        input_mode=InputMode.FULL_VIDEO,
        sampled_timestamps=(),
        observed_ranges=(MediaTimeRange(0.0, 10.0),),
        unobserved_ranges=(),
        limitations=(),
    )


@pytest.mark.parametrize("route", ["R", "G"])
def test_route_accumulates_scored_dimensions_before_product_reference_gate(
    route, analysis_request, artifacts, observation
):
    result = _assemble(
        _request_for_route(analysis_request, route),
        artifacts,
        observation,
        _draft(route),
    )

    assert result.evaluation.diagnostic_total is None
    assert result.evidence_card.evidence_complete is False
    dependent = "R4" if route == "R" else "G1"
    scored_ids = {
        item.dimension_id
        for section in (
            result.evaluation.common_score_c,
            result.evaluation.specialized_score_r,
            result.evaluation.specialized_score_g,
        )
        if section is not None
        for item in section.dimensions
        if item.scorable
    }
    assert dependent not in scored_ids
    assert result.evaluation.partial_points == (47 if route == "R" else 44)
    assert result.evaluation.partial_max_points == (94 if route == "R" else 88)


@pytest.mark.parametrize(
    ("request_route", "draft_route"),
    [
        (None, "R"),
        (None, "G"),
        ("R", "G"),
        ("G", "R"),
        ("R", None),
        ("G", None),
    ],
)
def test_request_and_draft_routes_must_match_exactly(
    request_route, draft_route, analysis_request, artifacts, observation
):
    mismatched_request = _request_for_route(analysis_request, request_route)

    with pytest.raises(InvalidEvaluationStructureError, match="route"):
        _assemble(mismatched_request, artifacts, observation, _draft(draft_route))


def test_none_route_scores_only_c_and_keeps_total_unavailable(
    analysis_request, artifacts, observation
):
    result = _assemble(analysis_request, artifacts, observation, _draft(None))

    assert result.evaluation.review_route is None
    assert result.evaluation.specialized_score_r is None
    assert result.evaluation.specialized_score_g is None
    assert result.evaluation.partial_points == 30
    assert result.evaluation.partial_max_points == 60
    assert result.evaluation.diagnostic_total is None
    assert result.decision.scoring_status is ScoringStatus.UNAVAILABLE
    assert result.evidence_card.evidence_complete is True


def test_unscorable_required_dimension_keeps_non_normalized_partial_sum(
    analysis_request, artifacts, observation
):
    draft = _draft("R")
    dimensions = list(draft.common_score_c.dimensions)
    dimensions[0] = dimensions[0].model_copy(
        update={"awarded_points": None, "scorable": False, "unscorable_reason": "missing"}
    )
    draft = draft.model_copy(
        update={"common_score_c": CommonScoreC(dimensions=dimensions)}
    )

    result = _assemble(
        _request_for_route(analysis_request, "R"), artifacts, observation, draft
    )

    assert result.evaluation.diagnostic_total is None
    assert result.evaluation.partial_points == 44
    assert result.evaluation.partial_max_points == 88


def test_assembler_rejects_result_object_with_model_owned_totals(
    analysis_request, artifacts, observation
):
    fake = EvaluationResult(
        **_draft("R").model_dump(),
        partial_points=100,
        partial_max_points=100,
        diagnostic_total=100,
    )

    with pytest.raises(InvalidEvaluationStructureError, match="evaluation draft"):
        _assemble(
            _request_for_route(analysis_request, "R"), artifacts, observation, fake
        )


@pytest.mark.parametrize(
    "field_name", ["partial_points", "partial_max_points", "diagnostic_total"]
)
def test_assembler_rejects_fixture_injected_totals(
    field_name, analysis_request, artifacts, observation
):
    draft = _draft("R")
    object.__setattr__(draft, field_name, 100)

    with pytest.raises(InvalidEvaluationStructureError, match="evaluation draft"):
        _assemble(
            _request_for_route(analysis_request, "R"), artifacts, observation, draft
        )


@pytest.mark.parametrize(
    "mutation",
    ["wrong_section", "both_sections", "out_of_range", "wrong_max", "full_without_timecode"],
)
def test_invalid_evaluation_structure_is_rejected(
    mutation, analysis_request, artifacts, observation
):
    draft = _draft("R")
    if mutation == "wrong_section":
        draft = EvaluationDraft.model_construct(
            **{
                **draft.__dict__,
                "specialized_score_r": None,
                "specialized_score_g": _section("G"),
            }
        )
    elif mutation == "both_sections":
        draft = EvaluationDraft.model_construct(
            **{**draft.__dict__, "specialized_score_g": _section("G")}
        )
    else:
        dimensions = list(draft.common_score_c.dimensions)
        original = dimensions[0]
        updates = {
            "out_of_range": {"awarded_points": 7},
            "wrong_max": {"max_points": 7},
            "full_without_timecode": {"awarded_points": 6, "evidence_timestamps": []},
        }[mutation]
        dimensions[0] = ScoreDimension.model_construct(
            **{**original.__dict__, **updates}
        )
        invalid_common = CommonScoreC.model_construct(dimensions=dimensions)
        draft = EvaluationDraft.model_construct(
            **{**draft.__dict__, "common_score_c": invalid_common}
        )

    with pytest.raises(InvalidEvaluationStructureError):
        _assemble(
            _request_for_route(analysis_request, "R"), artifacts, observation, draft
        )


def test_timecoded_positive_g0_always_blocks_regardless_of_dimension_scores(
    analysis_request, artifacts, observation
):
    finding = G0Finding(
        category=DefectCategory.PRODUCT,
        description="product identity drift",
        triggered=True,
        evidence_timestamps=[
            EvidenceReference(
                source=EvidenceSource.VIDEO, timestamp=2.0, positive=True
            )
        ],
        confidence=1.0,
    )
    result = _assemble(
        _request_for_route(analysis_request, "G"),
        artifacts,
        observation,
        _draft("G", g0_assessment=G0Assessment(findings=[finding])),
    )

    assert result.decision.gate_status is GateStatus.BLOCK
    assert result.decision.system_disposition is SystemDisposition.REJECT


def test_low_confidence_conflict_without_positive_g0_requires_owner_review(
    analysis_request, artifacts, observation
):
    conflict = EvidenceConflict(
        observation_claim="product is stable",
        evaluation_claim="product may drift",
        affected_dimension_ids=["G2"],
        confidence=0.4,
    )
    result = _assemble(
        _request_for_route(analysis_request, "G"),
        artifacts,
        observation,
        _draft("G", evidence_conflicts=[conflict]),
    )

    assert result.decision.gate_status is GateStatus.INSUFFICIENT_EVIDENCE
    assert (
        result.decision.system_disposition
        is SystemDisposition.OWNER_REVIEW_REQUIRED
    )


def test_ordinary_conflict_remains_visible_and_marks_dimension_unscorable(
    analysis_request, artifacts, observation
):
    conflict = EvidenceConflict(
        observation_claim="hook starts immediately",
        evaluation_claim="hook starts late",
        affected_dimension_ids=["C2"],
        confidence=0.9,
    )
    result = _assemble(
        _request_for_route(analysis_request, "R"),
        artifacts,
        observation,
        _draft("R", evidence_conflicts=[conflict]),
    )

    c2 = next(
        item for item in result.evaluation.common_score_c.dimensions
        if item.dimension_id == "C2"
    )
    assert not c2.scorable
    assert c2.awarded_points is None
    assert c2.unscorable_reason
    assert result.evaluation.evidence_conflicts == [conflict]


@pytest.mark.parametrize(("route", "dimension_id"), [("R", "R4"), ("G", "G1")])
def test_missing_product_reference_makes_dependent_dimension_unscorable(
    route, dimension_id, analysis_request, artifacts, observation
):
    result = _assemble(
        _request_for_route(analysis_request, route),
        artifacts,
        observation,
        _draft(route),
    )
    section = (
        result.evaluation.specialized_score_r
        if route == "R"
        else result.evaluation.specialized_score_g
    )

    dimension = next(
        item for item in section.dimensions if item.dimension_id == dimension_id
    )
    assert not dimension.scorable
    assert dimension.awarded_points is None
    assert "product reference" in dimension.unscorable_reason.lower()


def test_successful_result_keeps_governance_flags_and_excludes_temporary_paths(
    analysis_request, artifacts, observation
):
    result = _assemble(analysis_request, artifacts, observation, _draft(None))
    payload = result.model_dump_json()

    assert result.evidence_card.official_scoring_ready is False
    assert result.decision.recommended_grade is None
    assert result.meta.timings.total_duration_ms == 150
    assert result.evidence_card.observed_ranges[0].start_inclusive is True
    assert result.evidence_card.unobserved_ranges[1].start_inclusive is False
    assert result.evidence_card.source_id == artifacts.source_id
    assert result.evidence_card.source_sha256 == artifacts.source_sha256
    assert result.evidence_card.sampled_frame_count == len(artifacts.frames)
    assert result.evidence_card.sampled_timestamps == artifacts.timestamps
    assert result.evidence_card.coverage_limitations == list(
        artifacts.coverage.limitations
    )
    assert [item.model_dump() for item in result.evidence_card.observed_ranges] == [
        {
            "start_seconds": item.start_seconds,
            "end_seconds": item.end_seconds,
            "start_inclusive": item.start_inclusive,
            "end_inclusive": item.end_inclusive,
        }
        for item in artifacts.coverage.observed_ranges
    ]
    assert [item.model_dump() for item in result.evidence_card.unobserved_ranges] == [
        {
            "start_seconds": item.start_seconds,
            "end_seconds": item.end_seconds,
            "start_inclusive": item.start_inclusive,
            "end_inclusive": item.end_inclusive,
        }
        for item in artifacts.coverage.unobserved_ranges
    ]
    assert "C:/private" not in payload
    assert "must-never-leak" not in payload


def test_full_video_coverage_maps_exactly_without_binding_internal_frames(
    analysis_request, artifacts, observation
):
    _use_full_video_coverage(artifacts)

    result = _assemble(analysis_request, artifacts, observation, _draft(None))

    assert result.evidence_card.input_mode is InputMode.FULL_VIDEO
    assert result.evidence_card.sampled_timestamps == []
    assert result.evidence_card.sampled_frame_count == 2
    assert [item.model_dump() for item in result.evidence_card.observed_ranges] == [
        {
            "start_seconds": 0.0,
            "end_seconds": 10.0,
            "start_inclusive": True,
            "end_inclusive": True,
        }
    ]
    assert result.evidence_card.unobserved_ranges == []


@pytest.mark.parametrize(
    "mutation",
    ["sampled_timestamp", "wrong_observed", "unexpected_gap", "duration_mismatch"],
)
def test_assembler_rejects_damaged_full_video_coverage(
    mutation, analysis_request, artifacts, observation
):
    _use_full_video_coverage(artifacts)
    if mutation == "sampled_timestamp":
        artifacts.coverage = replace(
            artifacts.coverage, sampled_timestamps=(1.0,)
        )
    elif mutation == "wrong_observed":
        artifacts.coverage = replace(
            artifacts.coverage,
            observed_ranges=(MediaTimeRange(0.0, 9.0),),
        )
    elif mutation == "unexpected_gap":
        artifacts.coverage = replace(
            artifacts.coverage,
            unobserved_ranges=(MediaTimeRange(2.0, 3.0),),
        )
    else:
        artifacts.metadata = replace(artifacts.metadata, duration=9.0)

    with pytest.raises(InvalidEvaluationStructureError, match="analysis artifacts"):
        _assemble(analysis_request, artifacts, observation, _draft(None))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_coverage",
        "invalid_hash",
        "mismatched_source_id",
        "sample_count",
        "actual_timestamps",
        "observed_count",
        "observed_point",
        "invalid_range",
        "wrong_gaps",
        "timestamp_out_of_duration",
        "nonpositive_duration",
    ],
)
def test_assembler_rejects_missing_or_inconsistent_critical_evidence(
    mutation, analysis_request, artifacts, observation
):
    if mutation == "missing_coverage":
        artifacts.coverage = None
    elif mutation == "invalid_hash":
        artifacts.source_sha256 = "C:/private/secret.mp4"
    elif mutation == "mismatched_source_id":
        artifacts.source_id = f"sha256:{'b' * 64}"
    elif mutation == "sample_count":
        artifacts.frames = [b"a"]
    elif mutation == "actual_timestamps":
        artifacts.timestamps = [1.0, 8.0]
    elif mutation == "observed_count":
        artifacts.coverage = replace(
            artifacts.coverage,
            observed_ranges=artifacts.coverage.observed_ranges[:1],
        )
    elif mutation == "observed_point":
        artifacts.coverage = replace(
            artifacts.coverage,
            observed_ranges=(
                artifacts.coverage.observed_ranges[0],
                MediaTimeRange(8.0, 8.0),
            ),
        )
    elif mutation == "invalid_range":
        artifacts.coverage = replace(
            artifacts.coverage,
            unobserved_ranges=(MediaTimeRange(-1.0, 1.0),),
        )
    elif mutation == "wrong_gaps":
        artifacts.coverage = replace(
            artifacts.coverage,
            unobserved_ranges=(
                MediaTimeRange(0.0, 1.0, True, True),
                *artifacts.coverage.unobserved_ranges[1:],
            ),
        )
    elif mutation == "timestamp_out_of_duration":
        artifacts.timestamps = [1.0, 11.0]
        artifacts.coverage = replace(
            artifacts.coverage,
            sampled_timestamps=(1.0, 11.0),
            observed_ranges=(MediaTimeRange(1.0, 1.0), MediaTimeRange(11.0, 11.0)),
        )
    else:
        artifacts.metadata = replace(artifacts.metadata, duration=0.0)

    with pytest.raises(InvalidEvaluationStructureError, match="analysis artifacts") as exc:
        _assemble(analysis_request, artifacts, observation, _draft(None))

    assert "private" not in str(exc.value)


@pytest.mark.parametrize(
    "mutation",
    [
        "input_mode",
        "coverage_field_type",
        "coverage_object",
        "metadata_type",
        "metadata_object",
        "probe_object",
        "signals_object",
        "result_type",
    ],
)
def test_artifact_boundary_sanitizes_malicious_types_without_exception_chain(
    mutation, analysis_request, artifacts, observation
):
    secret = "C:/private/API_KEY=top-secret-token"
    if mutation == "input_mode":
        artifacts.coverage = replace(artifacts.coverage, input_mode=secret)
    elif mutation == "coverage_field_type":
        artifacts.coverage = replace(
            artifacts.coverage,
            unobserved_ranges=(MediaTimeRange(secret, secret),),
        )
    elif mutation == "coverage_object":
        artifacts.coverage = secret
    elif mutation == "metadata_type":
        artifacts.metadata = replace(artifacts.metadata, width=secret)
    elif mutation == "metadata_object":
        artifacts.metadata = {"duration": secret}
    elif mutation == "probe_object":
        artifacts.media_probe = {"duration_seconds": secret}
    elif mutation == "signals_object":
        artifacts.signals = {"audio": secret}
    else:
        analysis_request = replace(analysis_request, model={"token": secret})

    with pytest.raises(InvalidEvaluationStructureError) as exc:
        _assemble(analysis_request, artifacts, observation, _draft(None))

    assert secret not in str(exc.value)
    assert "API_KEY" not in str(exc.value)
    assert "token" not in str(exc.value)
    assert exc.value.__cause__ is None


@pytest.mark.parametrize(
    ("boundary", "expected_message"),
    [
        ("evidence_card", "invalid analysis artifacts"),
        ("analysis_result", "invalid analysis result"),
    ],
)
def test_sanitized_boundary_error_discards_sensitive_exception_context(
    boundary,
    expected_message,
    analysis_request,
    artifacts,
    observation,
):
    secret = "C:/private/API_KEY=top-secret-token"
    if boundary == "evidence_card":
        artifacts.metadata = replace(artifacts.metadata, fps=secret)
    else:
        analysis_request = replace(analysis_request, model={"token": secret})

    with pytest.raises(InvalidEvaluationStructureError) as exc:
        _assemble(analysis_request, artifacts, observation, _draft(None))

    assert str(exc.value) == expected_message
    assert secret not in str(exc.value)
    assert "API_KEY" not in str(exc.value)
    assert "token" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_internal_helper_type_error_is_not_sanitized(
    monkeypatch, analysis_request, artifacts, observation
):
    def programmer_bug(*args, **kwargs):
        raise TypeError("programmer-bug sentinel")

    monkeypatch.setattr(assembly, "_decision", programmer_bug)

    with pytest.raises(TypeError, match="programmer-bug sentinel"):
        _assemble(analysis_request, artifacts, observation, _draft(None))


def test_sampled_mismatch_diagnostic_pinpoints_drifted_frame_timestamp(
    analysis_request, artifacts, observation
):
    # The ffmpeg retry path USED to record the frame at requested - 0.1s (e.g.
    # 8.9 instead of the requested 9.0). If that drifted list ever reaches the
    # assembler while coverage still carries the requested point, the validator
    # must raise and log exactly which field diverged.
    drifted = replace(
        artifacts,
        timestamps=[1.0, 8.9],
        frames=[b"a", b"b"],
    )

    reason = assembly._sampled_coverage_mismatch_reason(
        drifted, drifted.coverage, 10.0
    )
    assert reason is not None
    assert "artifacts.timestamps" in reason
    assert "8.9" in reason

    with pytest.raises(
        InvalidEvaluationStructureError, match="analysis artifacts"
    ):
        _assemble(analysis_request, drifted, observation, _draft(None))


def test_sampled_coverage_matches_when_frame_timestamps_stay_on_requested_points(
    analysis_request, artifacts, observation
):
    # Regression for the cores fix: extract_video_frame_samples now records the
    # requested timestamp even when ffmpeg retries at an earlier seek offset, so
    # the assembler accepts artifacts whose timestamps equal the coverage points.
    synced = replace(
        artifacts,
        timestamps=[1.0, 9.0],
        frames=[b"a", b"b"],
    )
    assert synced.timestamps == list(synced.coverage.sampled_timestamps)
    assert assembly._sampled_coverage_mismatch_reason(
        synced, synced.coverage, 10.0
    ) is None
    result = _assemble(analysis_request, synced, observation, _draft(None))
    assert result is not None
