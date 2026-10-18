// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Action, Platform, Task } from "../../../../../utils/crawler/crawler-types";
import { TaskForm } from ".";
import type { ScheduleFormValue } from "./types/schedule";
import { initialSchedule, scheduleSummary, taskPayload } from "./utils/taskForm";

const defaultSchedule: ScheduleFormValue = {
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

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const platform: Platform = {
  bs_id: 1,
  bs_name: "TikTok",
  bs_platform_code: "tiktok",
  bs_url: null,
  bs_remark: null,
  bs_status: "1",
  bs_concurrency: 1,
  bs_rps: 1,
  bs_burst: 3,
  bs_cooldown: 300,
};
const action: Action = {
  ba_id: 2,
  bs_id: 1,
  ba_action: "analyze",
  ba_desc: null,
  ba_params_schema: null,
  ba_api_url: null,
  ba_api_method: "POST",
  ba_enabled: true,
  ba_sample_safe: false,
  create_time: null,
  update_time: null,
};
const videoTask: Task = {
  task_id: 3,
  platform: "tiktok",
  action: "analyze",
  ba_id: 2,
  platform_id: 1,
  status: "paused",
  priority: "normal",
  attempts: 0,
  error_msg: null,
  last_run_at: null,
  loop_enabled: false,
  loop_interval_seconds: null,
  schedule_type: "manual",
  cron_expression: null,
  run_once_at: null,
  schedule_start_at: null,
  schedule_end_at: null,
  max_runs: null,
  next_run_at: null,
  run_count: 0,
  last_run_status: null,
  retry_max_attempts: 0,
  retry_delay_seconds: 60,
  retry_backoff_multiplier: 2,
  retry_max_delay_seconds: 3600,
  retry_count: 0,
  next_retry_at: null,
  run_now_requested_at: null,
  pause_requested: false,
  active_trigger: null,
  active_scheduled_at: null,
  config: {
    executor: "video_analysis",
    analysis: { llm_model_id: 17, review_route: "R" },
    source: null,
    sink: { mode: "auto" },
  },
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

function mockMetadata(models: unknown[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.includes("llm-models")) return Promise.resolve(Response.json({ llm_models: models }));
    if (url.includes("action-schemas")) return Promise.resolve(Response.json({ schema: [] }));
    return Promise.resolve(Response.json(videoTask));
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("任务分析模型", () => {
  beforeEach(() => push.mockReset());
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("只为视频分析任务显示可用模型覆盖", async () => {
    mockMetadata([{ id: 17, display_name: "Claude Sonnet", litellm_model: "anthropic/claude-sonnet" }]);
    render(<TaskForm mode="edit" task={{ ...videoTask, config: { ...videoTask.config!, analysis: { llm_model_id: null, review_route: null } } }} platforms={[platform]} actions={[action]} />);

    expect((await screen.findByLabelText("分析模型") as HTMLSelectElement).value).toBe("");
    expect(screen.getByRole("option", { name: "使用系统默认模型" })).toBeTruthy();

    cleanup();
    render(<TaskForm mode="edit" task={{ ...videoTask, config: { ...videoTask.config!, executor: "rpc_crawl", analysis: undefined } }} platforms={[platform]} actions={[action]} />);
    expect(screen.queryByLabelText("分析模型")).toBeNull();
  });

  it("历史模型不可用时禁止保存，显式重选默认后恢复", async () => {
    const fetch = mockMetadata([]);
    render(<TaskForm mode="edit" task={videoTask} platforms={[platform]} actions={[action]} />);

    expect(await screen.findByText("原模型已不可用，请重新选择")).toBeTruthy();
    const save = screen.getByRole("button", { name: "保存修改" });
    expect((save as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("分析模型"), { target: { value: "" } });
    expect((save as HTMLButtonElement).disabled).toBe(false);
    fireEvent.submit(save.closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/tasks"));
    const request = fetch.mock.calls.find(([url]) => String(url).endsWith("/tasks/3"));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
      llm_model_id: null,
    });
  });

  it("把选择的模型 id 作为数字提交", async () => {
    const fetch = mockMetadata([{ id: 29, display_name: "Gemini Pro", litellm_model: "gemini/gemini-pro" }]);
    render(<TaskForm mode="edit" task={{ ...videoTask, config: { ...videoTask.config!, analysis: { llm_model_id: null, review_route: null } } }} platforms={[platform]} actions={[action]} />);

    fireEvent.change(await screen.findByLabelText("分析模型"), { target: { value: "29" } });
    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/tasks"));
    const request = fetch.mock.calls.find(([url]) => String(url).endsWith("/tasks/3"));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
      executor: "video_analysis",
      llm_model_id: 29,
    });
  });

  it("模型目录加载期间禁止保存，完成后恢复", async () => {
    const modelsResponse = deferred<Response>();
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("llm-models")) return modelsResponse.promise;
      return Promise.resolve(Response.json({ schema: [] }));
    });
    render(<TaskForm mode="edit" task={videoTask} platforms={[platform]} actions={[action]} />);

    const save = screen.getByRole("button", { name: "保存修改" });
    expect((save as HTMLButtonElement).disabled).toBe(true);

    modelsResponse.resolve(Response.json({
      llm_models: [{ id: 17, display_name: "Claude Sonnet", litellm_model: "anthropic/claude-sonnet" }],
    }));
    await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(false));
  });

  it("模型目录失败时显示准确原因并允许重试恢复", async () => {
    let modelRequests = 0;
    const retryResponse = deferred<Response>();
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("llm-models")) {
        modelRequests += 1;
        return modelRequests === 1
          ? Promise.resolve(Response.json({ detail: "目录不可用" }, { status: 503 }))
          : retryResponse.promise;
      }
      return Promise.resolve(Response.json({ schema: [] }));
    });
    render(<TaskForm mode="edit" task={videoTask} platforms={[platform]} actions={[action]} />);

    expect(await screen.findByText("目录不可用")).toBeTruthy();
    expect(screen.queryByText("原模型已不可用，请重新选择")).toBeNull();
    const save = screen.getByRole("button", { name: "保存修改" });
    expect((save as HTMLButtonElement).disabled).toBe(true);

    const retry = screen.getByRole("button", { name: "重试加载模型" });
    fireEvent.click(retry);
    expect(retry.getAttribute("aria-busy")).toBe("true");
    expect(retry.className).toContain("touch-target");
    expect(retry.querySelector("svg")?.classList.contains("motion-reduce:animate-none")).toBe(true);
    retryResponse.resolve(Response.json({
      llm_models: [{ id: 17, display_name: "Claude Sonnet", litellm_model: "anthropic/claude-sonnet" }],
    }));

    await waitFor(() => expect(screen.queryByText("目录不可用")).toBeNull());
    expect(screen.queryByText("原模型已不可用，请重新选择")).toBeNull();
    expect((save as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("任务分析评审路线", () => {
  beforeEach(() => push.mockReset());
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("只为视频分析任务显示双语消息表提供的评审路线选项", () => {
    mockMetadata([]);
    render(<TaskForm mode="edit" task={videoTask} platforms={[platform]} actions={[action]} />);

    expect(screen.getByLabelText("评审路线")).toBeTruthy();
    expect(screen.getByRole("option", { name: "未知来源（仅评 C）" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "参考视频（R）" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "生成视频（G）" })).toBeTruthy();

    cleanup();
    render(<TaskForm mode="edit" task={{ ...videoTask, config: { ...videoTask.config!, executor: "rpc_crawl", analysis: undefined } }} platforms={[platform]} actions={[action]} />);
    expect(screen.queryByLabelText("评审路线")).toBeNull();
  });

  it.each([
    ["R", "R"],
    ["G", "G"],
    [null, ""],
  ] as const)("编辑模式恢复 %s 评审路线", (reviewRoute, expectedValue) => {
    mockMetadata([]);
    render(
      <TaskForm
        mode="edit"
        task={{
          ...videoTask,
          config: {
            ...videoTask.config!,
            analysis: { llm_model_id: null, review_route: reviewRoute },
          },
        }}
        platforms={[platform]}
        actions={[action]}
      />,
    );

    expect((screen.getByLabelText("评审路线") as HTMLSelectElement).value).toBe(expectedValue);
  });

  it("把未知来源显式序列化为 null", async () => {
    const fetch = mockMetadata([]);
    render(
      <TaskForm
        mode="edit"
        task={{
          ...videoTask,
          config: {
            ...videoTask.config!,
            analysis: { llm_model_id: null, review_route: null },
          },
        }}
        platforms={[platform]}
        actions={[action]}
      />,
    );

    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/tasks"));
    const request = fetch.mock.calls.find(([url]) => String(url).endsWith("/tasks/3"));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
      review_route: null,
    });
  });

  it("切换离开视频分析时不提交陈旧评审路线", () => {
    const data = new FormData();
    data.set("review_route", "R");
    data.set("sink_mode", "auto");

    const payload = taskPayload({
      data,
      actionId: 2,
      table: "",
      keyColumn: "",
      parameterMapping: "",
      schedule: defaultSchedule,
      executor: "rpc_crawl",
    });

    expect(payload).not.toHaveProperty("review_route");
  });

  it("拒绝非法评审路线并保留原值证据", () => {
    const data = new FormData();
    data.set("review_route", "B");
    data.set("sink_mode", "auto");

    expect(() =>
      taskPayload({
        data,
        actionId: 2,
        table: "",
        keyColumn: "",
        parameterMapping: "",
        schedule: defaultSchedule,
        executor: "video_analysis",
      }),
    ).toThrowError("Invalid review_route: B");
  });

  it("拒绝缺失的评审路线字段", () => {
    const data = new FormData();
    data.set("sink_mode", "auto");

    expect(() =>
      taskPayload({
        data,
        actionId: 2,
        table: "",
        keyColumn: "",
        parameterMapping: "",
        schedule: defaultSchedule,
        executor: "video_analysis",
      }),
    ).toThrowError("Missing review_route");
  });
});

