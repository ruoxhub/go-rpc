/**
 * 视频素材与分析结果数据层，仅在服务端使用。
 */

// ---------------------------------------------------------------------------
// 类型定义（对齐 backend/schemas.py 的 v2.0 schema，字段全部可选以保证容错）
// ---------------------------------------------------------------------------

export interface AnalysisMeta {
  schema_version?: string | null;
  prompt_version?: string | null;
  model_name?: string | null;
  model_version?: string | null;
  analyzed_at?: string | null;
  analysis_duration_ms?: number | null;
  source_frames_count?: number | null;
  confidence_overall?: number | null;
  notes?: string | null;
}

export interface TargetAudience {
  gender?: string | null;
  age_range?: string | null;
  style_preference?: string[] | null;
  price_sensitivity?: string | null;
  pain_points?: string[] | null;
  interests?: string[] | null;
}

export interface TargetDefinition {
  target_audience?: TargetAudience | null;
  platform?: string | null;
  platform_tone_match?: number | null;
  content_purpose?: string | null;
  primary_kpi?: string | null;
  video_length_target?: number | null;
  target_audience_profile?: string | null;
  success_criteria?: string | null;
}

export interface CreativeConcept {
  theme?: string | null;
  conflict?: string | null;
  hook_strategy?: string | null;
  memory_hook?: string | null;
  story_arc?: string | null;
  creative_tags?: string[] | null;
}

export interface BasicInfo {
  duration?: number | null;
  resolution?: string | null;
  aspect_ratio?: string | null;
  language?: string | null;
  has_subtitle?: boolean | null;
  has_voice?: boolean | null;
}

export interface HandAction {
  timestamp?: number | null;
  hand_position?: string | null;
  purpose?: string | null;
}

export interface PersonInfo {
  description?: string | null;
  clothing?: string | null;
  actions?: string[] | null;
  gaze_direction?: string | null;
  gaze_changes?: { description?: string }[] | null;
  body_pose?: string | null;
  body_orientation?: string | null;
  hand_actions?: HandAction[] | null;
  gait_or_stance?: string | null;
  body_type?: string | null;
  identity_consistency_risk?: string | null;
}

export interface ProductInfo {
  description?: string | null;
  display_actions?: string[] | null;
  category?: string | null;
  material?: string | null;
  fabric_thickness?: string | null;
  elasticity?: string | null;
  size_recommendation?: string | null;
  price_range?: string | null;
  suitable_season?: string | null;
  suitable_scene?: string[] | null;
  craft_details?: string[] | null;
  color_options_visible?: string[] | null;
}

export interface SceneInfo {
  background?: string | null;
  lighting?: string | null;
  color?: string | null;
  visual_quality?: string | null;
  camera?: string | null;
  composition?: string | null;
  shot_size?: string | null;
  shooting_angle?: string | null;
  camera_movement?: string | null;
  time_of_day?: string | null;
  space_type?: string | null;
  space_depth?: string | null;
  light_direction?: string | null;
  light_temperature?: string | null;
  light_contrast?: string | null;
  color_grading?: string | null;
  style_genre?: string | null;
  style_keywords?: string[] | null;
  style_reference?: string | null;
}

export interface TimelineSegment {
  start_time?: number | null;
  end_time?: number | null;
  person_action?: string | null;
  product_action?: string | null;
  camera?: string | null;
  composition?: string | null;
  shooting_method?: string | null;
  action_purpose?: string | null;
  marketing_purpose?: string | null;
  emotion_state?: string | null;
  emotion_intensity?: number | null;
  transition_type?: string | null;
  beat_density?: string | null;
  subtitle_text?: string | null;
  bgm_mood?: string | null;
  is_hook_segment?: boolean | null;
  is_payoff_segment?: boolean | null;
  key_frame_description?: string | null;
  confidence?: number | null;
}

export interface IntensityPoint {
  timestamp?: number | null;
  emotion?: string | null;
  intensity?: number | null;
  trigger?: string | null;
}

export interface EmotionArc {
  opening_emotion?: string | null;
  middle_emotion?: string | null;
  ending_emotion?: string | null;
  peak_emotion?: string | null;
  peak_timestamp?: number | null;
  intensity_curve?: IntensityPoint[] | null;
  arc_type?: string | null;
}

