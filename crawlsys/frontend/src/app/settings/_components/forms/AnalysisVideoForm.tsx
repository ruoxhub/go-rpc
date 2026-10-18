"use client";

import { Select } from "../../../_components/ui/select";
import { t } from "../../../i18n";
import { ConfigCard } from "../ConfigCard";
import { updateAnalysisVideoSettings } from "../../utils/settings-api";
import type { AnalysisVideoSettings } from "../../utils/settings-types";
import { CheckField, Field, NumericField, TextField } from "./shared";

function timestamps(data: FormData) {
  const value = String(data.get("frame_timestamps") ?? "").trim();
  if (!value) return [];
  return value.split(/[，,\s]+/).filter(Boolean).map(Number);
}

function strategy(value: FormDataEntryValue | null): AnalysisVideoSettings["frame_sampling_strategy"] {
  if (value === "interval" || value === "count" || value === "timestamps" || value === "scene_guided") return value;
  return "scene_guided";
}

export function AnalysisVideoForm({ value }: { value: AnalysisVideoSettings }) {
  return (
    <ConfigCard
      title={t("settings.analysis.title")}
      description={t("settings.analysis.description")}
      saveLabel={t("settings.analysis.save")}
      onSave={(data) => updateAnalysisVideoSettings({
        is_base64: data.has("is_base64"),
        frame_sampling_strategy: strategy(data.get("frame_sampling_strategy")),
        max_frames: Number(data.get("max_frames")),
        frame_interval_seconds: Number(data.get("frame_interval_seconds")),
        frame_timestamps: timestamps(data),
      })}
    >
      {({ fieldErrors }) => (
        <>
          <div className="flex items-end pb-2"><CheckField name="is_base64" label={t("settings.analysis.base64")} defaultChecked={value.is_base64} /></div>
          <Field name="frame_sampling_strategy" label={t("settings.analysis.strategy")} error={fieldErrors.frame_sampling_strategy}>
            <Select id="frame_sampling_strategy" name="frame_sampling_strategy" defaultValue={value.frame_sampling_strategy} className="bg-background">
              <option value="scene_guided">{t("settings.analysis.strategySceneGuided")}</option>
              <option value="interval">{t("settings.analysis.strategyInterval")}</option>
              <option value="count">{t("settings.analysis.strategyCount")}</option>
              <option value="timestamps">{t("settings.analysis.strategyTimestamps")}</option>
            </Select>
          </Field>
          <NumericField name="max_frames" label={t("settings.analysis.maxFrames")} defaultValue={value.max_frames} integer error={fieldErrors.max_frames} />
          <NumericField name="frame_interval_seconds" label={t("settings.analysis.interval")} defaultValue={value.frame_interval_seconds} error={fieldErrors.frame_interval_seconds} />
          <TextField name="frame_timestamps" label={t("settings.analysis.timestamps")} defaultValue={value.frame_timestamps.join(", ")} hint={t("settings.analysis.timestampsHint")} error={fieldErrors.frame_timestamps} />
        </>
      )}
    </ConfigCard>
  );
}
