// 编辑接口页面：并行加载接口详情与平台选项，避免串行请求。
import { notFound } from "next/navigation";

import { PageHeader } from "../../../_components/PageHeader";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Action, PlatformList } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

import { ActionForm } from "../../_components/ActionForm";

export const dynamic = "force-dynamic";

export default async function EditActionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  let action: Action;
  let platforms: PlatformList;
  try {
    [action, platforms] = await Promise.all([
      crawlerRequest<Action>(`/actions/${id}`),
      crawlerRequest<PlatformList>("/platforms?include_deleted=true"),
    ]);
  } catch (error) {
    if (error instanceof CrawlerApiError && error.status === 404) notFound();
    throw error;
  }
  return (
    <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("actions.edit")} description={t("actions.description")} />
      <ActionForm mode="edit" action={action} platforms={platforms.items} />
    </main>
  );
}
