"use client";

import { useState, type ReactNode } from "react";

import { Loader2 } from "../../../_components/Loader2";
import { Button } from "../../../_components/ui/button";
import { Card } from "../../../_components/ui/card";
import { Alert, AlertDescription } from "../../../_components/ui/alert";
import { CrawlerApiError } from "../../../../utils/crawler/crawler-api";
import { t } from "../../../i18n";

export interface CardFormState {
  fieldErrors: Record<string, string>;
}

interface ConfigCardProps {
  title: string;
  description: string;
  saveLabel: string;
  onSave: (data: FormData) => Promise<unknown>;
  onSuccess?: (result: unknown, form: HTMLFormElement) => void;
  children: (state: CardFormState) => ReactNode;
}

function saveErrorMessage(error: unknown) {
  if (!(error instanceof CrawlerApiError)) return t("settings.saveError");
  if (error.kind === "validation") return t("api.validation");
  if (error.kind === "network") return t("settings.error.network");
  if (error.status === 503) return t("settings.error.unavailable");
  return t("settings.error.request");
}

export function ConfigCard({ title, description, saveLabel, onSave, onSuccess, children }: ConfigCardProps) {
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaving(true);
    setFeedback(null);
    setFieldErrors({});
    try {
      const result = await onSave(new FormData(form));
      onSuccess?.(result, form);
      setFeedback({ kind: "success", message: t("settings.saveSuccess") });
    } catch (error) {
      if (error instanceof CrawlerApiError) setFieldErrors(error.fieldErrors);
      setFeedback({ kind: "error", message: saveErrorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="rounded-xl shadow-sm">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-base font-semibold text-card-foreground">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <form onSubmit={submit} className="space-y-5 p-5">
        <div className="grid gap-4 sm:grid-cols-2">{children({ fieldErrors })}</div>
        {feedback ? (
          <Alert
            variant={feedback.kind === "error" ? "destructive" : "success"}
            role={feedback.kind === "error" ? "alert" : "status"}
            className="px-3 py-2 text-sm"
          >
            <AlertDescription>{feedback.message}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex justify-end">
          <Button type="submit" variant="gradient" disabled={saving}>
            {saving ? <Loader2 className="mr-2" /> : null}
            {saveLabel}
          </Button>
        </div>
      </form>
    </Card>
  );
}
