// 新建平台页面：复用平台表单提交完整平台配置。
import { PageHeader } from "../../_components/PageHeader";

import { PlatformForm } from "../_components/PlatformForm";
import { t } from "../../../i18n";

export default function NewPlatformPage() {
  return (
    <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("platforms.new")} description={t("platforms.description")} />
      <PlatformForm mode="create" />
    </main>
  );
}
