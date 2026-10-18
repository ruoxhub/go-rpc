import type { FilterRule, GradeRule, JsonScalar, PlatformPolicy } from "../../utils/settings-types";

export type Grade = "p1" | "p2" | "p3";
export type ValueType = "string" | "number" | "boolean";

export interface EditableFilterRule extends Omit<FilterRule, "value"> {
  valueType: ValueType;
  valueRaw: string;
}

export interface EditableGradeRule { maxHoursRaw: string; minViewsRaw: string; }

export interface EditablePlatformPolicy extends Omit<PlatformPolicy, "filters" | Grade> {
  p1: EditableGradeRule[];
  p2: EditableGradeRule[];
  p3: EditableGradeRule[];
  filters: EditableFilterRule[];
}

export function editablePolicy(policy: PlatformPolicy): EditablePlatformPolicy {
  return {
    p1: policy.p1.map(editableGrade),
    p2: policy.p2.map(editableGrade),
    p3: policy.p3.map(editableGrade),
    filters: policy.filters.map((rule) => ({
      valueType: inferValueType(rule.value),
      field: rule.field,
      operator: rule.operator,
      valueRaw: Array.isArray(rule.value) ? rule.value.join(", ") : String(rule.value ?? ""),
    })),
  };
}

export function storedPolicy(policy: EditablePlatformPolicy, gradeValues: Record<Grade, GradeRule[]>, values: FilterRule["value"][]): PlatformPolicy {
  return {
    p1: gradeValues.p1,
    p2: gradeValues.p2,
    p3: gradeValues.p3,
    filters: policy.filters.map((rule, index) => ({
      field: rule.field,
      operator: rule.operator,
      value: values[index],
    })),
  };
}

function editableGrade(rule: GradeRule): EditableGradeRule {
  return { maxHoursRaw: String(rule.max_hours), minViewsRaw: String(rule.min_views) };
}

function inferValueType(value: JsonScalar | JsonScalar[]): ValueType {
  const sample = Array.isArray(value) ? value[0] : value;
  if (typeof sample === "number") return "number";
  if (typeof sample === "boolean") return "boolean";
  return "string";
}
