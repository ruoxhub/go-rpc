// 新建任务页面：服务端并行加载平台和接口选项。
import { PageHeader } from "../../_components/PageHeader";
import { crawlerRequest } from "../../../../utils/crawler/crawler-api";
import type {
  ActionList,
  PlatformList,
} from "../../../../utils/crawler/crawler-types";

import { TaskForm } from "../_components/TaskForm";
import { t } from "../../../i18n";

export const dynamic = "force-dynamic";

export default async function NewTaskPage() {
  const [platforms, actions] = await Promise.all([
    crawlerRequest<PlatformList>("/platforms?include_deleted=false"),
    crawlerRequest<ActionList>("/actions"),
  ]);
  return (
    <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader
        title={t("tasks.new")}
        description={t("tasks.description")}
      />
      <TaskForm
        mode="create"
        platforms={platforms.items}
        actions={actions.items}
      />
    </main>
  );
}
