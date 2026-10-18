// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ActionForm } from "./_components/ActionForm";
import { ActionActions } from "./_components/ActionActions";
import { ActionsTable } from "./_components/ActionsTable";
import { ImportActionsDialog } from "./_components/ImportActionsDialog";
import ActionsPage from "./page";
import EditActionPage from "./[id]/edit/page";
import type { Action, Platform } from "../../../utils/crawler/crawler-types";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
  refresh.mockReset();
});

const platforms: Platform[] = [
  {
    bs_id: 7,
    bs_name: "TikTok",
    bs_platform_code: "tiktok",
    bs_url: null,
    bs_remark: null,
    bs_status: "1",
    bs_concurrency: 1,
    bs_rps: 1,
    bs_burst: 3,
    bs_cooldown: 300,
  },
];

const action: Action = {
  ba_id: 9,
  bs_id: 7,
  ba_action: "getUser",
  ba_desc: "用户信息",
  ba_params_schema: "[]",
  ba_api_url: "/user",
  ba_api_method: "GET",
  ba_enabled: true,
  ba_sample_safe: false,
  create_time: null,
  update_time: null,
};

const deletedPlatform: Platform = {
  ...platforms[0],
  bs_id: 8,
  bs_name: "旧平台",
  bs_platform_code: "legacy",
  bs_status: "D",
};

describe("接口列表", () => {
  it("通过 URL 平台参数筛选并保留筛选链接", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json({ items: platforms }),
    ).mockResolvedValueOnce(Response.json({ items: [action] }));
    render(await ActionsPage({ searchParams: Promise.resolve({ platform_id: "7" }) }));
    expect(String(request.mock.calls[1]?.[0])).toContain("/actions?platform_id=7");
    expect((screen.getByLabelText("平台筛选") as HTMLSelectElement).value).toBe("7");
    expect(screen.getByRole("button", { name: "筛选" })).toBeTruthy();
  });
});

describe("ActionForm", () => {
  it("提交取样安全字段并提供 Parser 配置入口", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({
      ...action,
      ba_sample_safe: true,
    }));
    render(<ActionForm mode="edit" platforms={platforms} action={action} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /取样无副作用/ }));
    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/actions"));
    const body = JSON.parse(String(vi.mocked(fetch).mock.calls[0]?.[1]?.body));
    expect(body.ba_sample_safe).toBe(true);

    cleanup();
    render(<ActionActions action={action} />);
    const parserLink = screen.getByRole("link", { name: "Parser 配置" });
    expect(parserLink.getAttribute("href")).toBe("/crawler/actions/9/parser");
  });

  it("提交字符串 schema，并将字段错误映射到控件", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        { detail: [{ loc: ["body", "ba_action"], msg: "已存在", type: "value_error" }] },
        { status: 422 },
      ),
    );
    render(<ActionForm mode="create" platforms={platforms} />);
    fireEvent.change(screen.getByLabelText("接口名称"), { target: { value: "getUser" } });
    fireEvent.change(screen.getByLabelText("参数 Schema"), { target: { value: '[{"name":"id"}]' } });
    fireEvent.submit(screen.getByRole("button", { name: "创建接口" }).closest("form")!);
    expect(await screen.findByText("已存在")).toBeTruthy();
    expect((screen.getByLabelText("参数 Schema") as HTMLTextAreaElement).value).toBe('[{"name":"id"}]');
  });

  it("编辑只提交后端允许更新的字段", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(action));
    render(<ActionForm mode="edit" platforms={platforms} action={action} />);
    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/actions"));
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]!;
    expect(init).toMatchObject({ method: "PUT" });
    expect(JSON.parse(String(init?.body))).not.toHaveProperty("bs_id");
  });

  it("编辑已删除平台的接口时只读展示真实归属", () => {
    render(
      <ActionForm
        mode="edit"
        platforms={[...platforms, deletedPlatform]}
        action={{ ...action, bs_id: deletedPlatform.bs_id }}
      />,
    );
    expect(screen.getByText("旧平台（已删除）")).toBeTruthy();
    expect(screen.queryByLabelText("所属平台")).toBeNull();
    expect(screen.queryByText("TikTok")).toBeNull();
  });

  it.each([
    ['"text"', "参数 Schema 根节点必须是对象、数组或布尔值"],
    ["42", "参数 Schema 根节点必须是对象、数组或布尔值"],
    ["null", "参数 Schema 根节点必须是对象、数组或布尔值"],
    ['{"type":"not-a-json-schema-type"}', "参数 Schema 不是有效的 JSON Schema"],
    ['["raw"]', "legacy 参数数组第 1 项必须是对象"],
  ])("拒绝不支持的参数 Schema：%s", async (schema, message) => {
    const request = vi.spyOn(globalThis, "fetch");
    render(<ActionForm mode="create" platforms={platforms} />);
    fireEvent.change(screen.getByLabelText("接口名称"), { target: { value: "getUser" } });
    fireEvent.change(screen.getByLabelText("参数 Schema"), { target: { value: schema } });
    fireEvent.submit(screen.getByRole("button", { name: "创建接口" }).closest("form")!);
    expect(await screen.findByText(message)).toBeTruthy();
    expect((screen.getByLabelText("参数 Schema") as HTMLTextAreaElement).value).toBe(schema);
    expect(request).not.toHaveBeenCalled();
  });

  it.each([
    "true",
    "false",
    '[{"name":"user_id","type":"string","required":true}]',
    '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"id":{"type":"string","format":"uuid"}}}',
    '{"type":"array","prefixItems":[{"type":"string"},{"type":"number"}]}',
    '{"$schema":"http://json-schema.org/draft-07/schema#","type":"object","dependencies":{"credit_card":["billing_address"]}}',
  ])("接受后端支持的参数 Schema：%s", async (schema) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(action, { status: 201 }));
    render(<ActionForm mode="create" platforms={platforms} />);
    fireEvent.change(screen.getByLabelText("接口名称"), { target: { value: "getUser" } });
    fireEvent.change(screen.getByLabelText("参数 Schema"), { target: { value: schema } });
    fireEvent.submit(screen.getByRole("button", { name: "创建接口" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/actions"));
  });
});

