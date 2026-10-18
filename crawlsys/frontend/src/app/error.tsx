"use client";

import { Button } from "./_components/ui/button";
import { t } from "./i18n";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto max-w-xl px-4 py-24 text-center">
      <h2 className="text-2xl font-semibold tracking-[-0.01em]">
        {t("error.title")}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {t("error.description")}
      </p>
      <Button
        type="button"
        variant="gradient"
        onClick={reset}
        className="mt-6"
      >
        {t("error.retry")}
      </Button>
    </main>
  );
}
