import type { AnalysisResultV3 as AnalysisResultV3Data } from "../../../../../../utils/analysis";

import { ClassificationSection } from "./components/ClassificationSection";
import { DecisionBanner } from "./components/DecisionBanner";
import { EvidenceSection } from "./components/EvidenceSection";
import { ReviewSection } from "./components/ReviewSection";
import { ScoringSection } from "./components/ScoringSection";
import { TimelineSection } from "./components/TimelineSection";

/** Evidence-first v3 detail view. The gate decision is intentionally first. */
export function AnalysisResultV3({ result }: { result: AnalysisResultV3Data }) {
  return (
    <div className="space-y-6" data-schema-version={result.meta.schema_version}>
      <DecisionBanner result={result} />
      <EvidenceSection result={result} />
      <ClassificationSection result={result} />
      <ScoringSection result={result} />
      <TimelineSection result={result} />
      <ReviewSection result={result} />
    </div>
  );
}
