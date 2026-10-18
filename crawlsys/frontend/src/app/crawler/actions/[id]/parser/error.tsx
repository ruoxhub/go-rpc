// ParserError：解析器路由错误边界和重试入口。
"use client";

import { Button } from "../../../../_components/ui/button";
import { t } from "../../../../i18n";

export default function ParserError({ reset }: { reset: () => void }) {
  return (
    <main className="mx-auto grid w-full max-w-7xl gap-4 px-4 py-6 lg:px-8">
      <h1 className="text-xl font-semibold text-foreground">
        {t("parser.error.title")}
      </h1>
      <p role="alert" className="text-sm text-destructive">
        {t("parser.error.description")}
      </p>
      <Button
        type="button"
        variant="gradient"
        onClick={reset}
        className="touch-target w-fit"
      >
        {t("common.retry")}
      </Button>
    </main>
  );
}
