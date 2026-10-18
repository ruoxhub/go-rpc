// TaskPriorityControl：原子调整任务优先级，并在请求失败时回滚本地选择。
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { Loader2 } from "../../../../_components/Loader2";
import { Select } from "../../../../_components/ui/select";
import {
  CrawlerApiError,
  updateTaskPriority,
} from "../../../../../utils/crawler/crawler-api";
import {
  isTaskPriority,
  TASK_PRIORITIES,
  type Task,
  type TaskPriority,
} from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";
import { taskPriorityLabel } from "../../_utils/taskPriority";

export function TaskPriorityControl({ task }: { task: Task }) {
  const router = useRouter();
  const [priority, setPriority] = useState(task.priority);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string>();
  const [failed, setFailed] = useState(false);

  async function changePriority(nextPriority: TaskPriority) {
    const previousPriority = priority;
    setPriority(nextPriority);
    setBusy(true);
    setFeedback(undefined);
    setFailed(false);
    try {
      const updated = await updateTaskPriority(task.task_id, nextPriority);
      setPriority(updated.priority);
      setFeedback(t("tasks.priorityUpdated"));
      router.refresh();
    } catch (error) {
      setPriority(previousPriority);
      setFailed(true);
      setFeedback(
        error instanceof CrawlerApiError
          ? error.message
          : t("tasks.priorityUpdateUnknownError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Select
        aria-label={t("tasks.adjustPriority", { id: task.task_id })}
        value={priority}
        disabled={busy}
        onChange={(event) => {
          if (isTaskPriority(event.target.value)) void changePriority(event.target.value);
        }}
        className="w-auto cursor-pointer bg-background px-2 text-sm"
      >
        {TASK_PRIORITIES.map((option) => (
          <option key={option} value={option}>
            {taskPriorityLabel(option)}
          </option>
        ))}
      </Select>
      {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
      {feedback ? (
        <Feedback variant={failed ? "error" : "success"}>{feedback}</Feedback>
      ) : null}
    </div>
  );
}
