"use client";

import { t } from "../../../i18n";
import { ConfigCard } from "../ConfigCard";
import { updateCleanerSettings } from "../../utils/settings-api";
import type { CleanerSettings } from "../../utils/settings-types";
import { CheckField, NumericField, TextField, numberValue } from "./shared";

export function CleanerForm({ value }: { value: CleanerSettings }) {
  const inactive = (name: string) => value.inactive_fields.includes(name);
  const hint = (name: string) => inactive(name) ? t("settings.inactive") : undefined;
  return (
    <ConfigCard
      title={t("settings.cleaner.title")}
      description={t("settings.cleaner.description")}
      saveLabel={t("settings.cleaner.save")}
      onSave={(data) => updateCleanerSettings({
        enabled: data.has("enabled"),
        poll_interval: value.poll_interval,
        batch_size: numberValue(data, "batch_size"),
        max_batches_per_platform: numberValue(data, "max_batches_per_platform"),
        ttl_days: numberValue(data, "ttl_days"),
        watermark_key: value.watermark_key,
        suspect_seconds: numberValue(data, "suspect_seconds"),
      })}
    >
      {({ fieldErrors }) => <>
        <div className="flex items-end pb-2"><CheckField name="enabled" label={t("settings.cleaner.enabled")} defaultChecked={value.enabled} /></div>
        <NumericField name="poll_interval" label={t("settings.cleaner.pollInterval")} defaultValue={value.poll_interval} error={fieldErrors.poll_interval} hint={hint("poll_interval")} disabled={inactive("poll_interval")} />
        <NumericField id="cleaner-batch_size" name="batch_size" label={t("settings.cleaner.batchSize")} defaultValue={value.batch_size} integer error={fieldErrors.batch_size} />
        <NumericField name="max_batches_per_platform" label={t("settings.cleaner.maxBatches")} defaultValue={value.max_batches_per_platform} integer error={fieldErrors.max_batches_per_platform} />
        <NumericField name="ttl_days" label={t("settings.cleaner.ttlDays")} defaultValue={value.ttl_days} integer error={fieldErrors.ttl_days} />
        <TextField name="watermark_key" label={t("settings.cleaner.watermark")} defaultValue={value.watermark_key} error={fieldErrors.watermark_key} hint={hint("watermark_key")} disabled={inactive("watermark_key")} />
        <NumericField name="suspect_seconds" label={t("settings.cleaner.suspectSeconds")} defaultValue={value.suspect_seconds} error={fieldErrors.suspect_seconds} />
      </>}
    </ConfigCard>
  );
}
