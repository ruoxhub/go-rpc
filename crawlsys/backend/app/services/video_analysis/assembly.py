"""Deterministic assembly of the latest evidence-first video-analysis result."""

import logging
from collections.abc import Mapping
from math import isfinite
from types import MappingProxyType
from typing import Final, Literal

from pydantic import ValidationError

from models.video_analysis_runtime import (
    AnalysisArtifacts,
    AnalysisRequest,
    MediaCoverage,
    MediaProbe,
    MediaTimeRange,
    VideoMetadata,
    VideoSignals,
)
from models.video_analysis import (
    AnalysisMeta,
    AnalysisResult,
    AnalysisTimings,
    CommonScoreC,
    Decision,
    EvaluationDraft,
    EvaluationResult,
    EvidenceCard,
    EvidenceReference,
    GateStatus,
    GeneratedScoreG,
    InputMode,
    ObservationResult,
    ReferenceScoreR,
    ScoreDimension,
    ScoringStatus,
    SystemDisposition,
    TechnicalAnalysis,
    TimeRange,
)

ScoreSpec = tuple[tuple[str, str, int], ...]
Route = Literal["R", "G"] | None

COMMON_SCORE_SPECS: Final[ScoreSpec] = (
    ("C1", "受众与购买需求", 6),
    ("C2", "钩子停留能力", 10),
    ("C3", "商品识别与曝光", 6),
    ("C4", "卖点选择", 8),
    ("C5", "可见证据链", 12),
    ("C6", "节奏与信息密度", 8),
    ("C7", "记忆点与商品绑定", 6),
    ("C8", "信任、顾虑与行动", 4),
)
REFERENCE_SCORE_SPECS: Final[ScoreSpec] = (
    ("R1", "时间线与结构可拆解性", 8),
    ("R2", "AI 复刻友好度", 10),
    ("R3", "可迁移变量丰富度", 8),
    ("R4", "换成我方商品的安全性", 6),
    ("R5", "生产成本与稳定性", 4),
    ("R6", "差异化潜力", 4),
)
GENERATED_SCORE_SPECS: Final[ScoreSpec] = (
    ("G1", "商品一致性", 12),
    ("G2", "人物身份与服装层级", 5),
    ("G3", "动作完整性与力量感", 8),
    ("G4", "物理、接触与回弹", 6),
    ("G5", "镜头与构图连续性", 4),
    ("G6", "技术画质", 3),
    ("G7", "背景、灯光与声音联动", 2),
)

SCORING_SPECS: Final[Mapping[str, ScoreSpec]] = MappingProxyType(
    {"C": COMMON_SCORE_SPECS, "R": REFERENCE_SCORE_SPECS, "G": GENERATED_SCORE_SPECS}
)
PRODUCT_REFERENCE_DIMENSIONS: Final = frozenset({"R4", "G1"})
ASSEMBLER_OWNED_FIELDS: Final = frozenset(
    {"partial_points", "partial_max_points", "diagnostic_total"}
)
LOW_CONFIDENCE_THRESHOLD: Final = 0.5

logger = logging.getLogger(__name__)


class InvalidEvaluationStructureError(ValueError):
    """Raised when an evaluation violates the frozen scoring contract."""


def _validate_evaluation(evaluation: EvaluationDraft) -> EvaluationDraft:
    if type(evaluation) is not EvaluationDraft or ASSEMBLER_OWNED_FIELDS.intersection(
        evaluation.__dict__
    ):
        raise InvalidEvaluationStructureError("evaluation must be an evaluation draft")
    try:
        return EvaluationDraft.model_validate(evaluation.model_dump())
    except ValidationError:
        raise InvalidEvaluationStructureError("invalid evaluation structure") from None


def _validate_request_route(request: AnalysisRequest, route: Route) -> None:
    if request.review_route != route:
        raise InvalidEvaluationStructureError("evaluation route does not match request")


def _has_positive_timecode(references: list[EvidenceReference]) -> bool:
    return any(
        reference.positive
        and (reference.timestamp is not None or reference.time_range is not None)
        for reference in references
    )


