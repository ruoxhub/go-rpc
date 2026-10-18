import { describe, expect, it } from "vitest";

import type { ActionSchemaResponse } from "@/api/task-metadata/task-metadata.types";

import { compileParamsValidator, describeBasicParams } from "./sampleParams";

const unsupportedSchemas: Array<
  [ActionSchemaResponse["schema"], "root" | "false-schema"]
> = [
  [true, "root"],
  [{ type: "array" }, "root"],
  [[{ name: "legacy" }], "root"],
  [false, "false-schema"],
];

describe("基础参数 Schema 描述", () => {
  it.each([undefined, null, []])("将缺省 Schema 降级为 JSON：%s", (schema) => {
    expect(describeBasicParams(schema)).toEqual({
      mode: "json",
      reason: "missing",
      initial: {},
    });
  });

  it("描述 string、boolean、数字、enum 和标量数组", () => {
    const description = describeBasicParams({
      type: "object",
      required: ["query", "limit"],
      properties: {
        query: { type: "string", description: "关键词", default: "cats" },
        safe: { type: "boolean" },
        limit: { type: "integer", default: 20 },
        score: { type: "number" },
        order: { enum: ["asc", "desc"] },
        tags: { type: "array", items: { type: "string" } },
        levels: { type: "array", items: { enum: [1, 2] } },
      },
    });

    expect(description).toMatchObject({
      mode: "basic",
      initial: { query: "cats", limit: 20 },
      fields: [
        { name: "query", required: true, kind: "string" },
        { name: "safe", required: false, kind: "boolean" },
        { name: "limit", required: true, kind: "integer" },
        { name: "score", required: false, kind: "number" },
        { name: "order", required: false, kind: "enum" },
        {
          name: "tags",
          required: false,
          kind: "array",
          itemKind: "string",
        },
        {
          name: "levels",
          required: false,
          kind: "array",
          itemKind: "enum",
        },
      ],
    });
  });

  it("保留未渲染复杂可选字段的默认值", () => {
    expect(
      describeBasicParams({
        type: "object",
        properties: {
          query: { type: "string" },
          options: { type: "object", default: { locale: "zh-CN" } },
        },
      }),
    ).toMatchObject({
      mode: "basic",
      fields: [{ name: "query" }],
      initial: { options: { locale: "zh-CN" } },
    });
  });

  it("必填复杂字段降级到 JSON 编辑", () => {
    expect(
      describeBasicParams({
        type: "object",
        required: ["payload"],
        properties: { payload: { type: "object", default: { id: 1 } } },
      }),
    ).toEqual({
      mode: "json",
      reason: "required-complex",
      initial: { payload: { id: 1 } },
    });
  });

  it.each(unsupportedSchemas)("安全降级不支持的根 Schema：%s", (schema, reason) => {
    expect(describeBasicParams(schema)).toEqual({
      mode: "json",
      reason,
      initial: {},
    });
  });
});

describe("参数 Ajv validator", () => {
  it("将 required 和字段错误映射为稳定路径", () => {
    const validate = compileParamsValidator({
      type: "object",
      required: ["query"],
      properties: {
        query: { type: "string" },
        limit: { type: "integer" },
      },
    });

    expect(validate({ limit: "many" })).toEqual(
      expect.arrayContaining([
        { path: "/query", validator: "required" },
        { path: "/limit", validator: "type" },
      ]),
    );
    expect(validate({ query: "cats", limit: 10 })).toEqual([]);
  });

  it("缺省和空 legacy Schema 接受对象参数", () => {
    expect(compileParamsValidator(undefined)({ query: "cats" })).toEqual([]);
    expect(compileParamsValidator([])({ query: "cats" })).toEqual([]);
  });

  it("服务端遗留非法或非空数组 Schema 返回稳定 schema 错误", () => {
    expect(compileParamsValidator([{ name: "legacy" }])({})).toEqual([
      { path: "$", validator: "schema" },
    ]);
    expect(
      compileParamsValidator({ type: "definitely-invalid" })({}),
    ).toEqual([{ path: "$", validator: "schema" }]);
  });
});
