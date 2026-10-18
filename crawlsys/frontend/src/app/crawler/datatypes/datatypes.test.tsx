// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DatatypeItem } from "../../../api/datatype/datatype.types";
import { DatatypeDetailDrawer } from "./_components/DatatypeDetailDrawer";
import { DatatypesTable } from "./_components/DatatypesTable";
import { SyncDatatypesButton } from "./_components/SyncDatatypesButton";
import DatatypesPage from "./page";

const refresh = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  refresh.mockReset();
  push.mockReset();
});

function mockDatatype(key: string, overrides: Partial<DatatypeItem> = {}): DatatypeItem {
  return {
    datatype_id: 1,
    datatype_key: key,
    table_name: `t_busi_${key}`,
    model_name: key.charAt(0).toUpperCase() + key.slice(1),
    description: `${key} model`,
    unique_field: `${key}_id`,
    update_fields: [`${key}_id`, "platform"],
    columns: [
      {
        name: `${key}_id`,
        type: "VARCHAR(64)",
        nullable: true,
        primary_key: false,
        comment: `${key} ID`,
      },
    ],
    dto_fields: [
      {
        name: `${key}_id`,
        target: `/${key}_id`,
        required: false,
        value_types: ["string"],
        description: null,
      },
    ],
    is_active: true,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

describe("DatatypesPage", () => {
  it("服务端加载并渲染数据模型列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json({ items: [mockDatatype("content"), mockDatatype("user")], total: 2 }),
    );

    render(await DatatypesPage());

    expect(screen.getByRole("heading", { name: "数据模型管理" })).toBeTruthy();
    expect(screen.getByText("Content")).toBeTruthy();
    expect(screen.getByText("t_busi_content")).toBeTruthy();
    expect(screen.getByText("User")).toBeTruthy();
  });
});

describe("SyncDatatypesButton", () => {
  it("触发同步并刷新列表", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json({ success: true, synced_count: 8, datatypes: ["content"] }),
    );
    render(<SyncDatatypesButton />);

    fireEvent.click(screen.getByRole("button", { name: "从代码同步" }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchSpy.mock.calls[0]?.[0])).toContain("/api/crawler/datatypes/sync");
    expect(vi.mocked(fetchSpy).mock.calls[0]?.[1]?.method).toBe("POST");
    expect(await screen.findByText("同步完成：共 8 个数据模型")).toBeTruthy();
  });

  it("同步失败时展示错误反馈", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json({ detail: "同步失败" }, { status: 500 }),
    );
    render(<SyncDatatypesButton />);

    fireEvent.click(screen.getByRole("button", { name: "从代码同步" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("DatatypesTable", () => {
  it("切换类型状态时发送 PATCH 并刷新", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json(mockDatatype("content", { is_active: false })),
    );
    render(<DatatypesTable datatypes={[mockDatatype("content")]} />);

    fireEvent.click(screen.getByRole("switch", { name: "content" }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/crawler/datatypes/content/status",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ is_active: false }),
      }),
    );
  });

  it("点击详情打开抽屉并展示列与 DTO 映射", () => {
    render(<DatatypesTable datatypes={[mockDatatype("content")]} />);

    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "数据库物理列" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "content_id" })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "解析器 DTO 映射" }));
    expect(screen.getByRole("cell", { name: "/content_id" })).toBeTruthy();
    expect(screen.getByText("string")).toBeTruthy();
  });

  it("未选中时抽屉不渲染", () => {
    render(<DatatypesTable datatypes={[mockDatatype("content")]} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("DatatypeDetailDrawer", () => {
  it("展示去重字段与冲突更新策略", () => {
    render(
      <DatatypeDetailDrawer
        datatype={mockDatatype("follow")}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Follow")).toBeTruthy();
    expect(screen.getByText(/t_busi_follow/)).toBeTruthy();
    expect(screen.getByText("冲突更新策略")).toBeTruthy();
    expect(screen.getByText("platform")).toBeTruthy();
  });
});
