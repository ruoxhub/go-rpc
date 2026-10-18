import type { CrawlerApiErrorKind, Task, TaskPriority } from "./crawler-types";
import { t } from "../../app/i18n";

const BROWSER_API_BASE_URL = "/api/crawler";
const SERVER_API_BASE_URL = "http://127.0.0.1:8081/api/crawler";

export class CrawlerApiError extends Error {
  readonly kind: CrawlerApiErrorKind;
  readonly status: number | null;
  readonly fieldErrors: Record<string, string>;
  readonly code?: string;
  readonly details?: ParserApiErrorDetails;
  readonly retryAfter?: number;
  readonly responseSnippet?: string;

  constructor({
    message,
    kind,
    status = null,
    fieldErrors = {},
    code,
    details,
    retryAfter,
    responseSnippet,
    cause,
  }: {
    message: string;
    kind: CrawlerApiErrorKind;
    status?: number | null;
    fieldErrors?: Record<string, string>;
    code?: string;
    details?: ParserApiErrorDetails;
    retryAfter?: number;
    responseSnippet?: string;
    cause?: unknown;
  }) {
    super(message, { cause });
    this.name = "CrawlerApiError";
    this.kind = kind;
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter;
    this.responseSnippet = responseSnippet;
  }
}

export interface ParserApiErrorDetails {
  ba_id?: number;
  sample_id?: number;
  revision_id?: number;
  model_id?: number;
  path?: string;
  validator?: string;
  retry_after_seconds?: number;
  /** 数据记录 CRUD 的字段级错误定位。 */
  field?: string;
}

export function getCrawlerApiBaseUrl() {
  if (typeof window !== "undefined") return BROWSER_API_BASE_URL;
  return (process.env.CRAWLER_API_BASE_URL || SERVER_API_BASE_URL).replace(
    /\/+$/,
    "",
  );
}

export async function apiRequest<T>(
  baseUrl: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return requestJson(baseUrl, path, init);
}

interface ValidationDetail {
  loc: Array<string | number>;
  msg: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isValidationDetail(value: unknown): value is ValidationDetail {
  return (
    isRecord(value) &&
    Array.isArray(value.loc) &&
    value.loc.every(
      (part) => typeof part === "string" || typeof part === "number",
    ) &&
    typeof value.msg === "string"
  );
}

function fieldPath(detail: ValidationDetail) {
  const parts = detail.loc[0] === "body" ? detail.loc.slice(1) : detail.loc;
  return parts.join(".");
}

function validationErrors(details: ValidationDetail[]) {
  return Object.fromEntries(
    details.map((detail) => [fieldPath(detail), detail.msg]),
  );
}

const numberDetailKeys = ["ba_id", "sample_id", "revision_id", "model_id"] as const;
const stringDetailKeys = ["path", "validator", "field"] as const;

function parserErrorDetails(value: unknown): ParserApiErrorDetails {
  if (!isRecord(value)) return {};
  const result: ParserApiErrorDetails = {};
  for (const key of numberDetailKeys) {
    const candidate = value[key];
    if (typeof candidate === "number" && Number.isSafeInteger(candidate) && candidate > 0) {
      result[key] = candidate;
    }
  }
  for (const key of stringDetailKeys) {
    const candidate = value[key];
    if (typeof candidate === "string") result[key] = candidate;
  }
  if (typeof value.retry_after_seconds === "number" && Number.isFinite(value.retry_after_seconds)) {
    result.retry_after_seconds = value.retry_after_seconds;
  }
  return result;
}

function retryAfterSeconds(response: Response, details: ParserApiErrorDetails) {
  if (response.status !== 429) return undefined;
  const header = Number(response.headers.get("Retry-After"));
  if (Number.isFinite(header) && header > 0) return Math.ceil(header);
  const fallback = details.retry_after_seconds;
  return typeof fallback === "number" && fallback > 0 ? Math.max(1, Math.ceil(fallback)) : undefined;
}

const RESPONSE_SNIPPET_LIMIT = 200;

function responseSnippet(text: string) {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > RESPONSE_SNIPPET_LIMIT
    ? `${normalized.slice(0, RESPONSE_SNIPPET_LIMIT)}…`
    : normalized;
}

async function readResponseText(response: Response) {
  try {
    return await response.text();
  } catch (cause) {
    throw new CrawlerApiError({
      message: t("api.network"),
      kind: "network",
      status: response.status,
      cause,
    });
  }
}

async function requestJson<T>(
  baseUrl: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  let response: Response;
  try {
    const normalizedPath = path.replace(/^\/+/, "");
    response = await fetch(
      normalizedPath
        ? `${normalizedBaseUrl}/${normalizedPath}`
        : normalizedBaseUrl,
      { ...init, headers },
    );
  } catch (cause) {
    throw new CrawlerApiError({
      message: t("api.network"),
      kind: "network",
      cause,
    });
  }

  if (response.ok && response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const text = await readResponseText(response);

  if (!contentType.includes("application/json")) {
    throw new CrawlerApiError({
      message: t("api.invalidResponse", { status: response.status }),
      kind: "invalid-response",
      status: response.status,
      responseSnippet: responseSnippet(text),
    });
  }

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch (cause) {
    throw new CrawlerApiError({
      message: t("api.invalidJson", { status: response.status }),
      kind: "invalid-response",
      status: response.status,
      responseSnippet: responseSnippet(text),
      cause,
    });
  }

  if (response.ok) return body as T;

  const detail = isRecord(body) ? body.detail : undefined;
  if (
    response.status === 422 &&
    Array.isArray(detail) &&
    detail.every(isValidationDetail)
  ) {
    throw new CrawlerApiError({
      message: t("api.validation"),
      kind: "validation",
      status: response.status,
      fieldErrors: validationErrors(detail),
    });
  }

  const structured = isRecord(body) ? body : {};
  const details = parserErrorDetails(structured.details);
  throw new CrawlerApiError({
    message:
      typeof structured.message === "string"
        ? structured.message
        : typeof detail === "string"
        ? detail
        : t("api.http", { status: response.status }),
    kind: "http",
    status: response.status,
    code: typeof structured.code === "string" ? structured.code : undefined,
    details,
    retryAfter: retryAfterSeconds(response, details),
  });
}
export interface SchedulePreviewResponse {
  timezone: string;
  occurrences: string[];
}

export function previewTaskSchedule(
  cron: string,
): Promise<SchedulePreviewResponse> {
  return crawlerRequest<SchedulePreviewResponse>("/tasks/schedule/preview", {
    method: "POST",
    body: JSON.stringify({ cron }),
  });
}

export function runTaskNow(taskId: number) {
  return crawlerRequest<void>(`/tasks/${taskId}/run-now`, { method: "POST" });
}

export function updateTaskOperation(taskId: number, operation: "start" | "pause") {
  return crawlerRequest<Task>(`/tasks/${taskId}/${operation}`, { method: "POST" });
}

export function updateTaskPriority(taskId: number, priority: TaskPriority) {
  return crawlerRequest<Task>(`/tasks/${taskId}/priority`, {
    method: "PATCH",
    body: JSON.stringify({ priority }),
  });
}

export function crawlerRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return apiRequest(getCrawlerApiBaseUrl(), path, init);
}
