// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Keyword, Platform } from "../../../utils/crawler/crawler-types";
import EditKeywordPage from "./[id]/edit/page";
import { KeywordActions } from "./_components/KeywordActions";
import { KeywordForm } from "./_components/KeywordForm";
import KeywordsPage from "./page";

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

const activePlatform: Platform = {
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
};
const keyword: Keyword = {
  id: 11,
  platform: "tiktok",
  keyword: "AI",
  is_crawled: false,
  created_at: "2026-07-31T00:00:00Z",
};

describe("关键词列表", () => {
  it("通过 URL 平台 code 筛选并保留筛选值", async () => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [activePlatform] }))
      .mockResolvedValueOnce(Response.json({ items: [keyword] }));
    render(await KeywordsPage({ searchParams: Promise.resolve({ platform: "tiktok" }) }));
    expect(String(request.mock.calls[1]?.[0])).toContain("/keywords?platform=tiktok");
    expect((screen.getByLabelText("平台筛选") as HTMLSelectElement).value).toBe("tiktok");
    expect(screen.getAllByText("TikTok")).toHaveLength(2);
  });

  it("重复平台参数取首个非空值并安全编码", async () => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [activePlatform] }))
      .mockResolvedValueOnce(Response.json({ items: [] }));
    render(await KeywordsPage({ searchParams: Promise.resolve({ platform: [" ", " tik tok ", "ignored"] }) }));
    expect(String(request.mock.calls[1]?.[0])).toContain("/keywords?platform=tik%20tok");
    expect(String(request.mock.calls[1]?.[0])).not.toContain("ignored");
  });

  it.each(["deleted", "unknown"])("直达 %s 平台筛选时准确显示历史值且仍按其查询", async (platformCode) => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ items: [activePlatform] }))
      .mockResolvedValueOnce(Response.json({ items: [] }));
    render(await KeywordsPage({ searchParams: Promise.resolve({ platform: platformCode }) }));
    const select = screen.getByLabelText("平台筛选") as HTMLSelectElement;
    expect(select.value).toBe(platformCode);
    expect(screen.getByRole("option", { name: `${platformCode}（不可用或历史）` }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("option", { name: "全部平台" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "TikTok" })).toBeTruthy();
    expect(String(request.mock.calls[1]?.[0])).toContain(`/keywords?platform=${platformCode}`);
  });
});

describe("KeywordForm", () => {
  it("创建提交平台 code，成功后返回列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(keyword, { status: 201 }));
    render(<KeywordForm mode="create" platforms={[activePlatform]} />);
    fireEvent.change(screen.getByLabelText("关键词"), { target: { value: "AI" } });
    fireEvent.submit(screen.getByRole("button", { name: "创建关键词" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/keywords"));
    expect(JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      platform: "tiktok",
      keyword: "AI",
    });
  });

  it("422 字段错误映射并保留输入", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ detail: [
      { loc: ["body", "keyword"], msg: "不能为空", type: "value_error" },
    ] }, { status: 422 }));
    render(<KeywordForm mode="create" platforms={[activePlatform]} />);
    fireEvent.change(screen.getByLabelText("关键词"), { target: { value: "保留我" } });
    fireEvent.submit(screen.getByRole("button", { name: "创建关键词" }).closest("form")!);
    expect(await screen.findByText("不能为空")).toBeTruthy();
    expect((screen.getByLabelText("关键词") as HTMLInputElement).value).toBe("保留我");
    expect(push).not.toHaveBeenCalled();
  });

  it("编辑成功后提交允许字段并返回列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ ...keyword, keyword: "LLM" }));
    render(<KeywordForm mode="edit" platforms={[activePlatform]} keyword={keyword} />);
    fireEvent.change(screen.getByLabelText("关键词"), { target: { value: "LLM" } });
    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/keywords"));
    expect(JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      platform: "tiktok",
      keyword: "LLM",
    });
  });

  it("平台不存在或禁用错误保留平台和输入", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ detail: "平台不存在" }, { status: 404 }),
    );
    render(<KeywordForm mode="create" platforms={[activePlatform]} />);
    fireEvent.change(screen.getByLabelText("关键词"), { target: { value: "保留我" } });
    fireEvent.submit(screen.getByRole("button", { name: "创建关键词" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toBe("平台不存在");
    expect((screen.getByLabelText("所属平台") as HTMLSelectElement).value).toBe("tiktok");
    expect((screen.getByLabelText("关键词") as HTMLInputElement).value).toBe("保留我");
  });

  it("编辑历史禁用平台时显示真实归属，迁移到活跃平台后可提交", async () => {
    const disabled = { ...activePlatform, bs_name: "旧平台", bs_status: "0" as const };
    const replacement = { ...activePlatform, bs_id: 8, bs_name: "新平台", bs_platform_code: "new" };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ ...keyword, platform: "new" }));
    render(<KeywordForm mode="edit" platforms={[disabled, replacement]} keyword={keyword} />);
    expect(screen.getByText("旧平台（已停用）")).toBeTruthy();
    expect(screen.getByText("所属平台不可用，请选择一个启用的平台后保存。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "保存修改" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("所属平台"), { target: { value: "new" } });
    expect(screen.getByRole("button", { name: "保存修改" }).hasAttribute("disabled")).toBe(false);
    fireEvent.submit(screen.getByRole("button", { name: "保存修改" }).closest("form")!);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/crawler/keywords"));
    expect(JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      platform: "new",
      keyword: "AI",
    });
  });

  it("平台已被彻底删除时按 code 只读展示，不错归属", () => {
    render(<KeywordForm mode="edit" platforms={[activePlatform]} keyword={{ ...keyword, platform: "gone" }} />);
    expect(screen.getByText("gone（平台不可用）")).toBeTruthy();
    expect(screen.getByRole("option", { name: "TikTok" })).toBeTruthy();
  });
});

describe("编辑关键词服务端页面", () => {
  it("并行加载详情和含历史记录的平台", async () => {
    const disabled = { ...activePlatform, bs_status: "D" as const };
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json(keyword))
      .mockResolvedValueOnce(Response.json({ items: [disabled] }));
    render(await EditKeywordPage({ params: Promise.resolve({ id: "11" }) }));
    expect(String(request.mock.calls[1]?.[0])).toContain("include_deleted=true");
    expect(screen.getByText("TikTok（已删除）")).toBeTruthy();
  });

  it("详情不存在时进入 404", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ detail: "关键词不存在" }, { status: 404 }))
      .mockResolvedValueOnce(Response.json({ items: [activePlatform] }));
    await expect(EditKeywordPage({ params: Promise.resolve({ id: "404" }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("KeywordActions", () => {
  it("删除错误保留在确认框内，成功后刷新", async () => {
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ detail: "删除失败" }, { status: 409 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<KeywordActions keyword={keyword} />);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect((await screen.findByRole("alert")).textContent).toBe("删除失败");
    expect(screen.getByRole("dialog").contains(screen.getByRole("alert"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(request.mock.calls[1]?.[1]).toMatchObject({ method: "DELETE" });
  });
});