describe("编辑接口服务端页面", () => {
  it("加载包含已删除平台的选项以识别当前归属", async () => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ ...action, bs_id: 8 }))
      .mockResolvedValueOnce(Response.json({ items: [...platforms, deletedPlatform] }));
    render(await EditActionPage({ params: Promise.resolve({ id: "9" }) }));
    expect(String(request.mock.calls[1]?.[0])).toContain("include_deleted=true");
    expect(screen.getByText("旧平台（已删除）")).toBeTruthy();
  });

  it("接口详情 404 时进入 not-found", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ detail: "接口不存在" }, { status: 404 }))
      .mockResolvedValueOnce(Response.json({ items: platforms }));
    await expect(
      EditActionPage({ params: Promise.resolve({ id: "404" }) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("ActionActions", () => {
  it("删除失败在确认框内显示，成功后刷新", async () => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ detail: "仍被任务引用" }, { status: 409 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<ActionActions action={action} />);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect((await screen.findByRole("alert")).textContent).toBe("仍被任务引用");
    expect(screen.getByRole("dialog").contains(screen.getByRole("alert"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(request.mock.calls[1]?.[1]).toMatchObject({ method: "DELETE" });
  });
});

describe("ImportActionsDialog", () => {
  it("校验数组根节点，失败保留选择，成功展示计数并刷新", async () => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ detail: "导入失败" }, { status: 400 }))
      .mockResolvedValueOnce(Response.json({ created_count: 2, updated_count: 1 }));
    render(<ImportActionsDialog platforms={platforms} />);
    fireEvent.click(screen.getByRole("button", { name: "导入接口" }));
    await screen.findByRole("dialog");
    const fileInput = screen.getByLabelText("JSON 文件");
    fireEvent.change(fileInput, {
      target: { files: [new File(['[{"name":"getUser","params":[]}]'], "actions.json", { type: "application/json" })] },
    });
    fireEvent.submit(screen.getByRole("button", { name: "确认导入" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toBe("导入失败");
    expect((screen.getByLabelText("目标平台") as HTMLSelectElement).value).toBe("7");
    expect((fileInput as HTMLInputElement).files?.[0]?.name).toBe("actions.json");
    fireEvent.submit(screen.getByRole("button", { name: "确认导入" }).closest("form")!);
    expect(await screen.findByText("新增 2 个，更新 1 个")).toBeTruthy();
    expect(refresh).toHaveBeenCalledOnce();
    expect(JSON.parse(String(request.mock.calls[1]?.[1]?.body))).toEqual({
      platform_id: 7,
      actions: [{ name: "getUser", params: [] }],
    });
  });

  it("拒绝非数组 JSON，不发送请求", async () => {
    const request = vi.spyOn(globalThis, "fetch");
    render(<ImportActionsDialog platforms={platforms} />);
    fireEvent.click(screen.getByRole("button", { name: "导入接口" }));
    await screen.findByRole("dialog");
    fireEvent.change(screen.getByLabelText("JSON 文件"), {
      target: { files: [new File(["{}"], "invalid.json", { type: "application/json" })] },
    });
    fireEvent.submit(screen.getByRole("button", { name: "确认导入" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toBe("JSON 根节点必须是数组");
    expect(request).not.toHaveBeenCalled();
  });

  it("读取内容前拒绝超过 2 MiB 的文件并保留选择", async () => {
    const request = vi.spyOn(globalThis, "fetch");
    render(<ImportActionsDialog platforms={platforms} />);
    fireEvent.click(screen.getByRole("button", { name: "导入接口" }));
    await screen.findByRole("dialog");
    const file = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "large.json", { type: "application/json" });
    const text = vi.spyOn(file, "text");
    fireEvent.change(screen.getByLabelText("JSON 文件"), { target: { files: [file] } });
    fireEvent.submit(screen.getByRole("button", { name: "确认导入" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toBe("JSON 文件不能超过 2 MiB");
    expect(text).not.toHaveBeenCalled();
    expect((screen.getByLabelText("JSON 文件") as HTMLInputElement).files?.[0]).toBe(file);
    expect(request).not.toHaveBeenCalled();
  });

  it("拒绝超过 1000 条接口且保留对话框上下文", async () => {
    const request = vi.spyOn(globalThis, "fetch");
    render(<ImportActionsDialog platforms={platforms} />);
    fireEvent.click(screen.getByRole("button", { name: "导入接口" }));
    await screen.findByRole("dialog");
    const file = new File([JSON.stringify(Array.from({ length: 1001 }, (_, index) => ({ name: `a${index}` })))], "many.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("JSON 文件"), { target: { files: [file] } });
    fireEvent.submit(screen.getByRole("button", { name: "确认导入" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toBe("单次最多导入 1000 个接口");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });

  it.each(["cancel", "close"])("原生 %s 事件关闭弹窗并恢复入口焦点", async (eventName) => {
    render(<ImportActionsDialog platforms={platforms} />);
    const trigger = screen.getByRole("button", { name: "导入接口" });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog");
    fireEvent(dialog, new Event(eventName, { bubbles: false, cancelable: eventName === "cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });
});

describe("ActionsTable 批量操作", () => {
  const action2: Action = {
    ...action,
    ba_id: 10,
    ba_action: "searchUser",
    ba_enabled: false,
  };
  const actionsList = [action, action2];
  const platformNames = { 7: "TikTok" };

  it("支持勾选单行与全选，并展示批量操作栏", () => {
    render(<ActionsTable actions={actionsList} platformNames={platformNames} />);

    expect(screen.queryByText(/已选择/)).toBeNull();

    // 勾选第一行
    const rowCheckboxes = screen.getAllByRole("checkbox");
    // rowCheckboxes[0] 是表头全选，[1] 是第一行，[2] 是第二行
    fireEvent.click(rowCheckboxes[1]!);
    expect(screen.getByText("已选择 1 项")).toBeTruthy();
    expect(screen.getByRole("button", { name: "批量启用" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "批量禁用" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "批量删除" })).toBeTruthy();

    // 点击取消选择
    fireEvent.click(screen.getByRole("button", { name: "取消选择" }));
    expect(screen.queryByText(/已选择/)).toBeNull();

    // 点击全选
    fireEvent.click(rowCheckboxes[0]!);
    expect(screen.getByText("已选择 2 项")).toBeTruthy();
  });

  it("执行批量启用状态更新并刷新列表", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ updated_count: 2 }),
    );
    render(<ActionsTable actions={actionsList} platformNames={platformNames} />);

    // 点击表头全选
    const rowCheckboxes = screen.getAllByRole("checkbox");
    fireEvent.click(rowCheckboxes[0]!);

    // 点击批量启用
    fireEvent.click(screen.getByRole("button", { name: "批量启用" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/crawler/actions/batch-status",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ action_ids: [9, 10], enabled: true }),
        }),
      );
    });

    expect(await screen.findByText("成功更新 2 个接口状态")).toBeTruthy();
    expect(refresh).toHaveBeenCalled();
    // 成功后自动清空已选
    expect(screen.queryByText(/已选择/)).toBeNull();
  });

  it("执行批量禁用状态更新", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ updated_count: 1 }),
    );
    render(<ActionsTable actions={actionsList} platformNames={platformNames} />);

    // 勾选第一行
    const rowCheckboxes = screen.getAllByRole("checkbox");
    fireEvent.click(rowCheckboxes[1]!);

    // 点击批量禁用
    fireEvent.click(screen.getByRole("button", { name: "批量禁用" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/crawler/actions/batch-status",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ action_ids: [9], enabled: false }),
        }),
      );
    });

    expect(await screen.findByText("成功更新 1 个接口状态")).toBeTruthy();
    expect(refresh).toHaveBeenCalled();
  });

  it("执行批量删除并触发二次确认弹窗", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ deleted_count: 1 }),
    );
    render(<ActionsTable actions={actionsList} platformNames={platformNames} />);

    // 勾选第一行
    const rowCheckboxes = screen.getAllByRole("checkbox");
    fireEvent.click(rowCheckboxes[1]!);

    // 点击批量删除打开弹窗
    fireEvent.click(screen.getByRole("button", { name: "批量删除" }));

    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByText("批量删除接口")).toBeTruthy();
    expect(screen.getByText("确认删除选中的 1 个接口？关联任务将解除这些接口。")).toBeTruthy();

    // 确认删除
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/crawler/actions/batch-delete",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ action_ids: [9] }),
        }),
      );
    });

    expect(await screen.findByText("成功删除 1 个接口")).toBeTruthy();
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("ActionsTable 分页功能", () => {
  const platformNames = { 7: "TikTok" };
  // 生成 25 个接口数据
  const mockActions: Action[] = Array.from({ length: 25 }, (_, i) => ({
    ...action,
    ba_id: 100 + i,
    ba_action: `action_${i + 1}`,
  }));

  it("默认每页展示 20 条，并显示总数与分页控件", () => {
    render(<ActionsTable actions={mockActions} platformNames={platformNames} />);

    expect(screen.getByText("共 25 项")).toBeTruthy();
    expect(screen.getByText("第 1 / 2 页")).toBeTruthy();

    // 默认展示第 1 页前 20 条
    expect(screen.getByText("action_1")).toBeTruthy();
    expect(screen.getByText("action_20")).toBeTruthy();
    expect(screen.queryByText("action_21")).toBeNull();

    // 首页与上一页应为禁用状态
    expect(screen.getByRole("button", { name: "首页" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "上一页" })).toHaveProperty("disabled", true);
    // 下一页与末页可用
    expect(screen.getByRole("button", { name: "下一页" })).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", { name: "末页" })).toHaveProperty("disabled", false);
  });

  it("支持翻页到下一页并在末页禁用下一页", () => {
    render(<ActionsTable actions={mockActions} platformNames={platformNames} />);

    // 点击下一页
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(screen.getByText("第 2 / 2 页")).toBeTruthy();
    expect(screen.queryByText("action_1")).toBeNull();
    expect(screen.getByText("action_21")).toBeTruthy();
    expect(screen.getByText("action_25")).toBeTruthy();

    // 末页时下一页与末页禁用，首页与上一页可用
    expect(screen.getByRole("button", { name: "下一页" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "末页" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "首页" })).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", { name: "上一页" })).toHaveProperty("disabled", false);
  });

  it("支持修改每页展示条数，并重置到第 1 页", () => {
    render(<ActionsTable actions={mockActions} platformNames={platformNames} />);

    // 切换到第 2 页
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByText("第 2 / 2 页")).toBeTruthy();

    // 切换每页条数为 10 条
    const sizeSelect = screen.getByLabelText("每页条数");
    fireEvent.change(sizeSelect, { target: { value: "10" } });

    // 总页数变成 3 页，当前页重置为第 1 页
    expect(screen.getByText("第 1 / 3 页")).toBeTruthy();
    expect(screen.getByText("action_1")).toBeTruthy();
    expect(screen.getByText("action_10")).toBeTruthy();
    expect(screen.queryByText("action_11")).toBeNull();
  });

  it("支持输入页码快速跳页", () => {
    render(<ActionsTable actions={mockActions} platformNames={platformNames} />);

    const jumpInput = screen.getByLabelText("跳至");
    fireEvent.change(jumpInput, { target: { value: "2" } });
    fireEvent.submit(jumpInput.closest("form")!);

    expect(screen.getByText("第 2 / 2 页")).toBeTruthy();
    expect(screen.getByText("action_21")).toBeTruthy();
  });

  it("表头全选仅针对当前页，并支持在批量栏一键全选所有项", () => {
    render(<ActionsTable actions={mockActions} platformNames={platformNames} />);

    // 点击表头全选
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]!); // 表头全选

    // 第 1 页有 20 项，应选 20 项
    expect(screen.getByText("已选择 20 项")).toBeTruthy();

    // 出现一键全选所有 25 项按钮
    const selectAllBtn = screen.getByRole("button", { name: "选择全部 25 项" });
    expect(selectAllBtn).toBeTruthy();

    // 点击全选所有 25 项
    fireEvent.click(selectAllBtn);
    expect(screen.getByText("已选择 25 项")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "选择全部 25 项" })).toBeNull();

    // 取消选择全部
    fireEvent.click(screen.getByRole("button", { name: "取消选择" }));
    expect(screen.queryByText(/已选择/)).toBeNull();
  });
});
