export interface LlmSettingsResponse {
  default_analysis_model_id: number | null;
  default_transcription_model_id: number | null;
  max_tokens: number;
  temperature: number;
  enable_thinking: boolean;
}

export interface LlmSettingsUpdate {
  default_analysis_model_id?: number | null;
  default_transcription_model_id?: number | null;
  max_tokens?: number;
  temperature?: number;
  enable_thinking?: boolean;
}

export type ProviderProtocol =
  | "openai-completion"
  | "claude"
  | "gemini"
  | "deepseek"
  | "openai-responses";

export interface LlmProvider {
  id: number;
  name: string;
  litellm_prefix: string;
  protocol: ProviderProtocol;
  base_url: string | null;
  enabled: boolean;
  api_key_configured: boolean;
  api_key_masked: string;
  last_sync_status: string | null;
  last_sync_at: string | null;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface LlmModel {
  id: number;
  provider_id: number;
  remote_model_id: string;
  litellm_model: string;
  display_name: string;
  enabled: boolean;
  remote_available: boolean;
  last_discovered_at: string | null;
}

export interface ProviderCreate {
  name: string;
  protocol: ProviderProtocol;
  base_url: string | null;
  api_key: string;
}

export interface ProviderUpdate {
  name?: string;
  protocol?: ProviderProtocol;
  base_url?: string;
  api_key?: string;
}

export interface ProviderModelSyncResult {
  created: number;
  updated: number;
  unavailable: number;
  status: string;
  synced_at: string;
}

export type ProviderModelStatus =
  "usable" | "enabled" | "disabled" | "unavailable" | "all";

export interface SchedulerSettings {
  timezone: string;
  worker_id: string;
  poll_interval_ms: number;
  default_loop_interval_seconds: number;
  batch_size: number;
  zombie_reap_after_seconds: number;
  graceful_shutdown_seconds: number;
}

export interface SchedulerSettingsResponse extends SchedulerSettings {
  inactive_fields: string[];
}

export interface RpcSettings {
  base_url: string;
  timeout_seconds: number;
}

export interface AnalysisVideoSettings {
  is_base64: boolean;
  frame_sampling_strategy: "interval" | "count" | "timestamps" | "scene_guided";
  max_frames: number;
  frame_interval_seconds: number;
  frame_timestamps: number[];
}

export type AnalysisVideoSettingsUpdate = Partial<AnalysisVideoSettings>;

export interface ProxySettingsResponse {
  url_configured: boolean;
  target: string;
}

export interface ProxySettingsUpdate {
  url?: string;
}

export type FilterOperator =
  | "="
  | "!="
  | ">"
  | ">="
  | "<"
  | "<="
  | "in"
  | "exists";
export type JsonScalar = string | number | boolean | null;

export interface GradeRule {
  max_hours: number;
  min_views: number;
}

export interface FilterRule {
  field: string;
  operator: FilterOperator;
  value: JsonScalar | JsonScalar[];
}

export interface PlatformPolicy {
  p2: GradeRule[];
  p3: GradeRule[];
  p1: GradeRule[];
  filters: FilterRule[];
}

export interface CleanerSettings {
  enabled: boolean;
  poll_interval: number;
  batch_size: number;
  max_batches_per_platform: number;
  ttl_days: number;
  watermark_key: string;
  suspect_seconds: number;
  inactive_fields: string[];
}

export interface PlatformSettingsResponse {
  platform: string;
  configured: boolean;
  policy: PlatformPolicy | null;
}

export interface SettingsResponse {
  llm: LlmSettingsResponse;
  scheduler: SchedulerSettingsResponse;
  rpc: RpcSettings;
  analysis_video: AnalysisVideoSettings;
  proxy: ProxySettingsResponse;
  cleaner: CleanerSettings;
  platforms: PlatformSettingsResponse[];
}
