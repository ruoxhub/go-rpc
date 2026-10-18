import { describe, expect, it } from "vitest";

import type {
  ParserCapabilities,
  ParserDefinition,
} from "@/api/action-parser/action-parser.types";

import {
  definitionsEqual,
  emptyParserDefinition,
  formatDefinitionJson,
  normalizeDefinition,
  parseDefinitionJson,
  validateDefinition,
} from "./definition";

const definition: ParserDefinition = {
  schema_version: 1,
  record_path: "/data/items",
  output: { mode: "model", datatype: "post" },
  fields: [
    {
      target: "/content",
      source: "/content",
      type: "string",
      default: { b: 2, a: 1 },
      required: true,
    },
    { target: "/id", source: "/id" },
  ],
};

describe("Definition 规范化", () => {
  it("忽略 JSON 空白和对象属性顺序", () => {
    const reordered = JSON.parse(`{
      "fields": [
        {"required": true, "default": {"a": 1, "b": 2}, "type": "string", "source": "/content", "target": "/content"},
        {"source": "/id", "target": "/id"}
      ],
      "output": {"datatype": "post", "mode": "model"},
      "record_path": "/data/items",
      "schema_version": 1
    }`) as ParserDefinition;

    expect(definitionsEqual(definition, reordered)).toBe(true);
    expect(normalizeDefinition(reordered)).toEqual(normalizeDefinition(definition));
  });

  it("保留 fields 数组顺序的语义差异", () => {
    const reorderedFields: ParserDefinition = {
      ...definition,
      fields: [...definition.fields].reverse(),
    };

    expect(definitionsEqual(definition, reorderedFields)).toBe(false);
  });

  it("区分显式 null default 和缺省 default", () => {
    const explicitNull: ParserDefinition = {
      ...definition,
      fields: [{ target: "/id", source: "/id", default: null }],
    };
    const absent: ParserDefinition = {
      ...definition,
      fields: [{ target: "/id", source: "/id" }],
    };

    expect(definitionsEqual(explicitNull, absent)).toBe(false);
  });

  it("将可缺省的 null 和 false 规范为同一语义", () => {
    const explicitDefaults: ParserDefinition = {
      schema_version: 1,
      record_path: "",
      output: { mode: "json", datatype: null },
      fields: [
        { target: "/id", source: "/id", type: null, required: false },
      ],
    };
    const absentDefaults: ParserDefinition = {
      schema_version: 1,
      record_path: "",
      output: { mode: "json" },
      fields: [{ target: "/id", source: "/id" }],
    };

    expect(definitionsEqual(explicitDefaults, absentDefaults)).toBe(true);
  });
});

const capabilities: ParserCapabilities = {
  model_datatypes: ["post"],
  field_types: ["string", "integer", "number", "boolean"],
  model_fields: {
    post: [
      { target: "/id", required: true, value_types: ["string", "integer"] },
      { target: "/content", required: false, value_types: ["string"] },
    ],
  },
};

const validDefinition: ParserDefinition = {
  schema_version: 1,
  record_path: "/data/items",
  output: { mode: "json" },
  fields: [
    { target: "/id", source: "/id", type: "string", required: true },
    { target: "/active", value: true, type: "boolean" },
  ],
};

