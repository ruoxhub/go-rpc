// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PlatformsPage from "./page";
import EditPlatformPage from "./[id]/edit/page";
import { PlatformActions } from "./_components/PlatformActions";
import { PlatformForm } from "./_components/PlatformForm";
import type { Platform } from "../../../utils/crawler/crawler-types";

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

const platform: Platform = {
  bs_id: 7,
  bs_name: "TikTok",
  bs_platform_code: "tiktok",
  bs_url: "https://www.tiktok.com",
  bs_remark: "短视频",
  bs_status: "1",
  bs_concurrency: 2,
  bs_rps: 1.5,
  bs_burst: 3,
  bs_cooldown: 300,
};

describe("平台列表", () => {
  it("默认隐藏已删除平台，并允许通过 URL 显示", async () => {
    const request = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [platform] }))
      .mockResolvedValueOnce(
        Response.json({ items: [platform, { ...platform, bs_id: 8, bs_name: "已删除", bs_status: "D" }] }),
      );

    const normal = await PlatformsPage({ searchParams: Promise.resolve({}) });
    const view = render(normal);
    expect(request.mock.calls[0]?.[0]).toContain("/platforms?include_deleted=false");
    expect(screen.queryByText("已删除")).toBeNull();
    expect(screen.getByRole("link", { name: "显示已删除" }).getAttribute("href")).toBe(
      "/crawler/platforms?include_deleted=1",
    );

    view.unmount();
    render(await PlatformsPage({ searchParams: Promise.resolve({ include_deleted: "1" }) }));
    expect(request.mock.calls[1]?.[0]).toContain("/platforms?include_deleted=true");
    expect(screen.getAllByText("已删除").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "隐藏已删除" }).getAttribute("href")).toBe(
      "/crawler/platforms",
    );
  });
});

describe("编辑平台服务端页面", () => {
  it("已删除平台不可进入编辑表单", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ ...platform, bs_status: "D" }),
    );

    await expect(
      EditPlatformPage({ params: Promise.resolve({ id: "7" }) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("PlatformForm", () => {
  it("创建成功后跳转列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(platform, { status: 201 }));
    render(<PlatformForm mode="create" />);

    fireEvent.change(screen.getByLabelText("平台名称"), { target: { value: "TikTok" } });
    fireEvent.change(screen.getByLabelText("平台代码"), { target: { value: "tiktok" } });
    fireEvent.submit(screen.getByRole("button", { name: "创建平台" }).closest("form")!);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/platforms"));
    expect(refresh).not.toHaveBeenCalled();
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]!;
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse(String(init?.body))).toEqual({
      bs_name: "TikTok",
      bs_platform_code: "tiktok",
      bs_url: null,
      bs_remark: null,
      bs_status: "1",
      bs_concurrency: 1,
      bs_rps: 1,
      bs_burst: 3,
      bs_cooldown: 300,
    });
  });

  it("编辑成功后刷新并返回列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(platform));
    render(<PlatformForm mode="edit" platform={platform} />);
    fireEvent.change(screen.getByLabelText("并发数"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("每秒请求数"), { target: { value: "2.75" } });
    fireEvent.change(screen.getByLabelText("突发量"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("冷却秒数"), { target: { value: "45" } });
    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/platforms"));
    expect(refresh).not.toHaveBeenCalled();
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]!;
    expect(init).toMatchObject({ method: "PUT" });
    expect(JSON.parse(String(init?.body))).toEqual({
      bs_name: "TikTok",
      bs_platform_code: "tiktok",
      bs_url: "https://www.tiktok.com",
      bs_remark: "短视频",
      bs_status: "1",
      bs_concurrency: 8,
      bs_rps: 2.75,
      bs_burst: 9,
      bs_cooldown: 45,
    });
  });

  it("字段错误映射到表单并保留输入", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        { detail: [{ loc: ["body", "bs_name"], msg: "不能为空", type: "value_error" }] },
        { status: 422 },
      ),
    );
    render(<PlatformForm mode="create" />);
    fireEvent.change(screen.getByLabelText("平台名称"), { target: { value: "保留我" } });
    fireEvent.change(screen.getByLabelText("平台代码"), { target: { value: "code" } });
    fireEvent.submit(screen.getByRole("button", { name: "创建平台" }).closest("form")!);
    expect(await screen.findByText("不能为空")).toBeTruthy();
    expect((screen.getByLabelText("平台名称") as HTMLInputElement).value).toBe("保留我");
    expect(push).not.toHaveBeenCalled();
  });

  it.each([
    [409, "平台代码已存在"],
    [500, "采集服务请求失败（500）"],
  ])("以 Feedback 展示 %i 错误", async (status, message) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(status === 409 ? { detail: message } : {}, { status }),
    );
    render(<PlatformForm mode="create" />);
    fireEvent.change(screen.getByLabelText("平台名称"), { target: { value: "名称" } });
    fireEvent.change(screen.getByLabelText("平台代码"), { target: { value: "code" } });
    fireEvent.submit(screen.getByRole("button", { name: "创建平台" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(push).not.toHaveBeenCalled();
  });
});

describe("PlatformActions", () => {
  it.each([
    ["删除", "DELETE", undefined],
    ["恢复", "POST", "/restore"],
  ])("%s成功后刷新，失败时保留对话框上下文", async (label, method, suffix) => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json({ detail: "操作失败" }, { status: 409 }),
    );
    render(<PlatformActions platform={{ ...platform, bs_status: label === "恢复" ? "D" : "1" }} />);
    fireEvent.click(screen.getByRole("button", { name: label }));
    fireEvent.click(screen.getByRole("button", { name: `确认${label}` }));
    expect((await screen.findByRole("alert")).textContent).toBe("操作失败");
    expect(
      screen.getByRole("dialog").contains(screen.getByRole("alert")),
    ).toBe(true);

    request.mockResolvedValueOnce(
      suffix ? Response.json({ ...platform, bs_status: "1" }) : new Response(null, { status: 204 }),
    );
    fireEvent.click(screen.getByRole("button", { name: `确认${label}` }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(request.mock.calls[1]?.[1]).toMatchObject({ method });
    expect(String(request.mock.calls[1]?.[0])).toContain(suffix ?? "/platforms/7");
  });
});
