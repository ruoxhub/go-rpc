"use client";

import { useState } from "react";
import { t } from "../../../i18n";
import { ConfigCard } from "../ConfigCard";
import { updateProxySettings } from "../../utils/settings-api";
import type { ProxySettingsResponse } from "../../utils/settings-types";
import { TextField } from "./shared";

export function ProxyForm({ value }: { value: ProxySettingsResponse }) {
  const [savedValue, setSavedValue] = useState(value);
  return (
    <ConfigCard
      title={t("settings.proxy.title")}
      description={t("settings.proxy.description")}
      saveLabel={t("settings.proxy.save")}
      onSave={(data) => {
        const url = String(data.get("url") ?? "").trim();
        return updateProxySettings(url ? { url } : {});
      }}
      onSuccess={(result, form) => {
        setSavedValue(result as ProxySettingsResponse);
        const secret = form.elements.namedItem("url");
        if (secret instanceof HTMLInputElement) secret.value = "";
      }}
    >
      {({ fieldErrors }) => (
        <div className="space-y-3 sm:col-span-2">
          <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{savedValue.url_configured ? t("settings.configured") : t("settings.notConfigured")}</span>
            {savedValue.target ? ` · ${savedValue.target}` : ""}
          </div>
          <TextField name="url" label={t("settings.proxy.url")} secret hint={savedValue.url_configured ? t("settings.secret.configuredHint") : t("settings.secret.emptyHint")} error={fieldErrors.url} />
        </div>
      )}
    </ConfigCard>
  );
}
