import {
  isTaskPriority,
  type Task,
  type TaskAnalysisConfig,
  type TaskDownloadConfig,
  type TaskPayload,
  type TaskRetryPolicy,
  type TaskSchedule,
} from "../../../../../../utils/crawler/crawler-types";
import type { ScheduleFormValue } from "../types/schedule";
import { t } from "../../../../../i18n";

export const controlClass =
  "h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function initialSchedule(task?: Task): ScheduleFormValue {
  if (task?.schedule) {
    const rp = task.retry_policy as Record<string, unknown> | undefined;
    const maxRetries =
      rp?.max_attempts != null
        ? String(rp.max_attempts)
        : rp?.max_retries != null
          ? String(rp.max_retries)
          : "3";
    const retryDelay =
      rp?.initial_delay_seconds != null
        ? String(rp.initial_delay_seconds)
        : rp?.retry_delay_seconds != null
          ? String(rp.retry_delay_seconds)
          : "60";
    const backoff =
      rp?.backoff_multiplier != null
        ? String(rp.backoff_multiplier)
        : rp?.retry_backoff_factor != null
          ? String(rp.retry_backoff_factor)
          : "2";

    return {
      type: task.schedule.type ?? "manual",
      run_at: task.schedule.run_at ?? "",
      interval_seconds:
        task.schedule.interval_seconds != null
          ? String(task.schedule.interval_seconds)
          : "",
      cron_expression: task.schedule.cron ?? "",
      start_at: task.schedule.start_at ?? "",
      end_at: task.schedule.end_at ?? "",
      max_runs: task.schedule.max_runs != null ? String(task.schedule.max_runs) : "",
      max_retries: maxRetries,
      retry_delay_seconds: retryDelay,
      retry_backoff_factor: backoff,
      retry_max_delay_seconds:
        task.retry_policy?.max_delay_seconds != null
          ? String(task.retry_policy.max_delay_seconds)
          : "3600",
    };
  }

  if (task?.loop_enabled) {
    return {
      type: "interval",
      run_at: "",
      interval_seconds:
        task.loop_interval_seconds != null
          ? String(task.loop_interval_seconds)
          : "",
      cron_expression: "",
      start_at: "",
      end_at: "",
      max_runs: "",
      max_retries: "3",
      retry_delay_seconds: "60",
      retry_backoff_factor: "2",
      retry_max_delay_seconds: "3600",
    };
  }

  return {
    type: "manual",
    run_at: "",
    interval_seconds: "",
    cron_expression: "",
    start_at: "",
    end_at: "",
    max_runs: "",
    max_retries: "3",
    retry_delay_seconds: "60",
    retry_backoff_factor: "2",
    retry_max_delay_seconds: "3600",
  };
}

export function scheduleSummary(
  task?: {
    schedule?: Partial<TaskSchedule> | null;
    loop_enabled?: boolean | null;
    loop_interval_seconds?: number | null;
  },
): string {
  const sched = task?.schedule;
  if (sched?.type) {
    switch (sched.type) {
      case "manual":
        return t("tasks.scheduleManual");
      case "once":
        return t("tasks.scheduleOnce", { run_at: sched.run_at ?? "-" });
      case "interval":
        return t("tasks.scheduleInterval", {
          seconds: String(sched.interval_seconds ?? "-"),
        });
      case "cron":
        return t("tasks.scheduleCron", { expression: sched.cron ?? "-" });
      default:
        return t("tasks.scheduleManual");
    }
  }

  if (task?.loop_enabled) {
    return t("tasks.scheduleInterval", {
      seconds: String(task.loop_interval_seconds ?? "-"),
    });
  }

  return t("tasks.scheduleManual");
}

export function formText(data: FormData, name: string) {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function priorityFromForm(data: FormData) {
  const value = formText(data, "priority") || "normal";
  if (!isTaskPriority(value)) {
    throw new Error(`Invalid priority: ${value}`);
  }
  return value;
}

export function serializeMapping(value: string) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [source, target] = line.split(/\s*=>\s*/, 2);
      return target ? `${source} AS ${target}` : source;
    })
    .join(", ");
}

export function initialMapping(task?: Task) {
  return Object.entries(task?.config?.source?.param_map ?? {})
    .map(([source, target]) => `${source} => ${target}`)
    .join("\n");
}

const defaultDownloadConfig: TaskDownloadConfig = {
  batch_size: 50,
  min_grade: 3,
  use_proxy: true,
  rps: 0,
  max_attempts: 5,
  claim_timeout_seconds: 1800,
  retry_base_seconds: 60,
  retry_max_seconds: 3600,
};

