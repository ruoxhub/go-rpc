// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import ErrorPage from "./error";

it("使用业务中立语境并保留重试操作", () => {
  const reset = vi.fn();
  render(<ErrorPage error={new Error("boom")} reset={reset} />);

  expect(screen.getByRole("heading", { name: "页面加载失败" })).toBeTruthy();
  expect(screen.getByText("当前页面暂时无法加载，请重试。")).toBeTruthy();
  expect(screen.queryByText(/分析结果/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(reset).toHaveBeenCalledOnce();
});
