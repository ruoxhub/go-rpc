import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createProvider,
  deleteProvider,
  getSettings,
  getSettingsApiBaseUrl,
  listProviderModels,
  listProviders,
  loadProviderModelCatalog,
  setModelEnabled,
  setProviderEnabled,
  syncProviderModels,
  updateAnalysisVideoSettings,
  updateCleanerSettings,
  updateLlmSettings,
  updatePlatformPolicy,
  updateProxySettings,
  updateRpcSettings,
  updateSchedulerSettings,
  updateProvider,
} from "./settings-api";
import type { ProviderCreate, ProviderUpdate } from "./settings-types";

const providerCreateContract = {
  name: "main",
  protocol: "openai-completion",
  base_url: null,
  api_key: "secret",
} satisfies ProviderCreate;

const invalidProviderPrefix = {
  ...providerCreateContract,
  // @ts-expect-error 创建请求不能覆盖后端派生的 LiteLLM 前缀
  litellm_prefix: "custom",
} satisfies ProviderCreate;

const providerUpdateContract = { name: "renamed" } satisfies ProviderUpdate;

// @ts-expect-error 创建提供商必须提供 API Key
const invalidProviderCreate = { name: "main", protocol: "openai-completion", base_url: null } satisfies ProviderCreate;

// @ts-expect-error 更新提供商不允许显式清空 base_url
const invalidProviderUpdate = { base_url: null } satisfies ProviderUpdate;

void providerCreateContract;
void invalidProviderPrefix;
void providerUpdateContract;
void invalidProviderCreate;
void invalidProviderUpdate;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("getSettingsApiBaseUrl", () => {
  it("浏览器使用同源 settings 路径", () => {
    vi.stubGlobal("window", {});
    expect(getSettingsApiBaseUrl()).toBe("/api/settings");
  });

  it("服务端使用默认 settings 地址", () => {
    expect(getSettingsApiBaseUrl()).toBe("http://127.0.0.1:8081/api/settings");
  });

  it("服务端只读取 settings 环境变量", () => {
    vi.stubEnv(
      "CRAWLER_API_BASE_URL",
      "https://crawler.example/api/crawler",
    );
    vi.stubEnv(
      "SETTINGS_API_BASE_URL",
      "https://settings.example/api/settings/",
    );
    expect(getSettingsApiBaseUrl()).toBe("https://settings.example/api/settings");
  });

  it("从完整 crawler 基址安全派生同源 settings 地址", () => {
    vi.stubEnv(
      "CRAWLER_API_BASE_URL",
      "https://crawler.example/internal/api/crawler/",
    );
    expect(getSettingsApiBaseUrl()).toBe(
      "https://crawler.example/internal/api/settings",
    );
  });

  it.each([
    "https://crawler.example/internal/crawler",
    "not-a-valid-url/api/crawler",
    "https://user:secret@crawler.example/api/crawler",
    "file:///api/crawler",
    "http://:8081/api/crawler",
    "https://crawler.example/api//crawler",
  ])("crawler 基址 %s 不符合契约时使用默认地址", (crawlerBaseUrl) => {
    vi.stubEnv("CRAWLER_API_BASE_URL", crawlerBaseUrl);
    expect(getSettingsApiBaseUrl()).toBe(
      "http://127.0.0.1:8081/api/settings",
    );
  });
});

