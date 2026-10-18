"""Evidence-first video-analysis contracts for schema v4.0."""

from enum import Enum
from typing import ClassVar, Literal

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field, field_validator, model_validator


class VideoAnalysisModel(PydanticBaseModel):
    """Lenient base for LLM-produced model payloads.

    Models emit unknown extra fields beyond the JSON schema (e.g. an extra
    ``lighting`` key inside a timeline entry); unknown keys are dropped instead
    of failing the whole task. Deterministic result shells that must stay strict
    (``AnalysisResult``) re-enable ``extra="forbid"`` explicitly.
    """

    model_config = ConfigDict(extra="ignore")


class ExternalEvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_PROVIDED = "NOT_PROVIDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class InputMode(str, Enum):
    FULL_VIDEO = "FULL_VIDEO"
    SAMPLED_FRAMES = "SAMPLED_FRAMES"


class EvidenceSource(str, Enum):
    VIDEO = "VIDEO"
    FRAME = "FRAME"
    AUDIO = "AUDIO"
    TRANSCRIPT = "TRANSCRIPT"
    TECHNICAL_METADATA = "TECHNICAL_METADATA"
    EXTERNAL = "EXTERNAL"


class GateStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ScoringStatus(str, Enum):
    PROVISIONAL = "PROVISIONAL"
    UNAVAILABLE = "UNAVAILABLE"


class SystemDisposition(str, Enum):
    REJECT = "REJECT"
    OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"
    PRIORITY_PRODUCTION = "PRIORITY_PRODUCTION"
    REPAIR_THEN_PRODUCTION = "REPAIR_THEN_PRODUCTION"
    EXPERIMENT_ONLY = "EXPERIMENT_ONLY"
    DEPRIORITIZE = "DEPRIORITIZE"
    REDESIGN = "REDESIGN"


