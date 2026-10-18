// 编辑平台页面：服务端加载详情，客户端叶子负责表单交互。
import { notFound } from "next/navigation";

import { PageHeader } from "../../../_components/PageHeader";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Platform } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

import { PlatformForm } from "../../_components/PlatformForm";

export default async function EditPlatformPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let platform: Platform;
  try {
    platform = await crawlerRequest<Platform>(`/platforms/${id}`);
  } catch (error) {
    if (error instanceof CrawlerApiError && error.status === 404) notFound();
    throw error;
  }
  if (platform.bs_status === "D") notFound();

  return (
    <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("platforms.edit")} description={t("platforms.description")} />
      <PlatformForm mode="edit" platform={platform} />
    </main>
  );
}
