// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TasksPage from "./page";
import { TaskForm } from "./_components/TaskForm";
import { TaskActions } from "./_components/TaskActions";
import { BatchTaskActions } from "./_components/TaskActions/BatchTaskActions";
import type { Action, Platform, Task } from "../../../utils/crawler/crawler-types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  refresh.mockReset();
  push.mockReset();
});
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
const actions: Action[] = [{
  ba_id: 2,
  bs_id: 1,
  ba_action: "search",
  ba_desc: null,
  ba_params_schema: null,
  ba_api_url: null,
  ba_api_method: "GET",
  ba_enabled: true,
  ba_sample_safe: false,
  create_time: null,
  update_time: null,
}];
const task: Task = {
  task_id: 3,
  platform: "tiktok",
  action: "search",
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
  config: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

describe("任务管理", () => {
  it("安全使用 URL 平台多值筛选", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [platform] }))
      .mockResolvedValueOnce(Response.json({ items: [task] }));
    render(await TasksPage({ searchParams: Promise.resolve({ platform: ["tiktok", "other"] }) }));
    expect(String(fetch.mock.calls[1]?.[0])).toContain("platform=tiktok");
  });
  it("列表显示 Cron 摘要、下一重试、执行次数和上一轮状态", async () => {
    const scheduledTask: Task = {
      ...task,
      schedule_type: "cron",
      schedule: {
        type: "cron",
        cron: "0 2 * * *",
        run_at: null,
        interval_seconds: null,
        start_at: null,
        end_at: null,
        max_runs: 10,
      },
      max_runs: 10,
      run_count: 2,
      last_run_status: "failed",
      next_run_at: "2026-08-11T18:00:00Z",
      next_retry_at: "2026-08-10T10:01:00Z",
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [platform] }))
      .mockResolvedValueOnce(Response.json({ items: [scheduledTask] }));
    render(await TasksPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText("Cron：0 2 * * *")).toBeTruthy();
    expect(screen.getByText("2026-08-10T10:01:00Z")).toBeTruthy();
    expect(screen.getByText("2 / 10")).toBeTruthy();
    expect(screen.getByText("失败")).toBeTruthy();
  });
  it("任务列表显示本地化优先级 badge", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [platform] }))
      .mockResolvedValueOnce(Response.json({ items: [{ ...task, priority: "urgent" }] }));
    render(await TasksPage({ searchParams: Promise.resolve({}) }));
    const badge = screen.getAllByText("紧急").find((element) => element.tagName === "SPAN");
    expect(badge).toBeTruthy();
    expect(badge!.className).toContain("text-destructive");
  });

  it("运行中任务也能快捷调整优先级", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ ...task, status: "running", priority: "high" }),
    );
    render(<TaskActions task={{ ...task, status: "running" }} />);
    fireEvent.change(screen.getByLabelText("调整任务 3 的优先级"), {
      target: { value: "high" },
    });
    await screen.findByText("任务优先级已更新");
    expect(String(fetch.mock.calls[0]?.[0])).toContain("/tasks/3/priority");
    expect(fetch.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual({ priority: "high" });
    expect(refresh).toHaveBeenCalled();
  });

  it("快捷调整失败时回滚原优先级并展示后端错误", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ detail: "更新冲突" }, { status: 409 }),
    );
    render(<TaskActions task={{ ...task, priority: "normal" }} />);
    const select = screen.getByLabelText("调整任务 3 的优先级") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "urgent" } });
    expect(select.disabled).toBe(true);
    expect(await screen.findByText("更新冲突")).toBeTruthy();
    expect(select.value).toBe("normal");
    expect(select.disabled).toBe(false);
  });
  it("支持立即执行操作", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 204, headers: { "content-type": "application/json" } }),
    );
    render(<TaskActions task={task} />);
    fireEvent.click(screen.getByRole("button", { name: "立即执行" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/crawler/tasks/3/run-now", expect.objectContaining({ method: "POST" })));
    expect(await screen.findByText("任务已加入队首")).toBeTruthy();
    expect(refresh).toHaveBeenCalledOnce();
  });
  it("已有立即执行请求时显示已排队并阻止重复点击", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<TaskActions task={{ ...task, run_now_requested_at: "2026-08-10T10:00:00Z" }} />);
    const queued = screen.getByRole("button", { name: "已排队" });
    expect((queued as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(queued);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("支持启动、暂停和删除且错误留在操作上下文", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json(task))
      .mockResolvedValueOnce(
        Response.json({ detail: "运行中不可删除" }, { status: 409 }),
      );
    render(<TaskActions task={task} />);
    fireEvent.click(screen.getByRole("button", { name: "恢复" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect((await screen.findByRole("alert")).textContent).toBe("运行中不可删除");
  });
  it("删除成功在当前操作区显示反馈", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    render(<TaskActions task={task} />);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect(await screen.findByText("任务已删除")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(refresh).toHaveBeenCalledOnce();
  });
  it("单项和批量操作 loading 时保留文案、禁用并显示 Loader2", async () => {
    const actionResponse = deferred<Response>();
    const batchResponse = deferred<Response>();
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(actionResponse.promise)
      .mockReturnValueOnce(batchResponse.promise);
    render(
      <>
        <TaskActions task={task} />
        <BatchTaskActions platform="tiktok" />
      </>,
    );
    const start = screen.getByRole("button", { name: "恢复" });
    fireEvent.click(start);
    expect(start.textContent).toContain("恢复");
    expect(start.getAttribute("aria-busy")).toBe("true");
    expect((start as HTMLButtonElement).disabled).toBe(true);
    expect(start.querySelector(".animate-spin")).toBeTruthy();
    const batchStart = screen.getByRole("button", { name: "批量启动" });
    fireEvent.click(batchStart);
    expect(batchStart.textContent).toContain("批量启动");
    expect(batchStart.getAttribute("aria-busy")).toBe("true");
    expect((batchStart as HTMLButtonElement).disabled).toBe(true);
    expect(batchStart.querySelector(".animate-spin")).toBeTruthy();
    actionResponse.resolve(Response.json(task));
    batchResponse.resolve(Response.json({ updated_count: 1 }));
  });
  it("支持单项暂停及按当前筛选批量启动/暂停", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ ...task, status: "paused" }))
      .mockResolvedValueOnce(Response.json({ updated_count: 2 }))
      .mockResolvedValueOnce(Response.json({ updated_count: 1 }));
    render(
      <>
        <TaskActions task={{ ...task, status: "pending" }} />
        <BatchTaskActions platform="tiktok" />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "批量启动" }));
    expect(await screen.findByText("已更新 2 个任务")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "批量暂停" }));
    expect(await screen.findByText("已更新 1 个任务")).toBeTruthy();
    expect(JSON.parse(String(fetch.mock.calls[1]?.[1]?.body))).toEqual({
      platform: "tiktok",
    });
  });
  it("联动平台、Action/schema、表字段，元数据失败保留输入并可重试", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ schema: { type: "object" } }))
      .mockResolvedValueOnce(
        Response.json({ detail: "元数据失败" }, { status: 500 }),
      )
      .mockResolvedValueOnce(Response.json({ columns: ["id", "keyword"] }));
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);
    fireEvent.change(screen.getByLabelText("查询表"), {
      target: { value: "t_keywords" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取字段" }));
    expect(await screen.findByText("元数据失败")).toBeTruthy();
    expect((screen.getByLabelText("查询表") as HTMLInputElement).value).toBe(
      "t_keywords",
    );
    fireEvent.click(screen.getByRole("button", { name: "重试读取字段" }));
    expect(await screen.findByRole("option", { name: "keyword" })).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it("换表立即清除旧字段和映射，乱序响应不能覆盖新表字段", async () => {
    const oldResponse = deferred<Response>();
    const newResponse = deferred<Response>();
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ schema: [] }))
      .mockReturnValueOnce(oldResponse.promise)
      .mockReturnValueOnce(newResponse.promise)
      .mockResolvedValueOnce(Response.json(task, { status: 201 }));
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);
    fireEvent.change(screen.getByLabelText("查询表"), { target: { value: "old_table" } });
    fireEvent.click(screen.getByRole("button", { name: "读取字段" }));
    fireEvent.change(screen.getByLabelText("查询表"), { target: { value: "new_table" } });
    expect(screen.queryByRole("option", { name: "old_id" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "读取字段" }));
    newResponse.resolve(Response.json({ columns: ["new_id"] }));
    expect(await screen.findByRole("option", { name: "new_id" })).toBeTruthy();
    oldResponse.resolve(Response.json({ columns: ["old_id"] }));
    await waitFor(() => expect(screen.queryByRole("option", { name: "old_id" })).toBeNull());
    fireEvent.submit(screen.getByRole("button", { name: "创建任务" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalled());
    const body = JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[3]?.[1]?.body));
    expect(body.entity_column).toBe("");
    expect(body.params_columns).toBe("");
  });
  it("Action 变更清除旧 schema，失败后可重试且保留其他输入", async () => {
    const secondAction = { ...actions[0], ba_id: 4, ba_action: "detail" };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ schema: { title: "旧参数" } }))
      .mockResolvedValueOnce(Response.json({ detail: "Schema 失败" }, { status: 500 }))
      .mockResolvedValueOnce(Response.json({ schema: { title: "新参数" } }));
    render(<TaskForm mode="create" platforms={[platform]} actions={[...actions, secondAction]} />);
    expect(await screen.findByText(/旧参数/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("查询表"), { target: { value: "kept_table" } });
    fireEvent.change(screen.getByLabelText("接口"), { target: { value: "4" } });
    expect(screen.queryByText(/旧参数/)).toBeNull();
    expect(await screen.findByText("Schema 失败")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试加载 Schema" }));
    expect(await screen.findByText(/新参数/)).toBeTruthy();
    expect((screen.getByLabelText("查询表") as HTMLInputElement).value).toBe("kept_table");
  });
  it.each([
    [null, actions, "search（不可用）"],
    [99, actions, "search（不可用）"],
    [2, [{ ...actions[0], bs_id: 8 }], "search（不可用）"],
  ])("历史接口异常时不静默改绑：%s", (baId, actionOptions, label) => {
    render(
      <TaskForm
        mode="edit"
        platforms={[platform]}
        actions={actionOptions}
        task={{ ...task, ba_id: baId }}
      />,
    );
    expect(screen.getByText(label)).toBeTruthy();
    expect((screen.getByLabelText("接口") as HTMLSelectElement).value).toBe("");
  });
  it.each([
    ["paused", "恢复", "/start"],
    ["done", "启动", "/start"],
    ["failed", "启动", "/start"],
    ["pending", "暂停", "/pause"],
    ["running", "暂停", "/pause"],
  ] as const)("%s 状态显示%s并提供成功反馈", async (status, label, suffix) => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ ...task, status }),
    );
    render(<TaskActions task={{ ...task, status }} />);
    const button = screen.getByRole("button", { name: label });
    fireEvent.click(button);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(
      await screen.findByText(label === "恢复" ? "任务已恢复" : label === "启动" ? "任务已启动" : "任务已暂停"),
    ).toBeTruthy();
    expect(String(fetch.mock.calls[0]?.[0])).toContain(suffix);
  });
  it("创建任务默认提交普通优先级", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/schema")) {
        return Promise.resolve(Response.json({ schema: [] }));
      }
      return Promise.resolve(Response.json(task, { status: 201 }));
    });
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);

    fireEvent.submit(
      screen.getByRole("button", { name: "创建任务" }).closest("form")!,
    );

    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/tasks"));
    const request = fetch.mock.calls.find(([url]) =>
      String(url).endsWith("/tasks"),
    );
    expect(JSON.parse(String(request?.[1]?.body)).priority).toBe("normal");
  });

  it("编辑任务恢复并提交原优先级", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/schema")) {
        return Promise.resolve(Response.json({ schema: [] }));
      }
      return Promise.resolve(Response.json({ ...task, priority: "low" }));
    });
    render(
      <TaskForm
        mode="edit"
        task={{ ...task, priority: "urgent" }}
        platforms={[platform]}
        actions={actions}
      />,
    );

    expect((screen.getByLabelText("任务优先级") as HTMLSelectElement).value).toBe(
      "urgent",
    );
    fireEvent.change(screen.getByLabelText("任务优先级"), {
      target: { value: "low" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "保存修改" }).closest("form")!,
    );

    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/tasks"));
    const request = fetch.mock.calls.find(([url]) =>
      String(url).endsWith("/tasks/3"),
    );
    expect(JSON.parse(String(request?.[1]?.body)).priority).toBe("low");
  });

  it("任务表单展示全部五级优先级", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ schema: [] }),
    );
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);

    const options = screen
      .getAllByRole("option")
      .filter((option) =>
        ["lowest", "low", "normal", "high", "urgent"].includes(
          (option as HTMLOptionElement).value,
        ),
      );
    expect(options.map((option) => option.textContent)).toEqual([
      "最低",
      "低",
      "普通",
      "高",
      "紧急",
    ]);
  });

  it("提交循环设置和参数映射", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockImplementation((input) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
        if (url.includes("/schema")) {
          return Promise.resolve(Response.json({ schema: [] }));
        }
        if (url.includes("/table-columns")) {
          return Promise.resolve(Response.json({ columns: ["id"] }));
        }
        if (url.includes("/tasks/schedule/preview")) {
          return Promise.resolve(Response.json({ timezone: "Asia/Shanghai", occurrences: [] }));
        }
        if (url.includes("/tasks")) {
          return Promise.resolve(Response.json(task, { status: 201 }));
        }
        return Promise.resolve(Response.json({}));
      });
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);
    fireEvent.change(screen.getByLabelText("查询表"), {
      target: { value: "items" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取字段" }));
    await screen.findByRole("option", { name: "id" });
    fireEvent.change(screen.getByLabelText("主键列"), {
      target: { value: "id" },
    });
    fireEvent.change(screen.getByLabelText("参数映射"), {
      target: { value: "id => item_id" },
    });
    fireEvent.change(screen.getByLabelText("接口"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByLabelText("固定间隔"));
    const intervalInput = screen.getByPlaceholderText("300");
    fireEvent.change(intervalInput, {
      target: { value: "60" },
    });
    fireEvent.blur(intervalInput);
    fireEvent.submit(
      screen.getByRole("button", { name: "创建任务" }).closest("form")!,
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/tasks"));
    const lastCall = fetch.mock.calls.find((call) => (call[1]?.body as string)?.includes("loop_interval_seconds"));
    const body = JSON.parse(String(lastCall?.[1]?.body));
    expect(body).toMatchObject({
      loop_enabled: true,
      loop_interval_seconds: 60,
      schedule: {
        type: "interval",
        interval_seconds: 60,
      },
      entity_column: "id",
      params_columns: "id AS item_id",
    });
  });
  it("循环间隔留空使用系统默认，正整数原值提交", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockImplementation((input) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
        if (url.includes("/schema")) {
          return Promise.resolve(Response.json({ schema: [] }));
        }
        if (url.includes("/table-columns")) {
          return Promise.resolve(Response.json({ columns: ["id"] }));
        }
        if (url.includes("/tasks/schedule/preview")) {
          return Promise.resolve(Response.json({ timezone: "Asia/Shanghai", occurrences: [] }));
        }
        if (url.includes("/tasks")) {
          return Promise.resolve(Response.json(task, { status: 201 }));
        }
        return Promise.resolve(Response.json({}));
      });
    const view = render(
      <TaskForm mode="create" platforms={[platform]} actions={actions} />,
    );
    fireEvent.change(screen.getByLabelText("接口"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByLabelText("固定间隔"));
    fireEvent.submit(
      screen.getByRole("button", { name: "创建任务" }).closest("form")!,
    );
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    const call1 = fetch.mock.calls.find((call) => (call[1]?.body as string)?.includes("loop_interval_seconds"));
    expect(JSON.parse(String(call1?.[1]?.body)))
      .toMatchObject({ loop_interval_seconds: 300, schedule: { type: "interval", interval_seconds: 300 } });
    view.unmount();
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);
    fireEvent.change(screen.getByLabelText("接口"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByLabelText("固定间隔"));
    const intervalInput = screen.getByPlaceholderText("300");
    fireEvent.change(intervalInput, {
      target: { value: "120" },
    });
    fireEvent.blur(intervalInput);
    fireEvent.submit(
      screen.getByRole("button", { name: "创建任务" }).closest("form")!,
    );
    await waitFor(() => expect(push).toHaveBeenCalledTimes(2));
    const call2 = fetch.mock.calls.filter((call) => (call[1]?.body as string)?.includes("loop_interval_seconds")).pop();
    expect(JSON.parse(String(call2?.[1]?.body)))
      .toMatchObject({ loop_interval_seconds: 120, schedule: { type: "interval", interval_seconds: 120 } });
  });
  it("查询表标签关联真实输入框", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ schema: [] }));
    render(<TaskForm mode="create" platforms={[platform]} actions={actions} />);
    const label = screen.getByText("查询表", { selector: "label" });
    const input = screen.getByLabelText("查询表");
    expect(label.getAttribute("for")).toBe(input.id);
    expect(input.id).toBe("ref_table");
  });
});
