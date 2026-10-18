import pytest
from pydantic import ValidationError

from models.results import AnalysisResult as ExportedAnalysisResult
from models.video_analysis import (
    ActionPhase,
    AnalysisMeta,
    AnalysisResult,
    CommonScoreC,
    ContentClassification,
    ContentType,
    Decision,
    EvaluationDraft,
    GateStatus,
    GeneratedScoreG,
    Grade,
    QualityScoring,
    ReferenceScoreR,
    ScoringStatus,
    SystemDisposition,
    TimelineEntry,
    Topology,
)


def test_results_exports_the_only_analysis_result_model():
    assert ExportedAnalysisResult is AnalysisResult


def test_latest_schema_version_is_fixed():
    assert AnalysisMeta().schema_version == "v4.0"

    with pytest.raises(ValidationError):
        AnalysisMeta(schema_version="v3.0")


def test_content_taxonomy_matches_prompt():
    assert {item.value for item in ContentType} == {
        "HOOK_FAST_ACTION",
        "FUNCTIONAL_PROOF",
        "PROBLEM_SOLUTION",
        "MULTI_COLOR_OR_PACK",
        "UGC_TRY_ON",
        "SCENARIO_IMMERSION",
        "COMMENT_OR_FAQ",
        "COMPARISON_CHOICE",
        "OUTFIT_TRANSFORMATION",
        "ATMOSPHERE_BRAND",
    }
    assert {item.value for item in Topology} == {
        "ONE_TAKE",
        "PRIMARY_TAKE_WITH_ONE_OR_TWO_CUTS",
        "MULTI_SHOT_FAST_CUT",
        "OCCLUSION_TRANSITION",
        "COLOR_OR_OUTFIT_TRANSFORMATION",
        "BEFORE_AFTER_COMPARISON",
    }


def test_secondary_content_types_are_unique_and_limited_to_two():
    ContentClassification(
        primary_type=ContentType.FUNCTIONAL_PROOF,
        secondary_types=[ContentType.PROBLEM_SOLUTION, ContentType.UGC_TRY_ON],
        topology=Topology.ONE_TAKE,
    )

    with pytest.raises(ValidationError):
        ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            secondary_types=[
                ContentType.PROBLEM_SOLUTION,
                ContentType.UGC_TRY_ON,
                ContentType.COMMENT_OR_FAQ,
            ],
            topology=Topology.ONE_TAKE,
        )

    with pytest.raises(ValidationError):
        ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            secondary_types=[ContentType.UGC_TRY_ON, ContentType.UGC_TRY_ON],
            topology=Topology.ONE_TAKE,
        )


def test_timeline_covers_prompt_required_fields():
    entry = TimelineEntry(
        start_seconds=0,
        end_seconds=0.5,
        person_action="右手抓住裤腰",
        product_action="裤腰被横向拉伸",
        shooting_method="手持近景",
        action_purpose="证明弹力",
        marketing_purpose="降低活动空间顾虑",
        emotion_state="惊喜",
        emotion_intensity=8,
        transition_type="无转场",
        rhythm_density="高",
        subtitle_text="真的很能拉",
        music_emotion="紧张后释放",
        is_hook_segment=True,
        is_conversion_closing_segment=False,
        key_frame_description="拉伸峰值时裤腰结构保持稳定",
        action_phases=list(ActionPhase),
        confidence=0.9,
    )

    assert entry.action_phases[-1] is ActionPhase.RECOVERY
    assert entry.marketing_purpose == "降低活动空间顾虑"


def test_c_r_g_score_contracts_match_prompt_totals():
    assert sum(item.max_points for item in CommonScoreC().dimensions) == 60
    assert sum(item.max_points for item in ReferenceScoreR().dimensions) == 40
    assert sum(item.max_points for item in GeneratedScoreG().dimensions) == 40


def test_evaluation_requires_exactly_one_specialized_route_when_selected():
    EvaluationDraft(review_route="R", specialized_score_r=ReferenceScoreR())
    EvaluationDraft(review_route="G", specialized_score_g=GeneratedScoreG())

    with pytest.raises(ValidationError):
        EvaluationDraft(review_route="R")

    with pytest.raises(ValidationError):
        EvaluationDraft(
            review_route="G",
            specialized_score_r=ReferenceScoreR(),
            specialized_score_g=GeneratedScoreG(),
        )


def test_quality_scoring_contains_all_fourteen_prompt_dimensions():
    assert set(QualityScoring.model_fields) == {
        "hook",
        "selling_point",
        "conversion",
        "human_action",
        "composition",
        "camera_language",
        "editing_rhythm",
        "visual_quality",
        "product_display",
        "emotion_impact",
        "style_consistency",
        "platform_fit",
        "replicability",
        "overall",
    }


def test_analysis_result_exposes_full_latest_architecture():
    result = AnalysisResult(
        content_classification=ContentClassification(
            primary_type=ContentType.HOOK_FAST_ACTION,
            topology=Topology.ONE_TAKE,
        ),
        decision=Decision(
            gate_status=GateStatus.INSUFFICIENT_EVIDENCE,
            scoring_status=ScoringStatus.UNAVAILABLE,
            system_disposition=SystemDisposition.OWNER_REVIEW_REQUIRED,
        ),
    )

    assert result.meta.schema_version == "v4.0"
    assert result.observation.timeline == []
    assert result.generation.ai_video_prompt.full_prompt_zh is None
    assert result.quality_scoring.overall.score is None


def test_blocked_result_must_be_rejected():
    with pytest.raises(ValidationError):
        AnalysisResult(
            content_classification=ContentClassification(
                primary_type=ContentType.FUNCTIONAL_PROOF,
                topology=Topology.ONE_TAKE,
            ),
            decision=Decision(
                gate_status=GateStatus.BLOCK,
                scoring_status=ScoringStatus.PROVISIONAL,
                recommended_grade=Grade.D,
                system_disposition=SystemDisposition.OWNER_REVIEW_REQUIRED,
            ),
        )
