// RevisionHistory：版本历史 Tab，展示状态并支持恢复、停用与删除草稿。
"use client";

import { useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { Loader2 } from "@/app/_components/Loader2";
import { ConfirmDialog } from "@/app/_components/ConfirmDialog";
import { Badge } from "@/app/_components/ui";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { t } from "@/app/i18n";
import {
  archiveParserRevision,
  deleteParserDraft,
  restoreParserRevision,
} from "@/api/action-parser/action-parser.api";
import type { ParserRevision } from "@/api/action-parser/action-parser.types";
import { CrawlerApiError } from "@/utils/crawler/crawler-api";
import { useParserWorkspace } from "../../index";

function statusVariant(status: ParserRevision["status"]) {
  if (status === "published") return "success";
  if (status === "draft") return "info";
  return "muted";
}

export function RevisionHistory() {
  const { action, revisions, replaceRevision, removeRevision } = useParserWorkspace(
    useShallow((state) => ({
      action: state.action,
      revisions: state.revisions,
      replaceRevision: state.replaceRevision,
      removeRevision: state.removeRevision,
    })),
  );

  const [busyId, setBusyId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  function errorMessage(error: unknown) {
    return error instanceof CrawlerApiError
      ? error.message
      : t("api.http", { status: 500 });
  }

  async function restore(revision: ParserRevision) {
    setBusyId(revision.revision_id);
    setFeedback(null);
    try {
      const restored = await restoreParserRevision(action.ba_id, revision.revision_id);
      replaceRevision(restored);
    } catch (error) {
      setFeedback(errorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  async function archive(revision: ParserRevision) {
    setBusyId(revision.revision_id);
    setFeedback(null);
    try {
      const archived = await archiveParserRevision(action.ba_id, revision.revision_id);
      replaceRevision(archived);
    } catch (error) {
      setFeedback(errorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(revisionId: number) {
    setBusyId(revisionId);
    setFeedback(null);
    try {
      await deleteParserDraft(action.ba_id, revisionId);
      removeRevision(revisionId);
      setDeleteId(null);
    } catch (error) {
      setFeedback(errorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card
      id="parser-history"
      role="tabpanel"
      aria-labelledby="parser-tab-history"
      className="grid gap-4 p-5 shadow-sm"
    >
      <h2 className="text-lg font-semibold text-foreground">
        {t("parser.revision.title")}
      </h2>

      {feedback ? (
        <p role="alert" className="text-sm text-destructive">
          {feedback}
        </p>
      ) : null}

      {revisions.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("parser.history.empty")}</p>
      ) : (
        <ul className="grid gap-2">
          {revisions.map((revision) => (
            <li
              key={revision.revision_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
            >
              <div className="grid gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {t("parser.revision.no", { no: revision.revision_no })}
                  </span>
                  <Badge variant={statusVariant(revision.status)}>
                    {t(`parser.revision.status.${revision.status}`)}
                  </Badge>
                </div>
                <span className="text-xs text-muted-foreground">
                  {t(`parser.revision.source.${revision.source}`)} ·{" "}
                  {t("parser.revision.updatedAt")}{" "}
                  {new Date(revision.updated_at).toLocaleString()}
                </span>
              </div>

              <div className="flex gap-2">
                {revision.status === "archived" ? (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busyId !== null}
                    onClick={() => void restore(revision)}
                    className="min-h-11 px-3"
                  >
                    {busyId === revision.revision_id ? (
                      <Loader2 className="mr-2 inline" />
                    ) : null}
                    {t("parser.restore.run")}
                  </Button>
                ) : null}
                {revision.status === "published" ? (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busyId !== null}
                    onClick={() => void archive(revision)}
                    className="min-h-11 px-3"
                  >
                    {busyId === revision.revision_id ? (
                      <Loader2 className="mr-2 inline" />
                    ) : null}
                    {t("parser.archive.run")}
                  </Button>
                ) : null}
                {revision.status === "draft" ? (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busyId !== null}
                    onClick={() => setDeleteId(revision.revision_id)}
                    className="min-h-11 px-3 text-destructive hover:bg-destructive/10 hover:text-destructive"
                  >
                    {t("common.delete")}
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleteId !== null}
        title={t("parser.draft.deleteTitle")}
        description={t("parser.draft.deleteDescription")}
        confirmLabel={t("common.delete")}
        cancelLabel={t("common.cancel")}
        destructive
        busy={busyId !== null}
        onCancel={() => setDeleteId(null)}
        onConfirm={() => deleteId !== null && void remove(deleteId)}
      />
    </Card>
  );
}