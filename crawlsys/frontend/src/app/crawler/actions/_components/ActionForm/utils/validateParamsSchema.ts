import Ajv from "ajv";
import { t } from "../../../../../i18n";
import Ajv2020 from "ajv/dist/2020";

const ajvOptions = { strict: false, validateFormats: false } as const;
const draft7Ajv = new Ajv(ajvOptions);
const draft2020Ajv = new Ajv2020(ajvOptions);
const DRAFT_7_SCHEMA_PATTERN = /json-schema\.org\/draft-07\/schema#?$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validateLegacyParams(params: unknown[]) {
  for (const [index, item] of params.entries()) {
    if (!isRecord(item)) return t("actions.legacyObject", { index: index + 1 });
    if (typeof item.name !== "string" || !item.name.trim()) {
      return t("actions.legacyName", { index: index + 1 });
    }
    if (item.type !== undefined && typeof item.type !== "string") {
      return t("actions.legacyType", { index: index + 1 });
    }
    if (item.required !== undefined && typeof item.required !== "boolean") {
      return t("actions.legacyRequired", { index: index + 1 });
    }
    if (item.description !== undefined && typeof item.description !== "string") {
      return t("actions.legacyDescription", { index: index + 1 });
    }
  }
}

export function validateParamsSchema(source: string) {
  let schema: unknown;
  try {
    schema = JSON.parse(source);
  } catch {
    return t("actions.validJson");
  }
  if (typeof schema === "boolean") return;
  if (Array.isArray(schema)) return validateLegacyParams(schema);
  if (!isRecord(schema)) return t("actions.schemaRoot");
  try {
    const schemaUri = typeof schema.$schema === "string" ? schema.$schema : "";
    const validator = DRAFT_7_SCHEMA_PATTERN.test(schemaUri)
      ? draft7Ajv
      : draft2020Ajv;
    validator.compile(schema);
  } catch {
    return t("actions.invalidSchema");
  }
}
