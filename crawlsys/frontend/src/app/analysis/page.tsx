/** 视频分析素材列表：筛选并分页浏览全部未删除素材。 */
import Link from "next/link";

import { Badge } from "../_components/ui";
import { Button } from "../_components/ui/button";
import { Card } from "../_components/ui/card";
import { Select } from "../_components/ui/select";
import { MaterialCover } from "./_components/MaterialCover";
import { t } from "../i18n";
import { getAnalysisFilters, getAnalysisThumbnailUrl, listMaterials } from "@/utils/analysis";

const statusVariants = {
  pending: "muted",
  succeeded: "success",
  processing: "info",
  failed: "destructive",
} as const;

const statusKeys = {
  pending: "analysis.status.pending",
  succeeded: "analysis.status.succeeded",
  processing: "analysis.status.processing",
  failed: "analysis.status.failed",
} as const;

function normalizedNumber(value: string | undefined, allowed: number[], fallback: number) {
  const number = Number(value);
  return allowed.includes(number) ? number : fallback;
}

export default async function AnalysisPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const page = normalizedNumber(params.page, Array.from({ length: 1000 }, (_, index) => index + 1), 1);
  const pageSize = normalizedNumber(params.page_size, [20, 40, 60], 20);
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  for (const key of ["platform", "status", "model"] as const) if (params[key]) query.set(key, params[key]);
  const [data, filters] = await Promise.all([listMaterials(query), getAnalysisFilters()]);

  const pageHref = (nextPage: number) => {
    const next = new URLSearchParams(query);
    next.set("page", String(nextPage));
    return `/analysis?${next.toString()}`;
  };

  return (
    <main className="mx-auto max-w-[1600px] px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-[-0.01em]">{t("analysis.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("analysis.total", { total: data.total })}</p>
        </div>
        <form className="flex flex-wrap gap-2" action="/analysis">
          <Select name="platform" defaultValue={params.platform ?? ""} aria-label={t("analysis.filter.platform")} className="h-9 w-auto bg-background">
            <option value="">{t("analysis.filter.allPlatforms")}</option>
            {filters.platforms.map((value) => <option key={value}>{value}</option>)}
          </Select>
          <Select name="status" defaultValue={params.status ?? ""} aria-label={t("analysis.filter.status")} className="h-9 w-auto bg-background">
            <option value="">{t("analysis.filter.allStatuses")}</option>
            {filters.statuses.map((value) => <option key={value} value={value}>{t(statusKeys[value])}</option>)}
          </Select>
          <Select name="model" defaultValue={params.model ?? ""} aria-label={t("analysis.filter.model")} className="h-9 w-auto bg-background">
            <option value="">{t("analysis.filter.allModels")}</option>
            {filters.models.map((value) => <option key={value}>{value}</option>)}
          </Select>
          <Button type="submit" variant="gradient">
            {t("analysis.filter.apply")}
          </Button>
        </form>
      </header>

      {data.items.length ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
          {data.items.map((item) => (
            <Link key={`${item.platform}:${item.content_id}`} href={`/analysis/${encodeURIComponent(item.platform)}/${encodeURIComponent(item.content_id)}`} className="group min-w-0 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary">
              <div className="relative aspect-[3/4] overflow-hidden rounded-lg bg-muted transition-transform duration-200 group-hover:-translate-y-1 motion-reduce:transition-none motion-reduce:group-hover:translate-y-0">
                <MaterialCover
                  alt={t("analysis.coverAlt", { contentId: item.content_id })}
                  placeholderLabel={t("analysis.videoPlaceholder")}
                  src={getAnalysisThumbnailUrl(item.platform, item.content_id)}
                />
                <div className="absolute left-2 top-2"><Badge variant={statusVariants[item.status]}>{t(statusKeys[item.status])}</Badge></div>
                {item.overall_score != null ? <div className="absolute bottom-2 right-2 rounded-md bg-background/85 px-2 py-1 text-xs font-semibold tabular-nums">{item.overall_score.toFixed(1)}</div> : null}
              </div>
              <div className="mt-2 min-w-0">
                <p className="truncate text-sm font-semibold">{item.content_id}</p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{item.platform} · P{item.grade_rank}</p>
                <p className="truncate text-xs text-muted-foreground">{item.model ?? t("analysis.noModel")}</p>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Card className="grid min-h-80 place-items-center text-center">
          <div>
            <h2 className="text-xl font-semibold">{t("analysis.empty.title")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t("analysis.empty.description")}</p>
          </div>
        </Card>
      )}

      {data.total_pages > 1 ? <nav aria-label={t("analysis.pagination")} className="mt-10 flex items-center justify-center gap-4 text-sm"><Link aria-disabled={page <= 1} className={page <= 1 ? "pointer-events-none text-muted-foreground" : "font-medium"} href={pageHref(Math.max(1, page - 1))}>{t("analysis.previous")}</Link><span className="tabular-nums">{page} / {data.total_pages}</span><Link aria-disabled={page >= data.total_pages} className={page >= data.total_pages ? "pointer-events-none text-muted-foreground" : "font-medium"} href={pageHref(Math.min(data.total_pages, page + 1))}>{t("analysis.next")}</Link></nav> : null}
    </main>
  );
}
