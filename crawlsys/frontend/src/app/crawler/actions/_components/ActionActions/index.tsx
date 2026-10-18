"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "../../../../_components/ConfirmDialog";
import { Feedback } from "../../../_components/Feedback";
import { Button } from "../../../../_components/ui/button";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Action } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

export function ActionActions({ action }: { action: Action }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string>();

  async function remove() {
    setBusy(true);
    setFeedback(undefined);
    try {
      await crawlerRequest<void>(`/actions/${action.ba_id}`, { method: "DELETE" });
      setOpen(false);
      router.refresh();
    } catch (error) {
      setFeedback(error instanceof CrawlerApiError ? error.message : t("actions.deleteUnknownError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <Link href={`/crawler/actions/${action.ba_id}/edit`} className="touch-target inline-flex cursor-pointer items-center text-sm font-medium text-primary hover:underline">
        {t("common.edit")}
      </Link>
      <Link href={`/crawler/actions/${action.ba_id}/parser`} className="touch-target inline-flex cursor-pointer items-center text-sm font-medium text-primary hover:underline">
        {t("actions.parserConfig")}
      </Link>
      <Button
        type="button"
        variant="link"
        size="sm"
        onClick={() => setOpen(true)}
        className="h-auto min-w-11 px-1 py-0 text-sm font-medium text-destructive hover:text-destructive hover:underline"
      >
        {t("common.delete")}
      </Button>
      <ConfirmDialog
        open={open}
        busy={busy}
        destructive
        title={t("actions.deleteTitle")}
        description={t("actions.deleteDescription", { action: action.ba_action })}
        confirmLabel={t("common.confirmDelete")}
        cancelLabel={t("common.cancel")}
        onCancel={() => setOpen(false)}
        onConfirm={remove}
      >
        {feedback ? <Feedback variant="error">{feedback}</Feedback> : null}
      </ConfirmDialog>
    </div>
  );
}
