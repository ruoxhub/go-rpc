import pytest
from pydantic import ValidationError

from models.video_analysis import (
    AnalysisMeta,
    AnalysisResult,
    CommonScoreC,
    ContentClassification,
    ContentType,
    Decision,
    EvaluationDraft,
    EvaluationResult,
    EvidenceReference,
    EvidenceSource,
    GateStatus,
    GeneratedScoreG,
    ObservationResult,
    Observation,
    ReferenceScoreR,
    ScoreDimension,
    ScoringStatus,
    SystemDisposition,
    TimelineEntry,
    TimeRange,
    Topology,
)


def _dimension(max_points: float, awarded_points: float | None = None):
    return ScoreDimension(
        awarded_points=awarded_points,
        max_points=max_points,
        reason="hand-checked reason",
        evidence_timestamps=(
            [EvidenceReference(source=EvidenceSource.VIDEO, timestamp=1.0, positive=True)]
            if awarded_points == max_points
            else []
        ),
        scorable=awarded_points is not None,
    )


def test_analysis_meta_schema_version_is_fixed_to_latest():
    assert AnalysisMeta().schema_version == "v4.0"

    with pytest.raises(ValidationError):
        AnalysisMeta(schema_version="v2.0")


def test_analysis_result_exposes_fixed_latest_schema_version():
    result = AnalysisResult(
        meta=AnalysisMeta(),
        content_classification=ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            topology=Topology.ONE_TAKE,
        ),
        decision=Decision(
            gate_status=GateStatus.INSUFFICIENT_EVIDENCE,
            scoring_status=ScoringStatus.UNAVAILABLE,
            system_disposition=SystemDisposition.OWNER_REVIEW_REQUIRED,
        ),
    )

    assert result.meta.schema_version == "v4.0"


def test_secondary_content_types_are_unique_and_limited_to_two():
    ContentClassification(
        primary_type=ContentType.FUNCTIONAL_PROOF,
        secondary_types=[ContentType.PROBLEM_SOLUTION, ContentType.UGC_TRY_ON],
        topology=Topology.ONE_TAKE,
    )

    with pytest.raises(ValidationError):
        ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            secondary_types=[ContentType.UGC_TRY_ON, ContentType.UGC_TRY_ON],
            topology=Topology.ONE_TAKE,
        )
    with pytest.raises(ValidationError):
        ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            secondary_types=[
                ContentType.PROBLEM_SOLUTION,
                ContentType.UGC_TRY_ON,
                ContentType.COMPARISON_CHOICE,
            ],
            topology=Topology.ONE_TAKE,
        )


@pytest.mark.parametrize(
    ("start_seconds", "end_seconds"),
    [(-0.1, 1.0), (0.0, -0.1), (2.0, 1.0)],
)
def test_timeline_rejects_negative_or_reversed_ranges(start_seconds, end_seconds):
    with pytest.raises(ValidationError):
        TimelineEntry(start_seconds=start_seconds, end_seconds=end_seconds)


def test_time_range_serializes_explicit_boundary_semantics():
    assert TimeRange(
        start_seconds=1.0,
        end_seconds=2.0,
        start_inclusive=False,
        end_inclusive=True,
    ).model_dump() == {
        "start_seconds": 1.0,
        "end_seconds": 2.0,
        "start_inclusive": False,
        "end_inclusive": True,
    }
    assert TimeRange(start_seconds=1.0, end_seconds=2.0).model_dump() == {
        "start_seconds": 1.0,
        "end_seconds": 2.0,
        "start_inclusive": True,
        "end_inclusive": True,
    }


@pytest.mark.parametrize(
    ("start_inclusive", "end_inclusive"),
    [(False, False), (False, True), (True, False)],
)
def test_zero_width_time_range_must_represent_a_closed_point(
    start_inclusive, end_inclusive
):
    with pytest.raises(ValidationError):
        TimeRange(
            start_seconds=1.0,
            end_seconds=1.0,
            start_inclusive=start_inclusive,
            end_inclusive=end_inclusive,
        )


@pytest.mark.parametrize("awarded_points", [-0.1, 10.1])
def test_score_dimension_rejects_points_outside_bounds(awarded_points):
    with pytest.raises(ValidationError):
        _dimension(10, awarded_points)