export interface ConversionPoint {
  timestamp?: number | null;
  description?: string | null;
  confidence?: number | null;
}

export interface ViralPoint {
  timestamp?: number | null;
  description?: string | null;
  target_metric?: string | null;
  confidence?: number | null;
}

export interface SellingPoint {
  description?: string | null;
  confidence?: number | null;
}

export interface ViralLogic {
  why_retention?: string | null;
  why_click?: string | null;
  why_conversion?: string | null;
  why_viral?: string | null;
  core_selling_point?: string | null;
  key_conversion_action?: string | null;
}

export interface ViralFormula {
  formula_id?: string | null;
  pattern_type?: string | null;
  formula_template?: string | null;
  template_variables?: Record<string, string> | null;
  replicability_score?: number | null;
  success_predictors?: string[] | null;
  similar_reference_count?: number | null;
}

export interface PromptKeyFrame {
  position?: string | null;
  timestamp?: number | null;
  description?: string | null;
  prompt_text?: string | null;
}

export interface AiVideoPrompt {
  subject_prompt?: string | null;
  scene_prompt?: string | null;
  action_prompt?: string | null;
  style_prompt?: string | null;
  full_prompt_zh?: string | null;
  full_prompt_en?: string | null;
  negative_prompt?: string | null;
  style_anchors?: string[] | null;
  key_frames?: PromptKeyFrame[] | null;
  consistency_constraints?: string[] | null;
  recommended_model?: string | null;
  recommended_params?: Record<string, string | number | null | undefined> | null;
}

export interface IterationIssue {
  category?: string | null;
  severity?: string | null;
  description?: string | null;
  timestamp_start?: number | null;
  timestamp_end?: number | null;
  suggested_fix?: string | null;
  revised_prompt_snippet?: string | null;
}

export interface IterationInfo {
  round_number?: number | null;
  verification_target?: string | null;
  issues?: IterationIssue[] | null;
  revised_prompt?: string | null;
  revision_focus?: string | null;
  passed?: boolean | null;
}

export interface SubtitleLine {
  start_time?: number | null;
  end_time?: number | null;
  text?: string | null;
  position?: string | null;
  style?: string | null;
  is_hook?: boolean | null;
}

export interface RhythmInfo {
  bpm_estimate?: number | null;
  cut_frequency?: number | null;
  avg_shot_duration?: number | null;
  rhythm_pattern?: string | null;
  beat_sync_score?: number | null;
}

export interface BgmInfo {
  genre?: string | null;
  tempo_bpm?: number | null;
  mood?: string | null;
  drop_timestamps?: number[] | null;
}

export interface FinalFormat {
  duration?: number | null;
  resolution?: string | null;
  aspect_ratio?: string | null;
  cover_frame_ts?: number | null;
}

export interface PlatformAdaptation {
  recommended_hashtags?: string[] | null;
}

export interface PostProduction {
  rhythm?: RhythmInfo | null;
  subtitles?: SubtitleLine[] | null;
  voiceover_script?: string | null;
  bgm?: BgmInfo | null;
  sound_effects?: string[] | null;
  final_format?: FinalFormat | null;
  platform_adaptations?: Record<string, PlatformAdaptation> | null;
}

export interface ScoreItem {
  score?: number | null;
  reason?: string | null;
}

export interface Scoring {
  hook?: ScoreItem | null;
  selling_point?: ScoreItem | null;
  conversion?: ScoreItem | null;
  human_action?: ScoreItem | null;
  composition?: ScoreItem | null;
  camera_language?: ScoreItem | null;
  editing_rhythm?: ScoreItem | null;
  visual_quality?: ScoreItem | null;
  product_display?: ScoreItem | null;
  overall?: ScoreItem | null;
  emotion_impact?: ScoreItem | null;
  style_consistency?: ScoreItem | null;
  platform_fit?: ScoreItem | null;
  replicability?: ScoreItem | null;
}

