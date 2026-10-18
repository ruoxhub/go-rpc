import type { TaskScheduleType } from "@/utils/crawler/crawler-types";

export interface ScheduleFormValue {
  type: TaskScheduleType;
  run_at: string;
  interval_seconds: string;
  cron_expression: string;
  start_at: string;
  end_at: string;
  max_runs: string;
  max_retries: string;
  retry_delay_seconds: string;
  retry_backoff_factor: string;
  retry_max_delay_seconds: string;
}
