import { NumberInput } from "../../../_components/NumberInput";
import { Button } from "../../../_components/ui/button";
import { Input } from "../../../_components/ui/input";
import { Select } from "../../../_components/ui/select";
import { t } from "../../../i18n";
import type { FilterOperator } from "../../utils/settings-types";
import type { EditableFilterRule, ValueType } from "./types";

const comparisonOperators: FilterOperator[] = ["=", "!=", ">", ">=", "<", "<=", "in", "exists"];
const equalityOperators: FilterOperator[] = ["=", "!=", "in", "exists"];
const plainFields = ["view_count", "pub_time", "download_time", "created_time"];

function requiredType(field: string): ValueType | null {
  if (field === "view_count") return "number";
  if (["pub_time", "download_time", "created_time"].includes(field)) return "string";
  return null;
}

export function FilterRulesEditor({ rules, errors, onChange }: { rules: EditableFilterRule[]; errors: Record<string, string>; onChange: (rules: EditableFilterRule[]) => void }) {
  function update(index: number, patch: Partial<EditableFilterRule>) {
    onChange(rules.map((rule, ruleIndex) => {
      if (ruleIndex !== index) return rule;
      const next = { ...rule, ...patch };
      if (patch.operator === "exists") next.valueRaw = "";
      return next;
    }));
  }

  function changeOperator(index: number, operator: FilterOperator) {
    const rule = rules[index];
    let valueRaw = operator === "exists" ? "" : rule.valueRaw;
    if (rule.operator === "in" && operator !== "in" && operator !== "exists") valueRaw = rule.valueRaw.split(",").map((item) => item.trim()).find(Boolean) ?? "";
    if (rule.valueType === "boolean" && operator !== "in" && operator !== "exists" && valueRaw !== "true" && valueRaw !== "false") valueRaw = "false";
    update(index, { operator, valueRaw });
  }

  function changeValueType(index: number, valueType: ValueType) {
    const rule = rules[index];
    const operator = valueType === "number" || equalityOperators.includes(rule.operator) ? rule.operator : "=";
    const valueRaw = valueType === "boolean" && operator !== "in" && rule.valueRaw !== "true" && rule.valueRaw !== "false" ? "false" : rule.valueRaw;
    update(index, { valueType, operator, valueRaw });
  }

  return (
    <section aria-labelledby="filter-rules" className="rounded-lg border border-border bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 id="filter-rules" className="font-semibold text-foreground">{t("settings.policy.filters.title")}</h3>
        <Button type="button" variant="link" size="sm" onClick={() => onChange([...rules, { field: "view_count", operator: ">", valueRaw: "0", valueType: "number" }])} className="h-auto p-0 text-sm font-medium text-primary hover:underline">{t("settings.policy.filters.add")}</Button>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{t("settings.policy.filters.fieldHint")}</p>
      <datalist id="policy-filter-fields">{plainFields.map((field) => <option key={field} value={field} />)}<option value="extend_data.aigcLabelType" /></datalist>
      <div className="mt-3 space-y-3">
        {rules.length === 0 ? <p className="text-sm text-muted-foreground">{t("settings.policy.filters.empty")}</p> : null}
        {rules.map((rule, index) => (
          <div key={index} className="grid gap-3 rounded-md border border-border p-3 lg:grid-cols-[minmax(12rem,2fr)_minmax(6rem,1fr)_minmax(6rem,1fr)_minmax(10rem,2fr)_auto]">
            <label className="grid gap-1 text-xs font-medium text-foreground">{t("settings.policy.filters.field")}
              <Input aria-label={`${t("settings.policy.filters.field")} ${index + 1}`} aria-invalid={Boolean(errors[`filters.${index}.field`])} aria-describedby={errors[`filters.${index}.field`] ? `filter-${index}-field-error` : undefined} list="policy-filter-fields" value={rule.field} onChange={(event) => { const field = event.target.value; const valueType = requiredType(field) ?? rule.valueType; const allowed = valueType === "number" || ["pub_time", "download_time", "created_time"].includes(field) ? comparisonOperators : equalityOperators; update(index, { field, valueType, operator: allowed.includes(rule.operator) ? rule.operator : "=" }); }} className="bg-background" />
              {errors[`filters.${index}.field`] ? <span id={`filter-${index}-field-error`} role="alert" className="text-destructive">{errors[`filters.${index}.field`]}</span> : null}
            </label>
            <label className="grid gap-1 text-xs font-medium text-foreground">{t("settings.policy.filters.operator")}
              <Select aria-label={`${t("settings.policy.filters.operator")} ${index + 1}`} aria-invalid={Boolean(errors[`filters.${index}.operator`])} aria-describedby={errors[`filters.${index}.operator`] ? `filter-${index}-operator-error` : undefined} value={rule.operator} onChange={(event) => changeOperator(index, event.target.value as FilterOperator)} className="bg-background">{(rule.valueType === "number" || ["pub_time", "download_time", "created_time"].includes(rule.field) ? comparisonOperators : equalityOperators).map((operator) => <option key={operator}>{operator}</option>)}</Select>
              {errors[`filters.${index}.operator`] ? <span id={`filter-${index}-operator-error`} role="alert" className="text-destructive">{errors[`filters.${index}.operator`]}</span> : null}
            </label>
            <label className="grid gap-1 text-xs font-medium text-foreground">{t("settings.policy.filters.valueType")}
              <Select aria-label={`${t("settings.policy.filters.valueType")} ${index + 1}`} value={rule.valueType} disabled={rule.operator === "exists" || requiredType(rule.field) !== null} onChange={(event) => changeValueType(index, event.target.value as ValueType)} className="bg-background">
                <option value="string">{t("settings.policy.type.string")}</option><option value="number">{t("settings.policy.type.number")}</option><option value="boolean">{t("settings.policy.type.boolean")}</option>
              </Select>
            </label>
            <label className="grid gap-1 text-xs font-medium text-foreground">{t("settings.policy.filters.value")}
              {rule.valueType === "boolean" && rule.operator !== "in" ? <Select aria-label={`${t("settings.policy.filters.value")} ${index + 1}`} aria-invalid={Boolean(errors[`filters.${index}.value`])} aria-describedby={errors[`filters.${index}.value`] ? `filter-${index}-value-error` : undefined} value={rule.valueRaw === "true" ? "true" : "false"} disabled={rule.operator === "exists"} onChange={(event) => update(index, { valueRaw: event.target.value })} className="bg-background"><option value="true">true</option><option value="false">false</option></Select> : rule.valueType === "number" ? <NumberInput aria-label={`${t("settings.policy.filters.value")} ${index + 1}`} aria-invalid={Boolean(errors[`filters.${index}.value`])} aria-describedby={errors[`filters.${index}.value`] ? `filter-${index}-value-error` : undefined} value={rule.valueRaw} disabled={rule.operator === "exists"} onChange={(event) => update(index, { valueRaw: event.target.value })} className="w-full" /> : <Input aria-label={`${t("settings.policy.filters.value")} ${index + 1}`} aria-invalid={Boolean(errors[`filters.${index}.value`])} aria-describedby={errors[`filters.${index}.value`] ? `filter-${index}-value-error` : undefined} value={rule.valueRaw} disabled={rule.operator === "exists"} onChange={(event) => update(index, { valueRaw: event.target.value })} className="bg-background" />}
              {errors[`filters.${index}.value`] ? <span id={`filter-${index}-value-error`} role="alert" className="text-destructive">{errors[`filters.${index}.value`]}</span> : null}
            </label>
            <Button type="button" variant="outline" aria-label={`${t("common.delete")} ${t("settings.policy.filters.rule")} ${index + 1}`} onClick={() => onChange(rules.filter((_, ruleIndex) => ruleIndex !== index))} className="self-end px-3 text-destructive hover:bg-accent hover:text-destructive">{t("common.delete")}</Button>
          </div>
        ))}
      </div>
    </section>
  );
}