export interface AnalysisResultV2 {
  meta?: AnalysisMeta | null;
  video_id?: string | null;
  target_definition?: TargetDefinition | null;
  creative_concept?: CreativeConcept | null;
  basic_info?: BasicInfo | null;
  person?: PersonInfo | null;
  product?: ProductInfo | null;
  scene?: SceneInfo | null;
  timeline?: TimelineSegment[] | null;
  emotion_arc?: EmotionArc | null;
  conversion_points?: ConversionPoint[] | null;
  viral_points?: ViralPoint[] | null;
  selling_points?: SellingPoint[] | null;
  viral_logic?: ViralLogic | null;
  viral_formula?: ViralFormula | null;
  ai_video_prompt?: AiVideoPrompt | null;
  iteration?: IterationInfo | null;
  post_production?: PostProduction | null;
  scoring?: Scoring | null;
}

export type ExternalEvidenceStatusV3 =
  | "AVAILABLE"
  | "NOT_PROVIDED"
  | "NOT_APPLICABLE";
export type InputModeV3 = "FULL_VIDEO" | "SAMPLED_FRAMES";
export type EvidenceSourceV3 =
  | "VIDEO"
  | "FRAME"
  | "AUDIO"
  | "TRANSCRIPT"
  | "TECHNICAL_METADATA"
  | "EXTERNAL";
export type GateStatusV3 = "PASS" | "BLOCK" | "INSUFFICIENT_EVIDENCE";
export type ScoringStatusV3 = "PROVISIONAL" | "UNAVAILABLE";
export type SystemDispositionV3 = "REJECT" | "OWNER_REVIEW_REQUIRED";
export type ContentTypeV3 =
  | "PRODUCT_DEMONSTRATION"
  | "PROBLEM_SOLUTION"
  | "TESTIMONIAL"
  | "COMPARISON"
  | "TUTORIAL"
  | "LIFESTYLE"
  | "STORYTELLING"
  | "OTHER";
export type TopologyV3 =
  | "LINEAR"
  | "LOOP"
  | "MONTAGE"
  | "SPLIT_SCREEN"
  | "ONE_TAKE"
  | "OTHER";
export type ActionPhaseV3 =
  | "POSITIONING"
  | "FORCE"
  | "PEAK"
  | "FEEDBACK"
  | "RELEASE"
  | "RECOVERY";
export type DefectCategoryV3 =
  | "PRODUCT"
  | "PERSON"
  | "PHYSICS"
  | "CAMERA"
  | "DELIVERY"
  | "VISUAL_QUALITY"
  | "AUDIO"
  | "OTHER";

export interface TimeRangeV3 {
  start_seconds: number;
  end_seconds: number;
  start_inclusive: boolean;
  end_inclusive: boolean;
}

export interface EvidenceReferenceV3 {
  source: EvidenceSourceV3;
  timestamp: number | null;
  time_range: TimeRangeV3 | null;
  description: string | null;
  positive: boolean;
}

export interface ExternalEvidenceAvailabilityV3 {
  status: ExternalEvidenceStatusV3;
  detail: string | null;
}

export interface ScoreDimensionV3 {
  dimension_id: string | null;
  name: string | null;
  awarded_points: number | null;
  max_points: number;
  reason: string | null;
  evidence_timestamps: EvidenceReferenceV3[];
  scorable: boolean;
  unscorable_reason: string | null;
  confidence: number | null;
}

export interface SupplementalEvidenceV3 {
  description: string;
  references: EvidenceReferenceV3[];
  affected_dimension_ids: string[];
  confidence: number | null;
}

export interface EvidenceConflictV3 {
  observation_claim: string;
  evaluation_claim: string;
  references: EvidenceReferenceV3[];
  affected_dimension_ids: string[];
  confidence: number | null;
}

export interface AnalysisTimingsV3 {
  observation_duration_ms: number | null;
  evaluation_duration_ms: number | null;
  total_duration_ms: number | null;
  observation_attempts: number;
  evaluation_attempts: number;
}

export interface TechnicalMetadataV3 {
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  aspect_ratio: string | null;
  fps: number | null;
  has_audio_stream: boolean | null;
  format_name: string | null;
  size_bytes: number | null;
}

