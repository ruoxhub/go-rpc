// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsClient } from "./_components/SettingsClient";
import { ProviderForm } from "./_components/ProviderManager/components/ProviderForm";
import type { LlmModel, LlmProvider, SettingsResponse } from "./utils/settings-types";

const provider: LlmProvider = {
  id: 7,
  name: "Anthropic",
  litellm_prefix: "anthropic",
  protocol: "claude",
  base_url: "https://api.anthropic.com",
  enabled: true,
  api_key_configured: true,
  api_key_masked: "********1234",
  last_sync_status: null,
  last_sync_at: null,
  last_sync_error: null,
  created_at: "2026-08-03T00:00:00Z",
  updated_at: "2026-08-03T00:00:00Z",
};

const analysisModel: LlmModel = {
  id: 11,
  provider_id: provider.id,
  remote_model_id: "claude-sonnet-4-5",
  litellm_model: "anthropic/claude-sonnet-4-5",
  display_name: "Claude Sonnet 4.5",
  enabled: true,
  remote_available: true,
  last_discovered_at: "2026-08-03T00:00:00Z",
};

const transcriptionModel: LlmModel = {
  ...analysisModel,
  id: 12,
  remote_model_id: "whisper-large-v3",
  litellm_model: "anthropic/whisper-large-v3",
  display_name: "Whisper Large V3",
};

const openAiProvider: LlmProvider = {
  ...provider,
  id: 8,
  name: "OpenAI",
  litellm_prefix: "openai",
  protocol: "openai-completion",
};

const openAiModel: LlmModel = {
  ...analysisModel,
  id: 21,
  provider_id: openAiProvider.id,
  remote_model_id: "gpt-5",
  litellm_model: "openai/gpt-5",
  display_name: "GPT-5",
};

const settings: SettingsResponse = {
  llm: { default_analysis_model_id: null, default_transcription_model_id: null, max_tokens: 2048, temperature: 0.3, enable_thinking: false },
  scheduler: { timezone: "Asia/Shanghai", worker_id: "worker-1", poll_interval_ms: 1000, default_loop_interval_seconds: 60, batch_size: 10, zombie_reap_after_seconds: 300, graceful_shutdown_seconds: 15, inactive_fields: ["worker_id", "batch_size", "graceful_shutdown_seconds"] },
  rpc: { base_url: "http://127.0.0.1:8090", timeout_seconds: 30 },
  analysis_video: { is_base64: false, frame_sampling_strategy: "scene_guided", max_frames: 32, frame_interval_seconds: 5, frame_timestamps: [] },
  proxy: { url_configured: true, target: "http://proxy.example.com:8080" },
  cleaner: { enabled: true, poll_interval: 30, batch_size: 20, max_batches_per_platform: 3, ttl_days: 7, watermark_key: "cleaner:watermark", suspect_seconds: 120, inactive_fields: ["poll_interval", "watermark_key"] },
  platforms: [
    { platform: "tiktok", configured: true, policy: { p1: [{ max_hours: 24, min_views: 100 }], p2: [], p3: [], filters: [{ field: "extend_data.aigcLabelType", operator: ">", value: 0 }] } },
    { platform: "douyin", configured: true, policy: { p1: [{ max_hours: 12, min_views: 50 }], p2: [], p3: [], filters: [] } },
  ],
};

afterEach(cleanup);
beforeEach(() => vi.restoreAllMocks());

