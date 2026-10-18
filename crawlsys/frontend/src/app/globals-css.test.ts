import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("全局触控媒体查询", () => {
  it("使用 any-pointer 覆盖混合鼠标与触屏设备", () => {
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

    expect(css).toContain("@media (any-pointer: coarse)");
    expect(css).not.toContain("@media (pointer: coarse)");
  });
});
