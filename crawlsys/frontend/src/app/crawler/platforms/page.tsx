// 平台管理列表：服务端首屏加载，并通过 URL 控制软删除记录可见性。
import Link from "next/link";

import { DataTable, type DataTableColumn } from "../_components/DataTable";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../../_components/ui/button";
import { crawlerRequest } from "../../../utils/crawler/crawler-api";
import type { Platform, PlatformList } from "../../../utils/crawler/crawler-types";
import { t } from "../../i18n";

import { PlatformActions } from "./_components/PlatformActions";

const columns: DataTableColumn<Platform>[] = [
  { id: "name", header: t("platforms.name"), accessor: (row) => row.bs_name ?? "—" },
  { id: "code", header: t("platforms.code"), accessor: (row) => row.bs_platform_code ?? "—" },
  {
    id: "quota",
    header: t("platforms.quota"),
    accessor: (row) => t("platforms.quotaValue", { concurrency: row.bs_concurrency ?? "—", rps: row.bs_rps ?? "—" }),
  },
  {
    id: "status",
    header: t("common.status"),
    render: (row) => (
      <span className={row.bs_status === "D" ? "text-destructive" : "text-success-strong"}>
        {row.bs_status === "D" ? t("common.deleted") : row.bs_status === "0" ? t("common.disabled") : t("common.enabled")}
      </span>
    ),
  },
  {
    id: "actions",
    header: t("common.actions"),
    className: "text-right",
    render: (row) => <PlatformActions platform={row} />,
  },
];

export default async function PlatformsPage({
  searchParams,
}: {
  searchParams: Promise<{ include_deleted?: string }>;
}) {
  const params = await searchParams;
  const includeDeleted = params.include_deleted === "1";
  const data = await crawlerRequest<PlatformList>(
    `/platforms?include_deleted=${includeDeleted}`,
  );

  return (
    <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("platforms.title")} description={t("platforms.description")}>
        <Button asChild variant="gradient">
          <Link href="/crawler/platforms/new">
            {t("platforms.new")}
          </Link>
        </Button>
      </PageHeader>
      <div className="flex justify-end">
        <Link
          href={includeDeleted ? "/crawler/platforms" : "/crawler/platforms?include_deleted=1"}
          className="touch-target inline-flex cursor-pointer items-center text-sm font-medium text-primary hover:underline"
        >
          {includeDeleted ? t("platforms.hideDeleted") : t("platforms.showDeleted")}
        </Link>
      </div>
      <DataTable
        caption={t("platforms.list")}
        columns={columns}
        rows={data.items}
        getRowKey={(row) => row.bs_id}
        emptyText={t("platforms.empty")}
      />
    </main>
  );
}
