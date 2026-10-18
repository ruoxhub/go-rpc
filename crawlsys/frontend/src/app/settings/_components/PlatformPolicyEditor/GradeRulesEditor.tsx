import { NumberInput } from "../../../_components/NumberInput";
import { Button } from "../../../_components/ui/button";
import { t } from "../../../i18n";
import type { EditableGradeRule, Grade } from "./types";

export function GradeRulesEditor({ grade, rules, errors, onChange }: { grade: Grade; rules: EditableGradeRule[]; errors: Record<string, string>; onChange: (rules: EditableGradeRule[]) => void }) {
  function update(index: number, field: keyof EditableGradeRule, value: string) {
    onChange(rules.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, [field]: value } : rule));
  }

  return (
    <section aria-labelledby={`grade-${grade}`} className="rounded-lg border border-border bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 id={`grade-${grade}`} className="font-semibold uppercase text-foreground">{grade}</h3>
        <Button
          type="button"
          variant="link"
          size="sm"
          onClick={() => onChange([...rules, { maxHoursRaw: "24", minViewsRaw: "0" }])}
          className="h-auto p-0 text-sm font-medium text-primary hover:underline"
        >
          {t("settings.policy.grade.add")}
        </Button>
      </div>
      <div className="mt-3 space-y-3">
        {rules.length === 0 ? <p className="text-sm text-muted-foreground">{t("settings.policy.grade.empty")}</p> : null}
        {rules.map((rule, index) => (
          <div key={index} className="grid gap-3 rounded-md border border-border p-3 sm:grid-cols-[1fr_1fr_auto]">
            <label className="grid gap-1 text-xs font-medium text-foreground">{t("settings.policy.grade.maxHours")}
              <NumberInput aria-label={`${grade.toUpperCase()} ${t("settings.policy.grade.maxHours")} ${index + 1}`} value={rule.maxHoursRaw} aria-invalid={Boolean(errors[`${grade}.${index}.max_hours`])} aria-describedby={errors[`${grade}.${index}.max_hours`] ? `${grade}-${index}-max-hours-error` : undefined} onChange={(event) => update(index, "maxHoursRaw", event.target.value)} className="w-full" />
              {errors[`${grade}.${index}.max_hours`] ? <span id={`${grade}-${index}-max-hours-error`} role="alert" className="text-destructive">{errors[`${grade}.${index}.max_hours`]}</span> : null}
            </label>
            <label className="grid gap-1 text-xs font-medium text-foreground">{t("settings.policy.grade.minViews")}
              <NumberInput integer aria-label={`${grade.toUpperCase()} ${t("settings.policy.grade.minViews")} ${index + 1}`} value={rule.minViewsRaw} aria-invalid={Boolean(errors[`${grade}.${index}.min_views`])} aria-describedby={errors[`${grade}.${index}.min_views`] ? `${grade}-${index}-min-views-error` : undefined} onChange={(event) => update(index, "minViewsRaw", event.target.value)} className="w-full" />
              {errors[`${grade}.${index}.min_views`] ? <span id={`${grade}-${index}-min-views-error`} role="alert" className="text-destructive">{errors[`${grade}.${index}.min_views`]}</span> : null}
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={`${t("common.delete")} ${grade.toUpperCase()} ${index + 1}`}
              onClick={() => onChange(rules.filter((_, ruleIndex) => ruleIndex !== index))}
              className="self-end px-3 text-destructive hover:bg-accent hover:text-destructive"
            >
              {t("common.delete")}
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
