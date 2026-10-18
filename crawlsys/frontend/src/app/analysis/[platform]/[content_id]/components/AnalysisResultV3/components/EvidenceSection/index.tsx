import type { ReactNode } from "react";

import { Badge, SectionCard } from "../../../../../../../_components/ui";
import { t } from "../../../../../../../i18n";
import type { AnalysisResultV3, TimeRangeV3 } from "../../types";
import { formatRange, formatSeconds, safeIdentifier } from "../../utils/format";
import { externalStatusKeys, inputModeKeys } from "../../utils/labels";

export function EvidenceSection({ result }: { result: AnalysisResultV3 }) {
  const evidence = result.evidence_card;
  const sourceId = safeIdentifier(evidence.source_id);
  const sourceHash = safeIdentifier(evidence.source_sha256);
  const externalEvidence = [
    ["analysis.v3.field.productReference", evidence.product_reference],
    ["analysis.v3.field.publishingContext", evidence.publishing_context],
    ["analysis.v3.field.performanceMetrics", evidence.performance_metrics],
    ["analysis.v3.field.taskConstraints", evidence.task_constraints],
  ] as const;

  return (
    <div role="region" aria-label={t("analysis.v3.evidence.title")}>
      <SectionCard
        title={t("analysis.v3.evidence.title")}
        description={t("analysis.v3.evidence.description")}
        extra={<Badge variant={evidence.evidence_complete ? "success" : "warning"}>{evidence.evidence_complete ? t("analysis.v3.yes") : t("analysis.v3.lowEvidence")}</Badge>}
      >
        <dl className="grid gap-4 md:grid-cols-2">
          <EvidenceField label={t("analysis.v3.field.sourceId")}>
            <IdentifierValue value={sourceId.value} hidden={sourceId.hidden} />
          </EvidenceField>
          <EvidenceField label={t("analysis.v3.field.sourceHash")}>
            <IdentifierValue value={sourceHash.value} hidden={sourceHash.hidden} />
          </EvidenceField>
          <EvidenceField label={t("analysis.v3.field.inputMode")}>
            {evidence.input_mode ? t(inputModeKeys[evidence.input_mode]) : t("analysis.v3.notProvided")}
          </EvidenceField>
          <EvidenceField label={t("analysis.v3.field.sampleCount")}>
            <span className="font-numeric tabular-nums">{evidence.sampled_frame_count}</span>
          </EvidenceField>
          <EvidenceField label={t("analysis.v3.field.evidenceComplete")}>
            {evidence.evidence_complete ? t("analysis.v3.yes") : t("analysis.v3.no")}
          </EvidenceField>
          <EvidenceField label={t("analysis.v3.field.officialReady")}>
            {evidence.official_scoring_ready ? t("analysis.v3.yes") : t("analysis.v3.no")}
          </EvidenceField>
        </dl>

        <div className="mt-6 grid gap-5 border-t border-border pt-5 md:grid-cols-2">
          <ListField label={t("analysis.v3.field.sampleTimestamps")} items={evidence.sampled_timestamps.map(formatSeconds)} />
          <RangeField label={t("analysis.v3.field.observedRanges")} ranges={evidence.observed_ranges} />
          <RangeField label={t("analysis.v3.field.unobservedRanges")} ranges={evidence.unobserved_ranges} />
          <ListField label={t("analysis.v3.field.coverageLimitations")} items={evidence.coverage_limitations} />
          <ListField label={t("analysis.v3.field.missingEvidence")} items={evidence.missing_evidence} />
          <ListField label={t("analysis.v3.field.limitations")} items={evidence.limitations} />
        </div>

        <dl className="mt-6 grid gap-4 border-t border-border pt-5 md:grid-cols-2">
          {externalEvidence.map(([labelKey, availability]) => (
            <EvidenceField key={labelKey} label={t(labelKey)}>
              <span>{t(externalStatusKeys[availability.status])}</span>
              {availability.detail ? <span className="ml-2 text-muted-foreground">{availability.detail}</span> : null}
            </EvidenceField>
          ))}
        </dl>
      </SectionCard>
    </div>
  );
}

function IdentifierValue({ value, hidden }: { value: string | null; hidden: boolean }) {
  if (hidden) return <span>{t("analysis.v3.sensitiveHidden")}</span>;
  if (!value) return <span>{t("analysis.v3.notProvided")}</span>;
  return <code className="break-all [overflow-wrap:anywhere]">{value}</code>;
}

function EvidenceField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0 rounded-md bg-muted p-3"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 text-sm leading-6">{children}</dd></div>;
}

function ListField({ label, items }: { label: string; items: string[] }) {
  return <div><h3 className="text-sm font-semibold">{label}</h3>{items.length ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}</div>;
}

function RangeField({ label, ranges }: { label: string; ranges: TimeRangeV3[] }) {
  return <div><h3 className="text-sm font-semibold">{label}</h3>{ranges.length ? <ul className="mt-2 space-y-2 text-sm">{ranges.map((range, index) => <li key={`${range.start_seconds}-${range.end_seconds}-${index}`}><span className="font-numeric tabular-nums">{formatRange(range)}</span><span className="ml-2 text-xs text-muted-foreground">{t(range.start_inclusive ? "analysis.v3.boundary.startInclusive" : "analysis.v3.boundary.startExclusive")}, {t(range.end_inclusive ? "analysis.v3.boundary.endInclusive" : "analysis.v3.boundary.endExclusive")}</span></li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>}</div>;
}