class Grade(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ContentType(str, Enum):
    HOOK_FAST_ACTION = "HOOK_FAST_ACTION"
    FUNCTIONAL_PROOF = "FUNCTIONAL_PROOF"
    PROBLEM_SOLUTION = "PROBLEM_SOLUTION"
    MULTI_COLOR_OR_PACK = "MULTI_COLOR_OR_PACK"
    UGC_TRY_ON = "UGC_TRY_ON"
    SCENARIO_IMMERSION = "SCENARIO_IMMERSION"
    COMMENT_OR_FAQ = "COMMENT_OR_FAQ"
    COMPARISON_CHOICE = "COMPARISON_CHOICE"
    OUTFIT_TRANSFORMATION = "OUTFIT_TRANSFORMATION"
    ATMOSPHERE_BRAND = "ATMOSPHERE_BRAND"


class Topology(str, Enum):
    ONE_TAKE = "ONE_TAKE"
    PRIMARY_TAKE_WITH_ONE_OR_TWO_CUTS = "PRIMARY_TAKE_WITH_ONE_OR_TWO_CUTS"
    MULTI_SHOT_FAST_CUT = "MULTI_SHOT_FAST_CUT"
    OCCLUSION_TRANSITION = "OCCLUSION_TRANSITION"
    COLOR_OR_OUTFIT_TRANSFORMATION = "COLOR_OR_OUTFIT_TRANSFORMATION"
    BEFORE_AFTER_COMPARISON = "BEFORE_AFTER_COMPARISON"


class ActionPhase(str, Enum):
    POSITIONING = "POSITIONING"
    FORCE = "FORCE"
    PEAK = "PEAK"
    FEEDBACK = "FEEDBACK"
    RELEASE = "RELEASE"
    RECOVERY = "RECOVERY"


class DefectCategory(str, Enum):
    PRODUCT = "PRODUCT"
    PERSON = "PERSON"
    PHYSICS = "PHYSICS"
    CAMERA = "CAMERA"
    DELIVERY = "DELIVERY"
    VISUAL_QUALITY = "VISUAL_QUALITY"
    AUDIO = "AUDIO"
    OTHER = "OTHER"


class TimeRange(VideoAnalysisModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    start_inclusive: bool = True
    end_inclusive: bool = True

    @model_validator(mode="after")
    def validate_order(self):
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")
        if self.end_seconds == self.start_seconds and not (
            self.start_inclusive and self.end_inclusive
        ):
            raise ValueError("zero-width ranges must include both boundaries")
        return self


class EvidenceReference(VideoAnalysisModel):
    source: EvidenceSource
    timestamp: float | None = Field(default=None, ge=0)
    time_range: TimeRange | None = None
    description: str | None = None
    positive: bool = True


class ExternalEvidenceAvailability(VideoAnalysisModel):
    status: ExternalEvidenceStatus = ExternalEvidenceStatus.NOT_PROVIDED
    detail: str | None = None


class ScoreDimension(VideoAnalysisModel):
    dimension_id: str | None = None
    name: str | None = None
    awarded_points: float | None = None
    max_points: float = Field(gt=0)
    reason: str | None = None
    evidence_timestamps: list[EvidenceReference] = Field(default_factory=list)
    scorable: bool = False
    unscorable_reason: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_scoring_contract(self):
        if not self.scorable and self.awarded_points is not None:
            raise ValueError("unscorable dimensions cannot award points")
        if self.scorable and self.awarded_points is None:
            raise ValueError("scorable dimensions must award points")
        if self.awarded_points is not None and not 0 <= self.awarded_points <= self.max_points:
            raise ValueError("awarded_points must be between zero and max_points")
        if self.awarded_points == self.max_points and not any(
            evidence.positive
            and (evidence.timestamp is not None or evidence.time_range is not None)
            for evidence in self.evidence_timestamps
        ):
            raise ValueError("full score requires positive timecoded evidence")
        return self


class SupplementalEvidence(VideoAnalysisModel):
    description: str
    references: list[EvidenceReference] = Field(default_factory=list)
    affected_dimension_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class EvidenceConflict(VideoAnalysisModel):
    observation_claim: str
    evaluation_claim: str
    references: list[EvidenceReference] = Field(default_factory=list)
    affected_dimension_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class AnalysisTimings(VideoAnalysisModel):
    observation_duration_ms: int | None = Field(default=None, ge=0)
    evaluation_duration_ms: int | None = Field(default=None, ge=0)
    total_duration_ms: int | None = Field(default=None, ge=0)
    observation_attempts: int = Field(default=1, ge=1)
    evaluation_attempts: int = Field(default=1, ge=1)


class TechnicalMetadata(VideoAnalysisModel):
    duration_seconds: float | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    aspect_ratio: str | None = None
    fps: float | None = Field(default=None, ge=0)
    has_audio_stream: bool | None = None
    format_name: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class EvidenceCard(VideoAnalysisModel):
    source_id: str | None = None
    source_sha256: str | None = None
    technical_metadata: TechnicalMetadata = Field(default_factory=TechnicalMetadata)
    input_mode: InputMode | None = None
    sampled_frame_count: int = Field(default=0, ge=0)
    sampled_timestamps: list[float] = Field(default_factory=list)
    observed_ranges: list[TimeRange] = Field(default_factory=list)
    unobserved_ranges: list[TimeRange] = Field(default_factory=list)
    coverage_limitations: list[str] = Field(default_factory=list)
    product_reference: ExternalEvidenceAvailability = Field(
        default_factory=ExternalEvidenceAvailability
    )
    publishing_context: ExternalEvidenceAvailability = Field(
        default_factory=ExternalEvidenceAvailability
    )
    performance_metrics: ExternalEvidenceAvailability = Field(
        default_factory=ExternalEvidenceAvailability
    )
    task_constraints: ExternalEvidenceAvailability = Field(
        default_factory=ExternalEvidenceAvailability
    )
    evidence_complete: bool = False
    official_scoring_ready: Literal[False] = False
    missing_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("sampled_timestamps")
    @classmethod
    def validate_sampled_timestamps(cls, value: list[float]):
        if any(timestamp < 0 for timestamp in value):
            raise ValueError("sampled timestamps must be non-negative")
        return value


class ContentClassification(VideoAnalysisModel):
    primary_type: ContentType
    secondary_types: list[ContentType] = Field(default_factory=list, max_length=2)
    topology: Topology
    evidence_timecodes: list[EvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("secondary_types")
    @classmethod
    def validate_secondary_types(cls, value: list[ContentType]):
        if len(value) != len(set(value)):
            raise ValueError("secondary content types must be unique")
        return value


class ObservationFacts(VideoAnalysisModel):
    summary: str | None = None
    subjects: list[str] = Field(default_factory=list)
    person_facts: list[str] = Field(default_factory=list)
    product_facts: list[str] = Field(default_factory=list)
    scene_facts: list[str] = Field(default_factory=list)


class TimelineEntry(TimeRange):
    evidence_sources: list[EvidenceReference] = Field(default_factory=list)
    subject: str | None = None
    person_pose: str | None = None
    person_action: str | None = None
    product_action: str | None = None
    primary_hand: str | None = None
    secondary_hand: str | None = None
    grip_point: str | None = None
    direction: str | None = None
    action_phases: list[ActionPhase] = Field(default_factory=list)
    product_state: str | None = None
    product_drift: str | None = None
    occlusion: str | None = None
    camera: str | None = None
    composition: str | None = None
    shooting_method: str | None = None
    action_purpose: str | None = None
    marketing_purpose: str | None = None
    emotion_state: str | None = None
    emotion_intensity: float | None = Field(default=None, ge=0, le=10)
    transition_type: str | None = None
    rhythm_density: str | None = None
    subtitle_text: str | None = None
    music_emotion: str | None = None
    is_hook_segment: bool | None = None
    is_conversion_closing_segment: bool | None = None
    key_frame_description: str | None = None
    background_motion: str | None = None
    lighting: str | None = None
    sound_feedback: str | None = None
    new_audience_information: str | None = None
    provable_claims: list[str] = Field(default_factory=list)
    defects: list[DefectCategory] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ClaimEvidenceChain(VideoAnalysisModel):
    claim: str
    product_structure: str | None = None
    demonstration_action: str | None = None
    visible_feedback: str | None = None
    usage_result: str | None = None
    user_benefit: str | None = None
    references: list[EvidenceReference] = Field(default_factory=list)
    supported: bool = False


class BusinessLogicAnswers(VideoAnalysisModel):
    audience_and_need: str | None = None
    hook_and_retention: str | None = None
    product_recognition: str | None = None
    selling_point: str | None = None
    visible_proof: str | None = None
    rhythm_and_density: str | None = None
    memory_and_product_binding: str | None = None
    trust_objection_and_action: str | None = None


class Defect(VideoAnalysisModel):
    category: DefectCategory
    description: str
    references: list[EvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TargetAudience(VideoAnalysisModel):
    gender: str | None = None
    age_range: str | None = None
    style_preferences: list[str] = Field(default_factory=list)
    price_sensitivity: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


class TargetDefinition(VideoAnalysisModel):
    target_audience: TargetAudience = Field(default_factory=TargetAudience)
    platform: str | None = None
    content_purpose: str | None = None
    primary_kpi: str | None = None
    target_duration_seconds: float | None = Field(default=None, ge=0)
    success_criteria: str | None = None


class CreativeConcept(VideoAnalysisModel):
    theme: str | None = None
    conflict: str | None = None
    hook_strategy: str | None = None
    memory_hook: str | None = None
    story_arc: str | None = None
    creative_tags: list[str] = Field(default_factory=list)


class EmotionBeat(VideoAnalysisModel):
    timestamp: float | None = Field(default=None, ge=0)
    emotion: str | None = None
    intensity: float | None = Field(default=None, ge=0, le=10)
    trigger: str | None = None


class EmotionArc(VideoAnalysisModel):
    opening_emotion: str | None = None
    middle_emotion: str | None = None
    ending_emotion: str | None = None
    peak_emotion: str | None = None
    beats: list[EmotionBeat] = Field(default_factory=list)
    summary: str | None = None


class PersonAnalysis(VideoAnalysisModel):
    identity: str | None = None
    appearance: str | None = None
    posture: str | None = None
    body_language: str | None = None
    orientation: str | None = None
    gaze_direction: str | None = None
    hand_actions: list[str] = Field(default_factory=list)
    gait: str | None = None
    stance: str | None = None
    action_rhythm: str | None = None
    identity_consistency: str | None = None


class ProductAnalysis(VideoAnalysisModel):
    name: str | None = None
    category: str | None = None
    color: str | None = None
    silhouette: str | None = None
    material: str | None = None
    key_structures: list[str] = Field(default_factory=list)
    visibility: str | None = None
    consistency: str | None = None
    reference_evidence_status: str | None = None


class SceneAnalysis(VideoAnalysisModel):
    background: str | None = None
    set_design: str | None = None
    lighting: str | None = None
    color_palette: str | None = None
    visual_quality: str | None = None
    shot_types: list[str] = Field(default_factory=list)
    camera_angles: list[str] = Field(default_factory=list)
    camera_movements: list[str] = Field(default_factory=list)
    composition: str | None = None
    color_grading: str | None = None
    style_summary: str | None = None


class MarketingPoint(VideoAnalysisModel):
    timestamp: float | None = Field(default=None, ge=0)
    description: str | None = None
    target_metric: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SellingPoint(VideoAnalysisModel):
    description: str | None = None
    priority: Literal["PRIMARY", "SECONDARY"] | None = None
    proof_action: str | None = None
    user_benefit: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ViralLogic(VideoAnalysisModel):
    why_retention: str | None = None
    why_click: str | None = None
    why_conversion: str | None = None
    why_viral: str | None = None
    core_selling_point: str | None = None
    key_conversion_action: str | None = None


class ViralFormula(VideoAnalysisModel):
    formula: str | None = None
    fixed_elements: list[str] = Field(default_factory=list)
    replaceable_variables: list[str] = Field(default_factory=list)
    replication_steps: list[str] = Field(default_factory=list)
    risk_controls: list[str] = Field(default_factory=list)


class KeyFramePrompt(VideoAnalysisModel):
    timestamp: float | None = Field(default=None, ge=0)
    description: str | None = None
    prompt: str | None = None


class ModelParameters(VideoAnalysisModel):
    duration_seconds: float | None = Field(default=None, ge=0)
    aspect_ratio: str | None = None
    resolution: str | None = None
    fps: float | None = Field(default=None, ge=0)
    guidance_scale: float | None = Field(default=None, ge=0)
    seed: int | None = None


class AIVideoPrompt(VideoAnalysisModel):
    subject_prompt: str | None = None
    scene_prompt: str | None = None
    action_prompt: str | None = None
    style_prompt: str | None = None
    full_prompt_zh: str | None = None
    full_prompt_en: str | None = None
    negative_prompt: str | None = None
    style_anchors: list[str] = Field(default_factory=list)
    key_frames: list[KeyFramePrompt] = Field(default_factory=list)
    consistency_constraints: list[str] = Field(default_factory=list)
    recommended_models: list[str] = Field(default_factory=list)
    recommended_parameters: ModelParameters = Field(default_factory=ModelParameters)


class IssueDiagnosis(VideoAnalysisModel):
    category: str | None = None
    description: str | None = None
    severity: Literal["LOW", "MEDIUM", "HIGH", "BLOCKING"] | None = None
    references: list[EvidenceReference] = Field(default_factory=list)
    correction: str | None = None


class IterationPlan(VideoAnalysisModel):
    first_pass_validation: list[str] = Field(default_factory=list)
    issues: list[IssueDiagnosis] = Field(default_factory=list)
    targeted_corrections: list[str] = Field(default_factory=list)
    revised_prompt_zh: str | None = None
    revised_prompt_en: str | None = None


class SubtitlePlan(VideoAnalysisModel):
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    text: str | None = None
    style: str | None = None


class PostProduction(VideoAnalysisModel):
    rhythm_plan: str | None = None
    subtitles: list[SubtitlePlan] = Field(default_factory=list)
    voiceover: str | None = None
    background_music: str | None = None
    sound_effects: list[str] = Field(default_factory=list)
    final_duration_seconds: float | None = Field(default=None, ge=0)
    final_resolution: str | None = None
    final_aspect_ratio: str | None = None
    cover_frame_timestamp: float | None = Field(default=None, ge=0)
    platform_adaptations: dict[str, str] = Field(default_factory=dict)


class GenerationArchitecture(VideoAnalysisModel):
    ai_video_prompt: AIVideoPrompt = Field(default_factory=AIVideoPrompt)
    iteration: IterationPlan = Field(default_factory=IterationPlan)
    post_production: PostProduction = Field(default_factory=PostProduction)


class QualityScoreItem(VideoAnalysisModel):
    score: float | None = Field(default=None, ge=0, le=10)
    reason: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class QualityScoring(VideoAnalysisModel):
    hook: QualityScoreItem = Field(default_factory=QualityScoreItem)
    selling_point: QualityScoreItem = Field(default_factory=QualityScoreItem)
    conversion: QualityScoreItem = Field(default_factory=QualityScoreItem)
    human_action: QualityScoreItem = Field(default_factory=QualityScoreItem)
    composition: QualityScoreItem = Field(default_factory=QualityScoreItem)
    camera_language: QualityScoreItem = Field(default_factory=QualityScoreItem)
    editing_rhythm: QualityScoreItem = Field(default_factory=QualityScoreItem)
    visual_quality: QualityScoreItem = Field(default_factory=QualityScoreItem)
    product_display: QualityScoreItem = Field(default_factory=QualityScoreItem)
    emotion_impact: QualityScoreItem = Field(default_factory=QualityScoreItem)
    style_consistency: QualityScoreItem = Field(default_factory=QualityScoreItem)
    platform_fit: QualityScoreItem = Field(default_factory=QualityScoreItem)
    replicability: QualityScoreItem = Field(default_factory=QualityScoreItem)
    overall: QualityScoreItem = Field(default_factory=QualityScoreItem)


class Observation(VideoAnalysisModel):
    target_definition: TargetDefinition = Field(default_factory=TargetDefinition)
    creative_concept: CreativeConcept = Field(default_factory=CreativeConcept)
    facts: ObservationFacts = Field(default_factory=ObservationFacts)
    person: PersonAnalysis = Field(default_factory=PersonAnalysis)
    product: ProductAnalysis = Field(default_factory=ProductAnalysis)
    scene: SceneAnalysis = Field(default_factory=SceneAnalysis)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    emotion_arc: EmotionArc = Field(default_factory=EmotionArc)
    conversion_points: list[MarketingPoint] = Field(default_factory=list)
    viral_points: list[MarketingPoint] = Field(default_factory=list)
    selling_points: list[SellingPoint] = Field(default_factory=list)
    viral_logic: ViralLogic = Field(default_factory=ViralLogic)
    viral_formula: ViralFormula = Field(default_factory=ViralFormula)
    claim_evidence_chains: list[ClaimEvidenceChain] = Field(default_factory=list)
    business_logic: BusinessLogicAnswers = Field(default_factory=BusinessLogicAnswers)
    defects: list[Defect] = Field(default_factory=list)


class ObservationResult(VideoAnalysisModel):
    content_classification: ContentClassification
    observation: Observation = Field(default_factory=Observation)


class EvidenceReview(VideoAnalysisModel):
    evidence_complete: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class G0Finding(VideoAnalysisModel):
    category: DefectCategory
    description: str
    triggered: bool = False
    evidence_timestamps: list[EvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class G0Assessment(VideoAnalysisModel):
    findings: list[G0Finding] = Field(default_factory=list)


COMMON_SCORE_SPECS = (
    ("C1", "受众与购买需求", 6),
    ("C2", "钩子停留能力", 10),
    ("C3", "商品识别与曝光", 6),
    ("C4", "卖点选择", 8),
    ("C5", "可见证据链", 12),
    ("C6", "节奏与信息密度", 8),
    ("C7", "记忆点与商品绑定", 6),
    ("C8", "信任、顾虑与行动", 4),
)
REFERENCE_SCORE_SPECS = (
    ("R1", "时间线与结构可拆解性", 8),
    ("R2", "AI 复刻友好度", 10),
    ("R3", "可迁移变量丰富度", 8),
    ("R4", "换成我方商品的安全性", 6),
    ("R5", "生产成本与稳定性", 4),
    ("R6", "差异化潜力", 4),
)
GENERATED_SCORE_SPECS = (
    ("G1", "商品一致性", 12),
    ("G2", "人物身份与服装层级", 5),
    ("G3", "动作完整性与力量感", 8),
    ("G4", "物理、接触与回弹", 6),
    ("G5", "镜头与构图连续性", 4),
    ("G6", "技术画质", 3),
    ("G7", "背景、灯光与声音联动", 2),
)


def _default_dimensions(specs):
    return [
        ScoreDimension(
            dimension_id=dimension_id,
            name=name,
            max_points=max_points,
            scorable=False,
        )
        for dimension_id, name, max_points in specs
    ]


class _ScoreSection(VideoAnalysisModel):
    dimensions: list[ScoreDimension]

    expected_specs: ClassVar[tuple[tuple[str, str, int], ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _repair_unscorable_awarded_points(cls, data):
        """Normalize LLM output that awards points on an explicitly unscorable dimension.

        The strict leaf contract (ScoreDimension) forbids awarded_points when
        scorable is false; some models still emit both fields. Dropping the award
        here — before the leaf validator runs — is exactly what the contract
        means (unscorable ⇒ no points), without loosening the leaf check itself.
        """
        if not isinstance(data, dict):
            return data
        dimensions = data.get("dimensions")
        if not isinstance(dimensions, list):
            return data
        for dimension in dimensions:
            if isinstance(dimension, dict) and dimension.get("scorable") is False:
                dimension.pop("awarded_points", None)
        return data

    @model_validator(mode="after")
    def validate_dimensions(self):
        expected = {
            dimension_id: (name, max_points)
            for dimension_id, name, max_points in self.expected_specs
        }
        actual = {
            dimension.dimension_id: (dimension.name, dimension.max_points)
            for dimension in self.dimensions
        }
        if actual != expected or len(actual) != len(self.dimensions):
            raise ValueError("score dimensions must match the declared scoring contract")
        return self


class CommonScoreC(_ScoreSection):
    dimensions: list[ScoreDimension] = Field(
        default_factory=lambda: _default_dimensions(COMMON_SCORE_SPECS)
    )
    expected_specs: ClassVar[tuple[tuple[str, str, int], ...]] = COMMON_SCORE_SPECS


class ReferenceScoreR(_ScoreSection):
    dimensions: list[ScoreDimension] = Field(
        default_factory=lambda: _default_dimensions(REFERENCE_SCORE_SPECS)
    )
    expected_specs: ClassVar[tuple[tuple[str, str, int], ...]] = REFERENCE_SCORE_SPECS


class GeneratedScoreG(_ScoreSection):
    dimensions: list[ScoreDimension] = Field(
        default_factory=lambda: _default_dimensions(GENERATED_SCORE_SPECS)
    )
    expected_specs: ClassVar[tuple[tuple[str, str, int], ...]] = GENERATED_SCORE_SPECS


class EvaluationDraft(VideoAnalysisModel):
    review_route: Literal["R", "G"] | None = None
    evidence_review: EvidenceReview = Field(default_factory=EvidenceReview)
    g0_assessment: G0Assessment = Field(default_factory=G0Assessment)
    common_score_c: CommonScoreC = Field(default_factory=CommonScoreC)
    specialized_score_r: ReferenceScoreR | None = None
    specialized_score_g: GeneratedScoreG | None = None
    supplemental_evidence: list[SupplementalEvidence] = Field(default_factory=list)
    evidence_conflicts: list[EvidenceConflict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_review_route(self):
        if self.specialized_score_r is not None and self.specialized_score_g is not None:
            raise ValueError("R and G score sections are mutually exclusive")
        if self.review_route == "R" and self.specialized_score_g is not None:
            raise ValueError("review route R cannot contain a G score section")
        if self.review_route == "R" and self.specialized_score_r is None:
            raise ValueError("review route R requires an R score section")
        if self.review_route == "G" and self.specialized_score_r is not None:
            raise ValueError("review route G cannot contain an R score section")
        if self.review_route == "G" and self.specialized_score_g is None:
            raise ValueError("review route G requires a G score section")
        if self.review_route is None and (
            self.specialized_score_r is not None or self.specialized_score_g is not None
        ):
            raise ValueError("a specialized score section requires an explicit review route")
        return self


class EvaluationResult(EvaluationDraft):
    partial_points: float = Field(default=0, ge=0)
    partial_max_points: float = Field(default=0, ge=0)
    diagnostic_total: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_partial_totals(self):
        if self.partial_points > self.partial_max_points:
            raise ValueError("partial_points cannot exceed partial_max_points")
        return self


class Decision(VideoAnalysisModel):
    gate_status: GateStatus
    scoring_status: ScoringStatus
    recommended_grade: Grade | None = None
    system_disposition: SystemDisposition
    reasons: list[str] = Field(default_factory=list)
    owner_decision: Literal["ACCEPT", "REPAIR", "REJECT"] | None = None


class AnalysisMeta(VideoAnalysisModel):
    schema_version: Literal["v4.0"] = "v4.0"
    observation_prompt_version: str | None = None
    evaluation_prompt_version: str | None = None
    observation_model_name: str | None = None
    observation_model_version: str | None = None
    evaluation_model_name: str | None = None
    evaluation_model_version: str | None = None
    analyzed_at: str | None = None
    source_frames_count: int | None = Field(default=None, ge=0)
    confidence_overall: float | None = Field(default=None, ge=0, le=1)
    timings: AnalysisTimings = Field(default_factory=AnalysisTimings)


class TechnicalAnalysis(VideoAnalysisModel):
    scene_count: int | None = Field(default=None, ge=0)
    average_shot_duration: float | None = Field(default=None, ge=0)
    cut_frequency: float | None = Field(default=None, ge=0)
    audio_summary: str | None = None


class AnalysisResult(VideoAnalysisModel):
    """Deterministic assembler output — keeps the strict wire contract."""

    model_config = ConfigDict(extra="forbid")

    meta: AnalysisMeta = Field(default_factory=AnalysisMeta)
    evidence_card: EvidenceCard = Field(default_factory=EvidenceCard)
    content_classification: ContentClassification
    observation: Observation = Field(default_factory=Observation)
    generation: GenerationArchitecture = Field(default_factory=GenerationArchitecture)
    quality_scoring: QualityScoring = Field(default_factory=QualityScoring)
    evaluation: EvaluationResult = Field(default_factory=EvaluationResult)
    decision: Decision
    technical_analysis: TechnicalAnalysis | None = None

    @model_validator(mode="after")
    def validate_hard_gate_decision(self):
        if (
            self.decision.gate_status is GateStatus.BLOCK
            and self.decision.system_disposition is not SystemDisposition.REJECT
        ):
            raise ValueError("G0 BLOCK results must use the REJECT disposition")
        if (
            self.decision.scoring_status is ScoringStatus.UNAVAILABLE
            and self.decision.recommended_grade is not None
        ):
            raise ValueError("unavailable scoring cannot produce a recommended grade")
        return self


__all__ = [
    "AIVideoPrompt",
    "ActionPhase",
    "AnalysisMeta",
    "AnalysisResult",
    "AnalysisTimings",
    "BusinessLogicAnswers",
    "ClaimEvidenceChain",
    "CommonScoreC",
    "ContentClassification",
    "ContentType",
    "CreativeConcept",
    "Decision",
    "Defect",
    "DefectCategory",
    "EmotionArc",
    "EmotionBeat",
    "EvaluationDraft",
    "EvaluationResult",
    "EvidenceCard",
    "EvidenceConflict",
    "EvidenceReference",
    "EvidenceReview",
    "EvidenceSource",
    "ExternalEvidenceAvailability",
    "ExternalEvidenceStatus",
    "G0Assessment",
    "G0Finding",
    "GateStatus",
    "GeneratedScoreG",
    "GenerationArchitecture",
    "Grade",
    "InputMode",
    "IssueDiagnosis",
    "KeyFramePrompt",
    "MarketingPoint",
    "ModelParameters",
    "Observation",
    "ObservationFacts",
    "ObservationResult",
    "PersonAnalysis",
    "PostProduction",
    "ProductAnalysis",
    "QualityScoreItem",
    "QualityScoring",
    "ReferenceScoreR",
    "SceneAnalysis",
    "ScoreDimension",
    "ScoringStatus",
    "SellingPoint",
    "SubtitlePlan",
    "SupplementalEvidence",
    "SystemDisposition",
    "TargetAudience",
    "TargetDefinition",
    "TechnicalAnalysis",
    "TechnicalMetadata",
    "TimelineEntry",
    "TimeRange",
    "Topology",
    "ViralFormula",
    "ViralLogic",
]