def _validate_section(dimensions: list[ScoreDimension], specs: ScoreSpec) -> None:
    expected = {
        dimension_id: (name, max_points)
        for dimension_id, name, max_points in specs
    }
    actual = {
        dimension.dimension_id: (dimension.name, dimension.max_points)
        for dimension in dimensions
    }
    if len(dimensions) != len(specs) or actual != expected:
        raise InvalidEvaluationStructureError("invalid score dimensions")
    for dimension in dimensions:
        max_points = expected[dimension.dimension_id][1]
        if dimension.scorable:
            points = dimension.awarded_points
            if points is None or not 0 <= points <= max_points:
                raise InvalidEvaluationStructureError("invalid awarded points")
            if points == max_points and not _has_positive_timecode(
                dimension.evidence_timestamps
            ):
                raise InvalidEvaluationStructureError("full score lacks timecoded evidence")
        elif dimension.awarded_points is not None:
            raise InvalidEvaluationStructureError("unscorable dimension awards points")


def _validate_scoring_contract(evaluation: EvaluationDraft) -> None:
    _validate_section(evaluation.common_score_c.dimensions, SCORING_SPECS["C"])
    route = evaluation.review_route
    if route == "R":
        if (
            evaluation.specialized_score_r is None
            or evaluation.specialized_score_g is not None
        ):
            raise InvalidEvaluationStructureError("invalid route section")
        _validate_section(evaluation.specialized_score_r.dimensions, SCORING_SPECS["R"])
    elif route == "G":
        if (
            evaluation.specialized_score_g is None
            or evaluation.specialized_score_r is not None
        ):
            raise InvalidEvaluationStructureError("invalid route section")
        _validate_section(evaluation.specialized_score_g.dimensions, SCORING_SPECS["G"])
    elif (
        evaluation.specialized_score_r is not None
        or evaluation.specialized_score_g is not None
    ):
        raise InvalidEvaluationStructureError("invalid route section")


def _unscore_dimensions(
    dimensions: list[ScoreDimension], reasons: dict[str, str]
) -> list[ScoreDimension]:
    return [
        dimension.model_copy(
            update={
                "awarded_points": None,
                "scorable": False,
                "unscorable_reason": reasons[dimension.dimension_id],
            }
        )
        if dimension.dimension_id in reasons
        else dimension.model_copy(deep=True)
        for dimension in dimensions
    ]


def _conflict_reasons(evaluation: EvaluationDraft) -> dict[str, str]:
    known_ids = {
        dimension_id
        for specs in SCORING_SPECS.values()
        for dimension_id, _, _ in specs
    }
    reasons: dict[str, str] = {}
    for conflict in evaluation.evidence_conflicts:
        for dimension_id in conflict.affected_dimension_ids:
            if dimension_id not in known_ids:
                raise InvalidEvaluationStructureError(
                    "conflict references an unknown dimension"
                )
            reasons[dimension_id] = "Unscorable because observation and evaluation conflict"
    return reasons


def _copy_scoring(evaluation: EvaluationDraft) -> tuple[
    CommonScoreC, ReferenceScoreR | None, GeneratedScoreG | None
]:
    reasons = _conflict_reasons(evaluation)
    reasons.update(
        {
            dimension_id: "Unscorable because product reference evidence was not provided"
            for dimension_id in PRODUCT_REFERENCE_DIMENSIONS
        }
    )
    common = CommonScoreC(
        dimensions=_unscore_dimensions(evaluation.common_score_c.dimensions, reasons)
    )
    reference = (
        ReferenceScoreR(
            dimensions=_unscore_dimensions(
                evaluation.specialized_score_r.dimensions, reasons
            )
        )
        if evaluation.specialized_score_r is not None
        else None
    )
    generated = (
        GeneratedScoreG(
            dimensions=_unscore_dimensions(
                evaluation.specialized_score_g.dimensions, reasons
            )
        )
        if evaluation.specialized_score_g is not None
        else None
    )
    return common, reference, generated


def _selected_dimensions(
    route: Route,
    common: CommonScoreC,
    reference: ReferenceScoreR | None,
    generated: GeneratedScoreG | None,
) -> list[ScoreDimension]:
    selected = list(common.dimensions)
    if route == "R" and reference is not None:
        selected.extend(reference.dimensions)
    elif route == "G" and generated is not None:
        selected.extend(generated.dimensions)
    return selected


