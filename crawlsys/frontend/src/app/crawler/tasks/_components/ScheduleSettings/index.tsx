"use client";

import { useEffect, useState } from "react";
import { NumberInput } from "../../../../_components/NumberInput";
import { Button } from "../../../../_components/ui/button";
import { Input } from "../../../../_components/ui/input";
import { Card } from "../../../../_components/ui/card";
import { previewTaskSchedule } from "../../../../../utils/crawler/crawler-api";
import type { TaskScheduleType } from "@/utils/crawler/crawler-types";
import type { ScheduleFormValue } from "../TaskForm/types/schedule";
import { t } from "../../../../i18n";

interface ScheduleSettingsProps {
  value: ScheduleFormValue;
  timezone: string;
  onChange: (value: ScheduleFormValue) => void;
}

const PRESETS = [
  { label: t("tasks.schedulePresetHourly"), value: "0 * * * *" },
  { label: t("tasks.schedulePresetDaily"), value: "0 0 * * *" },
  { label: t("tasks.schedulePresetWeekly"), value: "0 0 * * 1" },
  { label: t("tasks.schedulePresetMonthly"), value: "0 0 1 * *" },
];

export function ScheduleSettings({
  value,
  timezone,
  onChange,
}: ScheduleSettingsProps) {
  const [preview, setPreview] = useState<{
    cron: string;
    timezone: string;
    occurrences: string[];
    error: string | null;
  }>({ cron: "", timezone, occurrences: [], error: null });
  const cron = value.cron_expression.trim();
  const previewIsCurrent = preview.cron === cron;
  const previews = previewIsCurrent ? preview.occurrences : [];
  const error = previewIsCurrent ? preview.error : null;
  const previewTimezone = previewIsCurrent ? preview.timezone : timezone;
  const loading = value.type === "cron" && Boolean(cron) && !previewIsCurrent;

  useEffect(() => {
    let cancelled = false;

    if (value.type !== "cron" || !cron) return;

    previewTaskSchedule(cron)
      .then((res) => {
        if (!cancelled) {
          setPreview({
            cron,
            timezone: res.timezone,
            occurrences: res.occurrences ?? [],
            error: null,
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPreview({
            cron,
            timezone,
            occurrences: [],
            error: err instanceof Error ? err.message : t("tasks.schedulePreviewError"),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [value.type, cron, timezone]);

  const updateType = (type: TaskScheduleType) => {
    onChange({
      ...value,
      type,
      interval_seconds:
        type === "interval" && !value.interval_seconds
          ? "300"
          : value.interval_seconds,
    });
  };

  const numberValue = (raw: string) => (raw ? raw : "");

  return (
    <Card className="space-y-4 p-4 text-card-foreground shadow-sm">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-foreground">
          {t("tasks.scheduleTypeLabel")}
        </legend>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="radio"
              name="schedule_type"
              checked={value.type === "manual"}
              onChange={() => updateType("manual")}
              className="accent-primary"
            />
            {t("tasks.scheduleManualMode")}
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="radio"
              name="schedule_type"
              checked={value.type === "once"}
              onChange={() => updateType("once")}
              className="accent-primary"
            />
            {t("tasks.scheduleOnceMode")}
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="radio"
              name="schedule_type"
              checked={value.type === "interval"}
              onChange={() => updateType("interval")}
              className="accent-primary"
            />
            {t("tasks.scheduleIntervalMode")}
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="radio"
              name="schedule_type"
              checked={value.type === "cron"}
              onChange={() => updateType("cron")}
              className="accent-primary"
            />
            Cron
          </label>
        </div>
      </fieldset>

      {value.type === "once" && (
        <div className="space-y-1">
          <label htmlFor="once_run_at" className="text-sm font-medium text-foreground">
            {t("tasks.scheduleRunAtLabel")}
          </label>
          <Input
            id="once_run_at"
            type="datetime-local"
            value={value.run_at}
            onChange={(e) => onChange({ ...value, run_at: e.target.value })}
            className="w-full bg-background"
          />
        </div>
      )}

      {value.type === "interval" && (
        <div className="space-y-1">
          <label htmlFor="interval_seconds" className="text-sm font-medium text-foreground">
            {t("tasks.scheduleIntervalLabel")}
          </label>
          <div className="flex items-center gap-2">
            <NumberInput
              id="interval_seconds"
              value={numberValue(value.interval_seconds)}
              onChange={(e) =>
                onChange({
                  ...value,
                  interval_seconds: e.currentTarget.value,
                })
              }
              min={1}
              integer
              placeholder="300"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <span className="text-sm text-muted-foreground">{t("tasks.scheduleSecondsUnit")}</span>
          </div>
        </div>
      )}

      {value.type === "cron" && (
        <div className="space-y-2">
          <div className="space-y-1">
            <label htmlFor="cron_expression" className="text-sm font-medium text-foreground">
              {t("tasks.scheduleCronLabel")}
            </label>
            <Input
              id="cron_expression"
              type="text"
              value={value.cron_expression}
              onChange={(e) =>
                onChange({ ...value, cron_expression: e.target.value })
              }
              placeholder="0 * * * *"
              className="w-full bg-background font-mono"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <Button
                key={preset.value}
                type="button"
                variant="secondary"
                size="sm"
                onClick={() =>
                  onChange({ ...value, cron_expression: preset.value })
                }
                className="h-7 px-2.5 text-xs"
              >
                {preset.label}
              </Button>
            ))}
          </div>
        </div>
      )}

      {value.type !== "manual" ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <label htmlFor="schedule_start_at" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleStartAtLabel")}
            </label>
            <Input
              id="schedule_start_at"
              type="datetime-local"
              value={value.start_at}
              onChange={(event) => onChange({ ...value, start_at: event.currentTarget.value })}
              className="w-full bg-background"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="schedule_end_at" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleEndAtLabel")}
            </label>
            <Input
              id="schedule_end_at"
              type="datetime-local"
              value={value.end_at}
              onChange={(event) => onChange({ ...value, end_at: event.currentTarget.value })}
              className="w-full bg-background"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="schedule_max_runs" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleMaxRunsLabel")}
            </label>
            <NumberInput
              id="schedule_max_runs"
              value={value.max_runs}
              onChange={(event) => onChange({ ...value, max_runs: event.currentTarget.value })}
              min={1}
              integer
              placeholder={t("tasks.scheduleUnlimited")}
            />
          </div>
        </div>
      ) : null}

      {value.type === "cron" && (
        <div className="rounded-md border border-border/50 bg-muted/50 p-3 text-xs">
          <div className="font-medium text-foreground mb-1">
            {t("tasks.schedulePreviewTitle", { timezone: previewTimezone })}
          </div>
          {loading ? (
            <div role="status" className="text-muted-foreground">{t("tasks.schedulePreviewLoading")}</div>
          ) : error ? (
            <div role="alert" className="text-destructive font-medium">{error}</div>
          ) : previews.length > 0 ? (
            <ul className="list-disc list-inside space-y-0.5 text-muted-foreground font-mono">
              {previews.map((time, idx) => (
                <li key={idx}>{time}</li>
              ))}
            </ul>
          ) : (
            <div className="text-muted-foreground">{t("tasks.schedulePreviewEmpty")}</div>
          )}
        </div>
      )}

      <div className="border-t border-border pt-4 space-y-3">
        <div className="text-sm font-medium text-foreground">{t("tasks.scheduleRetryTitle")}</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <label htmlFor="max_retries" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleRetryMaxLabel")}
            </label>
            <NumberInput
              id="max_retries"
              value={numberValue(value.max_retries)}
              onChange={(e) =>
                onChange({
                  ...value,
                  max_retries: e.currentTarget.value,
                })
              }
              min={0}
              integer
              placeholder="3"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="retry_delay_seconds" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleRetryDelayLabel")}
            </label>
            <NumberInput
              id="retry_delay_seconds"
              value={numberValue(value.retry_delay_seconds)}
              onChange={(e) =>
                onChange({
                  ...value,
                  retry_delay_seconds: e.currentTarget.value,
                })
              }
              min={1}
              integer
              placeholder="60"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="retry_backoff_factor" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleRetryBackoffLabel")}
            </label>
            <NumberInput
              id="retry_backoff_factor"
              value={numberValue(value.retry_backoff_factor)}
              onChange={(e) =>
                onChange({
                  ...value,
                  retry_backoff_factor: e.currentTarget.value,
                })
              }
              min={1}
              step={0.1}
              placeholder="2"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="retry_max_delay_seconds" className="text-xs font-medium text-foreground">
              {t("tasks.scheduleRetryMaxDelayLabel")}
            </label>
            <NumberInput
              id="retry_max_delay_seconds"
              value={value.retry_max_delay_seconds}
              onChange={(event) =>
                onChange({ ...value, retry_max_delay_seconds: event.currentTarget.value })
              }
              min={1}
              integer
              placeholder="3600"
            />
          </div>
        </div>
      </div>
    </Card>
  );
}
