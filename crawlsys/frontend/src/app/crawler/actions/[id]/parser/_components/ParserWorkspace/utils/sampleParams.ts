import Ajv, { type ValidateFunction } from "ajv";

import type { JsonValue } from "@/api/action-parser/action-parser.types";
import type { ActionSchemaResponse } from "@/api/task-metadata/task-metadata.types";

import { jsonValueFromUnknown } from "./definition";

export interface BasicParamField {
  name: string;
  required: boolean;
  kind: "string" | "boolean" | "integer" | "number" | "enum" | "array";
  itemKind?: "string" | "boolean" | "integer" | "number" | "enum";
  options?: JsonValue[];
  description?: string;
}

export type ParamsFormDescription =
  | {
      mode: "basic";
      fields: BasicParamField[];
      initial: Record<string, JsonValue>;
    }
  | {
      mode: "json";
      reason: "missing" | "root" | "required-complex" | "false-schema";
      initial: Record<string, JsonValue>;
    };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function scalarKind(schema: Record<string, unknown>) {
  if (
    Array.isArray(schema.enum) &&
    schema.enum.length > 0 &&
    schema.enum.every(
      (item) =>
        item === null || ["string", "number", "boolean"].includes(typeof item),
    )
  ) {
    return "enum" as const;
  }
  return schema.type === "string" ||
    schema.type === "boolean" ||
    schema.type === "integer" ||
    schema.type === "number"
    ? schema.type
    : null;
}

function enumOptions(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => jsonValueFromUnknown(item))
    : undefined;
}

function basicField(
  name: string,
  schema: unknown,
  required: boolean,
): BasicParamField | null {
  if (!isRecord(schema)) return null;
  const scalar = scalarKind(schema);
  if (scalar !== null) {
    return {
      name,
      required,
      kind: scalar,
      options: scalar === "enum" ? enumOptions(schema.enum) : undefined,
      description:
        typeof schema.description === "string" ? schema.description : undefined,
    } satisfies BasicParamField;
  }
  if (schema.type !== "array" || !isRecord(schema.items)) return null;
  const itemKind = scalarKind(schema.items);
  if (itemKind === null) return null;
  return {
    name,
    required,
    kind: "array",
    itemKind,
    options: itemKind === "enum" ? enumOptions(schema.items.enum) : undefined,
    description:
      typeof schema.description === "string" ? schema.description : undefined,
  } satisfies BasicParamField;
}

function defaults(schema: Record<string, unknown>) {
  const initial: Record<string, JsonValue> = {};
  if (!isRecord(schema.properties)) return initial;
  for (const [name, property] of Object.entries(schema.properties)) {
    if (isRecord(property) && Object.hasOwn(property, "default")) {
      initial[name] = jsonValueFromUnknown(property.default);
    }
  }
  return initial;
}

export function describeBasicParams(
  schema: ActionSchemaResponse["schema"] | null | undefined,
): ParamsFormDescription {
  if (schema == null || (Array.isArray(schema) && schema.length === 0)) {
    return { mode: "json", reason: "missing", initial: {} };
  }
  if (schema === false) {
    return { mode: "json", reason: "false-schema", initial: {} };
  }
  if (
    !isRecord(schema) ||
    schema.type !== "object" ||
    !isRecord(schema.properties)
  ) {
    return { mode: "json", reason: "root", initial: {} };
  }
  const required = new Set(
    Array.isArray(schema.required)
      ? schema.required.filter(
          (item): item is string => typeof item === "string",
        )
      : [],
  );
  const fields = Object.entries(schema.properties)
    .map(([name, value]) => basicField(name, value, required.has(name)))
    .filter((field): field is BasicParamField => field !== null);
  if (
    Object.entries(schema.properties).some(
      ([name, value]) =>
        required.has(name) && basicField(name, value, true) === null,
    )
  ) {
    return {
      mode: "json",
      reason: "required-complex",
      initial: defaults(schema),
    };
  }
  return { mode: "basic", fields, initial: defaults(schema) };
}

const ajv = new Ajv({ allErrors: true, strict: false });

export function compileParamsValidator(
  schema: ActionSchemaResponse["schema"] | null | undefined,
) {
  const effectiveSchema =
    schema == null || (Array.isArray(schema) && schema.length === 0)
      ? { type: "object" }
      : schema;
  let validate: ValidateFunction;
  try {
    validate = ajv.compile(effectiveSchema);
  } catch {
    return () => [{ path: "$", validator: "schema" }];
  }
  return (params: Record<string, JsonValue>) => {
    if (validate(params)) return [];
    return (validate.errors ?? []).map((error) => ({
      path:
        error.keyword === "required" &&
        typeof error.params.missingProperty === "string"
          ? `${error.instancePath}/${error.params.missingProperty}`
          : error.instancePath || "$",
      validator: error.keyword,
    }));
  };
}
