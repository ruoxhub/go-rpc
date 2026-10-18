// 新建关键词页面：服务端加载可用平台，客户端表单负责提交。
import { PageHeader } from "../../_components/PageHeader";
import { crawlerRequest } from "../../../../utils/crawler/crawler-api";
import type { PlatformList } from "../../../../utils/crawler/crawler-types";

import { KeywordForm } from "../_components/KeywordForm";
import { t } from "../../../i18n";

export const dynamic = "force-dynamic";

export default async function NewKeywordPage() {
  const platforms = await crawlerRequest<PlatformList>("/platforms?include_deleted=false");
  return <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
    <PageHeader title={t("keywords.new")} description={t("keywords.description")} />
    <KeywordForm mode="create" platforms={platforms.items} />
  </main>;
}
