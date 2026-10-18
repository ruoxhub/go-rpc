import { FormField } from "../../../../../_components/FormField";
import { NumberInput } from "../../../../../../_components/NumberInput";
import { Card } from "../../../../../../_components/ui/card";
import { Switch } from "../../../../../../_components/ui/switch";
import { t } from "../../../../../../i18n";
import type { Task } from "../../../../../../../utils/crawler/crawler-types";

export function DownloadConfigFields({ task }: { task?: Task }) {
  const config = task?.config?.download;
  return (
    <Card className="grid gap-4 p-4 shadow-sm">
      <legend className="px-1 text-sm font-semibold">{t("tasks.downloadSettings")}</legend>
      <div className="grid gap-4 md:grid-cols-2">
        <FormField id="download_batch_size" label={t("tasks.downloadBatchSize")}>
          <NumberInput integer name="download_batch_size" defaultValue={config?.batch_size ?? 50} min={1} max={500} />
        </FormField>
        <FormField id="download_min_grade" label={t("tasks.downloadMinGrade")}>
          <NumberInput integer name="download_min_grade" defaultValue={config?.min_grade ?? 3} min={1} max={3} />
        </FormField>
        <FormField id="download_rps" label={t("tasks.downloadRps")}>
          <NumberInput name="download_rps" defaultValue={config?.rps ?? 0} min={0} />
        </FormField>
        <FormField id="download_max_attempts" label={t("tasks.downloadMaxAttempts")}>
          <NumberInput integer name="download_max_attempts" defaultValue={config?.max_attempts ?? 5} min={1} max={20} />
        </FormField>
        <FormField id="download_claim_timeout_seconds" label={t("tasks.downloadClaimTimeout")}>
          <NumberInput integer name="download_claim_timeout_seconds" defaultValue={config?.claim_timeout_seconds ?? 1800} min={60} />
        </FormField>
        <FormField id="download_retry_base_seconds" label={t("tasks.downloadRetryBase")}>
          <NumberInput integer name="download_retry_base_seconds" defaultValue={config?.retry_base_seconds ?? 60} min={1} />
        </FormField>
        <FormField id="download_retry_max_seconds" label={t("tasks.downloadRetryMax")}>
          <NumberInput integer name="download_retry_max_seconds" defaultValue={config?.retry_max_seconds ?? 3600} min={1} />
        </FormField>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <Switch name="download_use_proxy" defaultChecked={config?.use_proxy ?? true} />
        {t("tasks.downloadUseProxy")}
      </label>
    </Card>
  );
}