def _totals(
    route: Route, dimensions: list[ScoreDimension]
) -> tuple[float, float, float | None]:
    scorable = [dimension for dimension in dimensions if dimension.scorable]
    partial_points = sum(dimension.awarded_points or 0 for dimension in scorable)
    partial_max_points = sum(dimension.max_points for dimension in scorable)
    complete = len(scorable) == len(dimensions)
    diagnostic_total = partial_points if route is not None and complete else None
    return partial_points, partial_max_points, diagnostic_total


def _time_range(value: MediaTimeRange) -> TimeRange:
    return TimeRange(
        start_seconds=value.start_seconds,
        end_seconds=value.end_seconds,
        start_inclusive=value.start_inclusive,
        end_inclusive=value.end_inclusive,
    )


def _is_canonical_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _sampled_coverage_mismatch_reason(
    artifacts: AnalysisArtifacts, coverage: MediaCoverage, duration: float
) -> str | None:
    """Return the first validation mismatch for SAMPLED_FRAMES coverage, else None."""
    timestamps = coverage.sampled_timestamps

    def _expected_ranges() -> tuple[
        tuple[MediaTimeRange, ...], tuple[MediaTimeRange, ...]
    ]:
        observed = tuple(MediaTimeRange(t, t) for t in timestamps)
        unobserved: list[MediaTimeRange] = []
        if not timestamps:
            unobserved.append(MediaTimeRange(0.0, duration))
        else:
            if timestamps[0] > 0:
                unobserved.append(MediaTimeRange(0.0, timestamps[0], True, False))
            unobserved.extend(
                MediaTimeRange(start, end, False, False)
                for start, end in zip(timestamps, timestamps[1:])
            )
            if timestamps[-1] < duration:
                unobserved.append(
                    MediaTimeRange(timestamps[-1], duration, False, True)
                )
        return observed, tuple(unobserved)

    if tuple(artifacts.timestamps) != timestamps:
        return (
            f"artifacts.timestamps={tuple(artifacts.timestamps)!r} != "
            f"coverage.sampled_timestamps={timestamps!r}"
        )
    if len(artifacts.frames) != len(timestamps):
        return (
            f"len(artifacts.frames)={len(artifacts.frames)} != "
            f"len(coverage.sampled_timestamps)={len(timestamps)}"
        )
    if timestamps != tuple(sorted(set(timestamps))):
        return f"sampled_timestamps not strictly sorted/deduped: {timestamps!r}"
    out_of_range = [
        t for t in timestamps if not isfinite(t) or not (0 <= t <= duration)
    ]
    if out_of_range:
        return f"sampled_timestamps outside [0, {duration}]: {out_of_range!r}"
    expected_observed, expected_unobserved = _expected_ranges()
    if coverage.observed_ranges != expected_observed:
        return (
            f"observed_ranges={coverage.observed_ranges!r} != "
            f"expected={expected_observed!r}"
        )
    if coverage.unobserved_ranges != expected_unobserved:
        return (
            f"unobserved_ranges={coverage.unobserved_ranges!r} != "
            f"expected={expected_unobserved!r}"
        )
    return None


def _sampled_coverage_matches_artifacts(
    artifacts: AnalysisArtifacts, coverage: MediaCoverage, duration: float
) -> bool:
    return (
        _sampled_coverage_mismatch_reason(artifacts, coverage, duration) is None
    )


def _valid_media_range(value: MediaTimeRange) -> bool:
    return (
        isinstance(value.start_seconds, (int, float))
        and not isinstance(value.start_seconds, bool)
        and isinstance(value.end_seconds, (int, float))
        and not isinstance(value.end_seconds, bool)
        and isinstance(value.start_inclusive, bool)
        and isinstance(value.end_inclusive, bool)
        and isfinite(value.start_seconds)
        and isfinite(value.end_seconds)
        and value.start_seconds >= 0
        and value.end_seconds >= value.start_seconds
        and (
            value.end_seconds > value.start_seconds
            or (value.start_inclusive and value.end_inclusive)
        )
    )


