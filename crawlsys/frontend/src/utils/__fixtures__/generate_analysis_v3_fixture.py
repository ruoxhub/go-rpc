"""Regenerate analysis-v3.json from the backend v3 Pydantic wire model."""

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "backend/app/models/video_analysis_v3.py"
FIXTURE_DIR = Path(__file__).parent


def load_model_module():
    spec = importlib.util.spec_from_file_location("video_analysis_v3", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODEL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_result(model):
    reference = model.EvidenceReferenceV3(
        source=model.EvidenceSourceV3.VIDEO,
        timestamp=1.25,
        description="visible product proof",
    )
    observed_range = model.TimeRangeV3(start_seconds=1.0, end_seconds=2.0)
    classification = model.ContentClassificationV3(
        primary_type=model.ContentTypeV3.PRODUCT_DEMONSTRATION,
        secondary_types=[model.ContentTypeV3.TUTORIAL],
        topology=model.TopologyV3.LINEAR,
        evidence_timecodes=[reference],
        confidence=0.9,
    )
    observation = model.ObservationV3(
        facts=model.ObservationFactsV3(
            summary="product demo",
            subjects=["presenter"],
            product_facts=["product visible"],
        ),
        timeline=[
            model.TimelineEntryV3(
                start_seconds=1.0,
                end_seconds=2.0,
                evidence_sources=[reference],
                subject="presenter",
                action_phases=[model.ActionPhaseV3.FEEDBACK],
                provable_claims=["product bends"],
                defects=[model.DefectCategoryV3.CAMERA],
                confidence=0.8,
            )
        ],
        claim_evidence_chains=[
            model.ClaimEvidenceChainV3(
                claim="flexible",
                references=[reference],
                supported=True,
            )
        ],
        business_logic=model.BusinessLogicAnswersV3(visible_proof="bend is visible"),
        defects=[
            model.DefectV3(
                category=model.DefectCategoryV3.CAMERA,
                description="minor shake",
                references=[reference],
                confidence=0.7,
            )
        ],
    )
    evidence_card = model.EvidenceCardV3(
        source_id="fixture-video",
        technical_metadata=model.TechnicalMetadataV3(
            duration_seconds=10,
            width=1080,
            height=1920,
            aspect_ratio="9:16",
            fps=30,
            has_audio_stream=True,
            format_name="mp4",
            size_bytes=1024,
        ),
        input_mode=model.InputModeV3.FULL_VIDEO,
        sampled_frame_count=2,
        sampled_timestamps=[1.0, 2.0],
        observed_ranges=[observed_range],
        coverage_limitations=["ending not sampled"],
        product_reference=model.ExternalEvidenceAvailabilityV3(
            status=model.ExternalEvidenceStatusV3.AVAILABLE,
            detail="catalog",
        ),
        evidence_complete=False,
        missing_evidence=["performance metrics"],
        limitations=["no metrics"],
    )
    evaluation = model.EvaluationResultV3(
        review_route="R",
        evidence_review=model.EvidenceReviewV3(
            evidence_complete=False,
            missing_evidence=["metrics"],
            limitations=["organic reach unknown"],
            confidence=0.7,
        ),
        g0_assessment=model.G0AssessmentV3(
            findings=[
                model.G0FindingV3(
                    category=model.DefectCategoryV3.CAMERA,
                    description="no blocking issue",
                    triggered=False,
                    evidence_timestamps=[reference],
                    confidence=0.8,
                )
            ]
        ),
        specialized_score_r=model.ReferenceScoreRV3(),
        supplemental_evidence=[
            model.SupplementalEvidenceV3(
                description="audio cue",
                references=[reference],
                affected_dimension_ids=["C2"],
                confidence=0.6,
            )
        ],
        evidence_conflicts=[
            model.EvidenceConflictV3(
                observation_claim="product visible",
                evaluation_claim="proof incomplete",
                references=[reference],
                affected_dimension_ids=["C5"],
                confidence=0.6,
            )
        ],
        diagnostic_total=42,
    )
    return model.AnalysisResultV3(
        evidence_card=evidence_card,
        content_classification=classification,
        observation=observation,
        evaluation=evaluation,
        decision=model.DecisionV3(
            gate_status=model.GateStatusV3.INSUFFICIENT_EVIDENCE,
            scoring_status=model.ScoringStatusV3.PROVISIONAL,
            system_disposition=model.SystemDispositionV3.OWNER_REVIEW_REQUIRED,
            reasons=["owner review"],
        ),
        technical_analysis=model.TechnicalAnalysisV3(
            scene_count=2,
            average_shot_duration=5,
            cut_frequency=0.2,
            audio_summary="voice",
        ),
    )


def build_route_result(model, route):
    classification = model.ContentClassificationV3(
        primary_type=model.ContentTypeV3.PRODUCT_DEMONSTRATION,
        topology=model.TopologyV3.LINEAR,
    )
    decision = model.DecisionV3(
        gate_status=model.GateStatusV3.INSUFFICIENT_EVIDENCE,
        scoring_status=model.ScoringStatusV3.UNAVAILABLE,
        system_disposition=model.SystemDispositionV3.OWNER_REVIEW_REQUIRED,
    )
    evaluation = model.EvaluationResultV3()
    if route == "G":
        specialized_score = model.GeneratedScoreGV3()
        dimensions = [
            dimension.model_copy(
                update={
                    "unscorable_reason": "Missing product reference evidence",
                }
            )
            if dimension.dimension_id == "G1"
            else dimension
            for dimension in specialized_score.dimensions
        ]
        evaluation = model.EvaluationResultV3(
            review_route="G",
            specialized_score_g=model.GeneratedScoreGV3(dimensions=dimensions),
        )
    return model.AnalysisResultV3(
        content_classification=classification,
        evaluation=evaluation,
        decision=decision,
    )


def build_v2_result():
    sys.path.insert(0, str(ROOT / "backend/app"))
    from models.results import AnalysisResult

    return AnalysisResult()


def write_fixture(name: str, result) -> None:
    payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    (FIXTURE_DIR / name).write_text(f"{payload}\n", encoding="utf-8")


def main() -> None:
    model = load_model_module()
    write_fixture("analysis-v2.json", build_v2_result())
    write_fixture("analysis-v3.json", build_result(model))
    write_fixture("analysis-v3-c.json", build_route_result(model, "C"))
    write_fixture("analysis-v3-g.json", build_route_result(model, "G"))


if __name__ == "__main__":
    main()
