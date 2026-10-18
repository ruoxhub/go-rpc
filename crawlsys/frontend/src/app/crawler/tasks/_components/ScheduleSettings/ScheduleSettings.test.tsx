// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScheduleFormValue } from "../TaskForm/types/schedule";
import { ScheduleSettings } from "./index";

const manualScheduleValue: ScheduleFormValue = {
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

const onceScheduleValue: ScheduleFormValue = {
  ...manualScheduleValue,
  type: "once",
  run_at: "2026-08-15T10:00",
};

const intervalScheduleValue: ScheduleFormValue = {
  ...manualScheduleValue,
  type: "interval",
  interval_seconds: "300",
};

const cronScheduleValue: ScheduleFormValue = {
  ...manualScheduleValue,
  type: "cron",
  cron_expression: "0 * * * *",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ScheduleSettings 组件", () => {
  let onChange: (value: ScheduleFormValue) => void;

  beforeEach(() => {
    onChange = vi.fn() as unknown as (value: ScheduleFormValue) => void;
  });

  it("支持在 manual / once / interval / cron 四种模式之间切换", () => {
    const { rerender } = render(
      <ScheduleSettings
        value={manualScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );

    const manualRadio = screen.getByRole("radio", { name: "手动触发" }) as HTMLInputElement;
    expect(manualRadio.checked).toBe(true);
    expect(screen.queryByLabelText("单次执行时间")).toBeNull();
    expect(screen.queryByLabelText("执行间隔（秒）")).toBeNull();
    expect(screen.queryByLabelText("Cron 表达式")).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "Cron" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ type: "cron" }),
    );

    rerender(
      <ScheduleSettings
        value={cronScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );
    expect(screen.getByLabelText("Cron 表达式")).toBeTruthy();
    expect(screen.queryByLabelText("执行间隔（秒）")).toBeNull();
  });

  it("once 模式下显示 datetime-local 输入框", () => {
    render(
      <ScheduleSettings
        value={onceScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );
    expect(screen.getByLabelText("单次执行时间")).toBeTruthy();
  });

  it("interval 模式下显示 NumberInput 间隔输入", () => {
    render(
      <ScheduleSettings
        value={intervalScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );
    expect(screen.getByPlaceholderText("300")).toBeTruthy();
  });

  it("Cron 模式下支持点击预设按钮填入 Cron 表达式", () => {
    render(
      <ScheduleSettings
        value={cronScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );

    const hourlyPreset = screen.getByRole("button", { name: "每小时" });
    fireEvent.click(hourlyPreset);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ cron_expression: "0 * * * *" }),
    );
  });

  it("Cron 表达式格式无效或接口报错时显示错误预览", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        { detail: "Invalid cron expression format" },
        { status: 422 },
      ),
    );

    render(
      <ScheduleSettings
        value={{ ...cronScheduleValue, cron_expression: "invalid cron" }}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Invalid cron expression format|Cron 表达式格式无效/i)).toBeTruthy();
    });
  });

  it("显示重试策略配置字段并使用 NumberInput", () => {
    render(
      <ScheduleSettings
        value={manualScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText("最大重试次数")).toBeTruthy();
    expect(screen.getByLabelText("重试基础间隔（秒）")).toBeTruthy();
    expect(screen.getByLabelText("重试退避系数")).toBeTruthy();
    expect(screen.getByLabelText("最大重试间隔（秒）")).toBeTruthy();
  });

  it("为定时模式显示生效范围和最大执行次数", () => {
    render(
      <ScheduleSettings
        value={intervalScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );
    expect(screen.getByLabelText("生效时间")).toBeTruthy();
    expect(screen.getByLabelText("失效时间")).toBeTruthy();
    expect(screen.getByLabelText("最多执行次数").getAttribute("type")).toBe("text");
  });

  it("校验 label 与 input 的 aria 关联", () => {
    render(
      <ScheduleSettings
        value={cronScheduleValue}
        timezone="Asia/Shanghai"
        onChange={onChange}
      />,
    );

    const input = screen.getByLabelText("Cron 表达式");
    expect(input.id).toBeTruthy();
    const label = screen.getByText("Cron 表达式", { selector: "label" });
    expect(label.getAttribute("for")).toBe(input.id);
  });
});
