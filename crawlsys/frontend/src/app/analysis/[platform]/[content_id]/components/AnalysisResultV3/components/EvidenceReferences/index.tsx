import { Badge } from "../../../../../../../_components/ui";
import { t } from "../../../../../../../i18n";
import type { EvidenceReferenceV3 } from "../../types";
import { formatRange, formatSeconds } from "../../utils/format";
import { sourceKeys } from "../../utils/labels";

export function EvidenceReferences({ references }: { references: EvidenceReferenceV3[] }) {
  if (references.length === 0) {
    return <span className="text-xs text-muted-foreground">{t("analysis.v3.empty")}</span>;
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {references.map((reference, index) => (
        <li key={`${reference.source}-${reference.timestamp ?? "range"}-${index}`}>
          <Badge variant={reference.positive ? "success" : "warning"}>
            {t(sourceKeys[reference.source])}{" "}
            {reference.timestamp != null
              ? formatSeconds(reference.timestamp)
              : reference.time_range
                ? formatRange(reference.time_range)
                : t("analysis.v3.unavailable")}
          </Badge>
          {reference.description ? (
            <span className="ml-2 text-xs text-muted-foreground">{reference.description}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
