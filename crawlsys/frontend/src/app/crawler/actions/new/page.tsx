// 新建接口页面：服务端加载平台选项，客户端表单处理提交反馈。
import { PageHeader } from "../../_components/PageHeader";
import { crawlerRequest } from "../../../../utils/crawler/crawler-api";
import type { PlatformList } from "../../../../utils/crawler/crawler-types";

import { ActionForm } from "../_components/ActionForm";
import { t } from "../../../i18n";

export const dynamic = "force-dynamic";

export default async function NewActionPage() {
  const platforms = await crawlerRequest<PlatformList>("/platforms?include_deleted=false");
  return (
    <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("actions.new")} description={t("actions.description")} />
      <ActionForm mode="create" platforms={platforms.items} />
    </main>
  );
}
