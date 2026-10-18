"use client";

import { t } from "../../../i18n";
import { ConfigCard } from "../ConfigCard";
import { updateRpcSettings } from "../../utils/settings-api";
import type { RpcSettings } from "../../utils/settings-types";
import { NumericField, TextField, numberValue } from "./shared";

export function RpcForm({ value }: { value: RpcSettings }) {
  return (
    <ConfigCard
      title={t("settings.rpc.title")}
      description={t("settings.rpc.description")}
      saveLabel={t("settings.rpc.save")}
      onSave={(data) => updateRpcSettings({ base_url: String(data.get("base_url")), timeout_seconds: numberValue(data, "timeout_seconds") })}
    >
      {({ fieldErrors }) => <><TextField id="rpc-base_url" name="base_url" label={t("settings.rpc.baseUrl")} defaultValue={value.base_url} error={fieldErrors.base_url} /><NumericField name="timeout_seconds" label={t("settings.rpc.timeout")} defaultValue={value.timeout_seconds} error={fieldErrors.timeout_seconds} /></>}
    </ConfigCard>
  );
}
