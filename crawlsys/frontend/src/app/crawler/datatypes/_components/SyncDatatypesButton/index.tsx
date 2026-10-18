"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Loader2 } from "../../../../_components/Loader2";
import { Button } from "../../../../_components/ui/button";
import { Feedback } from "../../../_components/Feedback";
import { CrawlerApiError } from "../../../../../utils/crawler/crawler-api";
import { syncDatatypes } from "../../../../../api/datatype/datatype.api";
import { t } from "../../../../i18n";

export function SyncDatatypesButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ failed: boolean; text: string } | null>(null);

  async function sync() {
    setLoading(true);
    setFeedback(null);
    try {
      const result = await syncDatatypes();
      setFeedback({
        failed: false,
        text: t("datatypes.syncSuccess", { count: result.synced_count }),
      });
      router.refresh();
    } catch (error) {
      setFeedback({
        failed: true,
        text:
          error instanceof CrawlerApiError
            ? error.message
            : t("datatypes.syncUnknownError"),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button
        type="button"
        variant="outline"
        onClick={sync}
        disabled={loading}
        aria-busy={loading || undefined}
        className="touch-target gap-2"
      >
        {loading ? <Loader2 /> : null}
        {loading ? t("datatypes.syncing") : t("datatypes.sync")}
      </Button>
      {feedback ? (
        <Feedback variant={feedback.failed ? "error" : "success"}>
          {feedback.text}
        </Feedback>
      ) : null}
    </div>
  );
}
