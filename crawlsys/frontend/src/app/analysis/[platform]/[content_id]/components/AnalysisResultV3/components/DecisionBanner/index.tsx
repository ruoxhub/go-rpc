import { Badge } from "../../../../../../../_components/ui";
import { Card } from "../../../../../../../_components/ui/card";
import { t } from "../../../../../../../i18n";
import type { AnalysisResultV3 } from "../../types";
import { dispositionKeys, gateKeys } from "../../utils/labels";

const gateVariants = {
  PASS: "success",
  BLOCK: "destructive",
  INSUFFICIENT_EVIDENCE: "warning",
} as const;

export function DecisionBanner({ result }: { result: AnalysisResultV3 }) {
  const { decision } = result;
  const blocked = decision.gate_status === "BLOCK";
  return (
    <Card
      aria-labelledby="analysis-v3-decision-title"
      className={`p-6 shadow-sm ${
        blocked
          ? "border-destructive bg-destructive/10"
          : decision.gate_status === "PASS"
            ? "border-success/40 bg-success/10"
            : "border-warning/50 bg-warning/10"
      }`}
      role={blocked ? "alert" : "status"}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="analysis-v3-decision-title" className="text-2xl font-semibold leading-none tracking-[-0.01em]">
            {t("analysis.v3.decision.title")}
          </h2>
          <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">
            {t("analysis.v3.decision.description")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={gateVariants[decision.gate_status]}>{t(gateKeys[decision.gate_status])}</Badge>
          <Badge variant={blocked ? "destructive" : "outline"}>{t(dispositionKeys[decision.system_disposition])}</Badge>
          <Badge variant={decision.scoring_status === "PROVISIONAL" ? "primary" : "muted"}>
            {decision.scoring_status === "PROVISIONAL"
              ? t("analysis.v3.scoring.provisional")
              : t("analysis.v3.scoring.unavailable")}
          </Badge>
        </div>
      </div>
      <div className="mt-5">
        <h3 className="text-sm font-semibold">{t("analysis.v3.decision.reasons")}</h3>
        {decision.reasons.length ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6">
            {decision.reasons.map((reason, index) => <li key={`${reason}-${index}`}>{reason}</li>)}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">{t("analysis.v3.empty")}</p>
        )}
      </div>
    </Card>
  );
}
