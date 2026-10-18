"use client";

import { useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "../../../_components/ConfirmDialog";
import { Loader2 } from "../../../_components/Loader2";
import { Button } from "../../../_components/ui/button";
import { Card } from "../../../_components/ui/card";
import { Select } from "../../../_components/ui/select";
import { Alert, AlertDescription } from "../../../_components/ui/alert";
import { t } from "../../../i18n";
import { CrawlerApiError } from "../../../../utils/crawler/crawler-api";
import { updatePlatformPolicy } from "../../utils/settings-api";
import type { FilterRule, JsonScalar, PlatformSettingsResponse } from "../../utils/settings-types";
import { FilterRulesEditor } from "./FilterRulesEditor";
import { GradeRulesEditor } from "./GradeRulesEditor";
import { editablePolicy, storedPolicy, type EditablePlatformPolicy, type Grade } from "./types";

const emptyPolicy = { p1: [], p2: [], p3: [], filters: [] };
const grades: Grade[] = ["p1", "p2", "p3"];
const plainFields = new Set(["view_count", "pub_time", "download_time", "created_time"]);
const extendField = /^extend_data\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$/;

function validatePolicy(policy: EditablePlatformPolicy) {
  const result: Record<string, string> = {};
  const values: FilterRule["value"][] = [];
  const gradeValues = { p1: [], p2: [], p3: [] } as Record<Grade, Array<{ max_hours: number; min_views: number }>>;
  if (grades.every((grade) => policy[grade].length === 0)) result.p1 = t("settings.policy.error.gradeRequired");
  grades.forEach((grade) => policy[grade].forEach((rule, index) => {
    const maxHours = Number(rule.maxHoursRaw);
    const minViews = Number(rule.minViewsRaw);
    if (rule.maxHoursRaw.trim() === "" || !Number.isFinite(maxHours) || maxHours <= 0) result[`${grade}.${index}.max_hours`] = t("settings.policy.error.maxHours");
    if (rule.minViewsRaw.trim() === "" || !Number.isInteger(minViews) || minViews < 0) result[`${grade}.${index}.min_views`] = t("settings.policy.error.minViews");
    gradeValues[grade].push({ max_hours: maxHours, min_views: minViews });
  }));
  policy.filters.forEach((rule, index) => {
    if (!plainFields.has(rule.field) && !extendField.test(rule.field)) result[`filters.${index}.field`] = t("settings.policy.error.field");
    const rawItems = rule.operator === "in" ? rule.valueRaw.split(",").map((item) => item.trim()).filter(Boolean) : [rule.valueRaw.trim()];
    let parsed: JsonScalar[] = [];
    if (rule.operator === "exists") parsed = [null];
    else if (rawItems.length === 0 || rawItems.some((item) => item === "")) result[`filters.${index}.value`] = rule.operator === "in" ? t("settings.policy.error.array") : t("settings.policy.error.valueRequired");
    else if (rule.valueType === "number") {
      parsed = rawItems.map(Number);
      if (parsed.some((value) => typeof value !== "number" || !Number.isFinite(value))) result[`filters.${index}.value`] = t("settings.policy.error.number");
      else if (rule.field === "view_count" && parsed.some((value) => typeof value !== "number" || !Number.isInteger(value) || value < 0)) result[`filters.${index}.value`] = t("settings.policy.error.count");
    } else if (rule.valueType === "boolean") {
      if (rawItems.some((item) => item !== "true" && item !== "false")) result[`filters.${index}.value`] = t("settings.policy.error.boolean");
      else parsed = rawItems.map((item) => item === "true");
    } else {
      parsed = rawItems;
      if (["pub_time", "download_time", "created_time"].includes(rule.field) && rawItems.some((item) => !isIsoDateTime(item))) result[`filters.${index}.value`] = t("settings.policy.error.date");
    }
    if ([">", ">=", "<", "<="].includes(rule.operator) && rule.valueType !== "number" && !["pub_time", "download_time", "created_time"].includes(rule.field)) result[`filters.${index}.operator`] = t("settings.policy.error.operator");
    values.push(rule.operator === "in" ? parsed : parsed[0] ?? null);
  });
  return { errors: result, gradeValues, values };
}

const isoDateTime = /^(\d{4})-(\d{2})-(\d{2})(?:T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?$/;

function isIsoDateTime(value: string) {
  const match = isoDateTime.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function failureMessage(error: unknown) {
  if (!(error instanceof CrawlerApiError)) return t("settings.saveError");
  if (error.kind === "validation") return t("api.validation");
  if (error.kind === "network") return t("settings.error.network");
  if (error.status === 503) return t("settings.error.unavailable");
  return t("settings.error.request");
}

export function PlatformPolicyEditor({ platforms, pendingTabChange, onDirtyChange, onCancelTabChange, onConfirmTabChange, onSavingChange }: {
  platforms: PlatformSettingsResponse[];
  pendingTabChange: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onCancelTabChange: () => void;
  onConfirmTabChange: () => void;
  onSavingChange: (saving: boolean) => void;
}) {
  const initialPolicies = useMemo(() => Object.fromEntries(platforms.map(({ platform, policy }) => [platform, editablePolicy(policy ?? emptyPolicy)])), [platforms]);
  const [saved, setSaved] = useState<Record<string, EditablePlatformPolicy>>(initialPolicies);
  const [configured, setConfigured] = useState<Record<string, boolean>>(() => Object.fromEntries(platforms.map((item) => [item.platform, item.configured])));
  const [drafts, setDrafts] = useState<Record<string, EditablePlatformPolicy>>(initialPolicies);
  const [platform, setPlatform] = useState(platforms[0]?.platform ?? "");
  const [pendingPlatform, setPendingPlatform] = useState<string | null>(null);
  const [grade, setGrade] = useState<Grade>("p1");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const draft = drafts[platform];
  const dirty = Boolean(draft && JSON.stringify(draft) !== JSON.stringify(saved[platform]));

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = true;
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  if (!platform || !draft) {
    return (
      <Card className="rounded-xl p-5">
        <h2 className="font-semibold text-card-foreground">{t("settings.policy.title")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("settings.policy.noPlatforms")}</p>
      </Card>
    );
  }

  function replaceDraft(next: EditablePlatformPolicy) {
    setDrafts((current) => ({ ...current, [platform]: next }));
    setFeedback(null);
  }

  function requestPlatform(next: string) {
    if (next === platform) return;
    if (dirty) setPendingPlatform(next);
    else setPlatform(next);
  }

  function discardAnd(action: () => void) {
    setDrafts((current) => ({ ...current, [platform]: saved[platform] }));
    setErrors({});
    setFeedback(null);
    action();
  }

  async function save() {
    const validation = validatePolicy(draft);
    if (Object.keys(validation.errors).length > 0) {
      setErrors(validation.errors);
      setFeedback({ error: true, text: t("api.validation") });
      return;
    }
    setSaving(true);
    onSavingChange(true);
    setErrors({});
    setFeedback(null);
    try {
      const response = await updatePlatformPolicy(platform, storedPolicy(draft, validation.gradeValues, validation.values));
      const next = editablePolicy(response.policy ?? emptyPolicy);
      setSaved((current) => ({ ...current, [platform]: next }));
      setDrafts((current) => ({ ...current, [platform]: next }));
      setConfigured((current) => ({ ...current, [platform]: response.configured }));
      setFeedback({ error: false, text: t("settings.saveSuccess") });
    } catch (error) {
      if (error instanceof CrawlerApiError) setErrors(error.fieldErrors);
      setFeedback({ error: true, text: failureMessage(error) });
    } finally {
      setSaving(false);
      onSavingChange(false);
    }
  }

  const confirmOpen = pendingPlatform !== null || pendingTabChange;
  return (
    <Card className="rounded-xl shadow-sm">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-base font-semibold text-card-foreground">{t("settings.policy.title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("settings.policy.description")}</p>
      </div>
      <fieldset disabled={saving} className="space-y-5 p-5 disabled:opacity-70">
        <label className="grid max-w-sm gap-1.5 text-xs font-medium text-foreground">
          {t("settings.policy.platform")}
          <Select value={platform} onChange={(event) => requestPlatform(event.target.value)} className="bg-background">
            {platforms.map((item) => (
              <option key={item.platform} value={item.platform}>
                {item.platform}
              </option>
            ))}
          </Select>
        </label>
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{t("settings.policy.status")}：</span>
          {configured[platform] ? t("settings.configured") : t("settings.notConfigured")}
        </p>
        <div role="group" aria-label={t("settings.policy.grade.label")} className="flex gap-2">
          {grades.map((item) => (
            <Button
              key={item}
              type="button"
              variant={grade === item ? "default" : "outline"}
              aria-pressed={grade === item}
              onClick={() => setGrade(item)}
              className="uppercase"
            >
              {item}
            </Button>
          ))}
        </div>
        {grades.map((item) => (
          <div key={item} hidden={grade !== item}>
            <GradeRulesEditor
              grade={item}
              rules={draft[item]}
              errors={errors}
              onChange={(rules) => replaceDraft({ ...draft, [item]: rules })}
            />
          </div>
        ))}
        {errors.p1 ? <p role="alert" className="text-sm text-destructive">{errors.p1}</p> : null}
        <FilterRulesEditor
          rules={draft.filters}
          errors={errors}
          onChange={(filters) => replaceDraft({ ...draft, filters })}
        />
        <p className="text-xs text-muted-foreground">{t("settings.policy.filters.andHint")}</p>
        {feedback ? (
          <Alert
            variant={feedback.error ? "destructive" : "success"}
            role={feedback.error ? "alert" : "status"}
            className="px-3 py-2 text-sm"
          >
            <AlertDescription>{feedback.text}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex justify-end">
          <Button type="button" variant="gradient" disabled={saving || !dirty} onClick={save}>
            {saving ? <Loader2 className="mr-2" /> : null}
            {t("settings.policy.save", { platform })}
          </Button>
        </div>
      </fieldset>
      <ConfirmDialog
        open={confirmOpen}
        title={t("settings.policy.unsaved.title")}
        description={t("settings.policy.unsaved.description")}
        confirmLabel={t("settings.policy.unsaved.discard")}
        cancelLabel={t("common.cancel")}
        destructive
        onCancel={() => {
          setPendingPlatform(null);
          onCancelTabChange();
        }}
        onConfirm={() =>
          discardAnd(() => {
            if (pendingPlatform) setPlatform(pendingPlatform);
            setPendingPlatform(null);
            if (pendingTabChange) onConfirmTabChange();
          })
        }
      />
    </Card>
  );
}