describe("系统设置", () => {
  it("保存 analysis.video 的抽帧与传输配置", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(settings.analysis_video));
    render(<SettingsClient initialSettings={settings} initialModels={[analysisModel]} />);

    fireEvent.click(screen.getByRole("tab", { name: "媒体" }));
    fireEvent.change(screen.getByLabelText("抽帧策略"), { target: { value: "timestamps" } });
    fireEvent.change(screen.getByLabelText("最大帧数"), { target: { value: "64" } });
    fireEvent.change(screen.getByLabelText("抽帧间隔（秒）"), { target: { value: "2.5" } });
    fireEvent.change(screen.getByLabelText("抽帧时间戳"), { target: { value: "1, 2.5 4" } });
    fireEvent.click(screen.getByRole("button", { name: "保存视频分析配置" }));

    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({
      is_base64: false,
      frame_sampling_strategy: "timestamps",
      max_frames: 64,
      frame_interval_seconds: 2.5,
      frame_timestamps: [1, 2.5, 4],
    });
  }, 10_000);

  it("停用的 Provider 加载模型后不提供默认模型选项", async () => {
    const disabledProvider = { ...provider, enabled: false };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json([analysisModel]));

    render(
      <SettingsClient
        initialSettings={settings}
        initialProviders={[disabledProvider]}
        initialModels={[analysisModel]}
      />,
    );

    await screen.findByRole("button", { name: "停用模型" });
    await waitFor(() => {
      expect(screen.queryAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(0);
    });
  });

  it("停用 Provider 后忽略仍在途的模型加载结果", async () => {
    let resolveModels: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) {
        return new Promise((resolve) => { resolveModels = resolve; });
      }
      return Response.json({ ...provider, enabled: false });
    });

    render(
      <SettingsClient
        initialSettings={settings}
        initialProviders={[provider]}
        initialModels={[analysisModel]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "停用提供商" }));
    await screen.findByRole("button", { name: "启用提供商" });
    expect(screen.queryAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(0);

    await act(async () => {
      resolveModels?.(Response.json([analysisModel]));
    });
    await waitFor(() => {
      expect(screen.queryAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(0);
    });
  });

  it("保存默认分析与转写模型 ID，并允许清空默认值", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({
      ...settings.llm,
      default_analysis_model_id: analysisModel.id,
      default_transcription_model_id: null,
    }));

    render(
      <SettingsClient
        initialSettings={settings}
        initialModels={[analysisModel, transcriptionModel]}
      />,
    );
    fireEvent.change(screen.getByLabelText("默认分析模型"), { target: { value: String(analysisModel.id) } });
    fireEvent.change(screen.getByLabelText("默认转写模型"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));

    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({
      default_analysis_model_id: analysisModel.id,
      default_transcription_model_id: null,
      max_tokens: 2048,
      temperature: 0.3,
      enable_thinking: false,
    });
  });

  it("仅修改生成参数时保留已不可用的默认模型 ID", async () => {
    const unavailable = { ...analysisModel, id: 13, enabled: false };
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({
      ...settings.llm,
      default_analysis_model_id: unavailable.id,
      default_transcription_model_id: unavailable.id,
      max_tokens: 4096,
    }));
    render(
      <SettingsClient
        initialSettings={{ ...settings, llm: { ...settings.llm, default_analysis_model_id: unavailable.id, default_transcription_model_id: unavailable.id } }}
        initialModelCatalog={[unavailable]}
      />,
    );

    expect(screen.getAllByRole("option", { name: "Claude Sonnet 4.5（当前模型已不可用）" })).toHaveLength(2);
    expect((screen.getByLabelText("默认分析模型") as HTMLSelectElement).value).toBe(String(unavailable.id));
    fireEvent.change(screen.getByLabelText("最大 Token 数"), { target: { value: "4096" } });
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));

    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toMatchObject({
      default_analysis_model_id: unavailable.id,
      default_transcription_model_id: unavailable.id,
      max_tokens: 4096,
    });
  });

  it("保存新同步模型并停用后继续保留最新模型 ID 和名称", async () => {
    let modelLoads = 0;
    const llmBodies: Array<Record<string, unknown>> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) {
        modelLoads += 1;
        return Response.json(modelLoads === 1 ? [] : [analysisModel]);
      }
      if (url.endsWith("/sync-models")) {
        return Response.json({ created: 1, updated: 0, unavailable: 0, status: "success", synced_at: "2026-08-03T00:00:00Z" });
      }
      if (url.endsWith("/models/11/disable")) return Response.json({ ...analysisModel, enabled: false });
      if (url.endsWith("/api/settings/llm") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        llmBodies.push(body);
        return Response.json({ ...settings.llm, ...body });
      }
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    fireEvent.click(screen.getByRole("button", { name: "同步模型" }));
    expect(await screen.findAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("默认分析模型"), { target: { value: String(analysisModel.id) } });
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
    await waitFor(() => expect(llmBodies).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "停用模型" }));
    expect(await screen.findByRole("option", { name: "Claude Sonnet 4.5（当前模型已不可用）" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("最大 Token 数"), { target: { value: "4096" } });
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));

    await waitFor(() => expect(llmBodies).toHaveLength(2));
    expect(llmBodies[1]).toMatchObject({ default_analysis_model_id: analysisModel.id, max_tokens: 4096 });
  });

  it("模型目录部分加载失败时显示不完整提示", () => {
    render(<SettingsClient initialSettings={settings} modelCatalogIncomplete />);
    expect(screen.getByRole("status").textContent).toBe("部分模型目录加载失败，当前选项可能不完整。");
  });

  it("切换 Provider 后停用结果只更新请求发起时的 Provider 模型", async () => {
    let resolveDisable: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/7/models?status=all")) return Response.json([analysisModel]);
      if (url.endsWith("/8/models?status=all")) return Response.json([openAiModel]);
      return new Promise((resolve) => { resolveDisable = resolve; });
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider, openAiProvider]} initialModels={[analysisModel, openAiModel]} />);
    await screen.findByRole("button", { name: "停用模型" });
    fireEvent.click(screen.getByRole("button", { name: "停用提供商" }));
    fireEvent.click(screen.getByRole("button", { name: /OpenAI/ }));
    await screen.findByRole("button", { name: "停用模型" });

    await act(async () => { resolveDisable?.(Response.json({ ...provider, enabled: false })); });
    expect(screen.queryAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(0);
    expect(screen.getAllByRole("option", { name: "GPT-5" })).toHaveLength(2);
  });

  it("切换 Provider 后模型启停结果不覆盖当前 Provider 快照", async () => {
    let resolveModelToggle: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/7/models?status=all")) return Response.json([analysisModel]);
      if (url.endsWith("/8/models?status=all")) return Response.json([openAiModel]);
      return new Promise((resolve) => { resolveModelToggle = resolve; });
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider, openAiProvider]} initialModels={[analysisModel, openAiModel]} />);
    fireEvent.click(await screen.findByRole("button", { name: "停用模型" }));
    expect(screen.getByRole("button", { name: "停用模型" }).querySelector("svg")?.classList.contains("motion-reduce:animate-none")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /OpenAI/ }));
    await screen.findByRole("button", { name: "停用模型" });

    await act(async () => { resolveModelToggle?.(Response.json({ ...analysisModel, enabled: false })); });
    expect(screen.queryAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(0);
    expect(screen.getAllByRole("option", { name: "GPT-5" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "停用模型" })).toBeTruthy();
  });
  it("同步模型后显示刷新的模型目录", async () => {
    let resolveSync: ((response: Response) => void) | undefined;
    let modelRequests = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/sync-models")) {
        return new Promise((resolve) => { resolveSync = resolve; });
      }
      modelRequests += 1;
      if (modelRequests === 1) return Response.json([]);
      return Response.json([{
        id: 11,
        provider_id: provider.id,
        remote_model_id: "claude-sonnet-4-5",
        litellm_model: "anthropic/claude-sonnet-4-5",
        display_name: "Claude Sonnet 4.5",
        enabled: true,
        remote_available: true,
        last_discovered_at: "2026-08-03T00:00:00Z",
      }]);
    });

    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    fireEvent.click(screen.getByRole("button", { name: "同步模型" }));
    const syncButton = screen.getByRole("button", { name: "同步模型" });
    expect((syncButton as HTMLButtonElement).disabled).toBe(true);
    expect(syncButton.querySelector("svg")?.classList.contains("motion-reduce:animate-none")).toBe(true);
    resolveSync?.(Response.json({ created: 1, updated: 0, unavailable: 0, status: "success", synced_at: "2026-08-03T00:00:00Z" }));
    expect((await screen.findAllByText("Claude Sonnet 4.5")).length).toBeGreaterThan(0);
  });

  it("快速切换提供商时忽略旧同步结果", async () => {
    const secondProvider: LlmProvider = { ...provider, id: 8, name: "OpenAI", litellm_prefix: "openai", protocol: "openai-completion" };
    let resolveSync: ((response: Response) => void) | undefined;
    let firstProviderModelRequests = 0;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/7/sync-models")) return new Promise((resolve) => { resolveSync = resolve; });
      if (url.includes("/7/models")) {
        firstProviderModelRequests += 1;
        return Response.json([]);
      }
      if (url.includes("/8/models")) return Response.json([{
        id: 12,
        provider_id: 8,
        remote_model_id: "gpt-5",
        litellm_model: "openai/gpt-5",
        display_name: "GPT-5",
        enabled: true,
        remote_available: true,
        last_discovered_at: "2026-08-03T00:00:00Z",
      }]);
      return Response.json({ created: 0, updated: 0, unavailable: 0, status: "success", synced_at: "2026-08-03T00:00:00Z" });
    });

    render(<SettingsClient initialSettings={settings} initialProviders={[provider, secondProvider]} />);
    await screen.findByText("暂无模型，请先同步。");
    fireEvent.click(screen.getByRole("button", { name: "同步模型" }));
    fireEvent.click(screen.getByRole("button", { name: /OpenAI/ }));
    expect((await screen.findAllByText("GPT-5")).length).toBeGreaterThan(0);
    resolveSync?.(Response.json({ created: 1, updated: 0, unavailable: 0, status: "success", synced_at: "2026-08-03T00:00:00Z" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "同步模型" }) as HTMLButtonElement).disabled).toBe(false));
    expect(request).toHaveBeenCalledWith("/api/llm/providers/8/models?status=all", expect.anything());
    expect(firstProviderModelRequests).toBe(1);
    expect(screen.getAllByText("GPT-5").length).toBeGreaterThan(0);
  });

  it("快速切换提供商时忽略旧模型加载结果", async () => {
    const secondProvider: LlmProvider = { ...provider, id: 8, name: "OpenAI", litellm_prefix: "openai", protocol: "openai-completion" };
    let resolveFirstModels: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/7/models")) return new Promise((resolve) => { resolveFirstModels = resolve; });
      return Response.json([{
        id: 12,
        provider_id: 8,
        remote_model_id: "gpt-5",
        litellm_model: "openai/gpt-5",
        display_name: "GPT-5",
        enabled: true,
        remote_available: true,
        last_discovered_at: "2026-08-03T00:00:00Z",
      }]);
    });

    render(<SettingsClient initialSettings={settings} initialProviders={[provider, secondProvider]} />);
    fireEvent.click(screen.getByRole("button", { name: /OpenAI/ }));
    expect((await screen.findAllByText("GPT-5")).length).toBeGreaterThan(0);
    await act(async () => {
      resolveFirstModels?.(Response.json([{
        id: 11,
        provider_id: 7,
        remote_model_id: "claude-sonnet-4-5",
        litellm_model: "anthropic/claude-sonnet-4-5",
        display_name: "Claude Sonnet 4.5",
        enabled: true,
        remote_available: true,
        last_discovered_at: "2026-08-03T00:00:00Z",
      }]));
    });
    expect(screen.queryAllByText("Claude Sonnet 4.5")).toHaveLength(0);
    expect(screen.getAllByText("GPT-5").length).toBeGreaterThan(0);
  });

  it("编辑提供商时不回显已保存的 API Key", () => {
    render(<ProviderForm provider={provider} onSubmit={vi.fn()} />);
    expect((screen.getByLabelText("API Key") as HTMLInputElement).value).toBe("");
    expect(screen.getByText("已配置：********1234")).toBeTruthy();
  });

  it("只提供五种请求格式且不允许编辑 LiteLLM 前缀", () => {
    render(<ProviderForm onSubmit={vi.fn()} />);
    const format = screen.getByLabelText("请求格式") as HTMLSelectElement;
    expect([...format.options].map((option) => option.value)).toEqual([
      "openai-completion",
      "claude",
      "gemini",
      "deepseek",
      "openai-responses",
    ]);
    expect(format.value).toBe("openai-completion");
    expect(screen.queryByLabelText("LiteLLM 前缀")).toBeNull();
  });

  it("请求格式变化时阻止空密钥 PATCH，并在输入密钥后提交精确请求体", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/models?status=all")) return Response.json([]);
      if (init?.method === "PATCH") return Response.json({ ...provider, protocol: "openai-responses" });
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    const format = screen.getByLabelText("请求格式") as HTMLSelectElement;
    const key = screen.getByLabelText("API Key") as HTMLInputElement;

    fireEvent.change(format, { target: { value: "openai-responses" } });
    expect(key.required).toBe(true);
    expect(screen.getByText("目标或请求格式变化，需重新输入 API Key。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));
    expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(0);

    fireEvent.change(format, { target: { value: provider.protocol } });
    expect(key.required).toBe(false);
    expect(document.getElementById("provider-api-key-hint")?.textContent).toBe("已配置；留空将保留当前值。");

    fireEvent.change(format, { target: { value: "openai-responses" } });
    fireEvent.change(key, { target: { value: "new-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));

    await waitFor(() => expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(1));
    const patch = request.mock.calls.find(([, options]) => options?.method === "PATCH");
    expect(patch?.[0]).toBe("/api/llm/providers/7");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      name: "Anthropic",
      protocol: "openai-responses",
      base_url: "https://api.anthropic.com",
      api_key: "new-secret",
    });
  });

  it("Base URL authority 变化时阻止空密钥 PATCH，切回原值后恢复提示", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/models?status=all")) return Response.json([]);
      if (init?.method === "PATCH") return Response.json({ ...provider, base_url: "https://gateway.example.com/v1" });
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    const baseUrl = screen.getByLabelText("服务地址", { selector: "#provider-base-url" }) as HTMLInputElement;
    const key = screen.getByLabelText("API Key") as HTMLInputElement;

    fireEvent.change(baseUrl, { target: { value: "https://" } });
    expect(key.required).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));
    expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(0);

    fireEvent.change(baseUrl, { target: { value: "https://api.anthropic.com/v2" } });
    expect(key.required).toBe(false);

    for (const target of [
      "http://api.anthropic.com/v1",
      "https://gateway.example.com/v1",
      "https://api.anthropic.com:8443/v1",
    ]) {
      fireEvent.change(baseUrl, { target: { value: target } });
      expect(key.required).toBe(true);
    }

    fireEvent.change(baseUrl, { target: { value: "https://gateway.example.com/v1" } });
    expect(screen.getByText("目标或请求格式变化，需重新输入 API Key。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));
    expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(0);

    fireEvent.change(baseUrl, { target: { value: provider.base_url } });
    expect(key.required).toBe(false);
    expect(document.getElementById("provider-api-key-hint")?.textContent).toBe("已配置；留空将保留当前值。");

    fireEvent.change(baseUrl, { target: { value: "https://gateway.example.com/v1" } });
    fireEvent.change(key, { target: { value: "replacement-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));

    await waitFor(() => expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(1));
    const patch = request.mock.calls.find(([, options]) => options?.method === "PATCH");
    expect(patch?.[0]).toBe("/api/llm/providers/7");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      name: "Anthropic",
      protocol: "claude",
      base_url: "https://gateway.example.com/v1",
      api_key: "replacement-secret",
    });
  });

  it("只修改同 authority 路径时允许空密钥 PATCH 且不提交密钥", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/models?status=all")) return Response.json([]);
      if (init?.method === "PATCH") return Response.json({ ...provider, base_url: "https://api.anthropic.com/v2" });
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    fireEvent.change(screen.getByLabelText("服务地址", { selector: "#provider-base-url" }), {
      target: { value: "https://api.anthropic.com/v2" },
    });
    expect((screen.getByLabelText("API Key") as HTMLInputElement).required).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));

    await waitFor(() => expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(1));
    const patch = request.mock.calls.find(([, options]) => options?.method === "PATCH");
    expect(patch?.[0]).toBe("/api/llm/providers/7");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      name: "Anthropic",
      protocol: "claude",
      base_url: "https://api.anthropic.com/v2",
    });
  });

  it("模型提供商操作提供移动触控目标和显式加载状态", async () => {
    let resolveSave: (() => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json([]));
    const save = new Promise<void>((resolve) => { resolveSave = resolve; });
    render(<ProviderForm provider={provider} onSubmit={() => save} />);

    const saveButton = screen.getByRole("button", { name: "保存提供商" });
    expect(saveButton.className).toContain("touch-target");
    fireEvent.click(saveButton);
    expect(saveButton.getAttribute("aria-busy")).toBe("true");
    expect(saveButton.querySelector("svg")?.classList.contains("motion-reduce:animate-none")).toBe(true);

    resolveSave?.();
    await waitFor(() => expect(saveButton.getAttribute("aria-busy")).toBe("false"));

    cleanup();
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    for (const name of ["新增提供商", "停用提供商", "同步模型", "删除"]) {
      expect(screen.getByRole("button", { name }).className).toContain("touch-target");
    }
  });

  it("保存提供商期间锁定表单、导航和相关操作，并采用服务端返回值", async () => {
    let resolveSave: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) return Response.json([]);
      if (init?.method === "PATCH") return new Promise((resolve) => { resolveSave = resolve; });
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    fireEvent.change(screen.getByLabelText("提供商名称"), { target: { value: "草稿名称" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));

    for (const id of ["provider-name", "provider-protocol", "provider-base-url", "provider-api-key"]) {
      expect((document.getElementById(id) as HTMLInputElement | HTMLSelectElement).disabled).toBe(true);
    }
    expect((screen.getByRole("button", { name: "新增提供商" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Anthropic/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "同步模型" }) as HTMLButtonElement).disabled).toBe(true);

    resolveSave?.(Response.json({ ...provider, name: "服务端名称", updated_at: "2026-08-03T01:00:00Z" }));
    expect(await screen.findByRole("button", { name: /服务端名称/ })).toBeTruthy();
    expect((screen.getByRole("button", { name: "新增提供商" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("将 Provider 422 错误关联到对应字段并保留输入", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) return Response.json([]);
      if (init?.method === "PATCH") return Response.json({ detail: [{ loc: ["body", "name"], msg: "提供商名称已存在" }] }, { status: 422 });
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    await screen.findByText("暂无模型，请先同步。");
    const name = screen.getByLabelText("提供商名称") as HTMLInputElement;
    fireEvent.change(name, { target: { value: "重复名称" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提供商" }));
    const error = await screen.findByText("提供商名称已存在");
    expect(error.getAttribute("role")).toBe("alert");
    expect(name.getAttribute("aria-describedby")).toContain(error.id);
    expect(name.value).toBe("重复名称");
  });

  it("支持停用模型并通过确认对话框删除提供商", async () => {
    let resolveDelete: ((response: Response) => void) | undefined;
    const model = {
      id: 11,
      provider_id: provider.id,
      remote_model_id: "claude-sonnet-4-5",
      litellm_model: "anthropic/claude-sonnet-4-5",
      display_name: "Claude Sonnet 4.5",
      enabled: true,
      remote_available: true,
      last_discovered_at: "2026-08-03T00:00:00Z",
    };
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) return Response.json([model]);
      if (url.endsWith("/models/11/disable")) return Response.json({ ...model, enabled: false });
      if (init?.method === "DELETE") return new Promise((resolve) => { resolveDelete = resolve; });
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider, openAiProvider]} />);
    expect(await screen.findAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(2);
    fireEvent.click(await screen.findByRole("button", { name: "停用模型" }));
    expect(await screen.findByRole("button", { name: "启用模型" })).toBeTruthy();
    expect(screen.queryAllByRole("option", { name: "Claude Sonnet 4.5" })).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "删除提供商" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("/api/llm/providers/7", expect.objectContaining({ method: "DELETE" })));
    expect(screen.getByRole("button", { name: "删除提供商" }).querySelector("svg")?.classList.contains("motion-reduce:animate-none")).toBe(true);
    const otherProvider = screen.getByRole("button", { name: /OpenAI/ });
    expect((otherProvider as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(otherProvider);
    expect(screen.getByText("确认删除“Anthropic”？被设置或任务引用时无法删除。")).toBeTruthy();
    resolveDelete?.(new Response(null, { status: 204 }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: /OpenAI/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("远端不可用但仍启用的模型允许停用", async () => {
    const unavailableModel = {
      id: 13,
      provider_id: provider.id,
      remote_model_id: "legacy-model",
      litellm_model: "anthropic/legacy-model",
      display_name: "Legacy Model",
      enabled: true,
      remote_available: false,
      last_discovered_at: "2026-08-03T00:00:00Z",
    };
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) return Response.json([unavailableModel]);
      return Response.json({ ...unavailableModel, enabled: false });
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    const disable = await screen.findByRole("button", { name: "停用模型" });
    expect((disable as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(disable);
    await waitFor(() => expect(request).toHaveBeenCalledWith("/api/llm/providers/models/13/disable", expect.objectContaining({ method: "POST" })));
  });

  it("并发启停模型时分别保留各自的加载状态", async () => {
    const models = [11, 12].map((id) => ({
      id,
      provider_id: provider.id,
      remote_model_id: `model-${id}`,
      litellm_model: `anthropic/model-${id}`,
      display_name: `Model ${id}`,
      enabled: true,
      remote_available: true,
      last_discovered_at: "2026-08-03T00:00:00Z",
    }));
    let resolveFirst: ((response: Response) => void) | undefined;
    let resolveSecond: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) return Response.json(models);
      if (url.endsWith("/models/11/disable")) return new Promise((resolve) => { resolveFirst = resolve; });
      return new Promise((resolve) => { resolveSecond = resolve; });
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    const disableButtons = await screen.findAllByRole("button", { name: "停用模型" });
    fireEvent.click(disableButtons[0]!);
    fireEvent.click(disableButtons[1]!);
    expect(disableButtons.every((button) => (button as HTMLButtonElement).disabled)).toBe(true);

    resolveFirst?.(Response.json({ ...models[0], enabled: false }));
    expect(await screen.findByRole("button", { name: "启用模型" })).toBeTruthy();
    const stillPending = screen.getByRole("button", { name: "停用模型" }) as HTMLButtonElement;
    expect(stillPending.disabled).toBe(true);

    resolveSecond?.(Response.json({ ...models[1], enabled: false }));
    await waitFor(() => expect(screen.getAllByRole("button", { name: "启用模型" })).toHaveLength(2));
  });

  it("提供五个可访问页签并按职责切换配置卡", () => {
    render(<SettingsClient initialSettings={settings} />);
    expect(screen.getAllByRole("tab")).toHaveLength(5);
    expect(screen.getByRole("tab", { name: "AI" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "调度与调用" }));
    expect(screen.getByRole("heading", { name: "调度器" })).toBeTruthy();
    expect(screen.getAllByText("当前未接入")).toHaveLength(5);
  });

  it("保存调度器时区并提示 Cron 计划会重算", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(settings.scheduler));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "调度与调用" }));
    expect(screen.getByText("保存后会按新时区重新计算未运行的 Cron 任务")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("时区"), { target: { value: "UTC" } });
    fireEvent.click(screen.getByRole("button", { name: "保存调度器配置" }));
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toMatchObject({ timezone: "UTC" });
  });

  it("清洗兼容字段显示未接入且不可编辑", () => {
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    for (const label of ["轮询间隔（秒）", "水位线 Key"]) {
      const input = screen.getByLabelText(label) as HTMLInputElement;
      expect(input.disabled).toBe(true);
      expect(input.getAttribute("aria-describedby")).toBeTruthy();
    }
    expect(screen.getAllByText("当前未接入").length).toBeGreaterThanOrEqual(2);
  });

  it("切换页签保留未保存草稿", () => {
    render(<SettingsClient initialSettings={settings} initialModels={[analysisModel, transcriptionModel]} />);
    fireEvent.change(screen.getByLabelText("默认分析模型"), { target: { value: String(analysisModel.id) } });
    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    fireEvent.click(screen.getByRole("tab", { name: "AI" }));
    expect((screen.getByLabelText("默认分析模型") as HTMLSelectElement).value).toBe(String(analysisModel.id));
  });

  it("媒体页签只展示视频分析卡", () => {
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "媒体" }));
    expect(screen.getByRole("heading", { name: "视频分析" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "模型提供商" })).toBeNull();
  });

  it("支持方向键和 Home End 的 roving tabs 键盘操作", () => {
    render(<SettingsClient initialSettings={settings} />);
    const ai = screen.getByRole("tab", { name: "AI" });
    ai.focus();
    fireEvent.keyDown(ai, { key: "ArrowRight" });
    const media = screen.getByRole("tab", { name: "媒体" });
    expect(document.activeElement).toBe(media);
    expect(media.getAttribute("tabindex")).toBe("0");
    fireEvent.keyDown(media, { key: "ArrowRight" });
    const scheduler = screen.getByRole("tab", { name: "调度与调用" });
    expect(document.activeElement).toBe(scheduler);
    expect(scheduler.getAttribute("tabindex")).toBe("0");
    fireEvent.keyDown(scheduler, { key: "End" });
    const cleaner = screen.getByRole("tab", { name: "清洗" });
    expect(document.activeElement).toBe(cleaner);
    fireEvent.keyDown(cleaner, { key: "Home" });
    expect(document.activeElement).toBe(ai);
  });

  it("每张卡独立保存且保存中保留文案", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise((resolve) => { resolveRequest = resolve; }));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.change(screen.getByLabelText("最大 Token 数"), { target: { value: "4096" } });
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
    expect((screen.getByRole("button", { name: "保存模型配置" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "媒体" }));
    expect((screen.getByRole("button", { name: "保存视频分析配置" }) as HTMLButtonElement).disabled).toBe(false);
    const [, init] = request.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toMatchObject({ max_tokens: 4096 });
    resolveRequest?.(Response.json({ ...settings.llm, max_tokens: 4096 }));
    expect(await screen.findByText("设置已保存")).toBeTruthy();
  });

  it("显示 422 字段错误并保留草稿", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ detail: [{ loc: ["body", "max_tokens"], msg: "Token 数无效" }] }, { status: 422 }));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.change(screen.getByLabelText("最大 Token 数"), { target: { value: "4096" } });
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
    const error = await screen.findByText("Token 数无效");
    expect(error.getAttribute("role")).toBe("alert");
    expect(screen.getByLabelText("最大 Token 数").getAttribute("aria-describedby")).toContain(error.id);
    expect((screen.getByLabelText("最大 Token 数") as HTMLInputElement).value).toBe("4096");
  });

  it("代理卡显示脱敏目标并允许留空保留", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(settings.proxy));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    expect(screen.getByText((text) => text.includes("http://proxy.example.com:8080"))).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存代理配置" }));
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({});
  });

  it("未配置代理显示填写提示", () => {
    render(<SettingsClient initialSettings={{ ...settings, proxy: { url_configured: false, target: "" } }} />);
    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    expect(screen.getByText("尚未配置；填写后保存。")).toBeTruthy();
  });

  it("首次保存代理敏感值后刷新状态并清空输入", async () => {
    const initial = { ...settings, proxy: { url_configured: false, target: "" } };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ url_configured: true, target: "http://new.proxy:8080" }));
    render(<SettingsClient initialSettings={initial} />);

    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    fireEvent.change(screen.getByLabelText("代理 URL"), { target: { value: "http://user:pass@new.proxy:8080" } });
    fireEvent.click(screen.getByRole("button", { name: "保存代理配置" }));
    expect(await screen.findByText((text) => text.includes("http://new.proxy:8080"))).toBeTruthy();
    expect((screen.getByLabelText("代理 URL") as HTMLInputElement).value).toBe("");
  });

  it("服务端 detail 不直接展示，使用国际化通用错误", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ detail: "internal redis host leaked" }, { status: 500 }));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
    expect((await screen.findByRole("alert")).textContent).toBe("保存失败，请稍后重试。");
    expect(screen.queryByText("internal redis host leaked")).toBeNull();
  });

  it("编辑并保存类型化 AIGC、数组、布尔值与 exists 过滤条件", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const policy = JSON.parse(String(init?.body));
      return Response.json({ platform: "tiktok", configured: true, policy });
    });
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    expect((screen.getByLabelText("字段 1") as HTMLInputElement).value).toBe("extend_data.aigcLabelType");
    expect((screen.getByLabelText("值 1") as HTMLInputElement).value).toBe("0");

    fireEvent.click(screen.getByRole("button", { name: "添加过滤条件" }));
    fireEvent.change(screen.getByLabelText("字段 2"), { target: { value: "extend_data.tags" } });
    fireEvent.change(screen.getByLabelText("运算符 2"), { target: { value: "in" } });
    fireEvent.change(screen.getByLabelText("值类型 2"), { target: { value: "boolean" } });
    fireEvent.change(screen.getByLabelText("值 2"), { target: { value: "true, false" } });
    fireEvent.click(screen.getByRole("button", { name: "添加过滤条件" }));
    fireEvent.change(screen.getByLabelText("字段 3"), { target: { value: "extend_data.cover" } });
    fireEvent.change(screen.getByLabelText("运算符 3"), { target: { value: "exists" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));

    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    const body = JSON.parse(String(request.mock.calls[0]?.[1]?.body));
    expect(body.filters).toEqual([
      { field: "extend_data.aigcLabelType", operator: ">", value: 0 },
      { field: "extend_data.tags", operator: "in", value: [true, false] },
      { field: "extend_data.cover", operator: "exists", value: null },
    ]);
  });

  it("增删规则并在切换平台时支持取消和确认丢弃草稿", () => {
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.click(screen.getByRole("button", { name: "添加评级规则" }));
    expect(screen.getByLabelText("P1 最大小时数 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "删除 P1 2" }));
    fireEvent.change(screen.getByLabelText("P1 最少播放量 1"), { target: { value: "999" } });
    fireEvent.change(screen.getByLabelText("平台"), { target: { value: "douyin" } });
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect((screen.getByLabelText("平台") as HTMLSelectElement).value).toBe("tiktok");
    fireEvent.change(screen.getByLabelText("平台"), { target: { value: "douyin" } });
    fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));
    expect((screen.getByLabelText("平台") as HTMLSelectElement).value).toBe("douyin");
  });

  it("dirty 时保护清洗页签和 beforeunload，取消保留草稿", async () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.change(screen.getByLabelText("P1 最少播放量 1"), { target: { value: "321" } });
    expect(add).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    expect(screen.getByRole("tab", { name: "清洗" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect((screen.getByLabelText("P1 最少播放量 1") as HTMLInputElement).value).toBe("321");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("tab", { name: "清洗" })));
    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));
    expect(screen.getByRole("tab", { name: "网络" }).getAttribute("aria-selected")).toBe("true");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("tab", { name: "网络" })));
    expect(remove).toHaveBeenCalledWith("beforeunload", expect.any(Function));
  });

  it("平台策略保存失败和 422 字段错误不泄露服务端 detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ detail: [{ loc: ["body", "filters", 0, "value"], msg: "必须是有限数字" }] }, { status: 422 }));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.change(screen.getByLabelText("值 1"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    expect(await screen.findByText("必须是有限数字")).toBeTruthy();
    expect(screen.getAllByRole("alert").every((alert) => !alert.textContent?.includes("detail"))).toBe(true);
  });

  it("切换值类型会同步转换值，空 in 数组阻止保存", async () => {
    const request = vi.spyOn(globalThis, "fetch");
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.change(screen.getByLabelText("值类型 1"), { target: { value: "string" } });
    expect((screen.getByLabelText("值 1") as HTMLInputElement).value).toBe("0");
    fireEvent.change(screen.getByLabelText("值类型 1"), { target: { value: "boolean" } });
    expect((screen.getByLabelText("值 1") as HTMLSelectElement).value).toBe("false");
    fireEvent.change(screen.getByLabelText("运算符 1"), { target: { value: "in" } });
    fireEvent.change(screen.getByLabelText("值 1"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    expect(await screen.findByText("数组至少需要一项。")).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });

  it("本地关联评级约束错误并展示配置状态与 AND 说明", async () => {
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === "策略状态：已配置")).toBeTruthy();
    expect(screen.getByText("所有过滤条件按 AND 同时生效。")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("P1 最大小时数 1"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("P1 最少播放量 1"), { target: { value: "-1" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    const maxError = await screen.findByText("最大小时数必须大于 0。");
    const minError = screen.getByText("最少播放量不能小于 0。");
    expect(screen.getByLabelText("P1 最大小时数 1").getAttribute("aria-describedby")).toContain(maxError.id);
    expect(screen.getByLabelText("P1 最少播放量 1").getAttribute("aria-describedby")).toContain(minError.id);
  });

  it("策略保存期间锁定编辑、平台与清洗页签切换", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise((resolve) => { resolveRequest = resolve; }));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.change(screen.getByLabelText("值 1"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    expect(screen.getByLabelText("值 1").matches(":disabled")).toBe(true);
    expect(screen.getByLabelText("平台").matches(":disabled")).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "网络" }));
    expect(screen.getByRole("tab", { name: "清洗" }).getAttribute("aria-selected")).toBe("true");
    resolveRequest?.(Response.json({ platform: "tiktok", configured: true, policy: { ...settings.platforms[0]!.policy, filters: [{ field: "extend_data.aigcLabelType", operator: ">", value: 2 }] } }));
    expect(await screen.findByText("设置已保存")).toBeTruthy();
  });

  it("评级数字保留自然输入并在提交时严格解析", async () => {
    const request = vi.spyOn(globalThis, "fetch");
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.change(screen.getByLabelText("P1 最大小时数 1"), { target: { value: "" } });
    expect((screen.getByLabelText("P1 最大小时数 1") as HTMLInputElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("P1 最少播放量 1"), { target: { value: "-" } });
    expect((screen.getByLabelText("P1 最少播放量 1") as HTMLInputElement).value).toBe("-");
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    expect(await screen.findByText("最大小时数必须大于 0。")).toBeTruthy();
    expect(screen.getByText("最少播放量不能小于 0。")).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });

  it("严格校验 ISO 日期并接受合法格式", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => Response.json({ platform: "tiktok", configured: true, policy: JSON.parse(String(init?.body)) }));
    render(<SettingsClient initialSettings={settings} />);
    fireEvent.click(screen.getByRole("tab", { name: "清洗" }));
    fireEvent.change(screen.getByLabelText("字段 1"), { target: { value: "pub_time" } });
    fireEvent.change(screen.getByLabelText("值 1"), { target: { value: "01/02/2024" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    expect(await screen.findByText("请输入有效的 ISO 日期时间。")).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("值 1"), { target: { value: "0000-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    expect(await screen.findByText("请输入有效的 ISO 日期时间。")).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("值 1"), { target: { value: "2024-01-02T03:04:05+08:00" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 tiktok 策略" }));
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
  });

  it("模型目录支持按关键字过滤模型列表与展示统计", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/models?status=all")) return Response.json([analysisModel, transcriptionModel]);
      return Response.json(provider);
    });
    render(<SettingsClient initialSettings={settings} initialProviders={[provider]} />);
    expect(await screen.findByText("共 2 个模型，已启用 2 个")).toBeTruthy();
    const list = screen.getByRole("list");
    expect(within(list).getByText("Claude Sonnet 4.5")).toBeTruthy();
    expect(within(list).getByText("Whisper Large V3")).toBeTruthy();

    const searchInput = screen.getByPlaceholderText("搜索模型名称或标识...");
    fireEvent.change(searchInput, { target: { value: "whisper" } });
    expect(within(list).queryByText("Claude Sonnet 4.5")).toBeNull();
    expect(within(list).getByText("Whisper Large V3")).toBeTruthy();

    fireEvent.change(searchInput, { target: { value: "not-exist" } });
    expect(screen.getByText("未找到匹配的模型")).toBeTruthy();
  });
});
