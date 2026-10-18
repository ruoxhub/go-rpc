import { describe, expect, it } from "vitest";

import {
  decodePointer,
  encodePointer,
  relativePointer,
  representativeRecord,
  resolvePointer,
} from "./jsonPointer";

describe("JSON Pointer", () => {
  it("编码和解码 RFC 6901 转义", () => {
    expect(encodePointer(["data", "a/b", "x~y"])).toBe(
      "/data/a~1b/x~0y",
    );
    expect(decodePointer("/data/a~1b/x~0y")).toEqual([
      "data",
      "a/b",
      "x~y",
    ]);
    expect(encodePointer([])).toBe("");
    expect(decodePointer("")).toEqual([]);
  });

  it.each(["relative", "/bad~2escape", "/bad~"])(
    "拒绝非法 pointer：%s",
    (pointer) => {
      expect(() => decodePointer(pointer)).toThrow();
    },
  );

  it("解析对象和非负规范数组索引", () => {
    const root = { data: [{ id: 1 }, { id: 2 }] };
    expect(resolvePointer(root, "/data/1/id")).toBe(2);
    expect(resolvePointer(root, "/data/-1")).toBeUndefined();
    expect(resolvePointer(root, "/data/01")).toBeUndefined();
    expect(resolvePointer(root, "/missing")).toBeUndefined();
  });

  it("数组记录返回首项并把代表索引加入绝对基址", () => {
    expect(
      representativeRecord({ "a/b": [{ id: 1 }] }, "/a~1b"),
    ).toEqual({ value: { id: 1 }, absoluteBase: "/a~1b/0" });
    expect(representativeRecord({ data: [] }, "/data")).toBeNull();
  });

  it("对象记录保持 record path 为绝对基址", () => {
    expect(representativeRecord({ data: { id: 1 } }, "/data")).toEqual({
      value: { id: 1 },
      absoluteBase: "/data",
    });
    expect(representativeRecord({ data: "text" }, "/data")).toBeNull();
  });

  it.each([
    ["/data/items/0", "/data/items/0/content/id", "/content/id"],
    ["/data/item", "/data/item/0/value", "/0/value"],
    ["/data/items", "/outside/value", null],
    ["/data/item", "/data/item", ""],
  ])("只从明确基址计算相对 pointer", (base, node, expected) => {
    expect(relativePointer(base, node)).toBe(expected);
  });
});
