import type {
  AnalysisResultV2,
  AnalysisResultV3,
  EvidenceReferenceV3,
  ScoreDimensionV3,
  TimelineEntryV3,
} from "./analysis";

type RecordValue = Record<string, unknown>;
type Guard<T = unknown> = (value: unknown) => value is T;
type Validator = (value: unknown) => boolean;

function isRecord(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNull(value: unknown): value is null {
  return value === null;
}

function isNullable(value: unknown, validator: Validator): boolean {
  return value === null || validator(value);
}

function isArrayOf(value: unknown, validator: Validator): boolean {
  return Array.isArray(value) && value.every(validator);
}

function isEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
): value is T {
  return typeof value === "string" && allowed.some((item) => item === value);
}

function optional(record: RecordValue, key: string, validator: Validator): boolean {
  return record[key] == null || validator(record[key]);
}

function optionalFields(
  record: RecordValue,
  keys: readonly string[],
  validator: Validator,
): boolean {
  return keys.every((key) => optional(record, key, validator));
}

function requiredFields(
  record: RecordValue,
  keys: readonly string[],
  validator: Validator,
): boolean {
  return keys.every((key) => key in record && validator(record[key]));
}

const isNullableString: Guard<string | null> = (value): value is string | null =>
  isNullable(value, isString);
const isNullableNumber: Guard<number | null> = (value): value is number | null =>
  isNullable(value, isFiniteNumber);
const isStringArray: Guard<string[]> = (value): value is string[] =>
  isArrayOf(value, isString);
const isNumberArray: Guard<number[]> = (value): value is number[] =>
  isArrayOf(value, isFiniteNumber);

const EVIDENCE_SOURCES = [
  "VIDEO",
  "FRAME",
  "AUDIO",
  "TRANSCRIPT",
  "TECHNICAL_METADATA",
  "EXTERNAL",
] as const;
const EXTERNAL_EVIDENCE_STATUSES = [
  "AVAILABLE",
  "NOT_PROVIDED",
  "NOT_APPLICABLE",
] as const;
const INPUT_MODES = ["FULL_VIDEO", "SAMPLED_FRAMES"] as const;
const CONTENT_TYPES = [
  "PRODUCT_DEMONSTRATION",
  "PROBLEM_SOLUTION",
  "TESTIMONIAL",
  "COMPARISON",
  "TUTORIAL",
  "LIFESTYLE",
  "STORYTELLING",
  "OTHER",
] as const;
const TOPOLOGIES = [
  "LINEAR",
  "LOOP",
  "MONTAGE",
  "SPLIT_SCREEN",
  "ONE_TAKE",
  "OTHER",
] as const;
const ACTION_PHASES = [
  "POSITIONING",
  "FORCE",
  "PEAK",
  "FEEDBACK",
  "RELEASE",
  "RECOVERY",
] as const;
const DEFECT_CATEGORIES = [
  "PRODUCT",
  "PERSON",
  "PHYSICS",
  "CAMERA",
  "DELIVERY",
  "VISUAL_QUALITY",
  "AUDIO",
  "OTHER",
] as const;
const GATE_STATUSES = ["PASS", "BLOCK", "INSUFFICIENT_EVIDENCE"] as const;
const SCORING_STATUSES = ["PROVISIONAL", "UNAVAILABLE"] as const;
const SYSTEM_DISPOSITIONS = ["REJECT", "OWNER_REVIEW_REQUIRED"] as const;

function isTimeRangeV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isFiniteNumber(value.start_seconds) &&
    isFiniteNumber(value.end_seconds) &&
    isBoolean(value.start_inclusive) &&
    isBoolean(value.end_inclusive)
  );
}

function isEvidenceReferenceV3(value: unknown): value is EvidenceReferenceV3 {
  return (
    isRecord(value) &&
    isEnum(value.source, EVIDENCE_SOURCES) &&
    isNullableNumber(value.timestamp) &&
    isNullable(value.time_range, isTimeRangeV3) &&
    isNullableString(value.description) &&
    isBoolean(value.positive)
  );
}