def _artifacts_validation_reason(artifacts: AnalysisArtifacts) -> str | None:
    """Return the first failing artifact-validation check, else None."""
    coverage = artifacts.coverage
    metadata = artifacts.metadata
    if not isinstance(coverage, MediaCoverage):
        return f"coverage is {type(coverage).__name__}, not MediaCoverage"
    if not isinstance(metadata, VideoMetadata):
        return f"metadata is {type(metadata).__name__}, not VideoMetadata"
    if artifacts.media_probe is not None and not isinstance(
        artifacts.media_probe, MediaProbe
    ):
        return (
            f"media_probe is {type(artifacts.media_probe).__name__}, not MediaProbe"
        )
    if artifacts.signals is not None and not isinstance(
        artifacts.signals, VideoSignals
    ):
        return f"signals is {type(artifacts.signals).__name__}, not VideoSignals"
    duration_value = metadata.duration
    if not isinstance(duration_value, (int, float)) or isinstance(
        duration_value, bool
    ):
        return f"metadata.duration has invalid type {type(duration_value).__name__}"
    if not isfinite(duration_value) or duration_value <= 0:
        return f"metadata.duration={duration_value!r} must be finite and > 0"
    if not isinstance(metadata.width, int) or isinstance(metadata.width, bool):
        return f"metadata.width has invalid type {type(metadata.width).__name__}"
    if metadata.width <= 0:
        return f"metadata.width={metadata.width} must be > 0"
    if not isinstance(metadata.height, int) or isinstance(metadata.height, bool):
        return f"metadata.height has invalid type {type(metadata.height).__name__}"
    if metadata.height <= 0:
        return f"metadata.height={metadata.height} must be > 0"
    if not isinstance(coverage.input_mode, InputMode):
        return f"coverage.input_mode={coverage.input_mode!r} is not an InputMode"
    if not isinstance(coverage.sampled_timestamps, tuple):
        return "coverage.sampled_timestamps is not a tuple"
    bad_timestamp = next(
        (
            timestamp
            for timestamp in coverage.sampled_timestamps
            if not isinstance(timestamp, (int, float))
            or isinstance(timestamp, bool)
        ),
        None,
    )
    if bad_timestamp is not None:
        return f"sampled_timestamp {bad_timestamp!r} has invalid type"
    if not isinstance(coverage.observed_ranges, tuple):
        return "coverage.observed_ranges is not a tuple"
    if not isinstance(coverage.unobserved_ranges, tuple):
        return "coverage.unobserved_ranges is not a tuple"
    if any(
        not isinstance(value, MediaTimeRange)
        for value in coverage.observed_ranges + coverage.unobserved_ranges
    ):
        return "coverage ranges contain non-MediaTimeRange values"
    if not isinstance(coverage.limitations, tuple):
        return "coverage.limitations is not a tuple"
    if not all(isinstance(value, str) for value in coverage.limitations):
        return "coverage.limitations contain non-string values"
    if not isinstance(artifacts.timestamps, list):
        return f"artifacts.timestamps is {type(artifacts.timestamps).__name__}, not list"
    if not isinstance(artifacts.frames, list):
        return f"artifacts.frames is {type(artifacts.frames).__name__}, not list"

    duration = float(duration_value)
    if not _is_canonical_sha256(artifacts.source_sha256):
        return f"source_sha256={artifacts.source_sha256!r} is not canonical sha256"
    expected_source_id = f"sha256:{artifacts.source_sha256}"
    if artifacts.source_id != expected_source_id:
        return (
            f"source_id={artifacts.source_id!r} != expected {expected_source_id!r}"
        )
    invalid_range = next(
        (
            value
            for value in coverage.observed_ranges + coverage.unobserved_ranges
            if not _valid_media_range(value) or value.end_seconds > duration
        ),
        None,
    )
    if invalid_range is not None:
        return (
            f"media range {invalid_range!r} invalid or exceeds duration "
            f"{duration}"
        )
    if coverage.input_mode is InputMode.FULL_VIDEO:
        if coverage.sampled_timestamps:
            return (
                f"FULL_VIDEO coverage must not sample frames, got "
                f"{coverage.sampled_timestamps!r}"
            )
        expected_observed = (MediaTimeRange(0.0, duration, True, True),)
        if coverage.observed_ranges != expected_observed:
            return (
                f"FULL_VIDEO observed_ranges={coverage.observed_ranges!r} != "
                f"{expected_observed!r}"
            )
        if coverage.unobserved_ranges:
            return (
                f"FULL_VIDEO must not mark unobserved ranges, got "
                f"{coverage.unobserved_ranges!r}"
            )
    if coverage.input_mode is InputMode.SAMPLED_FRAMES:
        reason = _sampled_coverage_mismatch_reason(artifacts, coverage, duration)
        if reason is not None:
            return f"SAMPLED_FRAMES mismatch: {reason}"
    return None


