export type CrawlerApiErrorKind =
  | "network"
  | "invalid-response"
  | "http"
  | "validation";

export interface CrawlerValidationDetail {
  loc: Array<string | number>;
  msg: string;
  type: string;
}

export interface CrawlerErrorBody {
  detail?: string | CrawlerValidationDetail[];
}

export interface Platform {
  bs_id: number;
  bs_name: string | null;
  bs_platform_code: string | null;
  bs_url: string | null;
  bs_remark: string | null;
  bs_status: "0" | "1" | "D" | null;
  bs_concurrency: number | null;
  bs_rps: number | null;
  bs_burst: number | null;
  bs_cooldown: number | null;
}

export interface PlatformList {
  items: Platform[];
}

export interface PlatformPayload {
  bs_name: string;
  bs_platform_code: string;
  bs_url: string | null;
  bs_remark: string | null;
  bs_status: "0" | "1" | "D";
  bs_concurrency: number;
  bs_rps: number;
  bs_burst: number;
  bs_cooldown: number;
}

export interface Action {
  ba_id: number;
  bs_id: number;
  ba_action: string;
  ba_desc: string | null;
  ba_params_schema: string | null;
  ba_api_url: string | null;
  ba_api_method: string | null;
  ba_enabled: boolean;
  ba_sample_safe: boolean;
  create_time: string | null;
  update_time: string | null;
}

export interface ActionList {
  items: Action[];
}

export interface ActionPayload {
  bs_id: number;
  ba_action: string;
  ba_desc: string | null;
  ba_params_schema: string | null;
  ba_api_url: string | null;
  ba_api_method: string | null;
  ba_enabled: boolean;
  ba_sample_safe: boolean;
}

export interface ActionImportResponse {
  created_count: number;
  updated_count: number;
}

export interface ActionSyncItemDetail {
  platform: string;
  action: string;
  status: string;
  reason?: string | null;
}

export interface ActionSyncRequest {
  platform_id?: number;
  force?: boolean;
}

export interface ActionSyncResponse {
  inserted_count: number;
  updated_count: number;
  skipped_manual_count: number;
  total_synced: number;
  unknown_groups: string[];
  details: ActionSyncItemDetail[];
}

export interface ActionBatchStatusRequest {
  action_ids: number[];
  enabled: boolean;
}

export interface ActionBatchStatusResponse {
  updated_count: number;
}

export interface ActionBatchDeleteRequest {
  action_ids: number[];
}

export interface ActionBatchDeleteResponse {
  deleted_count: number;
}

export interface Keyword {
  id: number;
  platform: string;
  keyword: string;
  is_crawled: boolean;
  created_at: string | null;
}

export interface KeywordList {
  items: Keyword[];
}

export interface KeywordPayload {
  platform: string;
  keyword: string;
}

export type TaskStatus = "pending" | "running" | "paused" | "done" | "failed";

export const TASK_PRIORITIES = [
  "lowest",
  "low",
  "normal",
  "high",
  "urgent",
] as const;

export type TaskPriority = (typeof TASK_PRIORITIES)[number];

export function isTaskPriority(value: string): value is TaskPriority {
  return TASK_PRIORITIES.some((priority) => priority === value);
}

export interface TaskSourceConfig {
  table: string;
  where?: string | null;
  key_column: string;
  param_map: Record<string, string>;
  extra_columns: string[];
  filter_by_platform?: boolean;
  order_by?: string[];
  limit?: number;
}

export interface TaskSinkConfig {
  mode: "standard" | "direct" | "none" | "auto";
  result_column?: string | null;
  mark_done_column?: string | null;
  mark_done_table?: string | null;
}

export type TaskExecutor = "rpc_crawl" | "video_clean" | "video_download" | "video_analysis";

export interface TaskDownloadConfig {
  batch_size: number;
  min_grade: number;
  use_proxy: boolean;
  rps: number;
  max_attempts: number;
  claim_timeout_seconds: number;
  retry_base_seconds: number;
  retry_max_seconds: number;
}

export interface TaskAnalysisConfig {
  batch_size?: number;
  max_attempts?: number;
  llm_model_id?: number | null;
  review_route: "R" | "G" | null;
}


export type TaskScheduleType = "manual" | "once" | "interval" | "cron";

export interface TaskSchedule {
  type: TaskScheduleType;
  cron: string | null;
  run_at: string | null;
  interval_seconds: number | null;
  start_at: string | null;
  end_at: string | null;
  max_runs: number | null;
}

export interface TaskRetryPolicy {
  max_attempts: number;
  initial_delay_seconds: number;
  backoff_multiplier: number;
  max_delay_seconds: number;
}

export interface Task {
  task_id: number;
  platform: string;
  action: string;
  ba_id: number | null;
  platform_id: number | null;
  status: TaskStatus;
  priority: TaskPriority;
  attempts: number;
  error_msg: string | null;
  last_run_at: string | null;
  loop_enabled: boolean;
  loop_interval_seconds: number | null;
  schedule_type: TaskScheduleType;
  cron_expression: string | null;
  run_once_at: string | null;
  schedule_start_at: string | null;
  schedule_end_at: string | null;
  max_runs: number | null;
  next_run_at: string | null;
  schedule?: TaskSchedule | null;
  retry_policy?: TaskRetryPolicy | null;
  run_count: number;
  last_run_status: string | null;
  retry_max_attempts: number;
  retry_delay_seconds: number;
  retry_backoff_multiplier: number;
  retry_max_delay_seconds: number;
  retry_count: number;
  next_retry_at: string | null;
  run_now_requested_at: string | null;
  pause_requested: boolean;
  active_trigger: string | null;
  active_scheduled_at: string | null;
  config: {
    executor: TaskExecutor;
    download?: TaskDownloadConfig | null;
    analysis?: TaskAnalysisConfig | null;
    source: TaskSourceConfig | null;
    sink: TaskSinkConfig;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface TaskList { items: Task[] }

export interface TaskPayload {
  ba_id: number;
  ref_table: string;
  ref_where: string;
  params_columns: string;
  entity_column: string;
  result_column: string;
  post_update_column: string;
  post_update_table: string;
  sink_mode: TaskSinkConfig["mode"];
  priority: TaskPriority;
  loop_enabled: boolean;
  loop_interval_seconds: number | null;
  schedule?: TaskSchedule | null;
  retry_policy?: TaskRetryPolicy | null;
  executor?: TaskExecutor;
  download?: TaskDownloadConfig;
  llm_model_id?: number | null;
  review_route?: TaskAnalysisConfig["review_route"];
}

export interface TaskBatchStatusResponse { updated_count: number }
export interface TableColumnsResponse { columns: string[] }