function isExternalEvidenceV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isEnum(value.status, EXTERNAL_EVIDENCE_STATUSES) &&
    isNullableString(value.detail)
  );
}

function isAnalysisTimingsV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNullableNumber(value.observation_duration_ms) &&
    isNullableNumber(value.evaluation_duration_ms) &&
    isNullableNumber(value.total_duration_ms) &&
    isFiniteNumber(value.observation_attempts) &&
    isFiniteNumber(value.evaluation_attempts)
  );
}

function isTechnicalMetadataV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNullableNumber(value.duration_seconds) &&
    isNullableNumber(value.width) &&
    isNullableNumber(value.height) &&
    isNullableString(value.aspect_ratio) &&
    isNullableNumber(value.fps) &&
    isNullable(value.has_audio_stream, isBoolean) &&
    isNullableString(value.format_name) &&
    isNullableNumber(value.size_bytes)
  );
}

function isEvidenceCardV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNullableString(value.source_id) &&
    isNullableString(value.source_sha256) &&
    isTechnicalMetadataV3(value.technical_metadata) &&
    (value.input_mode === null || isEnum(value.input_mode, INPUT_MODES)) &&
    isFiniteNumber(value.sampled_frame_count) &&
    isNumberArray(value.sampled_timestamps) &&
    isArrayOf(value.observed_ranges, isTimeRangeV3) &&
    isArrayOf(value.unobserved_ranges, isTimeRangeV3) &&
    isStringArray(value.coverage_limitations) &&
    isExternalEvidenceV3(value.product_reference) &&
    isExternalEvidenceV3(value.publishing_context) &&
    isExternalEvidenceV3(value.performance_metrics) &&
    isExternalEvidenceV3(value.task_constraints) &&
    isBoolean(value.evidence_complete) &&
    value.official_scoring_ready === false &&
    isStringArray(value.missing_evidence) &&
    isStringArray(value.limitations)
  );
}

function isContentClassificationV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isEnum(value.primary_type, CONTENT_TYPES) &&
    isArrayOf(value.secondary_types, (item): item is string =>
      isEnum(item, CONTENT_TYPES),
    ) &&
    isEnum(value.topology, TOPOLOGIES) &&
    isArrayOf(value.evidence_timecodes, isEvidenceReferenceV3) &&
    isNullableNumber(value.confidence)
  );
}

function isObservationFactsV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNullableString(value.summary) &&
    isStringArray(value.subjects) &&
    isStringArray(value.person_facts) &&
    isStringArray(value.product_facts) &&
    isStringArray(value.scene_facts)
  );
}

function isTimelineEntryV3(value: unknown): value is TimelineEntryV3 {
  return (
    isTimeRangeV3(value) &&
    isRecord(value) &&
    isArrayOf(value.evidence_sources, isEvidenceReferenceV3) &&
    requiredFields(
      value,
      [
        "subject",
        "person_pose",
        "primary_hand",
        "secondary_hand",
        "grip_point",
        "direction",
        "product_state",
        "product_drift",
        "occlusion",
        "camera",
        "composition",
        "background_motion",
        "lighting",
        "sound_feedback",
        "new_audience_information",
      ],
      isNullableString,
    ) &&
    isArrayOf(value.action_phases, (item): item is string =>
      isEnum(item, ACTION_PHASES),
    ) &&
    isStringArray(value.provable_claims) &&
    isArrayOf(value.defects, (item): item is string =>
      isEnum(item, DEFECT_CATEGORIES),
    ) &&
    isNullableNumber(value.confidence)
  );
}

function isClaimEvidenceChainV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.claim) &&
    requiredFields(
      value,
      [
        "product_structure",
        "demonstration_action",
        "visible_feedback",
        "usage_result",
        "user_benefit",
      ],
      isNullableString,
    ) &&
    isArrayOf(value.references, isEvidenceReferenceV3) &&
    isBoolean(value.supported)
  );
}

function isBusinessLogicV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    requiredFields(
      value,
      [
        "audience_and_need",
        "hook_and_retention",
        "product_recognition",
        "selling_point",
        "visible_proof",
        "rhythm_and_density",
        "memory_and_product_binding",
        "trust_objection_and_action",
      ],
      isNullableString,
    )
  );
}

