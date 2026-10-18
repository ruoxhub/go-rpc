import { Badge, KeyValue, SectionCard } from "../../../../../../../_components/ui";
import { t } from "../../../../../../../i18n";
import type { AnalysisResultV3 } from "../../types";
import { contentTypeKeys, topologyKeys } from "../../utils/labels";
import { EvidenceReferences } from "../EvidenceReferences";

export function ClassificationSection({ result }: { result: AnalysisResultV3 }) {
  const classification = result.content_classification;
  const routeKey = result.evaluation.review_route === "R"
    ? "analysis.v3.route.r"
    : result.evaluation.review_route === "G"
      ? "analysis.v3.route.g"
      : "analysis.v3.route.cOnly";
  return (
    <div role="region" aria-label={t("analysis.v3.classification.title")}>
      <SectionCard title={t("analysis.v3.classification.title")} description={t("analysis.v3.classification.description")}>
        <dl className="divide-y divide-border">
          <KeyValue label={t("analysis.v3.field.primaryType")}>{t(contentTypeKeys[classification.primary_type])}</KeyValue>
          <KeyValue label={t("analysis.v3.field.secondaryTypes")}>
            {classification.secondary_types.length ? (
              <span className="flex flex-wrap justify-end gap-1.5">
                {classification.secondary_types.map((type) => <Badge key={type} variant="outline">{t(contentTypeKeys[type])}</Badge>)}
              </span>
            ) : t("analysis.v3.empty")}
          </KeyValue>
          <KeyValue label={t("analysis.v3.field.topology")}>{t(topologyKeys[classification.topology])}</KeyValue>
          <KeyValue label={t("analysis.v3.field.route")}>{t(routeKey)}</KeyValue>
        </dl>
        <div className="mt-5 border-t border-border pt-5">
          <h3 className="mb-2 text-sm font-semibold">{t("analysis.v3.field.classificationEvidence")}</h3>
          <EvidenceReferences references={classification.evidence_timecodes} />
        </div>
      </SectionCard>
    </div>
  );
}