def test_unscorable_dimension_cannot_have_awarded_points():
    with pytest.raises(ValidationError):
        ScoreDimension(max_points=10, awarded_points=1, scorable=False)


def test_full_score_requires_positive_timecoded_evidence():
    with pytest.raises(ValidationError):
        ScoreDimension(max_points=10, awarded_points=10, scorable=True)
    with pytest.raises(ValidationError):
        ScoreDimension(
            max_points=10,
            awarded_points=10,
            scorable=True,
            evidence_timestamps=[
                EvidenceReference(
                    source=EvidenceSource.VIDEO,
                    timestamp=1.0,
                    positive=False,
                )
            ],
        )


def test_declared_score_section_maximums_are_60_40_40():
    assert sum(d.max_points for d in CommonScoreC().dimensions) == 60
    assert sum(d.max_points for d in ReferenceScoreR().dimensions) == 40
    assert sum(d.max_points for d in GeneratedScoreG().dimensions) == 40


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        (
            CommonScoreC(),
            [
                ("C1", "受众与购买需求", 6),
                ("C2", "钩子停留能力", 10),
                ("C3", "商品识别与曝光", 6),
                ("C4", "卖点选择", 8),
                ("C5", "可见证据链", 12),
                ("C6", "节奏与信息密度", 8),
                ("C7", "记忆点与商品绑定", 6),
                ("C8", "信任、顾虑与行动", 4),
            ],
        ),
        (
            ReferenceScoreR(),
            [
                ("R1", "时间线与结构可拆解性", 8),
                ("R2", "AI 复刻友好度", 10),
                ("R3", "可迁移变量丰富度", 8),
                ("R4", "换成我方商品的安全性", 6),
                ("R5", "生产成本与稳定性", 4),
                ("R6", "差异化潜力", 4),
            ],
        ),
        (
            GeneratedScoreG(),
            [
                ("G1", "商品一致性", 12),
                ("G2", "人物身份与服装层级", 5),
                ("G3", "动作完整性与力量感", 8),
                ("G4", "物理、接触与回弹", 6),
                ("G5", "镜头与构图连续性", 4),
                ("G6", "技术画质", 3),
                ("G7", "背景、灯光与声音联动", 2),
            ],
        ),
    ],
)
def test_score_sections_preserve_every_frozen_dimension_tuple(section, expected):
    assert [
        (dimension.dimension_id, dimension.name, dimension.max_points)
        for dimension in section.dimensions
    ] == expected


@pytest.mark.parametrize("section_type", [CommonScoreC, ReferenceScoreR, GeneratedScoreG])
def test_score_sections_reject_tampered_dimension_names(section_type):
    payload = section_type().model_dump()
    payload["dimensions"][0]["name"] = "tampered"

    with pytest.raises(ValidationError):
        section_type.model_validate(payload)


def test_score_section_serializes_only_contract_data():
    assert set(CommonScoreC().model_dump()) == {"dimensions"}


def test_observation_result_separates_classification_from_observation_body():
    result = ObservationResult(
        content_classification=ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            topology=Topology.ONE_TAKE,
        ),
        observation=Observation(),
    )

    assert result.observation == Observation()


def test_evaluation_rejects_both_specialized_sections():
    with pytest.raises(ValidationError):
        EvaluationResult(
            review_route="R",
            specialized_score_r=ReferenceScoreR(),
            specialized_score_g=GeneratedScoreG(),
        )


@pytest.mark.parametrize("review_route", ["R", "G"])
def test_evaluation_requires_the_selected_specialized_section(review_route):
    with pytest.raises(ValidationError):
        EvaluationResult(review_route=review_route)


@pytest.mark.parametrize(
    ("review_route", "section"),
    [("R", "specialized_score_g"), ("G", "specialized_score_r"), (None, "specialized_score_r")],
)
def test_evaluation_rejects_section_inconsistent_with_route(review_route, section):
    with pytest.raises(ValidationError):
        EvaluationResult(
            review_route=review_route,
            **{section: GeneratedScoreG() if section.endswith("g") else ReferenceScoreR()},
        )


def test_decision_accepts_prompt_grade_recommendation():
    decision = Decision(
        gate_status=GateStatus.PASS,
        scoring_status=ScoringStatus.PROVISIONAL,
        recommended_grade="A",
        system_disposition=SystemDisposition.REPAIR_THEN_PRODUCTION,
    )

    assert decision.recommended_grade.value == "A"