function isDefectV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isEnum(value.category, DEFECT_CATEGORIES) &&
    isString(value.description) &&
    isArrayOf(value.references, isEvidenceReferenceV3) &&
    isNullableNumber(value.confidence)
  );
}

function isObservationV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isObservationFactsV3(value.facts) &&
    isArrayOf(value.timeline, isTimelineEntryV3) &&
    isArrayOf(value.claim_evidence_chains, isClaimEvidenceChainV3) &&
    isBusinessLogicV3(value.business_logic) &&
    isArrayOf(value.defects, isDefectV3)
  );
}

function isEvidenceReviewV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isBoolean(value.evidence_complete) &&
    isStringArray(value.missing_evidence) &&
    isStringArray(value.limitations) &&
    isNullableNumber(value.confidence)
  );
}

function isG0FindingV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isEnum(value.category, DEFECT_CATEGORIES) &&
    isString(value.description) &&
    isBoolean(value.triggered) &&
    isArrayOf(value.evidence_timestamps, isEvidenceReferenceV3) &&
    isNullableNumber(value.confidence)
  );
}

function isG0AssessmentV3(value: unknown): boolean {
  return isRecord(value) && isArrayOf(value.findings, isG0FindingV3);
}

function isScoreDimensionV3(value: unknown): value is ScoreDimensionV3 {
  return (
    isRecord(value) &&
    isNullableString(value.dimension_id) &&
    isNullableString(value.name) &&
    isNullableNumber(value.awarded_points) &&
    isFiniteNumber(value.max_points) &&
    isNullableString(value.reason) &&
    isArrayOf(value.evidence_timestamps, isEvidenceReferenceV3) &&
    isBoolean(value.scorable) &&
    isNullableString(value.unscorable_reason) &&
    isNullableNumber(value.confidence)
  );
}

function isScoreSectionV3(value: unknown): boolean {
  return isRecord(value) && isArrayOf(value.dimensions, isScoreDimensionV3);
}

function isSupplementalEvidenceV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.description) &&
    isArrayOf(value.references, isEvidenceReferenceV3) &&
    isStringArray(value.affected_dimension_ids) &&
    isNullableNumber(value.confidence)
  );
}

function isEvidenceConflictV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.observation_claim) &&
    isString(value.evaluation_claim) &&
    isArrayOf(value.references, isEvidenceReferenceV3) &&
    isStringArray(value.affected_dimension_ids) &&
    isNullableNumber(value.confidence)
  );
}

function isEvaluationV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    (value.review_route === null || isEnum(value.review_route, ["R", "G"] as const)) &&
    isEvidenceReviewV3(value.evidence_review) &&
    isG0AssessmentV3(value.g0_assessment) &&
    isScoreSectionV3(value.common_score_c) &&
    isNullable(value.specialized_score_r, isScoreSectionV3) &&
    isNullable(value.specialized_score_g, isScoreSectionV3) &&
    isArrayOf(value.supplemental_evidence, isSupplementalEvidenceV3) &&
    isArrayOf(value.evidence_conflicts, isEvidenceConflictV3) &&
    isFiniteNumber(value.partial_points) &&
    isFiniteNumber(value.partial_max_points) &&
    isNullableNumber(value.diagnostic_total)
  );
}

function isDecisionV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isEnum(value.gate_status, GATE_STATUSES) &&
    isEnum(value.scoring_status, SCORING_STATUSES) &&
    isNull(value.formal_grade) &&
    isEnum(value.system_disposition, SYSTEM_DISPOSITIONS) &&
    isStringArray(value.reasons)
  );
}

function isMetaV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    value.schema_version === "v3.0" &&
    requiredFields(
      value,
      [
        "observation_prompt_version",
        "evaluation_prompt_version",
        "observation_model_name",
        "observation_model_version",
        "evaluation_model_name",
        "evaluation_model_version",
        "analyzed_at",
      ],
      isNullableString,
    ) &&
    isNullableNumber(value.source_frames_count) &&
    isNullableNumber(value.confidence_overall) &&
    isAnalysisTimingsV3(value.timings)
  );
}

