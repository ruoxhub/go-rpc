"use client";

// 数据模型详情抽屉：展示物理列、解析器 DTO 映射与冲突更新策略。
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "@/app/_components/ui/button";
import { Badge } from "@/app/_components/ui/badge";
import { Sheet, SheetContent, SheetTitle } from "@/app/_components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/app/_components/ui/table";

import type {
  DatatypeColumnMeta,
  DatatypeDtoFieldMeta,
  DatatypeItem,
} from "../../../../../api/datatype/datatype.types";
import { t } from "../../../../i18n";

type DrawerTab = "columns" | "dtoFields";

interface DatatypeDetailDrawerProps {
  datatype: DatatypeItem | null;
  open: boolean;
  onClose: () => void;
}

export function DatatypeDetailDrawer({
  datatype,
  open,
  onClose,
}: DatatypeDetailDrawerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const tabsId = useId();
  const [tab, setTab] = useState<DrawerTab>("columns");

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement as HTMLElement | null;
      return () => restoreFocusRef.current?.focus();
    }

    if (dialogRef.current?.open && typeof dialogRef.current.close === "function") {
      dialogRef.current.close();
    }
    restoreFocusRef.current?.focus();
  }, [open]);

  if (!open || !datatype) return null;

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent
        ref={dialogRef}
        side="right"
        aria-labelledby={titleId}
        onCancel={(event) => {
          event.preventDefault();
          onClose();
        }}
        className="p-0"
      >
        <div className="flex h-full flex-col">
          <header className="border-b border-border px-6 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <SheetTitle id={titleId} className="text-lg font-semibold">
                  {datatype.model_name}
                </SheetTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {datatype.datatype_key} · {datatype.table_name}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("datatypes.uniqueField")}：
                  {datatype.unique_field ?? t("datatypes.uniqueFieldEmpty")}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                className="touch-target px-3"
              >
                {t("datatypes.close")}
              </Button>
            </div>
            {datatype.description ? (
              <p className="mt-2 text-sm text-muted-foreground">
                {datatype.description}
              </p>
            ) : null}
          </header>

          <div
            role="tablist"
            aria-label={t("datatypes.tabs.navigation")}
            className="flex gap-4 border-b border-border px-6"
          >
            <DrawerTabButton
              id={`${tabsId}-columns-tab`}
              controls={`${tabsId}-columns-panel`}
              active={tab === "columns"}
              onSelect={() => setTab("columns")}
            >
              {t("datatypes.tabs.columns")}
            </DrawerTabButton>
            <DrawerTabButton
              id={`${tabsId}-dto-tab`}
              controls={`${tabsId}-dto-panel`}
              active={tab === "dtoFields"}
              onSelect={() => setTab("dtoFields")}
            >
              {t("datatypes.tabs.dtoFields")}
            </DrawerTabButton>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-4">
            {tab === "columns" ? (
              <div
                id={`${tabsId}-columns-panel`}
                role="tabpanel"
                aria-labelledby={`${tabsId}-columns-tab`}
              >
                <ColumnsTable columns={datatype.columns} />
              </div>
            ) : (
              <div
                id={`${tabsId}-dto-panel`}
                role="tabpanel"
                aria-labelledby={`${tabsId}-dto-tab`}
              >
                <DtoFieldsTable fields={datatype.dto_fields} />
              </div>
            )}
          </div>

          <footer className="border-t border-border px-6 py-4">
            <h3 className="text-sm font-medium">{t("datatypes.updateFields")}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("datatypes.updateFieldsHint")}
            </p>
            {datatype.update_fields.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">
                {t("datatypes.updateFieldsEmpty")}
              </p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-2">
                {datatype.update_fields.map((field) => (
                  <li key={field}>
                    <Badge variant="outline" className="bg-muted font-numeric text-xs">
                      {field}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </footer>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function DrawerTabButton({
  id,
  controls,
  active,
  onSelect,
  children,
}: {
  id: string;
  controls: string;
  active: boolean;
  onSelect: () => void;
  children: ReactNode;
}) {
  return (
    <button
      id={id}
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      tabIndex={active ? 0 : -1}
      onClick={onSelect}
      className={`relative cursor-pointer py-3 text-sm font-medium transition-colors ${
        active ? "text-primary" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
      {active ? (
        <span
          aria-hidden
          className="absolute inset-x-0 -bottom-px h-0.5 bg-gradient-back"
        />
      ) : null}
    </button>
  );
}

const cellClass = "px-3 py-2 text-sm text-foreground";
const headCellClass =
  "px-3 py-2 text-left text-xs font-medium text-muted-foreground";

function ColumnsTable({ columns }: { columns: DatatypeColumnMeta[] }) {
  if (columns.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("datatypes.columnsEmpty")}</p>;
  }
  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.columns.name")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.columns.type")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.columns.primaryKey")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.columns.nullable")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.columns.comment")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {columns.map((column) => (
            <TableRow key={column.name}>
              <TableCell className={`${cellClass} font-numeric`}>{column.name}</TableCell>
              <TableCell className={`${cellClass} text-muted-foreground`}>{column.type}</TableCell>
              <TableCell className={cellClass}>
                {column.primary_key ? t("datatypes.yes") : t("datatypes.no")}
              </TableCell>
              <TableCell className={cellClass}>
                {column.nullable ? t("datatypes.yes") : t("datatypes.no")}
              </TableCell>
              <TableCell className={`${cellClass} text-muted-foreground`}>
                {column.comment ?? "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function DtoFieldsTable({ fields }: { fields: DatatypeDtoFieldMeta[] }) {
  if (fields.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("datatypes.dtoEmpty")}</p>;
  }
  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.columns.name")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.dto.target")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.dto.required")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.dto.valueTypes")}
            </TableHead>
            <TableHead scope="col" className={headCellClass}>
              {t("datatypes.dto.description")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => (
            <TableRow key={field.name}>
              <TableCell className={`${cellClass} font-numeric`}>{field.name}</TableCell>
              <TableCell className={`${cellClass} font-numeric text-muted-foreground`}>
                {field.target}
              </TableCell>
              <TableCell className={cellClass}>
                {field.required ? t("datatypes.yes") : t("datatypes.no")}
              </TableCell>
              <TableCell className={cellClass}>
                <span className="flex flex-wrap gap-1">
                  {field.value_types.map((valueType) => (
                    <Badge
                      key={valueType}
                      variant="outline"
                      className="bg-muted font-numeric text-xs"
                    >
                      {valueType}
                    </Badge>
                  ))}
                </span>
              </TableCell>
              <TableCell className={`${cellClass} text-muted-foreground`}>
                {field.description ?? "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