export interface EvidenceCardV3 {
  source_id: string | null;
  source_sha256: string | null;
  technical_metadata: TechnicalMetadataV3;
  input_mode: InputModeV3 | null;
  sampled_frame_count: number;
  sampled_timestamps: number[];
  observed_ranges: TimeRangeV3[];
  unobserved_ranges: TimeRangeV3[];
  coverage_limitations: string[];
  product_reference: ExternalEvidenceAvailabilityV3;
  publishing_context: ExternalEvidenceAvailabilityV3;
  performance_metrics: ExternalEvidenceAvailabilityV3;
  task_constraints: ExternalEvidenceAvailabilityV3;
  evidence_complete: boolean;
  official_scoring_ready: false;
  missing_evidence: string[];
  limitations: string[];
}

export interface ContentClassificationV3 {
  primary_type: ContentTypeV3;
  secondary_types: ContentTypeV3[];
  topology: TopologyV3;
  evidence_timecodes: EvidenceReferenceV3[];
  confidence: number | null;
}

export interface ObservationFactsV3 {
  summary: string | null;
  subjects: string[];
  person_facts: string[];
  product_facts: string[];
  scene_facts: string[];
}

export interface TimelineEntryV3 extends TimeRangeV3 {
  evidence_sources: EvidenceReferenceV3[];
  subject: string | null;
  person_pose: string | null;
  primary_hand: string | null;
  secondary_hand: string | null;
  grip_point: string | null;
  direction: string | null;
  action_phases: ActionPhaseV3[];
  product_state: string | null;
  product_drift: string | null;
  occlusion: string | null;
  camera: string | null;
  composition: string | null;
  background_motion: string | null;
  lighting: string | null;
  sound_feedback: string | null;
  new_audience_information: string | null;
  provable_claims: string[];
  defects: DefectCategoryV3[];
  confidence: number | null;
}

export interface ClaimEvidenceChainV3 {
  claim: string;
  product_structure: string | null;
  demonstration_action: string | null;
  visible_feedback: string | null;
  usage_result: string | null;
  user_benefit: string | null;
  references: EvidenceReferenceV3[];
  supported: boolean;
}

export interface BusinessLogicAnswersV3 {
  audience_and_need: string | null;
  hook_and_retention: string | null;
  product_recognition: string | null;
  selling_point: string | null;
  visible_proof: string | null;
  rhythm_and_density: string | null;
  memory_and_product_binding: string | null;
  trust_objection_and_action: string | null;
}

export interface DefectV3 {
  category: DefectCategoryV3;
  description: string;
  references: EvidenceReferenceV3[];
  confidence: number | null;
}

export interface ObservationV3 {
  facts: ObservationFactsV3;
  timeline: TimelineEntryV3[];
  claim_evidence_chains: ClaimEvidenceChainV3[];
  business_logic: BusinessLogicAnswersV3;
  defects: DefectV3[];
}

export interface EvidenceReviewV3 {
  evidence_complete: boolean;
  missing_evidence: string[];
  limitations: string[];
  confidence: number | null;
}

export interface G0FindingV3 {
  category: DefectCategoryV3;
  description: string;
  triggered: boolean;
  evidence_timestamps: EvidenceReferenceV3[];
  confidence: number | null;
}

export interface G0AssessmentV3 {
  findings: G0FindingV3[];
}

export interface ScoreSectionV3 {
  dimensions: ScoreDimensionV3[];
}

export interface EvaluationResultV3 {
  review_route: "R" | "G" | null;
  evidence_review: EvidenceReviewV3;
  g0_assessment: G0AssessmentV3;
  common_score_c: ScoreSectionV3;
  specialized_score_r: ScoreSectionV3 | null;
  specialized_score_g: ScoreSectionV3 | null;
  supplemental_evidence: SupplementalEvidenceV3[];
  evidence_conflicts: EvidenceConflictV3[];
  partial_points: number;
  partial_max_points: number;
  diagnostic_total: number | null;
}

export interface DecisionV3 {
  gate_status: GateStatusV3;
  scoring_status: ScoringStatusV3;
  formal_grade: null;
  system_disposition: SystemDispositionV3;
  reasons: string[];
}

export interface AnalysisMetaV3 {
  schema_version: "v3.0";
  observation_prompt_version: string | null;
  evaluation_prompt_version: string | null;
  observation_model_name: string | null;
  observation_model_version: string | null;
  evaluation_model_name: string | null;
  evaluation_model_version: string | null;
  analyzed_at: string | null;
  source_frames_count: number | null;
  confidence_overall: number | null;
  timings: AnalysisTimingsV3;
}

