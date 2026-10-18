"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { SubmitButton } from "../../../_components/SubmitButton";
import { Button } from "../../../../_components/ui/button";
import { Card } from "../../../../_components/ui/card";
import { Input } from "../../../../_components/ui/input";
import { Select } from "../../../../_components/ui/select";
import { Textarea } from "../../../../_components/ui/textarea";
import { Switch } from "../../../../_components/ui/switch";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Action, ActionPayload, Platform } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

import { validateParamsSchema } from "./utils/validateParamsSchema";

function value(data: FormData, name: string) {
  const entry = data.get(name);
  return typeof entry === "string" ? entry.trim() : "";
}

function payload(form: HTMLFormElement): ActionPayload {
  const data = new FormData(form);
  return {
    bs_id: Number(value(data, "bs_id")),
    ba_action: value(data, "ba_action"),
    ba_desc: value(data, "ba_desc") || null,
    ba_params_schema: value(data, "ba_params_schema") || null,
    ba_api_url: value(data, "ba_api_url") || null,
    ba_api_method: value(data, "ba_api_method") || null,
    ba_enabled: data.get("ba_enabled") === "on",
    ba_sample_safe: data.get("ba_sample_safe") === "on",
  };
}

export function ActionForm({
  mode,
  platforms,
  action,
}: {
  mode: "create" | "edit";
  platforms: Platform[];
  action?: Action;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const currentPlatform = action
    ? platforms.find((platform) => platform.bs_id === action.bs_id)
    : undefined;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = payload(event.currentTarget);
    setFeedback(undefined);
    setFieldErrors({});
    if (body.ba_params_schema) {
      const schemaError = validateParamsSchema(body.ba_params_schema);
      if (schemaError) {
        setFieldErrors({ ba_params_schema: schemaError });
        return;
      }
    }
    setLoading(true);
    try {
      const updateBody = {
        ba_action: body.ba_action,
        ba_desc: body.ba_desc,
        ba_params_schema: body.ba_params_schema,
        ba_api_url: body.ba_api_url,
        ba_api_method: body.ba_api_method,
        ba_enabled: body.ba_enabled,
        ba_sample_safe: body.ba_sample_safe,
      };
      await crawlerRequest<Action>(
        mode === "edit" ? `/actions/${action?.ba_id}` : "/actions",
        {
          method: mode === "edit" ? "PUT" : "POST",
          body: JSON.stringify(mode === "edit" ? updateBody : body),
        },
      );
      router.push("/crawler/actions");
    } catch (error) {
      if (error instanceof CrawlerApiError) {
        setFieldErrors(error.fieldErrors);
        if (error.kind !== "validation") setFeedback(error.message);
      } else {
        setFeedback(t("actions.saveUnknownError"));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="p-6 shadow-sm">
      <form onSubmit={submit} className="grid gap-5">
        {feedback ? <Feedback variant="error">{feedback}</Feedback> : null}
        <div className="grid gap-4 md:grid-cols-2">
          {mode === "edit" ? (
            <div className="grid gap-1.5">
              <span className="text-xs font-medium text-foreground">{t("actions.platform")}</span>
              <div className="flex h-9 items-center rounded-md border border-border bg-muted px-3 text-sm text-foreground">
                {currentPlatform
                  ? `${currentPlatform.bs_name ?? currentPlatform.bs_platform_code ?? t("actions.platformName", { id: currentPlatform.bs_id })}${
                      currentPlatform.bs_status === "D" ? t("actions.deletedSuffix") : ""
                    }`
                  : t("actions.platformUnavailable", { id: action?.bs_id ?? "" })}
              </div>
            </div>
          ) : (
            <FormField id="bs_id" label={t("actions.platform")} required error={fieldErrors.bs_id}>
              <Select name="bs_id" defaultValue={platforms[0]?.bs_id ?? ""} className="bg-background">
                {platforms.map((platform) => (
                  <option key={platform.bs_id} value={platform.bs_id}>
                    {platform.bs_name ?? platform.bs_platform_code ?? t("actions.platformName", { id: platform.bs_id })}
                  </option>
                ))}
              </Select>
            </FormField>
          )}
          <FormField id="ba_action" label={t("actions.name")} required error={fieldErrors.ba_action}>
            <Input name="ba_action" defaultValue={action?.ba_action ?? ""} className="bg-background" />
          </FormField>
          <FormField id="ba_api_url" label={t("actions.apiUrl")} error={fieldErrors.ba_api_url}>
            <Input name="ba_api_url" defaultValue={action?.ba_api_url ?? ""} className="bg-background" />
          </FormField>
          <FormField id="ba_api_method" label={t("actions.requestMethod")} error={fieldErrors.ba_api_method}>
            <Select name="ba_api_method" defaultValue={action?.ba_api_method ?? "GET"} className="bg-background">
              {["GET", "POST", "PUT", "PATCH", "DELETE"].map((method) => (
                <option key={method}>{method}</option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField id="ba_desc" label={t("actions.descriptionLabel")} error={fieldErrors.ba_desc}>
          <Textarea name="ba_desc" defaultValue={action?.ba_desc ?? ""} rows={3} className="bg-background" />
        </FormField>
        <FormField
          id="ba_params_schema"
          label={t("actions.schema")}
          hint={t("actions.schemaHint")}
          error={fieldErrors.ba_params_schema}
        >
          <Textarea name="ba_params_schema" defaultValue={action?.ba_params_schema ?? ""} rows={7} className="bg-background font-mono" />
        </FormField>
        <label className="touch-target flex cursor-pointer items-center gap-2 text-sm">
          <Switch name="ba_enabled" defaultChecked={action?.ba_enabled ?? true} />
          {t("actions.enable")}
        </label>
        <label className="touch-target flex cursor-pointer items-center gap-2 text-sm">
          <Switch name="ba_sample_safe" defaultChecked={action?.ba_sample_safe ?? false} />
          <span>
            {t("actions.sampleSafe")}
            <span className="block text-xs text-muted-foreground">{t("actions.sampleSafeHint")}</span>
          </span>
        </label>
        <div className="flex justify-end gap-2">
          <Link
            href="/crawler/actions"
            className="touch-target inline-flex h-9 cursor-pointer items-center rounded-md border border-border bg-background px-4 text-sm font-medium hover:bg-accent"
          >
            {t("common.cancel")}
          </Link>
          <SubmitButton loading={loading}>{mode === "create" ? t("actions.create") : t("common.save")}</SubmitButton>
        </div>
      </form>
    </Card>
  );
}
