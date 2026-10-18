// 编辑关键词页面：服务端并行加载详情与含历史记录的平台数据。
import { notFound } from "next/navigation";

import { PageHeader } from "../../../_components/PageHeader";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Keyword, PlatformList } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

import { KeywordForm } from "../../_components/KeywordForm";

export const dynamic = "force-dynamic";

export default async function EditKeywordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [keywordResult, platforms] = await Promise.all([
    crawlerRequest<Keyword>(`/keywords/${id}`).then((value) => ({ value })).catch((error: unknown) => ({ error })),
    crawlerRequest<PlatformList>("/platforms?include_deleted=true"),
  ]);
  if ("error" in keywordResult) {
    if (keywordResult.error instanceof CrawlerApiError && keywordResult.error.status === 404) notFound();
    throw keywordResult.error;
  }
  return <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
    <PageHeader title={t("keywords.edit")} description={t("keywords.description")} />
    <KeywordForm mode="edit" keyword={keywordResult.value} platforms={platforms.items} />
  </main>;
}
