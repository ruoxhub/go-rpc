"use client";

import { Button } from "../_components/ui/button";
import { t } from "../i18n";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  const detail = error.message?.trim();
  return (
    <main className="mx-auto max-w-xl px-4 py-24 text-center">
      <h2 className="text-2xl font-semibold text-foreground">{t("settings.loadError")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{t("settings.loadErrorHint")}</p>
      {detail ? (
        <p className="mt-4 break-words rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {detail}
        </p>
      ) : null}
      <Button type="button" variant="gradient" onClick={reset} className="mt-6">
        {t("error.retry")}
      </Button>
    </main>
  );
}