function isTechnicalAnalysisV3(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNullableNumber(value.scene_count) &&
    isNullableNumber(value.average_shot_duration) &&
    isNullableNumber(value.cut_frequency) &&
    isNullableString(value.audio_summary)
  );
}

export function isAnalysisResultV3(value: unknown): value is AnalysisResultV3 {
  return (
    isRecord(value) &&
    isMetaV3(value.meta) &&
    isEvidenceCardV3(value.evidence_card) &&
    isContentClassificationV3(value.content_classification) &&
    isObservationV3(value.observation) &&
    isEvaluationV3(value.evaluation) &&
    isDecisionV3(value.decision) &&
    isNullable(value.technical_analysis, isTechnicalAnalysisV3)
  );
}

function isOptionalStrings(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(
    (item) => item == null || isString(item),
  );
}

function isV2ScoreItem(value: unknown): boolean {
  return (
    isRecord(value) &&
    optional(value, "score", (item): item is number | null =>
      isNullable(item, isFiniteNumber),
    ) &&
    optional(value, "reason", isString)
  );
}

function isV2Scoring(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !Object.values(value).every(
      (item) => item === null || isV2ScoreItem(item),
    )
  ) return false;
  const overall = value.overall;
  return isRecord(overall) && "score" in overall && isNullableNumber(overall.score);
}

function isV2Audience(value: unknown): boolean {
  return (
    isRecord(value) &&
    optionalFields(value, ["gender", "age_range", "price_sensitivity"], isString) &&
    optionalFields(value, ["style_preference", "pain_points", "interests"], isStringArray)
  );
}

function isV2Target(value: unknown): boolean {
  return (
    isRecord(value) &&
    optional(value, "target_audience", isV2Audience) &&
    optionalFields(
      value,
      [
        "platform",
        "content_purpose",
        "primary_kpi",
        "target_audience_profile",
        "success_criteria",
      ],
      isString,
    ) &&
    optionalFields(value, ["platform_tone_match", "video_length_target"], isFiniteNumber)
  );
}

function isV2Person(value: unknown): boolean {
  return (
    isRecord(value) &&
    optionalFields(
      value,
      [
        "description",
        "clothing",
        "gaze_direction",
        "body_pose",
        "body_orientation",
        "gait_or_stance",
        "body_type",
        "identity_consistency_risk",
      ],
      isString,
    ) &&
    optional(value, "actions", isStringArray) &&
    optional(value, "gaze_changes", (items): items is RecordValue[] =>
      isArrayOf(items, isOptionalStrings),
    ) &&
    optional(value, "hand_actions", (items): items is RecordValue[] =>
      isArrayOf(items, (item): item is RecordValue =>
        isRecord(item) &&
        optional(item, "timestamp", isNullableNumber) &&
        optional(item, "hand_position", isString) &&
        optional(item, "purpose", isNullableString),
      ),
    )
  );
}

function isV2TimelineItem(value: unknown): boolean {
  return (
    isRecord(value) &&
    optionalFields(
      value,
      ["start_time", "end_time", "emotion_intensity", "confidence"],
      isFiniteNumber,
    ) &&
    optionalFields(
      value,
      [
        "person_action",
        "product_action",
        "camera",
        "composition",
        "shooting_method",
        "action_purpose",
        "marketing_purpose",
        "emotion_state",
        "transition_type",
        "beat_density",
        "subtitle_text",
        "bgm_mood",
        "key_frame_description",
      ],
      isString,
    ) &&
    optionalFields(value, ["is_hook_segment", "is_payoff_segment"], isBoolean)
  );
}

function isV2Point(value: unknown, extraStringKey?: string): boolean {
  return (
    isRecord(value) &&
    optionalFields(value, ["timestamp", "confidence"], isFiniteNumber) &&
    optional(value, "description", isString) &&
    (extraStringKey === undefined || optional(value, extraStringKey, isString))
  );
}

