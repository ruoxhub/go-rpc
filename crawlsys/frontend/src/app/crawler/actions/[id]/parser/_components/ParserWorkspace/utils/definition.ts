import type {
  JsonValue,
  ParserCapabilities,
  ParserDefinition,
  ParserFieldMapping,
  ParserFieldType,
  ParserOutput,
} from "@/api/action-parser/action-parser.types";

import { decodePointer, encodePointer } from "./jsonPointer";

function normalizeJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(normalizeJson);
  if (value !== null && typeof value === "object") {
    const normalized: Record<string, JsonValue> = {};
    for (const key of Object.keys(value).sort()) {
      normalized[key] = normalizeJson(value[key]);
    }
    return normalized;
  }
  return value;
}

export function normalizeDefinition(
  definition: ParserDefinition,
): ParserDefinition {
  return {
    schema_version: 1,
    record_path: definition.record_path,
    output:
      definition.output.mode === "model"
        ? {
            mode: "model",
            ...(definition.output.datatype != null
              ? { datatype: definition.output.datatype }
              : {}),
          }
        : { mode: "json" },
    fields: definition.fields.map((field) => ({
      target: field.target,
      ...(field.source !== undefined ? { source: field.source } : {}),
      ...(field.value !== undefined
        ? { value: normalizeJson(field.value) }
        : {}),
      ...(field.type != null ? { type: field.type } : {}),
      ...(field.default !== undefined
        ? { default: normalizeJson(field.default) }
        : {}),
      ...(field.required === true ? { required: true } : {}),
    })),
  };
}

export function definitionsEqual(
  left: ParserDefinition,
  right: ParserDefinition,
) {
  return (
    JSON.stringify(normalizeDefinition(left)) ===
    JSON.stringify(normalizeDefinition(right))
  );
}

export function emptyParserDefinition(): ParserDefinition {
  return {
    schema_version: 1,
    record_path: "",
    output: { mode: "json" },
    fields: [{ target: "", source: "" }],
  };
}

function isParserFieldType(value: unknown): value is ParserFieldType {
  return (
    value === "string" ||
    value === "integer" ||
    value === "number" ||
    value === "boolean" ||
    value === "datetime" ||
    value === "object" ||
    value === "array"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function assertKeys(value: Record<string, unknown>, allowed: string[]) {
  if (Object.keys(value).some((key) => !allowed.includes(key))) {
    throw new TypeError("unknown ParserDefinition property");
  }
}

export function jsonValueFromUnknown(
  value: unknown,
  budget = { nodes: 0 },
  depth = 0,
): JsonValue {
  budget.nodes += 1;
  if (depth > 64 || budget.nodes > 100_000) {
    throw new TypeError("JSON value exceeds editor limits");
  }
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) =>
      jsonValueFromUnknown(item, budget, depth + 1),
    );
  }
  if (value !== null && typeof value === "object") {
    const result: Record<string, JsonValue> = {};
    for (const [key, item] of Object.entries(value)) {
      result[key] = jsonValueFromUnknown(item, budget, depth + 1);
    }
    return result;
  }
  throw new TypeError("value is not JSON serializable");
}

function definitionFromUnknown(value: unknown): ParserDefinition {
  if (!isRecord(value)) {
    throw new TypeError("Definition must be an object");
  }
  assertKeys(value, ["schema_version", "record_path", "output", "fields"]);
  if (
    value.schema_version !== 1 ||
    typeof value.record_path !== "string" ||
    !isRecord(value.output) ||
    !Array.isArray(value.fields)
  ) {
    throw new TypeError("Definition shape is invalid");
  }
  if (value.fields.length > 500) {
    throw new TypeError("Definition has too many fields");
  }

  assertKeys(value.output, ["mode", "datatype"]);
  if (value.output.mode !== "json" && value.output.mode !== "model") {
    throw new TypeError("output.mode is invalid");
  }
  const output: ParserOutput = { mode: value.output.mode };
  if (Object.hasOwn(value.output, "datatype")) {
    if (
      value.output.datatype !== null &&
      typeof value.output.datatype !== "string"
    ) {
      throw new TypeError("output.datatype is invalid");
    }
    output.datatype = value.output.datatype;
  }

  const budget = { nodes: 0 };
  const fields = value.fields.map((item): ParserFieldMapping => {
    if (!isRecord(item)) {
      throw new TypeError("field mapping must be an object");
    }
    assertKeys(item, [
      "target",
      "source",
      "value",
      "type",
      "default",
      "required",
    ]);
    if (typeof item.target !== "string") {
      throw new TypeError("field.target is invalid");
    }
    const field: ParserFieldMapping = { target: item.target };
    if (Object.hasOwn(item, "source")) {
      if (typeof item.source !== "string") {
        throw new TypeError("field.source is invalid");
      }
      field.source = item.source;
    }
    if (Object.hasOwn(item, "value")) {
      field.value = jsonValueFromUnknown(item.value, budget);
    }
    if (Object.hasOwn(item, "type")) {
      if (item.type !== null && !isParserFieldType(item.type)) {
        throw new TypeError("field.type is invalid");
      }
      field.type = item.type;
    }
    if (Object.hasOwn(item, "default")) {
      field.default = jsonValueFromUnknown(item.default, budget);
    }
    if (Object.hasOwn(item, "required")) {
      if (typeof item.required !== "boolean") {
        throw new TypeError("field.required is invalid");
      }
      field.required = item.required;
    }
    return field;
  });
  return {
    schema_version: 1,
    record_path: value.record_path,
    output,
    fields,
  };
}

