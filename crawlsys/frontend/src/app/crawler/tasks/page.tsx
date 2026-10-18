// 任务管理列表：服务端并行加载筛选项和任务首屏数据。
import Link from "next/link";

import { DataTable, type DataTableColumn } from "../_components/DataTable";
import { FilterBar } from "../_components/FilterBar";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../../_components/ui/button";
import { Select } from "../../_components/ui/select";
import { crawlerRequest } from "../../../utils/crawler/crawler-api";
import type {
  PlatformList,
  Task,
  TaskList,
} from "../../../utils/crawler/crawler-types";
import { t } from "../../i18n";

import { TaskActions } from "./_components/TaskActions";
import { BatchTaskActions } from "./_components/TaskActions/BatchTaskActions";

import { scheduleSummary } from "./_components/TaskForm/utils/taskForm";
import {
  taskPriorityBadgeClass,
  taskPriorityLabel,
} from "./_utils/taskPriority";

export const dynamic = "force-dynamic";

function taskColumns(): DataTableColumn<Task>[] {
  return [
    {
      id: "task",
      header: t("nav.tasks"),
      accessor: (row) => `${row.platform} / ${row.action}`,
    },
    {
      id: "priority",
      header: t("tasks.priority"),
      render: (row) => (
        <span
          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${taskPriorityBadgeClass(row.priority)}`}
        >
          {taskPriorityLabel(row.priority)}
        </span>
      ),
    },
    { id: "status", header: t("common.status"), accessor: "status" },
    { id: "attempts", header: t("tasks.attempts"), accessor: "attempts" },
    {
      id: "schedule",
      header: t("tasks.scheduleType"),
      accessor: (row) => scheduleSummary(row),
    },
    {
      id: "next_execution",
      header: t("tasks.nextExecution"),
      className: "hidden md:table-cell",
      accessor: (row) => row.next_retry_at ?? row.next_run_at ?? t("tasks.none"),
    },
    {
      id: "run_progress",
      header: t("tasks.runProgress"),
      className: "hidden lg:table-cell",
      accessor: (row) =>
        `${row.run_count} / ${row.max_runs ?? t("tasks.unlimitedRuns")}`,
    },
    {
      id: "last_run_status",
      header: t("tasks.lastRunStatus"),
      className: "hidden lg:table-cell",
      accessor: (row) =>
        row.last_run_status === "success"
          ? t("tasks.lastRunSuccess")
          : row.last_run_status === "failed"
            ? t("tasks.lastRunFailed")
            : t("tasks.none"),
    },
    {
      id: "error",
      header: t("tasks.latestError"),
      accessor: (row) => row.error_msg ?? t("tasks.none"),
    },
    {
      id: "actions",
      header: t("common.actions"),
      className: "text-right",
      render: (row) => <TaskActions task={row} />,
    },
  ];
}

export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<{ platform?: string | string[] }>;
}) {
  const { platform: rawPlatform } = await searchParams;
  const firstPlatform = Array.isArray(rawPlatform)
    ? rawPlatform[0]
    : rawPlatform;
  const platform =
    firstPlatform && /^[a-zA-Z0-9_-]+$/.test(firstPlatform)
      ? firstPlatform
      : undefined;
  const [platforms, tasks] = await Promise.all([
    crawlerRequest<PlatformList>("/platforms?include_deleted=false"),
    crawlerRequest<TaskList>(
      `/tasks${platform ? `?platform=${encodeURIComponent(platform)}` : ""}`,
    ),
  ]);

  return (
    <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader
        title={t("tasks.title")}
        description={t("tasks.description")}
      >
        <Link
          href="/crawler/tasks/new"
          className="touch-target inline-flex h-9 items-center rounded-md bg-gradient-back px-4 text-sm font-medium text-gradient-foreground"
        >
          {t("tasks.new")}
        </Link>
      </PageHeader>
      <FilterBar aria-label={t("tasks.filter")}>
        <form
          action="/crawler/tasks"
          className="flex flex-wrap items-end gap-2"
        >
          <label className="grid gap-1 text-xs font-medium">
            {t("common.platformFilter")}
            <Select
              aria-label={t("common.platformFilter")}
              name="platform"
              defaultValue={platform ?? ""}
              className="bg-background"
            >
              <option value="">{t("common.allPlatforms")}</option>
              {platforms.items.map((item) => (
                <option key={item.bs_id} value={item.bs_platform_code ?? ""}>
                  {item.bs_name ?? item.bs_platform_code}
                </option>
              ))}
            </Select>
          </label>
          <Button
            type="submit"
            variant="outline"
          >
            {t("common.filter")}
          </Button>
          <BatchTaskActions platform={platform} />
        </form>
      </FilterBar>
      <DataTable
        caption={t("tasks.list")}
        columns={taskColumns()}
        rows={tasks.items}
        getRowKey={(row) => row.task_id}
        emptyText={t("tasks.empty")}
      />
    </main>
  );
}