def _validate_artifacts(artifacts: AnalysisArtifacts) -> MediaCoverage:
    failure = _artifacts_validation_reason(artifacts)
    if failure is not None:
        logger.error("invalid analysis artifacts: %s", failure)
        raise InvalidEvaluationStructureError("invalid analysis artifacts")
    return artifacts.coverage


def _evidence_card_payload(
    artifacts: AnalysisArtifacts,
    evaluation: EvaluationDraft,
    coverage: MediaCoverage,
) -> dict[str, object]:
    metadata = artifacts.metadata
    probe = artifacts.media_probe
    missing = list(evaluation.evidence_review.missing_evidence)
    if evaluation.review_route is not None:
        product_reference_missing = "product reference evidence was not provided"
        if product_reference_missing not in missing:
            missing.append(product_reference_missing)
    return {
        "source_id": artifacts.source_id,
        "source_sha256": artifacts.source_sha256,
        "technical_metadata": {
            "duration_seconds": (
                metadata.duration
                if metadata
                else probe.duration_seconds
                if probe
                else None
            ),
            "width": metadata.width if metadata else None,
            "height": metadata.height if metadata else None,
            "aspect_ratio": metadata.aspect_ratio if metadata else None,
            "fps": metadata.fps if metadata else None,
            "has_audio_stream": metadata.has_audio_stream if metadata else None,
            "format_name": probe.format_name if probe else None,
            "size_bytes": probe.size_bytes if probe else None,
        },
        "input_mode": coverage.input_mode,
        "sampled_frame_count": len(artifacts.frames),
        "sampled_timestamps": list(coverage.sampled_timestamps),
        "observed_ranges": [_time_range(value) for value in coverage.observed_ranges],
        "unobserved_ranges": [
            _time_range(value) for value in coverage.unobserved_ranges
        ],
        "coverage_limitations": list(coverage.limitations),
        "evidence_complete": (
            evaluation.evidence_review.evidence_complete
            if evaluation.review_route is None
            else False
        ),
        "missing_evidence": missing,
        "limitations": list(evaluation.evidence_review.limitations),
        "official_scoring_ready": False,
    }


def _build_evidence_card(
    artifacts: AnalysisArtifacts,
    evaluation: EvaluationDraft,
    coverage: MediaCoverage,
) -> EvidenceCard:
    payload = _evidence_card_payload(artifacts, evaluation, coverage)
    evidence_card = None
    try:
        evidence_card = EvidenceCard.model_validate(payload)
    except (ValidationError, TypeError):
        pass
    if evidence_card is None:
        raise InvalidEvaluationStructureError("invalid analysis artifacts")
    return evidence_card


def _technical_analysis(artifacts: AnalysisArtifacts) -> TechnicalAnalysis | None:
    signals = artifacts.signals
    if signals is None:
        return None
    return TechnicalAnalysis(
        scene_count=len(signals.scenes),
        average_shot_duration=signals.average_shot_duration,
        cut_frequency=signals.cut_frequency,
    )


def _has_timecoded_g0(evaluation: EvaluationDraft) -> bool:
    return any(
        finding.triggered and _has_positive_timecode(finding.evidence_timestamps)
        for finding in evaluation.g0_assessment.findings
    )