export function parseDefinitionJson(source: string) {
  const parsed: unknown = JSON.parse(source);
  return definitionFromUnknown(parsed);
}

export function formatDefinitionJson(definition: ParserDefinition) {
  return JSON.stringify(normalizeDefinition(definition), null, 2);
}

export interface DefinitionError {
  code: string;
  path: string;
}

export function validateDefinition(
  definition: ParserDefinition,
  capabilities: ParserCapabilities,
) {
  const errors: DefinitionError[] = [];
  try {
    decodePointer(definition.record_path);
  } catch {
    errors.push({ code: "invalid_record_path", path: "record_path" });
  }

  const modelFields = definition.output.datatype
    ? (capabilities.model_fields[definition.output.datatype] ?? [])
    : [];
  if (
    definition.output.mode === "model" &&
    (!definition.output.datatype ||
      !capabilities.model_datatypes.includes(definition.output.datatype))
  ) {
    errors.push({ code: "invalid_datatype", path: "output.datatype" });
  }
  if (
    definition.output.mode === "json" &&
    definition.output.datatype !== undefined &&
    definition.output.datatype !== null
  ) {
    errors.push({ code: "invalid_datatype", path: "output.datatype" });
  }
  if (definition.fields.length < 1 || definition.fields.length > 500) {
    errors.push({ code: "invalid_field_count", path: "fields" });
  }

  const targets: Array<{ index: number; tokens: string[] }> = [];
  definition.fields.forEach((field, index) => {
    const base = `fields.${index}`;
    const hasSource = field.source !== undefined;
    const hasValue = field.value !== undefined;
    if (hasSource === hasValue) {
      errors.push({ code: "source_value_exclusive", path: base });
    }
    if (hasSource) {
      try {
        decodePointer(field.source ?? "");
      } catch {
        errors.push({ code: "invalid_source", path: `${base}.source` });
      }
    }
    try {
      const tokens = decodePointer(field.target);
      if (tokens.length === 0) throw new Error("root target");
      targets.push({ index, tokens });
      const modelField = modelFields.find(
        (item) => item.target === field.target,
      );
      if (
        definition.output.mode === "model" &&
        (tokens.length !== 1 ||
          tokens[0] === "datatype" ||
          modelField === undefined)
      ) {
        errors.push({ code: "invalid_model_target", path: `${base}.target` });
      }
      if (
        definition.output.mode === "model" &&
        modelField !== undefined &&
        field.type !== undefined &&
        field.type !== null &&
        !modelField.value_types.includes(field.type)
      ) {
        errors.push({
          code: "incompatible_field_type",
          path: `${base}.type`,
        });
      }
    } catch {
      errors.push({ code: "invalid_target", path: `${base}.target` });
    }
    if (
      field.type !== undefined &&
      field.type !== null &&
      !capabilities.field_types.includes(field.type)
    ) {
      errors.push({ code: "invalid_field_type", path: `${base}.type` });
    }
  });

  targets.forEach((target, position) => {
    const prior = targets.slice(0, position);
    if (
      prior.some(
        (item) =>
          encodePointer(item.tokens) === encodePointer(target.tokens),
      )
    ) {
      errors.push({
        code: "duplicate_target",
        path: `fields.${target.index}.target`,
      });
    } else if (
      prior.some((item) => {
        const shortest = Math.min(item.tokens.length, target.tokens.length);
        return item.tokens
          .slice(0, shortest)
          .every((token, index) => target.tokens[index] === token);
      })
    ) {
      errors.push({
        code: "target_ancestor_conflict",
        path: `fields.${target.index}.target`,
      });
    }
  });
  return errors;
}
