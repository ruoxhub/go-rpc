// ProviderForm：创建或编辑模型提供商，敏感密钥始终使用空输入。
"use client";

import { useState } from "react";
import { Loader2 } from "../../../../../_components/Loader2";
import { Button } from "../../../../../_components/ui/button";
import { Input } from "../../../../../_components/ui/input";
import { Select } from "../../../../../_components/ui/select";
import { t } from "../../../../../i18n";
import { CrawlerApiError } from "../../../../../../utils/crawler/crawler-api";
import type { LlmProvider, ProviderCreate, ProviderProtocol, ProviderUpdate } from "../../../../utils/settings-types";
import { Field } from "../../../forms/shared";

interface ProviderFormProps {
  provider?: LlmProvider | null;
  onSubmit: (value: ProviderCreate | ProviderUpdate) => Promise<unknown> | unknown;
  onCancel?: () => void;
  onSavingChange?: (saving: boolean) => void;
}

function providerAuthority(value: string) {
  try {
    const url = new URL(value);
    return [url.protocol, url.hostname, url.port];
  } catch {
    return null;
  }
}

function providerAuthorityChanged(current: string | null, next: string) {
  const nextAuthority = providerAuthority(next.trim());
  if (!next.trim() || !nextAuthority) return false;
  const currentAuthority = current ? providerAuthority(current) : null;
  return !currentAuthority || nextAuthority.some((part, index) => part !== currentAuthority[index]);
}

export function ProviderForm({ provider = null, onSubmit, onCancel, onSavingChange }: ProviderFormProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [protocol, setProtocol] = useState<ProviderProtocol>(provider?.protocol ?? "openai-completion");
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? "");
  const apiKeyRequired = !provider || protocol !== provider.protocol || providerAuthorityChanged(provider.base_url, baseUrl);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const apiKey = String(data.get("api_key") ?? "").trim();
    const normalizedBaseUrl = baseUrl.trim();
    const common = {
      name: String(data.get("name") ?? "").trim(),
      protocol,
    };
    const value: ProviderCreate | ProviderUpdate = provider
      ? { ...common, ...(normalizedBaseUrl ? { base_url: normalizedBaseUrl } : {}), ...(apiKey ? { api_key: apiKey } : {}) }
      : { ...common, base_url: normalizedBaseUrl || null, api_key: apiKey };
    setSaving(true);
    onSavingChange?.(true);
    setError(false);
    setFieldErrors({});
    try {
      await onSubmit(value);
      const secret = form.elements.namedItem("api_key");
      if (secret instanceof HTMLInputElement) secret.value = "";
    } catch (caught) {
      if (caught instanceof CrawlerApiError && caught.kind === "validation") {
        setFieldErrors(caught.fieldErrors);
      } else {
        setError(true);
      }
    } finally {
      setSaving(false);
      onSavingChange?.(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-card-foreground">{provider ? t("settings.providers.edit") : t("settings.providers.create")}</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {provider?.api_key_configured ? t("settings.providers.apiKeyConfigured", { key: provider.api_key_masked }) : t("settings.providers.apiKeyRequired")}
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field name="provider-name" label={t("settings.providers.name")} error={fieldErrors.name}>
          <Input required disabled={saving} autoComplete="organization" id="provider-name" name="name" defaultValue={provider?.name} className="touch-target" />
        </Field>
        <Field name="provider-protocol" label={t("settings.providers.protocol")} error={fieldErrors.protocol}>
          <Select disabled={saving} id="provider-protocol" name="protocol" value={protocol} onChange={(event) => setProtocol(event.target.value as ProviderProtocol)} className="touch-target">
            <option value="openai-completion">{t("settings.providers.protocolOpenaiCompletion")}</option>
            <option value="claude">{t("settings.providers.protocolClaude")}</option>
            <option value="gemini">{t("settings.providers.protocolGemini")}</option>
            <option value="deepseek">{t("settings.providers.protocolDeepseek")}</option>
            <option value="openai-responses">{t("settings.providers.protocolOpenaiResponses")}</option>
          </Select>
        </Field>
        <Field name="provider-base-url" label={t("settings.providers.baseUrl")} error={fieldErrors.base_url}>
          <Input disabled={saving} id="provider-base-url" name="base_url" type="url" autoComplete="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="touch-target" />
        </Field>
        <div className="sm:col-span-2">
          <Field name="provider-api-key" label={t("settings.providers.apiKey")} hint={!provider ? t("settings.providers.apiKeyRequired") : apiKeyRequired ? t("settings.providers.apiKeyTargetChangedHint") : t("settings.secret.configuredHint")} error={fieldErrors.api_key}>
            <Input required={apiKeyRequired} disabled={saving} autoComplete="new-password" id="provider-api-key" name="api_key" type="password" className="touch-target" />
          </Field>
        </div>
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{t("settings.providers.saveFailed")}</p> : null}
      <div className="flex flex-wrap justify-end gap-2">
        {onCancel ? (
          <Button type="button" variant="outline" onClick={onCancel} disabled={saving} className="touch-target">
            {t("common.cancel")}
          </Button>
        ) : null}
        <Button type="submit" variant="gradient" disabled={saving} aria-busy={saving} className="touch-target">
          {saving ? <Loader2 className="mr-2 motion-reduce:animate-none" /> : null}
          {provider ? t("settings.providers.save") : t("settings.providers.create")}
        </Button>
      </div>
    </form>
  );
}