describe("Definition JSON 边界", () => {
  it("提供允许暂时无效的最小可编辑初值", () => {
    expect(emptyParserDefinition()).toEqual({
      schema_version: 1,
      record_path: "",
      output: { mode: "json" },
      fields: [{ target: "", source: "" }],
    });
  });

  it("解析时重建允许字段并保留 fields 顺序及显式 null default", () => {
    const source = JSON.stringify({
      fields: [
        { source: "/b", target: "/b" },
        { default: null, source: "/a", target: "/a" },
      ],
      output: { datatype: null, mode: "json" },
      record_path: "/data",
      schema_version: 1,
    });

    const parsed = parseDefinitionJson(source);

    expect(parsed.fields.map((field) => field.target)).toEqual(["/b", "/a"]);
    expect(parsed.fields[1]).toHaveProperty("default", null);
    expect(normalizeDefinition(parsed).output).toEqual({ mode: "json" });
  });

  it("格式化为规范化且稳定缩进的 JSON", () => {
    const formatted = formatDefinitionJson(validDefinition);
    expect(formatted).toBe(
      JSON.stringify(normalizeDefinition(validDefinition), null, 2),
    );
    expect(parseDefinitionJson(formatted)).toEqual(
      normalizeDefinition(validDefinition),
    );
  });

  it.each([
    "null",
    '{"schema_version":1,"record_path":"","output":{"mode":"json"},"fields":[],"extra":true}',
    '{"schema_version":2,"record_path":"","output":{"mode":"json"},"fields":[]}',
    '{"schema_version":1,"record_path":"","output":{"mode":"json","extra":true},"fields":[]}',
    '{"schema_version":1,"record_path":"","output":{"mode":"json"},"fields":[{"target":"/id","source":"/id","extra":true}]}',
  ])("拒绝不受信任的 Definition 结构：%s", (source) => {
    expect(() => parseDefinitionJson(source)).toThrow(TypeError);
  });

  it("拒绝超过编辑器节点预算的 JSON 值", () => {
    const deeplyNested = Array.from({ length: 66 }).reduce<unknown>(
      (value) => [value],
      null,
    );
    const source = JSON.stringify({
      schema_version: 1,
      record_path: "",
      output: { mode: "json" },
      fields: [{ target: "/value", value: deeplyNested }],
    });

    expect(() => parseDefinitionJson(source)).toThrow(
      "JSON value exceeds editor limits",
    );
  });
});

describe("Definition 校验", () => {
  it("接受合法 Definition", () => {
    expect(validateDefinition(validDefinition, capabilities)).toEqual([]);
  });

  it("按固定顺序报告 record、output、数量和字段错误", () => {
    const invalid: ParserDefinition = {
      schema_version: 1,
      record_path: "not-absolute",
      output: { mode: "model", datatype: "unknown" },
      fields: [],
    };

    expect(validateDefinition(invalid, capabilities)).toEqual([
      { code: "invalid_record_path", path: "record_path" },
      { code: "invalid_datatype", path: "output.datatype" },
      { code: "invalid_field_count", path: "fields" },
    ]);
  });

  it.each([
    [{ target: "/id" }, "source_value_exclusive", "fields.0"],
    [
      { target: "/id", source: "/id", value: 1 },
      "source_value_exclusive",
      "fields.0",
    ],
    [
      { target: "/id", source: "bad" },
      "invalid_source",
      "fields.0.source",
    ],
    [
      { target: "bad", source: "/id" },
      "invalid_target",
      "fields.0.target",
    ],
    [
      { target: "/id", source: "/id", type: "array" },
      "invalid_field_type",
      "fields.0.type",
    ],
  ] as const)("校验字段 shape：%s", (field, code, path) => {
    const invalid: ParserDefinition = {
      ...validDefinition,
      fields: [field],
    };
    expect(validateDefinition(invalid, capabilities)).toContainEqual({
      code,
      path,
    });
  });

  it("报告重复 target 和祖先冲突", () => {
    const invalid: ParserDefinition = {
      ...validDefinition,
      fields: [
        { target: "/profile", source: "/profile" },
        { target: "/profile", source: "/other" },
        { target: "/profile/name", source: "/name" },
      ],
    };

    expect(validateDefinition(invalid, capabilities)).toEqual(
      expect.arrayContaining([
        { code: "duplicate_target", path: "fields.1.target" },
        { code: "target_ancestor_conflict", path: "fields.2.target" },
      ]),
    );
  });

  it("限制 model 顶层 target、禁止 /datatype 并校验字段类型", () => {
    const invalid: ParserDefinition = {
      schema_version: 1,
      record_path: "/data",
      output: { mode: "model", datatype: "post" },
      fields: [
        { target: "/datatype", source: "/type" },
        { target: "/nested/id", source: "/id" },
        { target: "/content", source: "/content", type: "integer" },
      ],
    };

    expect(validateDefinition(invalid, capabilities)).toEqual(
      expect.arrayContaining([
        { code: "invalid_model_target", path: "fields.0.target" },
        { code: "invalid_model_target", path: "fields.1.target" },
        { code: "incompatible_field_type", path: "fields.2.type" },
      ]),
    );
  });

  it("json output 不接受非空 datatype", () => {
    expect(
      validateDefinition(
        { ...validDefinition, output: { mode: "json", datatype: "post" } },
        capabilities,
      ),
    ).toContainEqual({ code: "invalid_datatype", path: "output.datatype" });
  });
});
