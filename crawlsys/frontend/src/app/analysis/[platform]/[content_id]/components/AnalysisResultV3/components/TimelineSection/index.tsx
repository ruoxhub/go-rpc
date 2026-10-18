import { Badge, Field, SectionCard } from "../../../../../../../_components/ui";
import { t } from "../../../../../../../i18n";
import type { AnalysisResultV3 } from "../../types";
import { formatRange } from "../../utils/format";
import { defectKeys, phaseKeys } from "../../utils/labels";
import { EvidenceReferences } from "../EvidenceReferences";

export function TimelineSection({ result }: { result: AnalysisResultV3 }) {
  const observation = result.observation;
  const businessAnswers = [
    ["analysis.v3.business.audience", observation.business_logic.audience_and_need],
    ["analysis.v3.business.hook", observation.business_logic.hook_and_retention],
    ["analysis.v3.business.recognition", observation.business_logic.product_recognition],
    ["analysis.v3.business.sellingPoint", observation.business_logic.selling_point],
    ["analysis.v3.business.proof", observation.business_logic.visible_proof],
    ["analysis.v3.business.rhythm", observation.business_logic.rhythm_and_density],
    ["analysis.v3.business.memory", observation.business_logic.memory_and_product_binding],
    ["analysis.v3.business.trust", observation.business_logic.trust_objection_and_action],
  ] as const;

  return (
    <div role="region" aria-label={t("analysis.v3.timeline.title")}>
      <SectionCard title={t("analysis.v3.timeline.title")} description={t("analysis.v3.timeline.description")}>
        <section aria-labelledby="analysis-v3-summary-title">
          <h3 id="analysis-v3-summary-title" className="text-lg font-semibold">{t("analysis.v3.timeline.summary")}</h3>
          <p className="mt-2 text-sm leading-6">{observation.facts.summary ?? t("analysis.v3.notProvided")}</p>
        </section>

        <section className="mt-6 border-t border-border pt-5">
          {observation.timeline.length ? (
            <ol className="space-y-5">
              {observation.timeline.map((entry, index) => (
                <li key={`${entry.start_seconds}-${entry.end_seconds}-${index}`} className="rounded-md border border-border p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="font-numeric text-sm font-semibold tabular-nums">{formatRange(entry)}</span>
                    <span className="text-xs text-muted-foreground">{entry.subject ?? t("analysis.v3.notProvided")}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {entry.action_phases.length ? entry.action_phases.map((phase) => <Badge key={phase} variant="primary">{t(phaseKeys[phase])}</Badge>) : <span className="text-xs text-muted-foreground">{t("analysis.v3.empty")}</span>}
                  </div>
                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <Field label={t("analysis.v3.timeline.productState")}>{entry.product_state ?? t("analysis.v3.notProvided")}</Field>
                    <Field label={t("analysis.v3.timeline.camera")}>{[entry.camera, entry.composition].filter(Boolean).join(" / ") || t("analysis.v3.notProvided")}</Field>
                    <Field label={t("analysis.v3.timeline.claims")}>
                      {entry.provable_claims.length ? <ul className="list-disc space-y-1 pl-5">{entry.provable_claims.map((claim, claimIndex) => <li key={`${claim}-${claimIndex}`}>{claim}</li>)}</ul> : t("analysis.v3.empty")}
                    </Field>
                    <Field label={t("analysis.v3.timeline.defects")}>
                      {entry.defects.length ? <div className="flex flex-wrap gap-1.5">{entry.defects.map((defect) => <Badge key={defect} variant="warning">{t(defectKeys[defect])}</Badge>)}</div> : t("analysis.v3.empty")}
                    </Field>
                  </div>
                  <div className="mt-4"><h4 className="mb-2 text-sm font-semibold">{t("analysis.v3.timeline.references")}</h4><EvidenceReferences references={entry.evidence_sources} /></div>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}
        </section>

        <section className="mt-6 border-t border-border pt-5" aria-labelledby="analysis-v3-proof-title">
          <h3 id="analysis-v3-proof-title" className="text-lg font-semibold">{t("analysis.v3.timeline.proofChains")}</h3>
          {observation.claim_evidence_chains.length ? (
            <ul className="mt-3 space-y-4">
              {observation.claim_evidence_chains.map((chain, index) => (
                <li key={`${chain.claim}-${index}`} className="rounded-md bg-muted p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">{chain.claim}</h4><Badge variant={chain.supported ? "success" : "warning"}>{chain.supported ? t("analysis.v3.supported") : t("analysis.v3.unsupported")}</Badge></div>
                  <dl className="mt-3 grid gap-3 md:grid-cols-2">
                    <ProofValue label={t("analysis.v3.chain.structure")} value={chain.product_structure} />
                    <ProofValue label={t("analysis.v3.chain.action")} value={chain.demonstration_action} />
                    <ProofValue label={t("analysis.v3.chain.feedback")} value={chain.visible_feedback} />
                    <ProofValue label={t("analysis.v3.chain.result")} value={chain.usage_result} />
                    <ProofValue label={t("analysis.v3.chain.benefit")} value={chain.user_benefit} />
                  </dl>
                  <div className="mt-3"><EvidenceReferences references={chain.references} /></div>
                </li>
              ))}
            </ul>
          ) : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}
        </section>

        <section className="mt-6 grid gap-6 border-t border-border pt-5 lg:grid-cols-2">
          <div><h3 className="text-lg font-semibold">{t("analysis.v3.timeline.businessQuestions")}</h3><dl className="mt-3 space-y-3">{businessAnswers.map(([labelKey, value]) => <ProofValue key={labelKey} label={t(labelKey)} value={value} />)}</dl></div>
          <div><h3 className="text-lg font-semibold">{t("analysis.v3.timeline.defects")}</h3>{observation.defects.length ? <ul className="mt-3 space-y-3">{observation.defects.map((defect, index) => <li key={`${defect.category}-${index}`} className="rounded-md border border-border p-3"><div className="flex items-center gap-2"><Badge variant="warning">{t(defectKeys[defect.category])}</Badge><span className="text-sm">{defect.description}</span></div><div className="mt-2"><EvidenceReferences references={defect.references} /></div></li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}</div>
        </section>
      </SectionCard>
    </div>
  );
}

function ProofValue({ label, value }: { label: string; value: string | null }) {
  return <div><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 text-sm leading-6">{value ?? t("analysis.v3.notProvided")}</dd></div>;
}