@pytest.mark.parametrize("forbidden_field", ["partial_points", "partial_max_points", "diagnostic_total"])
def test_evaluation_draft_discards_assembler_owned_totals(forbidden_field):
    # Assembler-owned totals are never honored from LLM input: they are dropped
    # at the boundary and recomputed by the assembler from the score dimensions.
    draft = EvaluationDraft(**{forbidden_field: 1})
    assert forbidden_field not in draft.model_dump()


@pytest.mark.parametrize("removed_field", ["ai_video_prompt", "iteration", "post_production"])
def test_analysis_result_rejects_removed_v2_generation_fields(removed_field):
    with pytest.raises(ValidationError):
        AnalysisResult(
            content_classification=ContentClassification(
                primary_type=ContentType.FUNCTIONAL_PROOF,
                topology=Topology.ONE_TAKE,
            ),
            decision=Decision(
                gate_status=GateStatus.INSUFFICIENT_EVIDENCE,
                scoring_status=ScoringStatus.UNAVAILABLE,
                system_disposition=SystemDisposition.OWNER_REVIEW_REQUIRED,
            ),
            **{removed_field: {}},
        )


def _generated_section_raw_with_unscorable_g1_award():
    """Raw LLM-shaped payload: G1 declares scorable=false yet carries points."""
    dimensions = []
    for dimension_id, name, max_points in (
        ("G1", "商品一致性", 12),
        ("G2", "人物身份与服装层级", 5),
        ("G3", "动作完整性与力量感", 8),
        ("G4", "物理、接触与回弹", 6),
        ("G5", "镜头与构图连续性", 4),
        ("G6", "技术画质", 3),
        ("G7", "背景、灯光与声音联动", 2),
    ):
        if dimension_id == "G1":
            dimensions.append(
                {
                    "dimension_id": dimension_id,
                    "name": name,
                    "max_points": max_points,
                    "awarded_points": max_points / 2,
                    "scorable": False,
                    "unscorable_reason": "无外部商品参考证据",
                    "reason": "hand-checked",
                    "confidence": 0.9,
                }
            )
        else:
            dimensions.append(
                {
                    "dimension_id": dimension_id,
                    "name": name,
                    "max_points": max_points,
                    "awarded_points": max_points / 2,
                    "scorable": True,
                    "reason": "hand-checked",
                    "confidence": 0.9,
                }
            )
    return {"dimensions": dimensions}


def test_generated_section_repairs_award_on_explicitly_unscorable_dimension():
    section = GeneratedScoreG.model_validate(
        _generated_section_raw_with_unscorable_g1_award()
    )

    g1 = next(d for d in section.dimensions if d.dimension_id == "G1")
    assert g1.scorable is False
    assert g1.awarded_points is None
    assert g1.unscorable_reason == "无外部商品参考证据"
    # Other dimensions keep their awards.
    g2 = next(d for d in section.dimensions if d.dimension_id == "G2")
    assert g2.scorable is True
    assert g2.awarded_points == 2.5


def test_unscorable_award_repair_applies_through_evaluation_draft_llm_path():
    common_dimensions = []
    for dimension_id, name, max_points in (
        ("C1", "受众与购买需求", 6),
        ("C2", "钩子停留能力", 10),
        ("C3", "商品识别与曝光", 6),
        ("C4", "卖点选择", 8),
        ("C5", "可见证据链", 12),
        ("C6", "节奏与信息密度", 8),
        ("C7", "记忆点与商品绑定", 6),
        ("C8", "信任、顾虑与行动", 4),
    ):
        common_dimensions.append(
            {
                "dimension_id": dimension_id,
                "name": name,
                "max_points": max_points,
                "awarded_points": max_points / 2,
                "scorable": True,
                "reason": "hand-checked",
                "confidence": 0.9,
            }
        )
    payload = {
        "review_route": "G",
        "evidence_review": {"evidence_complete": True, "confidence": 0.9},
        "common_score_c": {"dimensions": common_dimensions},
        "specialized_score_g": _generated_section_raw_with_unscorable_g1_award(),
    }

    draft = EvaluationDraft.model_validate(payload)

    g1 = next(
        d for d in draft.specialized_score_g.dimensions if d.dimension_id == "G1"
    )
    assert g1.scorable is False
    assert g1.awarded_points is None

