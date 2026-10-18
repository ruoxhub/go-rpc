// 编辑任务页面：并行加载详情及包含历史归属的选项。
import { notFound } from "next/navigation";

import { PageHeader } from "../../../_components/PageHeader";
import {
  CrawlerApiError,
  crawlerRequest,
} from "../../../../../utils/crawler/crawler-api";
import type {
  ActionList,
  PlatformList,
  Task,
} from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

import { TaskForm } from "../../_components/TaskForm";

export const dynamic = "force-dynamic";

export default async function EditTaskPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  let task: Task;
  let platforms: PlatformList;
  let actions: ActionList;
  try {
    [task, platforms, actions] = await Promise.all([
      crawlerRequest<Task>(`/tasks/${id}`),
      crawlerRequest<PlatformList>("/platforms?include_deleted=true"),
      crawlerRequest<ActionList>("/actions"),
    ]);
  } catch (error) {
    if (error instanceof CrawlerApiError && error.status === 404) notFound();
    throw error;
  }
  return (
    <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader
        title={t("tasks.edit")}
        description={t("tasks.description")}
      />
      <TaskForm
        mode="edit"
        task={task}
        platforms={platforms.items}
        actions={actions.items}
      />
    </main>
  );
}
