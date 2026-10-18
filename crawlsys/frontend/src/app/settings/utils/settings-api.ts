import { apiRequest } from "../../../utils/crawler/crawler-api";

import type {
  AnalysisVideoSettings,
  AnalysisVideoSettingsUpdate,
  CleanerSettings,
  LlmModel,
  LlmProvider,
  LlmSettingsResponse,
  LlmSettingsUpdate,
  PlatformPolicy,
  PlatformSettingsResponse,
  ProxySettingsResponse,
  ProxySettingsUpdate,
  RpcSettings,
  SchedulerSettings,
  SchedulerSettingsResponse,
  SettingsResponse,
  ProviderModelStatus,
  ProviderModelSyncResult,
  ProviderCreate,
  ProviderUpdate,
} from "./settings-types";

const BROWSER_SETTINGS_API_BASE_URL = "/api/settings";
const SERVER_SETTINGS_API_BASE_URL = "http://127.0.0.1:8081/api/settings";
const BROWSER_LLM_PROVIDER_API_BASE_URL = "/api/llm/providers";

function settingsBaseUrlFromCrawler(value: string | undefined) {
  if (!value) return null;

  try {
    const url = new URL(value);
    const pathname = url.pathname.replace(/\/+$/, "");
    if (
      !["http:", "https:"].includes(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password ||
      pathname.includes("//") ||
      !pathname.endsWith("/api/crawler")
    ) {
      return null;
    }

    url.pathname = `${pathname.slice(0, -"/api/crawler".length)}/api/settings`;
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return null;
  }
}

export function getSettingsApiBaseUrl() {
  if (typeof window !== "undefined") return BROWSER_SETTINGS_API_BASE_URL;
  if (process.env.SETTINGS_API_BASE_URL) {
    return process.env.SETTINGS_API_BASE_URL.replace(/\/+$/, "");
  }
  return (
    settingsBaseUrlFromCrawler(process.env.CRAWLER_API_BASE_URL) ??
    SERVER_SETTINGS_API_BASE_URL
  );
}

export function settingsRequest<T>(path: string, init: RequestInit = {}) {
  return apiRequest<T>(getSettingsApiBaseUrl(), path, init);
}

function getLlmProviderApiBaseUrl() {
  if (typeof window !== "undefined") return BROWSER_LLM_PROVIDER_API_BASE_URL;
  return getSettingsApiBaseUrl().replace(
    /\/api\/settings$/,
    "/api/llm/providers",
  );
}

function llmProviderRequest<T>(path: string, init: RequestInit = {}) {
  return apiRequest<T>(getLlmProviderApiBaseUrl(), path, init);
}

function put<T>(path: string, body: unknown) {
  return settingsRequest<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export function getSettings() {
  return settingsRequest<SettingsResponse>("");
}

export function updateLlmSettings(value: LlmSettingsUpdate) {
  return put<LlmSettingsResponse>("/llm", value);
}

export function updateSchedulerSettings(value: SchedulerSettings) {
  return put<SchedulerSettingsResponse>("/scheduler", value);
}

export function updateRpcSettings(value: RpcSettings) {
  return put<RpcSettings>("/scheduler/rpc", value);
}

export function updateAnalysisVideoSettings(value: AnalysisVideoSettingsUpdate) {
  return put<AnalysisVideoSettings>("/analysis/video", value);
}

export function updateProxySettings(value: ProxySettingsUpdate) {
  return put<ProxySettingsResponse>("/proxy", value);
}

export function updateCleanerSettings(value: Omit<CleanerSettings, "inactive_fields">) {
  return put<CleanerSettings>("/cleaner", value);
}

export function updatePlatformPolicy(platform: string, value: PlatformPolicy) {
  return put<PlatformSettingsResponse>(
    `/platforms/${encodeURIComponent(platform)}`,
    value,
  );
}

export function listProviders() {
  return llmProviderRequest<LlmProvider[]>("");
}

export function createProvider(value: ProviderCreate) {
  return llmProviderRequest<LlmProvider>("", {
    method: "POST",
    body: JSON.stringify(value),
  });
}

export function updateProvider(providerId: number, value: ProviderUpdate) {
  return llmProviderRequest<LlmProvider>(`/${providerId}`, {
    method: "PATCH",
    body: JSON.stringify(value),
  });
}

export function setProviderEnabled(providerId: number, enabled: boolean) {
  return llmProviderRequest<LlmProvider>(
    `/${providerId}/${enabled ? "enable" : "disable"}`,
    { method: "POST" },
  );
}

export function deleteProvider(providerId: number) {
  return llmProviderRequest<void>(`/${providerId}`, { method: "DELETE" });
}

export function syncProviderModels(providerId: number) {
  return llmProviderRequest<ProviderModelSyncResult>(
    `/${providerId}/sync-models`,
    { method: "POST" },
  );
}

export function listProviderModels(
  providerId: number,
  status?: ProviderModelStatus,
) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return llmProviderRequest<LlmModel[]>(`/${providerId}/models${query}`);
}

export async function loadProviderModelCatalog(providers: LlmProvider[]) {
  const results = await Promise.allSettled(
    providers.map((provider) => listProviderModels(provider.id, "all")),
  );
  const catalog = results.flatMap((result) => result.status === "fulfilled" ? result.value : []);
  const enabledProviderIds = new Set(providers.filter((provider) => provider.enabled).map((provider) => provider.id));
  return {
    catalog,
    models: catalog.filter((model) => enabledProviderIds.has(model.provider_id) && model.enabled && model.remote_available),
    incomplete: results.some((result) => result.status === "rejected"),
  };
}

export function setModelEnabled(modelId: number, enabled: boolean) {
  return llmProviderRequest<LlmModel>(
    `/models/${modelId}/${enabled ? "enable" : "disable"}`,
    { method: "POST" },
  );
}
