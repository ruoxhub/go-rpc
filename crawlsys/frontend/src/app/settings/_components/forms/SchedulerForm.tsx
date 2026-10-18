"use client";

import { Select } from "../../../_components/ui/select";
import { t } from "../../../i18n";
import { ConfigCard } from "../ConfigCard";
import { updateSchedulerSettings } from "../../utils/settings-api";
import type { SchedulerSettingsResponse } from "../../utils/settings-types";
import { NumericField, TextField, numberValue } from "./shared";

const inactiveFields = ["worker_id", "batch_size", "graceful_shutdown_seconds"] as const;

export function SchedulerForm({ value }: { value: SchedulerSettingsResponse }) {
  const hint = (name: string) => value.inactive_fields.includes(name) ? t("settings.inactive") : undefined;
  const timezones = (typeof Intl !== "undefined" && typeof Intl.supportedValuesOf === "function")
    ? Intl.supportedValuesOf("timeZone")
    : ["Asia/Shanghai", "UTC"];
  const tzOptions = Array.from(new Set([value.timezone || "Asia/Shanghai", "Asia/Shanghai", "UTC", ...timezones]));

  return (
    <ConfigCard
      title={t("settings.scheduler.title")}
      description={t("settings.scheduler.description")}
      saveLabel={t("settings.scheduler.save")}
      onSave={(data) => updateSchedulerSettings({
        timezone: String(data.get("timezone")),
        worker_id: String(data.get("worker_id")),
        poll_interval_ms: numberValue(data, "poll_interval_ms"),
        default_loop_interval_seconds: numberValue(data, "default_loop_interval_seconds"),
        batch_size: numberValue(data, "batch_size"),
        zombie_reap_after_seconds: numberValue(data, "zombie_reap_after_seconds"),
        graceful_shutdown_seconds: numberValue(data, "graceful_shutdown_seconds"),
      })}
    >
      {({ fieldErrors }) => <>
        <div className="space-y-1">
          <label htmlFor="scheduler-timezone" className="text-sm font-medium text-foreground">
            {t("settings.scheduler.timezone")}
          </label>
          <Select
            id="scheduler-timezone"
            name="timezone"
            defaultValue={value.timezone || "Asia/Shanghai"}
            aria-invalid={Boolean(fieldErrors.timezone)}
            aria-describedby="scheduler-timezone-help"
            className="bg-background"
          >
            {tzOptions.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </Select>
          {fieldErrors.timezone ? (
            <p id="scheduler-timezone-help" role="alert" className="text-xs text-destructive">{fieldErrors.timezone}</p>
          ) : (
            <p id="scheduler-timezone-help" className="text-xs text-muted-foreground">{t("settings.scheduler.timezoneHint")}</p>
          )}
        </div>
        <TextField name={inactiveFields[0]} label={t("settings.scheduler.workerId")} defaultValue={value.worker_id} hint={hint(inactiveFields[0])} error={fieldErrors.worker_id} />
        <NumericField name="poll_interval_ms" label={t("settings.scheduler.pollInterval")} defaultValue={value.poll_interval_ms} integer error={fieldErrors.poll_interval_ms} />
        <NumericField name="default_loop_interval_seconds" label={t("settings.scheduler.loopInterval")} defaultValue={value.default_loop_interval_seconds} integer error={fieldErrors.default_loop_interval_seconds} />
        <NumericField id="scheduler-batch_size" name={inactiveFields[1]} label={t("settings.scheduler.batchSize")} defaultValue={value.batch_size} integer hint={hint(inactiveFields[1])} error={fieldErrors.batch_size} />
        <NumericField name="zombie_reap_after_seconds" label={t("settings.scheduler.zombieReap")} defaultValue={value.zombie_reap_after_seconds} integer error={fieldErrors.zombie_reap_after_seconds} />
        <NumericField name={inactiveFields[2]} label={t("settings.scheduler.shutdown")} defaultValue={value.graceful_shutdown_seconds} integer hint={hint(inactiveFields[2])} error={fieldErrors.graceful_shutdown_seconds} />
      </>}
    </ConfigCard>
  );
}
