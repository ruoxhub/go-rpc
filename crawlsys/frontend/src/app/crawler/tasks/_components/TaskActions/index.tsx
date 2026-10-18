"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "../../../../_components/ConfirmDialog";
import { Feedback } from "../../../_components/Feedback";
import { Loader2 } from "../../../../_components/Loader2";
import { TaskPriorityControl } from "../TaskPriorityControl";
import {
  CrawlerApiError,
  crawlerRequest,
  runTaskNow,
  updateTaskOperation,
} from "../../../../../utils/crawler/crawler-api";
import type { Task } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

type Operation = "start" | "pause" | "delete" | "run-now";

function primaryOperation(task: Task): Exclude<Operation, "delete" | "run-now"> {
  return task.status === "pending" || task.status === "running"
    ? "pause"
    : "start";
}

export function TaskActions({ task }: { task: Task }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<Operation | null>(null);
  const [feedback, setFeedback] = useState<string>();
  const [failed, setFailed] = useState(false);
  const operation = primaryOperation(task);

  async function operate(nextOperation: Operation) {
    setBusy(nextOperation);
    setFeedback(undefined);
    setFailed(false);
    try {
      if (nextOperation === "delete") {
        await crawlerRequest(`/tasks/${task.task_id}`, { method: "DELETE" });
      } else if (nextOperation === "run-now") {
        await runTaskNow(task.task_id);
      } else {
        await updateTaskOperation(task.task_id, nextOperation);
      }
      if (nextOperation === "delete") setOpen(false);
      setFeedback(
        nextOperation === "delete"
          ? t("tasks.deleted")
          : nextOperation === "run-now"
            ? t("tasks.queued")
            : nextOperation === "start"
              ? task.status === "paused" ? t("tasks.resumed") : t("tasks.started")
              : t("tasks.paused"),
      );
      router.refresh();
    } catch (error) {
      setFailed(true);
      setFeedback(
        error instanceof CrawlerApiError
          ? error.message
          : t("tasks.operationUnknownError"),
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <TaskPriorityControl task={task} />
      <Link
        href={`/crawler/tasks/${task.task_id}/edit`}
        className="touch-target inline-flex items-center text-sm font-medium text-primary hover:underline"
      >
        {t("common.edit")}
      </Link>
      <button
        type="button"
        disabled={busy !== null || Boolean(task.run_now_requested_at)}
        aria-busy={busy === "run-now" || undefined}
        onClick={() => operate("run-now")}
        className="min-w-11 cursor-pointer px-2 text-sm font-medium text-primary disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy === "run-now" ? <Loader2 className="mr-1 inline" /> : null}
        {task.run_now_requested_at ? t("tasks.queuedLabel") : t("tasks.runNow")}
      </button>
      <button
        type="button"
        disabled={busy !== null}
        aria-busy={busy === operation || undefined}
        onClick={() => operate(operation)}
        className="min-w-11 cursor-pointer px-2 text-sm font-medium text-primary disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy === operation ? <Loader2 className="mr-1 inline" /> : null}
        {operation === "start"
          ? task.status === "paused" ? t("tasks.resume") : t("tasks.start")
          : t("tasks.pause")}
      </button>
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => setOpen(true)}
        className="min-w-11 cursor-pointer px-2 text-sm font-medium text-destructive disabled:cursor-not-allowed disabled:opacity-50"
      >
        {t("common.delete")}
      </button>
      {feedback && !open ? (
        <Feedback variant={failed ? "error" : "success"}>{feedback}</Feedback>
      ) : null}
      <ConfirmDialog
        open={open}
        busy={busy === "delete"}
        destructive
        title={t("tasks.deleteTitle")}
        description={t("tasks.deleteDescription", { platform: task.platform, action: task.action })}
        confirmLabel={t("common.confirmDelete")}
        cancelLabel={t("common.cancel")}
        onCancel={() => setOpen(false)}
        onConfirm={() => operate("delete")}
      >
        {feedback ? (
          <Feedback variant={failed ? "error" : "success"}>
            {feedback}
          </Feedback>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}