function isV2EmotionArc(value: unknown): boolean {
  return (
    isRecord(value) &&
    optionalFields(
      value,
      ["opening_emotion", "middle_emotion", "ending_emotion", "peak_emotion", "arc_type"],
      isString,
    ) &&
    optional(value, "peak_timestamp", isFiniteNumber) &&
    optional(value, "intensity_curve", (items): items is RecordValue[] =>
      isArrayOf(items, (item): item is RecordValue =>
        isRecord(item) &&
        optionalFields(item, ["timestamp", "intensity"], isFiniteNumber) &&
        optionalFields(item, ["emotion", "trigger"], isString),
      ),
    )
  );
}

function isV2Prompt(value: unknown): boolean {
  return (
    isRecord(value) &&
    optionalFields(
      value,
      [
        "subject_prompt",
        "scene_prompt",
        "action_prompt",
        "style_prompt",
        "full_prompt_zh",
        "full_prompt_en",
        "negative_prompt",
        "recommended_model",
      ],
      isString,
    ) &&
    optionalFields(value, ["style_anchors", "consistency_constraints"], isStringArray) &&
    optional(value, "key_frames", (items): items is RecordValue[] =>
      isArrayOf(items, (item): item is RecordValue =>
        isRecord(item) &&
        optional(item, "timestamp", isFiniteNumber) &&
        optionalFields(item, ["position", "description", "prompt_text"], isString),
      ),
    ) &&
    optional(value, "recommended_params", (params): params is RecordValue =>
      isRecord(params) &&
      Object.values(params).every(
        (item) => item == null || isString(item) || isFiniteNumber(item),
      ),
    )
  );
}

function isV2Iteration(value: unknown): boolean {
  return (
    isRecord(value) &&
    optional(value, "round_number", isFiniteNumber) &&
    optionalFields(
      value,
      ["verification_target", "revised_prompt", "revision_focus"],
      isString,
    ) &&
    optional(value, "passed", isBoolean) &&
    optional(value, "issues", (items): items is RecordValue[] =>
      isArrayOf(items, (item): item is RecordValue =>
        isRecord(item) &&
        optionalFields(item, ["timestamp_start", "timestamp_end"], isFiniteNumber) &&
        optionalFields(
          item,
          ["category", "severity", "description", "suggested_fix", "revised_prompt_snippet"],
          isString,
        ),
      ),
    )
  );
}

function isV2PostProduction(value: unknown): boolean {
  return (
    isRecord(value) &&
    optional(value, "rhythm", (rhythm): rhythm is RecordValue =>
      isRecord(rhythm) &&
      optionalFields(
        rhythm,
        ["bpm_estimate", "cut_frequency", "avg_shot_duration", "beat_sync_score"],
        isFiniteNumber,
      ) &&
      optional(rhythm, "rhythm_pattern", isString),
    ) &&
    optional(value, "subtitles", (items): items is RecordValue[] =>
      isArrayOf(items, (item): item is RecordValue =>
        isRecord(item) &&
        optionalFields(item, ["start_time", "end_time"], isFiniteNumber) &&
        optionalFields(item, ["text", "position", "style"], isString) &&
        optional(item, "is_hook", isBoolean),
      ),
    ) &&
    optional(value, "voiceover_script", isNullableString) &&
    optional(value, "bgm", (bgm): bgm is RecordValue =>
      isRecord(bgm) &&
      optionalFields(bgm, ["genre", "mood"], isString) &&
      optional(bgm, "tempo_bpm", isFiniteNumber) &&
      optional(bgm, "drop_timestamps", isNumberArray),
    ) &&
    optional(value, "sound_effects", isStringArray) &&
    optional(value, "final_format", (format): format is RecordValue =>
      isRecord(format) &&
      optionalFields(format, ["duration", "cover_frame_ts"], isFiniteNumber) &&
      optionalFields(format, ["resolution", "aspect_ratio"], isString),
    ) &&
    optional(value, "platform_adaptations", (adaptations): adaptations is RecordValue =>
      isRecord(adaptations) &&
      Object.values(adaptations).every(
        (adaptation) =>
          isRecord(adaptation) &&
          optional(adaptation, "recommended_hashtags", isStringArray),
      ),
    )
  );
}

