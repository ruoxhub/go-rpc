"use client";

import { Button } from "../_components/ui/button";
import { t } from "../i18n";

export default function AnalysisError({ reset }: { reset: () => void }) {
  return (
    <main className="grid min-h-96 place-items-center px-4 text-center">
      <div>
        <h1 className="text-2xl font-semibold">{t("analysis.error.title")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("analysis.error.description")}</p>
        <Button onClick={reset} variant="gradient" className="mt-5 rounded-full px-5 py-2.5">
          {t("analysis.error.retry")}
        </Button>
      </div>
    </main>
  );
}
