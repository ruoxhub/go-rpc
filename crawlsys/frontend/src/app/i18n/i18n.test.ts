import { describe, expect, it } from "vitest";

import { en } from "./messages/en";
import { zhCN } from "./messages/zh-CN";
import { getAppLocale, t } from ".";

describe("i18n", () => {
  it("默认使用中文并插值 typed message", () => {
    expect(getAppLocale()).toBe("zh-CN");
    expect(t("api.http", { status: 503 })).toBe("采集服务请求失败（503）");
  });

  it("中英文消息键完全一致", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zhCN).sort());
  });

  it("调度文案支持时区和运行摘要插值", () => {
    expect(t("tasks.schedulePreviewTitle", { timezone: "Asia/Shanghai" })).toBe(
      "未来执行时间（Asia/Shanghai）",
    );
    expect(t("tasks.scheduleInterval", { seconds: 300 })).toBe("每 300 秒");
  });

  it("Parser 页面文案支持 Action 标题和首屏区域", () => {
    expect(t("parser.title", { action: "getUser" })).toBe(
      "getUser · Parser 配置",
    );
    expect([
      t("parser.section.workspace"),
      t("parser.section.samples"),
      t("parser.section.history"),
    ]).toEqual(["工作台", "响应样例", "版本历史"]);
  });
});
