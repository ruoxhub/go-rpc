// 接口管理列表：服务端并行加载平台选项与按 URL 筛选的接口数据。
import Link from "next/link";

import { FilterBar } from "../_components/FilterBar";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../../_components/ui/button";
import { Select } from "../../_components/ui/select";
import { crawlerRequest } from "../../../utils/crawler/crawler-api";
import type { ActionList, PlatformList } from "../../../utils/crawler/crawler-types";
import { t } from "../../i18n";

import { ActionsTable } from "./_components/ActionsTable";
import { ImportActionsDialog } from "./_components/ImportActionsDialog";
import { SyncActionsDialog } from "./_components/SyncActionsDialog";

export const dynamic = "force-dynamic";

export default async function ActionsPage({
  searchParams,
}: {
  searchParams: Promise<{ platform_id?: string }>;
}) {
  const { platform_id: rawPlatformId } = await searchParams;
  const platformId = /^\d+$/.test(rawPlatformId ?? "") ? rawPlatformId : undefined;
  const [platforms, actions] = await Promise.all([
    crawlerRequest<PlatformList>("/platforms?include_deleted=false"),
    crawlerRequest<ActionList>(`/actions${platformId ? `?platform_id=${platformId}` : ""}`),
  ]);
  const names = new Map(platforms.items.map((platform) => [
    platform.bs_id,
    platform.bs_name ?? platform.bs_platform_code ?? t("actions.platformName", { id: platform.bs_id }),
  ]));
  const platformNames = Object.fromEntries(names);

  return (
    <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader title={t("actions.title")} description={t("actions.description")}>
        <SyncActionsDialog platforms={platforms.items} defaultPlatformId={platformId} />
        <ImportActionsDialog platforms={platforms.items} />
        <Link href="/crawler/actions/new" className="touch-target inline-flex h-9 cursor-pointer items-center rounded-md bg-gradient-back px-4 text-sm font-medium text-gradient-foreground shadow-sm hover:shadow-md">
          {t("actions.new")}
        </Link>
      </PageHeader>
      <FilterBar aria-label={t("actions.filter")}>
        <form action="/crawler/actions" className="flex items-end gap-2">
          <label className="grid gap-1.5 text-xs font-medium">
            {t("common.platformFilter")}
            <Select aria-label={t("common.platformFilter")} name="platform_id" defaultValue={platformId ?? ""} className="bg-background font-normal">
              <option value="">{t("common.allPlatforms")}</option>
              {platforms.items.map((platform) => <option key={platform.bs_id} value={platform.bs_id}>{names.get(platform.bs_id)}</option>)}
            </Select>
          </label>
          <Button type="submit" variant="outline">{t("common.filter")}</Button>
        </form>
      </FilterBar>
      <ActionsTable actions={actions.items} platformNames={platformNames} />
    </main>
  );
}
