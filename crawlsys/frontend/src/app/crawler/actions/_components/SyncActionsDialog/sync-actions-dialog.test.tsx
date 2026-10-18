// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SyncActionsDialog } from "./index";
import type { Platform } from "../../../../../utils/crawler/crawler-types";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
  refresh.mockReset();
});

const platforms: Platform[] = [
  {
    bs_id: 1,
    bs_name: "哔哩哔哩",
    bs_platform_code: "bilibili",
    bs_url: null,
    bs_remark: null,
    bs_status: "1",
    bs_concurrency: 1,
    bs_rps: 1,
    bs_burst: 3,
    bs_cooldown: 300,
  },
  {
    bs_id: 2,
    bs_name: "抖音",
    bs_platform_code: "douyin",
    bs_url: null,
    bs_remark: null,
    bs_status: "1",
    bs_concurrency: 1,
    bs_rps: 1,
    bs_burst: 3,
    bs_cooldown: 300,
  },
];

describe("SyncActionsDialog", () => {
  it("打开弹窗，支持选择平台和勾选 force，提交后显示同步成功总结", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        inserted_count: 7,
        updated_count: 0,
        skipped_manual_count: 0,
        total_synced: 7,
        unknown_groups: [],
        details: [
          { platform: "bilibili", action: "getUserInfo", status: "inserted" },
          { platform: "bilibili", action: "getComment", status: "inserted" },
        ],
      }),
    );

    render(<SyncActionsDialog platforms={platforms} defaultPlatformId="1" />);

    // 点击按钮打开弹窗
    const openBtn = screen.getByRole("button", { name: "同步接口" });
    fireEvent.click(openBtn);

    await screen.findByRole("dialog");
    expect(screen.getByRole("heading", { name: "从 RPC 注册同步接口" })).toBeTruthy();
    expect(screen.getByLabelText("同步平台")).toBeTruthy();

    const select = screen.getByLabelText("同步平台") as HTMLSelectElement;
    expect(select.value).toBe("1");

    // 勾选 force
    const checkbox = screen.getByRole("checkbox", { name: /强制覆盖人工修改/ });
    fireEvent.click(checkbox);

    // 提交表单
    const submitBtn = screen.getByRole("button", { name: "开始同步" });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const callArgs = fetchMock.mock.calls[0];
    expect(String(callArgs[0])).toContain("/actions/sync");
    const sentBody = JSON.parse(String(callArgs[1]?.body));
    expect(sentBody).toEqual({ platform_id: 1, force: true });

    // 检查反馈信息与详情
    await waitFor(() => {
      expect(screen.getByText(/同步完成：新增 7 项，更新 0 项/)).toBeTruthy();
      expect(screen.getByText("bilibili/getUserInfo")).toBeTruthy();
    });

    expect(refresh).toHaveBeenCalled();
  });

  it("当无新增和更新时显示契约已对齐提示", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        inserted_count: 0,
        updated_count: 0,
        skipped_manual_count: 0,
        total_synced: 0,
        unknown_groups: [],
        details: [],
      }),
    );

    render(<SyncActionsDialog platforms={platforms} />);
    fireEvent.click(screen.getByRole("button", { name: "同步接口" }));
    await screen.findByRole("dialog");
    fireEvent.submit(screen.getByRole("button", { name: "开始同步" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("契约与数据库已对齐，无新增或更新项")).toBeTruthy();
    });
  });

  it("处理同步请求失败报错", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ detail: "网络连接失败" }, { status: 500 }),
    );

    render(<SyncActionsDialog platforms={platforms} />);
    fireEvent.click(screen.getByRole("button", { name: "同步接口" }));
    await screen.findByRole("dialog");
    fireEvent.submit(screen.getByRole("button", { name: "开始同步" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("网络连接失败")).toBeTruthy();
    });
  });
});
