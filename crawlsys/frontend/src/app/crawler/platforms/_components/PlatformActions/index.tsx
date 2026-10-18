"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "../../../../_components/ConfirmDialog";
import { Feedback } from "../../../_components/Feedback";
import { Button } from "../../../../_components/ui/button";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Platform } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

export function PlatformActions({ platform }: { platform: Platform }) {
  const router = useRouter();
  const deleted = platform.bs_status === "D";
  const action = deleted ? t("common.restore") : t("common.delete");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string>();

  async function confirm() {
    setBusy(true);
    setFeedback(undefined);
    try {
      await crawlerRequest<void | Platform>(
        `/platforms/${platform.bs_id}${deleted ? "/restore" : ""}`,
        { method: deleted ? "POST" : "DELETE" },
      );
      setOpen(false);
      router.refresh();
    } catch (error) {
      setFeedback(
        error instanceof CrawlerApiError ? error.message : t("platforms.operationUnknownError", { action }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {!deleted ? (
        <Link
          href={`/crawler/platforms/${platform.bs_id}/edit`}
          className="touch-target inline-flex cursor-pointer items-center text-sm font-medium text-primary hover:underline"
        >
          {t("common.edit")}
        </Link>
      ) : null}
      <Button
        type="button"
        variant="link"
        size="sm"
        onClick={() => setOpen(true)}
        className={`h-auto min-w-11 px-1 py-0 text-sm font-medium hover:underline ${
          deleted ? "text-primary" : "text-destructive hover:text-destructive"
        }`}
      >
        {action}
      </Button>
      <ConfirmDialog
        open={open}
        busy={busy}
        destructive={!deleted}
        title={t("platforms.operationTitle", { action })}
        description={
          deleted
            ? t("platforms.restoreDescription", { name: platform.bs_name ?? platform.bs_platform_code ?? "" })
            : t("platforms.deleteDescription", { name: platform.bs_name ?? platform.bs_platform_code ?? "" })
        }
        confirmLabel={t("platforms.confirmOperation", { action })}
        cancelLabel={t("common.cancel")}
        onCancel={() => setOpen(false)}
        onConfirm={confirm}
      >
        {feedback ? <Feedback variant="error">{feedback}</Feedback> : null}
      </ConfirmDialog>
    </div>
  );
}
