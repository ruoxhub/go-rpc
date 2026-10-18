import { Badge, Field, SectionCard } from "../../../../../../../_components/ui";
import { t } from "../../../../../../../i18n";
import type { AnalysisResultV3 } from "../../types";
import { dispositionKeys } from "../../utils/labels";
import { EvidenceReferences } from "../EvidenceReferences";

export function ReviewSection({ result }: { result: AnalysisResultV3 }) {
  const { evaluation, decision } = result;
  return (
    <div role="region" aria-label={t("analysis.v3.review.title")}>
      <SectionCard
        title={t("analysis.v3.review.title")}
        description={t("analysis.v3.review.description")}
        extra={<Badge variant={evaluation.evidence_review.evidence_complete ? "success" : "warning"}>{evaluation.evidence_review.evidence_complete ? t("analysis.v3.yes") : t("analysis.v3.lowEvidence")}</Badge>}
      >
        <div className="grid gap-4 md:grid-cols-3">
          <Field label={t("analysis.v3.ownerAction")}><Badge variant={decision.system_disposition === "REJECT" ? "destructive" : "warning"}>{t(dispositionKeys[decision.system_disposition])}</Badge></Field>
          <ListBlock label={t("analysis.v3.review.missingEvidence")} items={evaluation.evidence_review.missing_evidence} />
          <ListBlock label={t("analysis.v3.review.limitations")} items={evaluation.evidence_review.limitations} />
        </div>

        <section className="mt-6 border-t border-border pt-5" aria-labelledby="analysis-v3-supplemental-title">
          <h3 id="analysis-v3-supplemental-title" className="text-lg font-semibold">{t("analysis.v3.review.supplemental")}</h3>
          {evaluation.supplemental_evidence.length ? (
            <ul className="mt-3 space-y-3">{evaluation.supplemental_evidence.map((item, index) => <li key={`${item.description}-${index}`} className="rounded-md border border-border p-4"><p className="text-sm font-medium">{item.description}</p><AffectedDimensions items={item.affected_dimension_ids} /><div className="mt-3"><EvidenceReferences references={item.references} /></div></li>)}</ul>
          ) : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}
        </section>

        <section className="mt-6 border-t border-border pt-5" aria-labelledby="analysis-v3-conflicts-title">
          <h3 id="analysis-v3-conflicts-title" className="text-lg font-semibold">{t("analysis.v3.review.conflicts")}</h3>
          {evaluation.evidence_conflicts.length ? (
            <ul className="mt-3 space-y-4">{evaluation.evidence_conflicts.map((conflict, index) => <li key={`${conflict.observation_claim}-${index}`} className="rounded-md bg-muted p-4"><dl className="grid gap-4 md:grid-cols-2"><div><dt className="text-xs font-medium text-muted-foreground">{t("analysis.v3.review.observationClaim")}</dt><dd className="mt-1 text-sm leading-6">{conflict.observation_claim}</dd></div><div><dt className="text-xs font-medium text-muted-foreground">{t("analysis.v3.review.evaluationClaim")}</dt><dd className="mt-1 text-sm leading-6">{conflict.evaluation_claim}</dd></div></dl><AffectedDimensions items={conflict.affected_dimension_ids} /><div className="mt-3"><EvidenceReferences references={conflict.references} /></div></li>)}</ul>
          ) : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}
        </section>
      </SectionCard>
    </div>
  );
}

function ListBlock({ label, items }: { label: string; items: string[] }) {
  return <div><h3 className="text-xs font-medium text-muted-foreground">{label}</h3>{items.length ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="mt-2 text-sm">{t("analysis.v3.empty")}</p>}</div>;
}

function AffectedDimensions({ items }: { items: string[] }) {
  return <div className="mt-3"><span className="mr-2 text-xs text-muted-foreground">{t("analysis.v3.review.affectedDimensions")}</span>{items.length ? <span className="inline-flex flex-wrap gap-1.5">{items.map((item) => <Badge key={item} variant="outline">{item}</Badge>)}</span> : <span className="text-xs">{t("analysis.v3.empty")}</span>}</div>;
}
