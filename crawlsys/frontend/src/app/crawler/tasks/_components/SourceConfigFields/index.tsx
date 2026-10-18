import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { Button } from "../../../../_components/ui/button";
import { Input } from "../../../../_components/ui/input";
import { Select } from "../../../../_components/ui/select";
import { Textarea } from "../../../../_components/ui/textarea";
import { t } from "../../../../i18n";

interface SourceConfigFieldsProps {
  table: string;
  columns: string[];
  keyColumn: string;
  parameterMapping: string;
  loading: boolean;
  error?: string;
  initialWhere?: string;
  onTableChange: (value: string) => void;
  onKeyColumnChange: (value: string) => void;
  onParameterMappingChange: (value: string) => void;
  onLoadColumns: () => void;
}

export function SourceConfigFields({
  table,
  columns,
  keyColumn,
  parameterMapping,
  loading,
  error,
  initialWhere = "",
  onTableChange,
  onKeyColumnChange,
  onParameterMappingChange,
  onLoadColumns,
}: SourceConfigFieldsProps) {
  return (
    <fieldset className="grid gap-4 rounded-md border border-border p-4">
      <legend className="px-1 text-sm font-semibold">{t("tasks.source")}</legend>
      <div className="grid gap-1.5">
        <label htmlFor="ref_table" className="text-xs font-medium text-foreground">
          {t("tasks.queryTable")}
        </label>
        <div className="flex gap-2">
          <Input
            id="ref_table"
            name="ref_table"
            value={table}
            onChange={(event) => onTableChange(event.target.value)}
            className="min-w-0 flex-1 bg-background"
          />
          <Button
            type="button"
            variant="outline"
            disabled={loading || !table.trim()}
            onClick={onLoadColumns}
          >
            {error ? t("tasks.retryReadColumns") : t("tasks.readColumns")}
          </Button>
        </div>
      </div>
      {error ? <Feedback variant="error">{error}</Feedback> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <FormField id="entity_column" label={t("tasks.primaryColumn")}>
          <Select
            name="entity_column"
            aria-label={t("tasks.primaryColumn")}
            value={keyColumn}
            onChange={(event) => onKeyColumnChange(event.target.value)}
            className="bg-background"
          >
            <option value="">{t("tasks.choose")}</option>
            {columns.map((column) => <option key={column}>{column}</option>)}
          </Select>
        </FormField>
        <FormField id="ref_where" label={t("tasks.where")}>
          <Input
            name="ref_where"
            defaultValue={initialWhere}
            className="bg-background"
            placeholder={t("tasks.wherePlaceholder")}
          />
        </FormField>
      </div>
      <FormField
        id="params_columns"
        label={t("tasks.mapping")}
        hint={t("tasks.mappingHint")}
      >
        <Textarea
          name="params_columns_editor"
          value={parameterMapping}
          onChange={(event) => onParameterMappingChange(event.target.value)}
          rows={4}
          className="bg-background font-mono"
        />
      </FormField>
    </fieldset>
  );
}
