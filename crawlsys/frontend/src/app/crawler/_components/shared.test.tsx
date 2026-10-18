// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "../../_components/ConfirmDialog";
import { DataTable } from "./DataTable";
import { Feedback } from "./Feedback";
import { FilterBar } from "./FilterBar";
import { FormField } from "./FormField";
import { PageHeader } from "./PageHeader";
import { NumberInput } from "../../_components/NumberInput";
import { SubmitButton } from "./SubmitButton";

afterEach(cleanup);

describe("crawler 共享组件", () => {
  it("PageHeader 渲染标题、说明和操作区", () => {
    render(
      <PageHeader title="平台管理" description="维护采集平台">
        <button>新增平台</button>
      </PageHeader>,
    );

    expect(screen.getByRole("heading", { name: "平台管理" })).toBeTruthy();
    expect(screen.getByText("维护采集平台")).toBeTruthy();
    expect(screen.getByRole("button", { name: "新增平台" })).toBeTruthy();
  });

  it("DataTable 关联表头并渲染空状态", () => {
    const { rerender } = render(
      <DataTable<{ id: string; name: string }>
        caption="平台列表"
        columns={[
          { id: "name", header: "名称", accessor: "name" },
          {
            id: "actions",
            header: "操作",
            render: (row) => <button>编辑 {row.name}</button>,
          },
        ]}
        rows={[{ id: "1", name: "TikTok" }]}
        getRowKey={(row) => row.id}
        emptyText="暂无平台"
      />,
    );

    expect(screen.getByRole("columnheader", { name: "名称" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "TikTok" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "编辑 TikTok" })).toBeTruthy();

    rerender(
      <DataTable<{ id: string; name: string }>
        caption="平台列表"
        columns={[{ id: "name", header: "名称", accessor: "name" }]}
        rows={[]}
        getRowKey={(row) => row.id}
        emptyText="暂无平台"
      />,
    );
    expect(screen.getByText("暂无平台")).toBeTruthy();
  });

  it("FilterBar 提供带名称的筛选区域", () => {
    render(
      <FilterBar aria-label="平台筛选">
        <input aria-label="关键词" />
      </FilterBar>,
    );
    expect(screen.getByRole("search", { name: "平台筛选" })).toBeTruthy();
  });

  it("FormField 合并控件已有说明、提示和错误关联", () => {
    render(
      <FormField
        id="name"
        label="名称"
        hint="使用平台展示名称"
        error="名称不能为空"
      >
        <input aria-describedby="external-help" />
      </FormField>,
    );

    const input = screen.getByLabelText("名称");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe(
      "external-help name-hint name-error",
    );
    expect(screen.getByText("使用平台展示名称")).toBeTruthy();
    expect(screen.getByText("名称不能为空")).toBeTruthy();
  });

  it("FormField 未明确设置时保留控件的 required 和 aria-invalid", () => {
    render(
      <FormField id="code" label="代码">
        <input required aria-invalid="spelling" />
      </FormField>,
    );

    const input = screen.getByLabelText("代码");
    expect((input as HTMLInputElement).required).toBe(true);
    expect(input.getAttribute("aria-invalid")).toBe("spelling");
  });

  it("ConfirmDialog 支持取消事件、操作中禁用和焦点恢复", () => {
    const onCancel = vi.fn();
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();

    const view = render(
      <ConfirmDialog
        open
        title="删除平台"
        description="删除后无法恢复"
        confirmLabel="删除"
        cancelLabel="取消"
        onCancel={onCancel}
        onConfirm={vi.fn()}
      />,
    );
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "删除" }));
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(onCancel).toHaveBeenCalledOnce();

    view.rerender(
      <ConfirmDialog
        open
        busy
        loaderClassName="motion-reduce:animate-none"
        title="删除平台"
        description="删除后无法恢复"
        confirmLabel="删除"
        cancelLabel="取消"
        onCancel={onCancel}
        onConfirm={vi.fn()}
      />,
    );
    expect(
      (screen.getByRole("button", { name: "取消" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "删除" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByRole("button", { name: "删除" }).querySelector("svg")?.classList.contains("motion-reduce:animate-none")).toBe(true);
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(screen.getByRole("dialog")).toBeTruthy();

    view.rerender(
      <ConfirmDialog
        open={false}
        title="删除平台"
        confirmLabel="删除"
        cancelLabel="取消"
        onCancel={onCancel}
        onConfirm={vi.fn()}
      />,
    );
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it("危险确认默认聚焦取消", () => {
    render(
      <ConfirmDialog
        open
        destructive
        title="删除平台"
        description="无法恢复"
        confirmLabel="删除"
        cancelLabel="取消"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "取消" }),
    );
  });

  it("ConfirmDialog 在对话框内部渲染操作反馈", () => {
    render(
      <ConfirmDialog
        open
        title="恢复平台"
        confirmLabel="恢复"
        cancelLabel="取消"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      >
        <Feedback variant="error">恢复失败</Feedback>
      </ConfirmDialog>,
    );

    expect(
      screen.getByRole("dialog").contains(screen.getByRole("alert")),
    ).toBe(true);
  });

  it("每个 ConfirmDialog 生成唯一关联 ID", () => {
    render(
      <>
        <ConfirmDialog
          open
          destructive
          title="删除平台"
          description="无法恢复"
          confirmLabel="删除"
          cancelLabel="取消"
          onCancel={vi.fn()}
          onConfirm={vi.fn()}
        />
        <ConfirmDialog
          open
          title="启用平台"
          description="立即生效"
          confirmLabel="启用"
          cancelLabel="取消"
          onCancel={vi.fn()}
          onConfirm={vi.fn()}
        />
      </>,
    );

    const dialogs = screen.getAllByRole("dialog");
    const titleIds = dialogs.map((dialog) => dialog.getAttribute("aria-labelledby"));
    const descriptionIds = dialogs.map((dialog) =>
      dialog.getAttribute("aria-describedby"),
    );
    expect(new Set(titleIds).size).toBe(2);
    expect(new Set(descriptionIds).size).toBe(2);
    for (const id of [...titleIds, ...descriptionIds]) {
      expect(id && document.getElementById(id)).toBeTruthy();
    }
  });

  it("SubmitButton 加载时保留文案并禁用", () => {
    render(<SubmitButton loading>保存</SubmitButton>);
    const button = screen.getByRole("button", { name: "保存" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.querySelector("svg")).toBeTruthy();
  });

  it("NumberInput 使用文本输入和数值键盘提示", () => {
    render(<NumberInput aria-label="并发数" integer />);
    const input = screen.getByLabelText("并发数");
    expect(input.getAttribute("type")).toBe("text");
    expect(input.getAttribute("inputmode")).toBe("numeric");
  });

  it("Feedback 使用与状态匹配的 live region", () => {
    render(<Feedback variant="error">保存失败</Feedback>);
    expect(screen.getByRole("alert").textContent).toBe("保存失败");
  });
});
