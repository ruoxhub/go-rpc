import { FormField } from "../../../../../_components/FormField";
import { Input } from "../../../../../../_components/ui/input";
import { Select } from "../../../../../../_components/ui/select";
import { t } from "../../../../../../i18n";
import type { Task } from "../../../../../../../utils/crawler/crawler-types";

export function SinkConfigFields({ task }: { task?: Task }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <FormField id="sink_mode" label={t("tasks.sinkMode")}>
        <Select
          name="sink_mode"
          defaultValue={task?.config?.sink.mode ?? "auto"}
          className="bg-background"
        >
          {["auto", "standard", "direct", "none"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </Select>
      </FormField>
      <FormField id="result_column" label={t("tasks.resultColumn")}>
        <Input
          name="result_column"
          defaultValue={task?.config?.sink.result_column ?? ""}
          className="bg-background"
        />
      </FormField>
      <FormField id="post_update_table" label={t("tasks.postUpdateTable")}>
        <Input
          name="post_update_table"
          defaultValue={task?.config?.sink.mark_done_table ?? ""}
          className="bg-background"
        />
      </FormField>
      <FormField id="post_update_column" label={t("tasks.postUpdateColumn")}>
        <Input
          name="post_update_column"
          defaultValue={task?.config?.sink.mark_done_column ?? ""}
          className="bg-background"
        />
      </FormField>
    </div>
  );
}