def _has_low_confidence_conflict(evaluation: EvaluationDraft) -> bool:
    return any(
        conflict.confidence is not None
        and conflict.confidence < LOW_CONFIDENCE_THRESHOLD
        for conflict in evaluation.evidence_conflicts
    )


def _decision(
    evaluation: EvaluationDraft,
    diagnostic_total: float | None,
    dimensions: list[ScoreDimension],
) -> Decision:
    if _has_timecoded_g0(evaluation):
        return Decision(
            gate_status=GateStatus.BLOCK,
            scoring_status=(
                ScoringStatus.PROVISIONAL
                if diagnostic_total is not None
                else ScoringStatus.UNAVAILABLE
            ),
            recommended_grade=None,
            system_disposition=SystemDisposition.REJECT,
            reasons=["Timecoded positive G0 evidence requires rejection"],
        )
    incomplete = any(not dimension.scorable for dimension in dimensions)
    insufficient = (
        _has_low_confidence_conflict(evaluation)
        or not evaluation.evidence_review.evidence_complete
        or incomplete
    )
    return Decision(
        gate_status=(
            GateStatus.INSUFFICIENT_EVIDENCE if insufficient else GateStatus.PASS
        ),
        scoring_status=(
            ScoringStatus.PROVISIONAL
            if diagnostic_total is not None
            else ScoringStatus.UNAVAILABLE
        ),
        recommended_grade=None,
        system_disposition=SystemDisposition.OWNER_REVIEW_REQUIRED,
        reasons=["Evidence is incomplete"] if insufficient else [],
    )


def assemble_analysis_result(
    *,
    request: AnalysisRequest,
    artifacts: AnalysisArtifacts,
    observation: ObservationResult,
    evaluation: EvaluationDraft,
    timings: AnalysisTimings,
) -> AnalysisResult:
    """Validate, score, and assemble one analysis result without side effects."""

    draft = _validate_evaluation(evaluation)
    _validate_request_route(request, draft.review_route)
    _validate_scoring_contract(draft)
    coverage = _validate_artifacts(artifacts)
    common, reference, generated = _copy_scoring(draft)
    dimensions = _selected_dimensions(draft.review_route, common, reference, generated)
    partial_points, partial_max_points, diagnostic_total = _totals(
        draft.review_route, dimensions
    )
    evidence_card = _build_evidence_card(artifacts, draft, coverage)
    evaluation_payload = draft.model_dump(
        exclude={
            "common_score_c",
            "specialized_score_r",
            "specialized_score_g",
        }
    )
    result_evaluation = None
    try:
        result_evaluation = EvaluationResult(
            **evaluation_payload,
            common_score_c=common,
            specialized_score_r=reference,
            specialized_score_g=generated,
            partial_points=partial_points,
            partial_max_points=partial_max_points,
            diagnostic_total=diagnostic_total,
        )
    except (ValidationError, TypeError):
        pass
    if result_evaluation is None:
        raise InvalidEvaluationStructureError("invalid analysis result")

    timings_copy = timings.model_copy(deep=True)
    content_classification = observation.content_classification.model_copy(deep=True)
    observation_copy = observation.observation.model_copy(deep=True)
    decision = _decision(draft, diagnostic_total, dimensions)
    technical_analysis = _technical_analysis(artifacts)

    meta = None
    try:
        meta = AnalysisMeta(
            observation_model_name=request.model,
            evaluation_model_name=request.model,
            source_frames_count=len(artifacts.frames),
            confidence_overall=draft.evidence_review.confidence,
            timings=timings_copy,
        )
    except (ValidationError, TypeError):
        pass
    if meta is None:
        raise InvalidEvaluationStructureError("invalid analysis result")

    result = None
    try:
        result = AnalysisResult(
            meta=meta,
            evidence_card=evidence_card,
            content_classification=content_classification,
            observation=observation_copy,
            evaluation=result_evaluation,
            decision=decision,
            technical_analysis=technical_analysis,
        )
    except (ValidationError, TypeError):
        pass
    if result is None:
        raise InvalidEvaluationStructureError("invalid analysis result")
    return result


__all__ = ["InvalidEvaluationStructureError", "assemble_analysis_result"]
