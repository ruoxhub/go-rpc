"use client";

import { useState } from "react";

import { Select } from "../../../_components/ui/select";
import { t } from "../../../i18n";
import { ConfigCard } from "../ConfigCard";
import { updateLlmSettings } from "../../utils/settings-api";
import type { LlmModel, LlmSettingsResponse } from "../../utils/settings-types";
import { CheckField, Field, NumericField, numberValue } from "./shared";

function modelId(data: FormData, name: string) {
  const value = String(data.get(name) ?? "");
  return value ? Number(value) : null;
}

function unavailableModel(modelId: number | null, models: LlmModel[], catalogModels: LlmModel[]) {
  if (modelId === null || models.some((model) => model.id === modelId)) return null;
  const model = catalogModels.find((item) => item.id === modelId);
  return { id: modelId, label: t("settings.llm.unavailableModel", { model: model?.display_name ?? `#${modelId}` }) };
}

export function LlmForm({ value, models, catalogModels = models }: { value: LlmSettingsResponse; models: LlmModel[]; catalogModels?: LlmModel[] }) {
  const [savedValue, setSavedValue] = useState(value);
  const [analysisModelId, setAnalysisModelId] = useState(value.default_analysis_model_id);
  const [transcriptionModelId, setTranscriptionModelId] = useState(value.default_transcription_model_id);
  const unavailableAnalysisModel = unavailableModel(savedValue.default_analysis_model_id, models, catalogModels);
  const unavailableTranscriptionModel = unavailableModel(savedValue.default_transcription_model_id, models, catalogModels);

  return (
    <ConfigCard
      title={t("settings.llm.title")}
      description={t("settings.llm.description")}
      saveLabel={t("settings.llm.save")}
      onSave={(data) => {
        return updateLlmSettings({
          default_analysis_model_id: modelId(data, "default_analysis_model_id"),
          default_transcription_model_id: modelId(data, "default_transcription_model_id"),
          max_tokens: numberValue(data, "max_tokens"),
          temperature: numberValue(data, "temperature"),
          enable_thinking: data.has("enable_thinking"),
        });
      }}
      onSuccess={(result) => {
        const next = result as LlmSettingsResponse;
        setSavedValue(next);
        setAnalysisModelId(next.default_analysis_model_id);
        setTranscriptionModelId(next.default_transcription_model_id);
      }}
    >
      {({ fieldErrors }) => (
        <>
          <Field name="default_analysis_model_id" label={t("settings.llm.defaultAnalysisModel")} error={fieldErrors.default_analysis_model_id}>
            <Select id="default_analysis_model_id" name="default_analysis_model_id" value={analysisModelId ?? ""} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setAnalysisModelId(event.target.value ? Number(event.target.value) : null)} className="bg-background">
              <option value="">{t("settings.llm.noDefaultModel")}</option>
              {unavailableAnalysisModel ? <option value={unavailableAnalysisModel.id} disabled>{unavailableAnalysisModel.label}</option> : null}
              {models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}
            </Select>
          </Field>
          <Field name="default_transcription_model_id" label={t("settings.llm.defaultTranscriptionModel")} error={fieldErrors.default_transcription_model_id}>
            <Select id="default_transcription_model_id" name="default_transcription_model_id" value={transcriptionModelId ?? ""} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setTranscriptionModelId(event.target.value ? Number(event.target.value) : null)} className="bg-background">
              <option value="">{t("settings.llm.noDefaultModel")}</option>
              {unavailableTranscriptionModel ? <option value={unavailableTranscriptionModel.id} disabled>{unavailableTranscriptionModel.label}</option> : null}
              {models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}
            </Select>
          </Field>
          <NumericField name="max_tokens" label={t("settings.llm.maxTokens")} defaultValue={value.max_tokens} integer error={fieldErrors.max_tokens} />
          <NumericField name="temperature" label={t("settings.llm.temperature")} defaultValue={value.temperature} error={fieldErrors.temperature} />
          <div className="flex items-end pb-2"><CheckField name="enable_thinking" label={t("settings.llm.thinking")} defaultChecked={value.enable_thinking} /></div>
        </>
      )}
    </ConfigCard>
  );
}