describe("视频下载任务配置", () => {
  it("将下载配置按后端字段提交为数字和布尔值", () => {
    const data = new FormData();
    data.set("sink_mode", "auto");
    data.set("download_batch_size", "25");
    data.set("download_min_grade", "2");
    data.set("download_rps", "1.5");
    data.set("download_max_attempts", "7");
    data.set("download_claim_timeout_seconds", "900");
    data.set("download_retry_base_seconds", "30");
    data.set("download_retry_max_seconds", "120");
    data.set("download_use_proxy", "on");

    expect(
      taskPayload({
        data,
        actionId: 2,
        table: "videos",
        keyColumn: "id",
        parameterMapping: "video_id => id",
        schedule: defaultSchedule,
        executor: "video_download",
      }),
    ).toMatchObject({
      executor: "video_download",
      download: {
        batch_size: 25,
        min_grade: 2,
        use_proxy: true,
        rps: 1.5,
        max_attempts: 7,
        claim_timeout_seconds: 900,
        retry_base_seconds: 30,
        retry_max_seconds: 120,
      },
    });
  });
});

describe("调度与重试配置", () => {
  it("initialSchedule 从 TaskSchedule 提取配置", () => {
    const task: Task = {
      ...videoTask,
      schedule: {
        type: "interval",
        cron: null,
        run_at: null,
        interval_seconds: 3600,
        start_at: null,
        end_at: null,
        max_runs: null,
      },
      retry_policy: {
        max_attempts: 5,
        initial_delay_seconds: 120,
        backoff_multiplier: 2.5,
        max_delay_seconds: 900,
      },
    };
    expect(initialSchedule(task)).toEqual({
      type: "interval",
      run_at: "",
      interval_seconds: "3600",
      cron_expression: "",
      start_at: "",
      end_at: "",
      max_runs: "",
      max_retries: "5",
      retry_delay_seconds: "120",
      retry_backoff_factor: "2.5",
      retry_max_delay_seconds: "900",
    });
  });

  it("initialSchedule 从旧版 loop 字段回退", () => {
    const task: Task = {
      ...videoTask,
      schedule: null,
      loop_enabled: true,
      loop_interval_seconds: 1800,
    };
    expect(initialSchedule(task)).toEqual({
      type: "interval",
      run_at: "",
      interval_seconds: "1800",
      cron_expression: "",
      start_at: "",
      end_at: "",
      max_runs: "",
      max_retries: "3",
      retry_delay_seconds: "60",
      retry_backoff_factor: "2",
      retry_max_delay_seconds: "3600",
    });
  });

  it("taskPayload 将 schedule 表单转换为 schedule 与 retry_policy 对象，并保留兼容字段", () => {
    const data = new FormData();
    data.set("sink_mode", "auto");

    const payload = taskPayload({
      data,
      actionId: 2,
      table: "",
      keyColumn: "",
      parameterMapping: "",
      schedule: {
        type: "cron",
        run_at: "",
        interval_seconds: "",
        cron_expression: "0 * * * *",
        start_at: "2026-08-10T00:00",
        end_at: "2026-09-10T00:00",
        max_runs: "10",
        max_retries: "5",
        retry_delay_seconds: "30",
        retry_backoff_factor: "1.5",
        retry_max_delay_seconds: "600",
      },
      executor: "rpc_crawl",
    });

    expect(payload.schedule).toEqual({
      type: "cron",
      cron: "0 * * * *",
      run_at: null,
      interval_seconds: null,
      start_at: "2026-08-10T00:00",
      end_at: "2026-09-10T00:00",
      max_runs: 10,
    });
    expect(payload.retry_policy).toEqual({
      max_attempts: 5,
      initial_delay_seconds: 30,
      backoff_multiplier: 1.5,
      max_delay_seconds: 600,
    });
    expect(payload.loop_enabled).toBe(false);
    expect(payload.loop_interval_seconds).toBeNull();
  });

  it("scheduleSummary 返回可读摘要", () => {
    expect(scheduleSummary({ schedule: { type: "manual" }, loop_enabled: false })).toBe("手动触发");
    expect(scheduleSummary({ schedule: { type: "once", run_at: "2026-08-10T12:00:00Z" } })).toContain("单次");
    expect(scheduleSummary({ schedule: { type: "interval", interval_seconds: 3600 } })).toBe("每 3600 秒");
    expect(scheduleSummary({ schedule: { type: "cron", cron: "0 * * * *" } })).toBe("Cron：0 * * * *");
    expect(scheduleSummary({ schedule: null, loop_enabled: true, loop_interval_seconds: 600 })).toBe("每 600 秒");
  });
});
