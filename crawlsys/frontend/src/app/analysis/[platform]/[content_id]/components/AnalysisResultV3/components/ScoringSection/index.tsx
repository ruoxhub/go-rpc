import { Badge, SectionCard } from "../../../../../../../_components/ui";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../../../../../_components/ui/table";
import { t } from "../../../../../../../i18n";
import type { AnalysisResultV3, ScoreDimensionV3, ScoreSectionV3 } from "../../types";
import { formatScore } from "../../utils/format";
import { defectKeys, dimensionKeys } from "../../utils/labels";
import { EvidenceReferences } from "../EvidenceReferences";

export function ScoringSection({ result }: { result: AnalysisResultV3 }) {
  const { evaluation, decision } = result;
  const specialized = evaluation.review_route === "R"
    ? { title: t("analysis.v3.score.reference"), section: evaluation.specialized_score_r }
    : evaluation.review_route === "G"
      ? { title: t("analysis.v3.score.generated"), section: evaluation.specialized_score_g }
      : null;

  return (
    <div role="region" aria-label={t("analysis.v3.scoring.title")}>
      <SectionCard
        title={t("analysis.v3.scoring.title")}
        description={t("analysis.v3.scoring.description")}
        extra={<Badge variant={decision.scoring_status === "PROVISIONAL" ? "primary" : "muted"}>{decision.scoring_status === "PROVISIONAL" ? t("analysis.v3.scoring.provisional") : t("analysis.v3.scoring.unavailable")}</Badge>}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <ScoreSummary label={t("analysis.v3.score.partial")} value={`${formatScore(evaluation.partial_points)} / ${formatScore(evaluation.partial_max_points)}`} />
          <ScoreSummary label={t("analysis.v3.score.diagnosticTotal")} value={formatScore(evaluation.diagnostic_total) ?? t("analysis.v3.unavailable")} />
        </div>

        <section className="mt-6 border-t border-border pt-5" aria-labelledby="analysis-v3-g0-title">
          <h3 id="analysis-v3-g0-title" className="text-lg font-semibold">{t("analysis.v3.g0.title")}</h3>
          {evaluation.g0_assessment.findings.length ? (
            <ul className="mt-3 space-y-3">
              {evaluation.g0_assessment.findings.map((finding, index) => (
                <li key={`${finding.category}-${index}`} className="rounded-md border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={finding.triggered ? "destructive" : "success"}>{finding.triggered ? t("analysis.v3.g0.triggered") : t("analysis.v3.g0.clear")}</Badge>
                    <Badge variant="outline">{t(defectKeys[finding.category])}</Badge>
                  </div>
                  <p className="mt-2 text-sm leading-6">{finding.description}</p>
                  <div className="mt-2"><EvidenceReferences references={finding.evidence_timestamps} /></div>
                </li>
              ))}
            </ul>
          ) : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}
        </section>

        <ScoreTable title={t("analysis.v3.score.common")} section={evaluation.common_score_c} />
        {specialized ? <ScoreTable title={specialized.title} section={specialized.section} /> : null}
      </SectionCard>
    </div>
  );
}

function ScoreSummary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md bg-muted p-4"><div className="text-xs font-medium text-muted-foreground">{label}</div><div className="mt-1 font-numeric text-2xl font-semibold tabular-nums">{value}</div></div>;
}

function ScoreTable({ title, section }: { title: string; section: ScoreSectionV3 | null }) {
  return (
    <section className="mt-6 border-t border-border pt-5">
      <h3 className="text-lg font-semibold">{title}</h3>
      {!section || section.dimensions.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>
      ) : (
        <div className="mt-3 rounded-lg border border-border">
          <Table className="min-w-[680px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-3 py-2 font-medium">{t("analysis.v3.score.dimension")}</TableHead>
                <TableHead className="px-3 py-2 font-medium">{t("analysis.v3.score.points")}</TableHead>
                <TableHead className="px-3 py-2 font-medium">{t("analysis.v3.score.scorable")}</TableHead>
                <TableHead className="px-3 py-2 font-medium">{t("analysis.v3.score.reason")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {section.dimensions.map((dimension, index) => (
                <DimensionRow key={`${dimension.dimension_id ?? "dimension"}-${index}`} dimension={dimension} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}

function DimensionRow({ dimension }: { dimension: ScoreDimensionV3 }) {
  const labelKey = dimension.dimension_id ? dimensionKeys[dimension.dimension_id] : undefined;
  const label = labelKey ? t(labelKey) : (dimension.name ?? dimension.dimension_id ?? t("analysis.v3.unavailable"));
  const score = dimension.awarded_points == null ? t("analysis.v3.unavailable") : formatScore(dimension.awarded_points);
  const reason = dimension.scorable
    ? (dimension.reason ?? t("analysis.v3.notProvided"))
    : (dimension.unscorable_reason?.trim() || t("analysis.v3.score.unscorableMissing"));
  return (
    <TableRow className="align-top">
      <th scope="row" className="px-3 py-3 text-left font-medium">
        <span className="mr-2 font-numeric text-xs text-muted-foreground">{dimension.dimension_id ?? t("analysis.v3.unavailable")}</span>
        {label}
      </th>
      <TableCell className="px-3 py-3 font-numeric tabular-nums">
        {score} / {formatScore(dimension.max_points)}
      </TableCell>
      <TableCell className="px-3 py-3">
        <Badge variant={dimension.scorable ? "success" : "warning"}>
          {dimension.scorable ? t("analysis.v3.yes") : t("analysis.v3.no")}
        </Badge>
      </TableCell>
      <TableCell className="px-3 py-3">
        <p className="leading-6">{reason}</p>
        {dimension.evidence_timestamps.length ? (
          <div className="mt-2">
            <EvidenceReferences references={dimension.evidence_timestamps} />
          </div>
        ) : null}
      </TableCell>
    </TableRow>
  );
}
