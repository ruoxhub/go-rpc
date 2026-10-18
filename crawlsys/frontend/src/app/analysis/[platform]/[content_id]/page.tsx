/** 视频分析详情：展示素材元数据、分析源视频与结构化分析结果。 */
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, KeyValue, SectionCard } from "../../../_components/ui";
import { formatDateTime } from "../../../_components/format";
import { OverviewSection } from "../../../_components/sections/OverviewSection";
import { ScoreboardSection } from "../../../_components/sections/ScoreboardSection";
import { TimelineSection } from "../../../_components/sections/TimelineSection";
import { ViralSection } from "../../../_components/sections/ViralSection";
import { ContentSection } from "../../../_components/sections/ContentSection";
import { PromptSection } from "../../../_components/sections/PromptSection";
import { PostProductionSection } from "../../../_components/sections/PostProductionSection";
import { t } from "../../../i18n";
import {
  AnalysisApiError,
  classifyAnalysisResult,
  getAnalysisVideoUrl,
  getMaterialAnalysis,
} from "@/utils/analysis";
import { AnalysisResultV3 } from "./components/AnalysisResultV3";

const statusVariants = { pending: "muted", succeeded: "success", processing: "info", failed: "destructive" } as const;
const statusKeys = { pending: "analysis.status.pending", succeeded: "analysis.status.succeeded", processing: "analysis.status.processing", failed: "analysis.status.failed" } as const;

export default async function AnalysisDetailPage({ params }: { params: Promise<{ platform: string; content_id: string }> }) {
  const { platform, content_id: contentId } = await params;
  let detail;
  try {
    detail = await getMaterialAnalysis(platform, contentId);
  } catch (error) {
    if (error instanceof AnalysisApiError && error.status === 404) notFound();
    throw error;
  }

  let videoUrl: string | null = null;
  if (detail.analysis?.minio_object_name) {
    try { videoUrl = (await getAnalysisVideoUrl(platform, contentId)).url; } catch { videoUrl = null; }
  }
  const result = detail.analysis?.analysis_result;
  const classifiedResult = classifyAnalysisResult(result);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 md:px-6 md:py-8">
      <Link href="/analysis" className="text-sm font-medium text-primary hover:underline">← {t("analysis.detail.back")}</Link>
      <header className="mt-5 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-[-0.01em]">{t("analysis.detail.title")}</h1>
        <Badge variant={statusVariants[detail.status]}>{t(statusKeys[detail.status])}</Badge>
      </header>

      <div className="mt-7 grid gap-7 lg:grid-cols-[minmax(260px,360px)_minmax(0,1fr)]">
        <aside className="space-y-5 lg:sticky lg:top-6 lg:self-start">
          {detail.status !== "pending" ? (
            <section aria-label={t("analysis.detail.video")} className="overflow-hidden rounded-lg bg-muted">
              {videoUrl ? <video className="aspect-[9/16] w-full bg-foreground/5 object-contain" controls preload="metadata" src={videoUrl} /> : <div className="grid aspect-[9/16] place-items-center px-6 text-center text-sm text-muted-foreground">{t("analysis.detail.videoUnavailable")}</div>}
            </section>
          ) : null}
          <SectionCard title={t("analysis.detail.material")}>
            <dl>
              <KeyValue label={t("analysis.field.platform")}>{detail.platform}</KeyValue>
              <KeyValue label={t("analysis.field.contentId")}><span className="break-all">{detail.content_id}</span></KeyValue>
              <KeyValue label={t("analysis.field.grade")}>P{detail.grade_rank}</KeyValue>
              <KeyValue label={t("analysis.field.model")}>{detail.model ?? t("analysis.noModel")}</KeyValue>
              <KeyValue label={t("analysis.field.attempts")}>{detail.attempt_count ?? 0}</KeyValue>
              <KeyValue label={t("analysis.field.created")}>{formatDateTime(detail.created_time)}</KeyValue>
            </dl>
          </SectionCard>
        </aside>

        <div className="min-w-0 space-y-6">
          {detail.status === "pending" ? <section className="grid min-h-72 place-items-center rounded-lg border border-border bg-card px-6 text-center text-muted-foreground">{t("analysis.detail.pending")}</section> : null}
          {detail.status === "failed" ? <SectionCard title={t("analysis.detail.error")}><p className="whitespace-pre-wrap text-sm text-destructive">{detail.analysis?.error_message ?? "-"}</p></SectionCard> : null}
          {detail.status === "processing" ? <section className="grid min-h-72 place-items-center rounded-lg border border-border bg-card text-muted-foreground">{t("analysis.status.processing")}</section> : null}
          {detail.status === "succeeded" && classifiedResult.version === "v3" ? (
            <AnalysisResultV3 result={classifiedResult.result} />
          ) : null}
          {detail.status === "succeeded" && classifiedResult.version === "v2" ? (
            <>
              <OverviewSection data={classifiedResult.result} />
              <ScoreboardSection scoring={classifiedResult.result.scoring ?? undefined} />
              <TimelineSection timeline={classifiedResult.result.timeline ?? undefined} />
              <ViralSection data={classifiedResult.result} />
              <ContentSection data={classifiedResult.result} />
              <PromptSection data={classifiedResult.result} />
              <PostProductionSection data={classifiedResult.result} />
            </>
          ) : null}
          {detail.status === "succeeded" && classifiedResult.version === "unavailable" ? (
            <SectionCard title={t("analysis.detail.resultUnavailableTitle")}>
              <p className="text-sm text-muted-foreground">
                {t("analysis.detail.resultUnavailable")}
              </p>
            </SectionCard>
          ) : null}
        </div>
      </div>
    </main>
  );
}
