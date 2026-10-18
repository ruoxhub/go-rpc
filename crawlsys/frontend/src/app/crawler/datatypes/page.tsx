// 数据模型管理列表：服务端加载已同步的 ORM/DTO 数据类型元数据。
import { getDatatypes } from "../../../api/datatype/datatype.api";
import { PageHeader } from "../_components/PageHeader";
import { t } from "../../i18n";

import { DatatypesTable } from "./_components/DatatypesTable";
import { SyncDatatypesButton } from "./_components/SyncDatatypesButton";

export const dynamic = "force-dynamic";

export default async function DatatypesPage() {
  const datatypes = await getDatatypes();

  return (
    <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("datatypes.title")} description={t("datatypes.description")}>
        <SyncDatatypesButton />
      </PageHeader>
      <DatatypesTable datatypes={datatypes.items} />
    </main>
  );
}
