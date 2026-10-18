"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { Loader2 } from "../../../../_components/Loader2";
import { Button } from "../../../../_components/ui/button";
import {
  CrawlerApiError,
  crawlerRequest,
} from "../../../../../utils/crawler/crawler-api";
import type { TaskBatchStatusResponse } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

type BatchOperation = "start-all" | "pause-all";

export function BatchTaskActions({ platform }: { platform?: string }) {
  const router = useRouter();
  const [busyAction, setBusyAction] = useState<BatchOperation>();
  const busy = busyAction !== undefined;
  const [message, setMessage] = useState<string>();
  const [failed, setFailed] = useState(false);

  async function run(action: BatchOperation) {
    setBusyAction(action);
    setMessage(undefined);
    setFailed(false);
    try {
      const result = await crawlerRequest<TaskBatchStatusResponse>(
        `/tasks/${action}`,
        {
          method: "POST",
          body: JSON.stringify({ platform: platform || null }),
        },
      );
      setMessage(t("tasks.updated", { count: result.updated_count }));
      router.refresh();
    } catch (error) {
      setFailed(true);
      setMessage(
        error instanceof CrawlerApiError ? error.message : t("tasks.batchFailed"),
      );
    } finally {
      setBusyAction(undefined);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        disabled={busy}
        aria-busy={busyAction === "start-all" || undefined}
        onClick={() => run("start-all")}
        className="px-3"
      >
        {busyAction === "start-all" ? (
          <Loader2 className="mr-1 inline" />
        ) : null}
        {t("tasks.batchStart")}
      </Button>
      <Button
        type="button"
        variant="outline"
        disabled={busy}
        aria-busy={busyAction === "pause-all" || undefined}
        onClick={() => run("pause-all")}
        className="px-3"
      >
        {busyAction === "pause-all" ? (
          <Loader2 className="mr-1 inline" />
        ) : null}
        {t("tasks.batchPause")}
      </Button>
      {message ? (
        <Feedback variant={failed ? "error" : "success"}>{message}</Feedback>
      ) : null}
    </div>
  );
}
