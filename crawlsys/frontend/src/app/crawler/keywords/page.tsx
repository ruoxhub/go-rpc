// 关键词管理列表：服务端并行加载平台选项与按 URL 筛选的关键词。
import Link from "next/link";

import { DataTable, type DataTableColumn } from "../_components/DataTable";
import { FilterBar } from "../_components/FilterBar";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../../_components/ui/button";
import { Select } from "../../_components/ui/select";
import { crawlerRequest } from "../../../utils/crawler/crawler-api";
import type { Keyword, KeywordList, PlatformList } from "../../../utils/crawler/crawler-types";
import { t } from "../../i18n";

import { KeywordActions } from "./_components/KeywordActions";

export const dynamic = "force-dynamic";

export default async function KeywordsPage({ searchParams }: { searchParams: Promise<{ platform?: string | string[] }> }) {
  const { platform: rawPlatform } = await searchParams;
  const platformValues = Array.isArray(rawPlatform) ? rawPlatform : [rawPlatform];
  const platform = platformValues.find((value) => value?.trim())?.trim();
  const [platforms, keywords] = await Promise.all([
    crawlerRequest<PlatformList>("/platforms?include_deleted=false"),
    crawlerRequest<KeywordList>(`/keywords${platform ? `?platform=${encodeURIComponent(platform)}` : ""}`),
  ]);
  const activePlatforms = platforms.items.filter((item) => item.bs_status === "1" && item.bs_platform_code);
  const activeCodes = new Set(activePlatforms.map((item) => item.bs_platform_code));
  const unavailableFilter = platform && !activeCodes.has(platform);
  const names = new Map(platforms.items.flatMap((item) => item.bs_platform_code ? [[item.bs_platform_code, item.bs_name ?? item.bs_platform_code] as const] : []));
  const columns: DataTableColumn<Keyword>[] = [
    { id: "keyword", header: t("keywords.name"), accessor: "keyword" },
    { id: "platform", header: t("nav.platforms"), accessor: (row) => names.get(row.platform) ?? row.platform },
    { id: "status", header: t("keywords.crawlStatus"), render: (row) => <span className={row.is_crawled ? "text-success-strong" : "text-muted-foreground"}>{row.is_crawled ? t("keywords.crawled") : t("keywords.pending")}</span> },
    { id: "actions", header: t("common.actions"), className: "text-right", render: (row) => <KeywordActions keyword={row} /> },
  ];

  return <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
    <PageHeader title={t("keywords.title")} description={t("keywords.description")}>
      <Link href="/crawler/keywords/new" className="touch-target inline-flex h-9 cursor-pointer items-center rounded-md bg-gradient-back px-4 text-sm font-medium text-gradient-foreground shadow-sm hover:shadow-md">{t("keywords.new")}</Link>
    </PageHeader>
    <FilterBar aria-label={t("keywords.filter")}><form action="/crawler/keywords" className="flex items-end gap-2">
      <label className="grid gap-1.5 text-xs font-medium">{t("common.platformFilter")}<Select aria-label={t("common.platformFilter")} name="platform" defaultValue={platform ?? ""} className="bg-background font-normal"><option value="">{t("common.allPlatforms")}</option>{unavailableFilter ? <option value={platform} disabled>{t("keywords.unavailableHistory", { platform })}</option> : null}{activePlatforms.map((item) => <option key={item.bs_id} value={item.bs_platform_code!}>{item.bs_name ?? item.bs_platform_code}</option>)}</Select></label>
      <Button type="submit" variant="outline">{t("common.filter")}</Button>
    </form></FilterBar>
    <DataTable caption={t("keywords.list")} columns={columns} rows={keywords.items} getRowKey={(row) => row.id} emptyText={t("keywords.empty")} />
  </main>;
}