function isV2ViralFormula(value: unknown): boolean {
  return (
    isRecord(value) &&
    optionalFields(
      value,
      ["formula_id", "pattern_type", "formula_template"],
      isString,
    ) &&
    optional(value, "template_variables", (variables): variables is RecordValue =>
      isRecord(variables) && Object.values(variables).every(isString),
    ) &&
    optionalFields(
      value,
      ["replicability_score", "similar_reference_count"],
      isFiniteNumber,
    ) &&
    optional(value, "success_predictors", isStringArray)
  );
}

export function isAnalysisResultV2(value: unknown): value is AnalysisResultV2 {
  if (!isRecord(value)) return false;
  if (value.meta != null) {
    if (!isRecord(value.meta)) return false;
    if (
      value.meta.schema_version != null &&
      value.meta.schema_version !== "v2.0"
    ) return false;
    if (!optional(value.meta, "confidence_overall", isFiniteNumber)) return false;
  }

  return (
    isV2Scoring(value.scoring) &&
    optional(value, "timeline", (items) => isArrayOf(items, isV2TimelineItem)) &&
    optional(value, "conversion_points", (items) =>
      isArrayOf(items, (item) => isV2Point(item)),
    ) &&
    optional(value, "viral_points", (items) =>
      isArrayOf(items, (item) => isV2Point(item, "target_metric")),
    ) &&
    optional(value, "selling_points", (items) =>
      isArrayOf(items, (item) => isV2Point(item)),
    ) &&
    optional(value, "target_definition", isV2Target) &&
    optional(value, "creative_concept", (item): item is RecordValue =>
      isRecord(item) &&
      optionalFields(item, ["theme", "conflict", "hook_strategy", "memory_hook", "story_arc"], isString) &&
      optional(item, "creative_tags", isStringArray),
    ) &&
    optional(value, "basic_info", (item): item is RecordValue =>
      isRecord(item) &&
      optional(item, "duration", isFiniteNumber) &&
      optionalFields(item, ["resolution", "aspect_ratio", "language"], isString) &&
      optionalFields(item, ["has_subtitle", "has_voice"], isBoolean),
    ) &&
    optional(value, "person", isV2Person) &&
    optional(value, "product", (item): item is RecordValue =>
      isRecord(item) &&
      optionalFields(
        item,
        ["description", "category", "material", "fabric_thickness", "elasticity", "size_recommendation", "price_range", "suitable_season"],
        isString,
      ) &&
      optionalFields(item, ["display_actions", "suitable_scene", "craft_details", "color_options_visible"], isStringArray),
    ) &&
    optional(value, "scene", (item): item is RecordValue =>
      isRecord(item) &&
      optionalFields(
        item,
        ["background", "lighting", "color", "visual_quality", "camera", "composition", "shot_size", "shooting_angle", "camera_movement", "time_of_day", "space_type", "space_depth", "light_direction", "light_temperature", "light_contrast", "color_grading", "style_genre", "style_reference"],
        isString,
      ) &&
      optional(item, "style_keywords", isStringArray),
    ) &&
    optional(value, "emotion_arc", isV2EmotionArc) &&
    optional(value, "viral_logic", isOptionalStrings) &&
    optional(value, "viral_formula", isV2ViralFormula) &&
    optional(value, "ai_video_prompt", isV2Prompt) &&
    optional(value, "iteration", isV2Iteration) &&
    optional(value, "post_production", isV2PostProduction)
  );
}

export type ClassifiedAnalysisResult =
  | { version: "v3"; result: AnalysisResultV3 }
  | { version: "v2"; result: AnalysisResultV2 }
  | { version: "unavailable" };

export function classifyAnalysisResult(value: unknown): ClassifiedAnalysisResult {
  if (isAnalysisResultV3(value)) return { version: "v3", result: value };
  if (isAnalysisResultV2(value)) return { version: "v2", result: value };
  return { version: "unavailable" };
}
