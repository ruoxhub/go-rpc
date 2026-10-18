"use client";

// 数据模型列表：展示已同步元数据、启停状态与详情抽屉入口。
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataTable, type DataTableColumn } from "../../../_components/DataTable";
import { Feedback } from "../../../_components/Feedback";
import { CrawlerApiError } from "../../../../../utils/crawler/crawler-api";
import { updateDatatypeStatus } from "../../../../../api/datatype/datatype.api";
import type { DatatypeItem } from "../../../../../api/datatype/datatype.types";
import { t } from "../../../../i18n";

import { DatatypeDetailDrawer } from "../DatatypeDetailDrawer";
import { DatatypeStatusSwitch } from "../DatatypeStatusSwitch";

export function DatatypesTable({ datatypes }: { datatypes: DatatypeItem[] }) {
  const router = useRouter();
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const active = datatypes.find((item) => item.datatype_key === activeKey) ?? null;

  async function toggleStatus(item: DatatypeItem, next: boolean) {
    setFeedback(null);
    try {
      await updateDatatypeStatus(item.datatype_key, next);
      router.refresh();
    } catch (error) {
      setFeedback(
        error instanceof CrawlerApiError
          ? error.message
          : t("datatypes.statusUnknownError"),
      );
    }
  }

  const columns: DataTableColumn<DatatypeItem>[] = [
    { id: "key", header: t("datatypes.key"), accessor: "datatype_key" },
    { id: "model_name", header: t("datatypes.modelName"), accessor: "model_name" },
    { id: "table_name", header: t("datatypes.tableName"), accessor: "table_name" },
    {
      id: "description",
      header: t("datatypes.descriptionLabel"),
      render: (row) => row.description ?? "—",
    },
    {
      id: "columns",
      header: t("datatypes.columnCount"),
      className: "font-numeric",
      render: (row) => row.columns.length,
    },
    {
      id: "dto_fields",
      header: t("datatypes.dtoFieldCount"),
      className: "font-numeric",
      render: (row) => row.dto_fields.length,
    },
    {
      id: "status",
      header: t("datatypes.status"),
      render: (row) => (
        <DatatypeStatusSwitch
          label={row.datatype_key}
          checked={row.is_active}
          onChange={(next) => toggleStatus(row, next)}
        />
      ),
    },
    {
      id: "actions",
      header: t("common.actions"),
      className: "text-right",
      render: (row) => (
        <div className="flex items-center justify-end gap-3">
          <Link
            href={`/crawler/datatypes/${encodeURIComponent(row.datatype_key)}/data`}
            className="touch-target inline-flex cursor-pointer items-center text-sm font-medium text-primary hover:underline"
          >
            {t("datatypes.manageData")}
          </Link>
          <button
            type="button"
            onClick={() => setActiveKey(row.datatype_key)}
            className="touch-target inline-flex cursor-pointer items-center text-sm font-medium text-primary hover:underline"
          >
            {t("datatypes.detail")}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-3">
      {feedback ? <Feedback variant="error">{feedback}</Feedback> : null}
      <DataTable
        caption={t("datatypes.list")}
        columns={columns}
        rows={datatypes}
        getRowKey={(row) => row.datatype_key}
        emptyText={t("datatypes.empty")}
      />
      <DatatypeDetailDrawer
        key={active?.datatype_key ?? "none"}
        datatype={active}
        open={active !== null}
        onClose={() => setActiveKey(null)}
      />
    </div>
  );
}