describe("settings API", () => {
  it("读取完整设置", async () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ platforms: [] })),
    );
    await getSettings();
    expect(fetch).toHaveBeenCalledWith(
      "/api/settings",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  const updateCases = [
    {
      request: () => updateLlmSettings({ default_analysis_model_id: 11 }),
      path: "/llm",
      body: { default_analysis_model_id: 11 },
    },
    {
      request: () =>
        updateSchedulerSettings({
          timezone: "Asia/Shanghai",
          worker_id: "worker",
          poll_interval_ms: 1000,
          default_loop_interval_seconds: 3600,
          batch_size: 10,
          zombie_reap_after_seconds: 600,
          graceful_shutdown_seconds: 30,
        }),
      path: "/scheduler",
      body: {
        timezone: "Asia/Shanghai",
        worker_id: "worker",
        poll_interval_ms: 1000,
        default_loop_interval_seconds: 3600,
        batch_size: 10,
        zombie_reap_after_seconds: 600,
        graceful_shutdown_seconds: 30,
      },
    },
    {
      request: () =>
        updateRpcSettings({
          base_url: "https://rpc.test",
          timeout_seconds: 2,
        }),
      path: "/scheduler/rpc",
      body: { base_url: "https://rpc.test", timeout_seconds: 2 },
    },
    {
      request: () => updateAnalysisVideoSettings({ is_base64: true }),
      path: "/analysis/video",
      body: { is_base64: true },
    },
    {
      request: () => updateProxySettings({ url: "   " }),
      path: "/proxy",
      body: { url: "   " },
    },
    {
      request: () =>
        updateCleanerSettings({
          enabled: false,
          poll_interval: 3600,
          batch_size: 1000,
          max_batches_per_platform: 10,
          ttl_days: 14,
          watermark_key: "cleaner:grade:watermark",
          suspect_seconds: 120,
        }),
      path: "/cleaner",
      body: {
        enabled: false,
        poll_interval: 3600,
        batch_size: 1000,
        max_batches_per_platform: 10,
        ttl_days: 14,
        watermark_key: "cleaner:grade:watermark",
        suspect_seconds: 120,
      },
    },
  ];

  it.each(updateCases)("PUT $path 使用正确路径和请求体", async ({ request, path, body }) => {
    vi.stubGlobal("window", {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({})));

    await request();

    expect(fetch).toHaveBeenCalledWith(
      `/api/settings${path}`,
      expect.objectContaining({ method: "PUT", body: JSON.stringify(body) }),
    );
  });

  it("更新编码后的平台策略路径", async () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({})));
    const policy = {
      p1: [{ max_hours: 24, min_views: 100 }],
      p2: [],
      p3: [],
      filters: [],
    };

    await updatePlatformPolicy("tik tok", policy);

    expect(fetch).toHaveBeenCalledWith(
      "/api/settings/platforms/tik%20tok",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(policy) }),
    );
  });
});

describe("LLM provider API", () => {
  const provider = {
    id: 7,
    name: "main",
    litellm_prefix: "openai",
    protocol: "openai-completion" as const,
    base_url: "https://api.openai.com",
    enabled: true,
    api_key_configured: true,
    api_key_masked: "********test",
    last_sync_status: null,
    last_sync_at: null,
    last_sync_error: null,
    created_at: "2026-08-03T00:00:00Z",
    updated_at: "2026-08-03T00:00:00Z",
  };

  it("逐 Provider 容错加载模型目录并标记不完整", async () => {
    const model = {
      id: 11,
      provider_id: provider.id,
      remote_model_id: "gpt-5",
      litellm_model: "openai/gpt-5",
      display_name: "GPT-5",
      enabled: true,
      remote_available: true,
      last_discovered_at: null,
    };
    vi.stubGlobal("window", {});
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (input) => {
      if (String(input).includes("/7/models")) return Response.json([model]);
      return Response.json({ detail: "unavailable" }, { status: 503 });
    }));

    const result = await loadProviderModelCatalog([
      provider,
      { ...provider, id: 8, name: "backup" },
    ]);

    expect(result).toEqual({ catalog: [model], models: [model], incomplete: true });
  });

  it("使用提供商与模型端点", async () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(() => Promise.resolve(Response.json(provider))),
    );

    await listProviders();
    await createProvider({
      name: "main",
      protocol: "openai-completion",
      base_url: "https://api.openai.com",
      api_key: "secret",
    });
    await setProviderEnabled(7, false);
    await deleteProvider(7);
    await syncProviderModels(7);
    await listProviderModels(7, "usable");
    await setModelEnabled(9, true);

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/llm/providers",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/llm/providers",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "main",
          protocol: "openai-completion",
          base_url: "https://api.openai.com",
          api_key: "secret",
        }),
      }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/llm/providers/7/disable",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      4,
      "/api/llm/providers/7",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      5,
      "/api/llm/providers/7/sync-models",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      6,
      "/api/llm/providers/7/models?status=usable",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      7,
      "/api/llm/providers/models/9/enable",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("更新提供商时未传 api_key 则保留现有密钥", async () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(provider)));

    await updateProvider(7, {
      name: "main",
    });

    const request = vi.mocked(fetch).mock.calls[0][1];
    expect(JSON.parse(String(request?.body))).not.toHaveProperty("api_key");
    expect(fetch).toHaveBeenCalledWith(
      "/api/llm/providers/7",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});
