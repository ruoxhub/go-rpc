"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { NumberInput } from "../../../../_components/NumberInput";
import { SubmitButton } from "../../../_components/SubmitButton";
import { Button } from "../../../../_components/ui/button";
import { Card } from "../../../../_components/ui/card";
import { Input } from "../../../../_components/ui/input";
import { Textarea } from "../../../../_components/ui/textarea";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Platform, PlatformPayload } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

interface PlatformFormProps {
  mode: "create" | "edit";
  platform?: Platform;
}

function stringValue(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.trim() : "";
}

function payloadFromForm(
  form: HTMLFormElement,
  status: PlatformPayload["bs_status"],
): PlatformPayload {
  const data = new FormData(form);
  return {
    bs_name: stringValue(data.get("bs_name")),
    bs_platform_code: stringValue(data.get("bs_platform_code")),
    bs_url: stringValue(data.get("bs_url")) || null,
    bs_remark: stringValue(data.get("bs_remark")) || null,
    bs_status: status,
    bs_concurrency: Number(stringValue(data.get("bs_concurrency"))),
    bs_rps: Number(stringValue(data.get("bs_rps"))),
    bs_burst: Number(stringValue(data.get("bs_burst"))),
    bs_cooldown: Number(stringValue(data.get("bs_cooldown"))),
  };
}

export function PlatformForm({ mode, platform }: PlatformFormProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setFieldErrors({});
    setFeedback(undefined);
    try {
      await crawlerRequest<Platform>(
        mode === "edit" ? `/platforms/${platform?.bs_id}` : "/platforms",
        {
          method: mode === "edit" ? "PUT" : "POST",
          body: JSON.stringify(
            payloadFromForm(
              event.currentTarget,
              platform?.bs_status === "0" ? "0" : "1",
            ),
          ),
        },
      );
      router.push("/crawler/platforms");
    } catch (error) {
      if (error instanceof CrawlerApiError) {
        setFieldErrors(error.fieldErrors);
        if (error.kind !== "validation") setFeedback(error.message);
      } else {
        setFeedback(t("platforms.saveUnknownError"));
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
          <FormField id="bs_name" label={t("platforms.name")} required error={fieldErrors.bs_name}>
            <Input name="bs_name" defaultValue={platform?.bs_name ?? ""} className="bg-background" />
          </FormField>
          <FormField id="bs_platform_code" label={t("platforms.code")} required error={fieldErrors.bs_platform_code}>
            <Input
              name="bs_platform_code"
              defaultValue={platform?.bs_platform_code ?? ""}
              className="bg-background"
            />
          </FormField>
          <FormField id="bs_url" label={t("platforms.url")} error={fieldErrors.bs_url}>
            <Input name="bs_url" defaultValue={platform?.bs_url ?? ""} className="bg-background" />
          </FormField>
          <FormField id="bs_concurrency" label={t("platforms.concurrency")} required error={fieldErrors.bs_concurrency}>
            <NumberInput name="bs_concurrency" integer defaultValue={platform?.bs_concurrency ?? 1} />
          </FormField>
          <FormField id="bs_rps" label={t("platforms.rps")} required error={fieldErrors.bs_rps}>
            <NumberInput name="bs_rps" defaultValue={platform?.bs_rps ?? 1} />
          </FormField>
          <FormField id="bs_burst" label={t("platforms.burst")} required error={fieldErrors.bs_burst}>
            <NumberInput name="bs_burst" integer defaultValue={platform?.bs_burst ?? 3} />
          </FormField>
          <FormField id="bs_cooldown" label={t("platforms.cooldown")} required error={fieldErrors.bs_cooldown}>
            <NumberInput name="bs_cooldown" integer defaultValue={platform?.bs_cooldown ?? 300} />
          </FormField>
        </div>
        <FormField id="bs_remark" label={t("platforms.remark")} error={fieldErrors.bs_remark}>
          <Textarea
            name="bs_remark"
            defaultValue={platform?.bs_remark ?? ""}
            rows={4}
            className="bg-background"
          />
        </FormField>
        <div className="flex justify-end gap-2">
          <Link
            href="/crawler/platforms"
            className="touch-target inline-flex h-9 cursor-pointer items-center rounded-md border border-border bg-background px-4 text-sm font-medium hover:bg-accent"
          >
            {t("common.cancel")}
          </Link>
          <SubmitButton loading={loading}>
            {mode === "create" ? t("platforms.create") : t("common.save")}
          </SubmitButton>
        </div>
      </form>
    </Card>
  );
}