export interface TechnicalAnalysisV3 {
  scene_count: number | null;
  average_shot_duration: number | null;
  cut_frequency: number | null;
  audio_summary: string | null;
}

export interface AnalysisResultV3 {
  meta: AnalysisMetaV3;
  evidence_card: EvidenceCardV3;
  content_classification: ContentClassificationV3;
  observation: ObservationV3;
  evaluation: EvaluationResultV3;
  decision: DecisionV3;
  technical_analysis: TechnicalAnalysisV3 | null;
}

export type AnalysisResult = AnalysisResultV2 | AnalysisResultV3;

export {
  classifyAnalysisResult,
  isAnalysisResultV2,
  isAnalysisResultV3,
} from "./analysisGuards";
export type { ClassifiedAnalysisResult } from "./analysisGuards";

// ---------------------------------------------------------------------------
// FastAPI 数据读取
// ---------------------------------------------------------------------------
export type MaterialAnalysisStatus =
  | "pending"
  | "succeeded"
  | "processing"
  | "failed";

export interface MaterialAnalysisItem {
  platform: string;
  content_id: string;
  status: MaterialAnalysisStatus;
  grade_rank: number;
  grade_reason?: string;
  grade_time: string;
  snap_view_count?: number;
  snap_pub_time?: string;
  snap_hours?: number;
  clean_status: string;
  expire_time: string;
  created_time?: string;
  model?: string;
  attempt_count?: number;
  started_time?: string;
  finished_time?: string;
  updated_time?: string;
  schema_version: string | null;
  overall_score: number | null;
  gate_status: GateStatusV3 | null;
  scoring_status: ScoringStatusV3 | null;
}

export interface VideoAnalysisRecord {
  minio_bucket: string;
  minio_object_name?: string;
  status: string;
  analysis_result?: unknown;
  error_message?: string;
  attempt_count: number;
  model: string;
  started_time: string;
  finished_time?: string;
  created_time: string;
  updated_time: string;
}

export interface MaterialAnalysisDetail extends MaterialAnalysisItem {
  analysis?: VideoAnalysisRecord;
}

export interface MaterialAnalysisPage {
  items: MaterialAnalysisItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AnalysisFilters {
  platforms: string[];
  statuses: MaterialAnalysisStatus[];
  models: string[];
}

const BROWSER_ANALYSIS_API_BASE_URL = "/api/analysis";
const SERVER_ANALYSIS_API_BASE_URL = "http://127.0.0.1:8081/api/analysis";

export function getAnalysisApiBaseUrl() {
  if (typeof window !== "undefined") return BROWSER_ANALYSIS_API_BASE_URL;
  return (
    process.env.ANALYSIS_API_BASE_URL ?? SERVER_ANALYSIS_API_BASE_URL
  ).replace(/\/+$/, "");
}

export class AnalysisApiError extends Error {
  constructor(readonly status: number) {
    super(`Analysis API request failed: ${status}`);
    this.name = "AnalysisApiError";
  }
}

async function analysisRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${getAnalysisApiBaseUrl()}${path}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new AnalysisApiError(response.status);
  }
  return (await response.json()) as T;
}

export function listMaterials(query: URLSearchParams) {
  return analysisRequest<MaterialAnalysisPage>(`?${query.toString()}`);
}

export function getAnalysisFilters() {
  return analysisRequest<AnalysisFilters>("/filters");
}

export function getMaterialAnalysis(platform: string, contentId: string) {
  return analysisRequest<MaterialAnalysisDetail>(
    `/${encodeURIComponent(platform)}/${encodeURIComponent(contentId)}`,
  );
}

export function getAnalysisVideoUrl(platform: string, contentId: string) {
  return analysisRequest<{ url: string; expires_at: string }>(
    `/${encodeURIComponent(platform)}/${encodeURIComponent(contentId)}/video-url`,
  );
}

export function getAnalysisThumbnailUrl(platform: string, contentId: string) {
  return `${BROWSER_ANALYSIS_API_BASE_URL}/${encodeURIComponent(platform)}/${encodeURIComponent(contentId)}/thumbnail`;
}