function downloadConfig(data: FormData): TaskDownloadConfig {
  const defaults: Record<string, number> = {
    download_batch_size: defaultDownloadConfig.batch_size,
    download_min_grade: defaultDownloadConfig.min_grade,
    download_rps: defaultDownloadConfig.rps,
    download_max_attempts: defaultDownloadConfig.max_attempts,
    download_claim_timeout_seconds: defaultDownloadConfig.claim_timeout_seconds,
    download_retry_base_seconds: defaultDownloadConfig.retry_base_seconds,
    download_retry_max_seconds: defaultDownloadConfig.retry_max_seconds,
  };
  const number = (name: string) => {
    const value = formText(data, name);
    return value ? Number(value) : defaults[name];
  };
  return {
    batch_size: number("download_batch_size"),
    min_grade: number("download_min_grade"),
    use_proxy: data.get("download_use_proxy") === "on",
    rps: number("download_rps"),
    max_attempts: number("download_max_attempts"),
    claim_timeout_seconds: number("download_claim_timeout_seconds"),
    retry_base_seconds: number("download_retry_base_seconds"),
    retry_max_seconds: number("download_retry_max_seconds"),
  };
}

function reviewRoute(data: FormData): TaskAnalysisConfig["review_route"] {
  const value = data.get("review_route");
  if (value === null) throw new Error("Missing review_route");
  if (value === "") return null;
  if (value === "R" || value === "G") return value;
  throw new Error(`Invalid review_route: ${String(value)}`);
}

export function taskPayload({
  data,
  actionId,
  table,
  keyColumn,
  parameterMapping,
  schedule,
  loopEnabled,
  interval,
  executor,
}: {
  data: FormData;
  actionId: number;
  table: string;
  keyColumn: string;
  parameterMapping: string;
  schedule?: ScheduleFormValue;
  loopEnabled?: boolean;
  interval?: string;
  executor: TaskPayload["executor"];
}): TaskPayload {
  const llmModelId = formText(data, "llm_model_id");

  const schedType = schedule?.type ?? (loopEnabled ? "interval" : "manual");
  const intervalSeconds = schedule
    ? schedule.interval_seconds
      ? Number(schedule.interval_seconds)
      : null
    : interval && interval.trim()
      ? Number(interval)
      : null;

  const wireSchedule: TaskSchedule = {
    type: schedType,
    cron: schedType === "cron" ? schedule?.cron_expression || null : null,
    run_at: schedType === "once" ? schedule?.run_at || null : null,
    interval_seconds: schedType === "interval" ? intervalSeconds : null,
    start_at: schedule?.start_at || null,
    end_at: schedule?.end_at || null,
    max_runs: schedule?.max_runs ? Number(schedule.max_runs) : null,
  };

  const wireRetryPolicy: TaskRetryPolicy = {
    max_attempts: schedule?.max_retries ? Number(schedule.max_retries) : 3,
    initial_delay_seconds: schedule?.retry_delay_seconds ? Number(schedule.retry_delay_seconds) : 60,
    backoff_multiplier: schedule?.retry_backoff_factor ? Number(schedule.retry_backoff_factor) : 2,
    max_delay_seconds: schedule?.retry_max_delay_seconds
      ? Number(schedule.retry_max_delay_seconds)
      : 3600,
  };

  const legacyLoopEnabled = schedType === "interval";

  return {
    ba_id: actionId,
    ref_table: table.trim(),
    ref_where: formText(data, "ref_where"),
    params_columns: serializeMapping(parameterMapping),
    entity_column: keyColumn,
    result_column: formText(data, "result_column"),
    post_update_column: formText(data, "post_update_column"),
    post_update_table: formText(data, "post_update_table"),
    sink_mode: formText(data, "sink_mode") as TaskPayload["sink_mode"],
    priority: priorityFromForm(data),
    schedule: wireSchedule,
    retry_policy: wireRetryPolicy,
    loop_enabled: legacyLoopEnabled,
    loop_interval_seconds: legacyLoopEnabled ? intervalSeconds : null,
    executor,
    ...(executor === "video_analysis"
      ? {
          llm_model_id: llmModelId ? Number(llmModelId) : null,
          review_route: reviewRoute(data),
        }
      : executor === "video_download"
        ? { download: downloadConfig(data) }
      : {}),
  };
}
