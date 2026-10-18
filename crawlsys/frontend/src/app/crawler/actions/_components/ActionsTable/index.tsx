// 接口管理表格组件：支持客户端分页、跨页勾选、当前页全选与批量操作
"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState } from "react";

import { ConfirmDialog } from "../../../../_components/ConfirmDialog";
import { Loader2 } from "../../../../_components/Loader2";
import { NumberInput } from "../../../../_components/NumberInput";
import { Button } from "../../../../_components/ui/button";
import { Card } from "../../../../_components/ui/card";
import { Select } from "../../../../_components/ui/select";
import { DataTable, type DataTableColumn } from "../../../_components/DataTable";
import { Feedback } from "../../../_components/Feedback";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type {
  Action,
  ActionBatchDeleteResponse,
  ActionBatchStatusResponse,
} from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";
import { ActionActions } from "../ActionActions";

interface ActionsTableProps {
  actions: Action[];
  platformNames: Record<number, string>;
}

type BusyActionType = "enable" | "disable" | "delete" | null;

export function ActionsTable({ actions, platformNames }: ActionsTableProps) {
  const router = useRouter();
  const selectAllId = useId();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [busyAction, setBusyAction] = useState<BusyActionType>(null);
  const [feedback, setFeedback] = useState<{ text: string; failed: boolean } | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  // 分页状态：默认每页 20 条，支持下拉切换与跳页
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [jumpInput, setJumpInput] = useState("");

  const totalItems = actions.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safeCurrentPage = Math.min(Math.max(1, currentPage), totalPages);

  const startIndex = (safeCurrentPage - 1) * pageSize;
  const pagedActions = actions.slice(startIndex, startIndex + pageSize);

  const busy = busyAction !== null;
  const currentPageIds = pagedActions.map((item) => item.ba_id);
  const currentPageSelectedCount = currentPageIds.filter((id) => selectedIds.has(id)).length;
  const allCurrentPageSelected =
    currentPageIds.length > 0 && currentPageSelectedCount === currentPageIds.length;
  const isIndeterminate =
    currentPageSelectedCount > 0 && currentPageSelectedCount < currentPageIds.length;

  function toggleSelectAllCurrentPage() {
    if (allCurrentPageSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const id of currentPageIds) {
          next.delete(id);
        }
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const id of currentPageIds) {
          next.add(id);
        }
        return next;
      });
    }
  }

  function toggleSelectRow(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function selectAllTotal() {
    setSelectedIds(new Set(actions.map((item) => item.ba_id)));
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  function handlePageSizeChange(newSize: number) {
    setPageSize(newSize);
    setCurrentPage(1);
  }

  function handleJumpSubmit(e: FormEvent) {
    e.preventDefault();
    const pageNum = parseInt(jumpInput.trim(), 10);
    if (!isNaN(pageNum)) {
      setCurrentPage(Math.min(Math.max(1, pageNum), totalPages));
      setJumpInput("");
    }
  }

  async function runBatchStatus(enabled: boolean) {
    if (selectedIds.size === 0) return;
    const actionType = enabled ? "enable" : "disable";
    setBusyAction(actionType);
    setFeedback(null);
    try {
      const result = await crawlerRequest<ActionBatchStatusResponse>("/actions/batch-status", {
        method: "POST",
        body: JSON.stringify({
          action_ids: Array.from(selectedIds),
          enabled,
        }),
      });
      setFeedback({
        text: t("actions.batchUpdated", { count: result.updated_count }),
        failed: false,
      });
      clearSelection();
      router.refresh();
    } catch (error) {
      setFeedback({
        text: error instanceof CrawlerApiError ? error.message : t("actions.batchFailed"),
        failed: true,
      });
    } finally {
      setBusyAction(null);
    }
  }

  async function runBatchDelete() {
    if (selectedIds.size === 0) return;
    setBusyAction("delete");
    setFeedback(null);
    try {
      const result = await crawlerRequest<ActionBatchDeleteResponse>("/actions/batch-delete", {
        method: "POST",
        body: JSON.stringify({
          action_ids: Array.from(selectedIds),
        }),
      });
      setFeedback({
        text: t("actions.batchDeleted", { count: result.deleted_count }),
        failed: false,
      });
      clearSelection();
      setConfirmDeleteOpen(false);
      router.refresh();
    } catch (error) {
      setFeedback({
        text: error instanceof CrawlerApiError ? error.message : t("actions.batchFailed"),
        failed: true,
      });
    } finally {
      setBusyAction(null);
    }
  }

  const columns: DataTableColumn<Action>[] = [
    {
      id: "select",
      header: (
        <span className="inline-flex items-center">
          <input
            id={selectAllId}
            type="checkbox"
            aria-label={t("actions.selectAll")}
            checked={allCurrentPageSelected}
            ref={(el) => {
              if (el) el.indeterminate = isIndeterminate;
            }}
            onChange={toggleSelectAllCurrentPage}
            className="h-4 w-4 cursor-pointer rounded border-input text-primary focus:ring-1 focus:ring-ring"
          />
        </span>
      ),
      className: "w-10 px-3",
      render: (row) => (
        <input
          type="checkbox"
          aria-label={row.ba_action}
          checked={selectedIds.has(row.ba_id)}
          onChange={() => toggleSelectRow(row.ba_id)}
          className="h-4 w-4 cursor-pointer rounded border-input text-primary focus:ring-1 focus:ring-ring"
        />
      ),
    },
    { id: "name", header: t("actions.name"), accessor: "ba_action" },
    {
      id: "platform",
      header: t("nav.platforms"),
      accessor: (row) => platformNames[row.bs_id] ?? t("actions.platformName", { id: row.bs_id }),
    },
    { id: "method", header: t("actions.method"), accessor: (row) => row.ba_api_method ?? "—" },
    { id: "url", header: t("actions.apiUrl"), accessor: (row) => row.ba_api_url ?? "—" },
    {
      id: "status",
      header: t("common.status"),
      render: (row) => (
        <span className={row.ba_enabled ? "text-success-strong" : "text-muted-foreground"}>
          {row.ba_enabled ? t("common.enabled") : t("common.disabled")}
        </span>
      ),
    },
    {
      id: "actions",
      header: t("common.actions"),
      className: "text-right",
      render: (row) => <ActionActions action={row} />,
    },
  ];

  return (
    <div className="grid gap-3">
      {selectedIds.size > 0 ? (
        <Card className="flex flex-wrap items-center justify-between gap-3 p-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-2 text-sm text-foreground">
            <span className="font-medium">
              {t("actions.selectedCount", { count: selectedIds.size })}
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={clearSelection}
              className="h-auto px-1 py-0 text-xs text-muted-foreground hover:text-foreground"
            >
              {t("actions.deselectAll")}
            </Button>
            {selectedIds.size < totalItems ? (
              <Button
                type="button"
                variant="link"
                size="sm"
                onClick={selectAllTotal}
                className="h-auto px-1 py-0 text-xs text-primary"
              >
                {t("actions.selectAllTotal", { total: totalItems })}
              </Button>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => runBatchStatus(true)}
            >
              {busyAction === "enable" ? <Loader2 className="mr-1.5 inline" /> : null}
              {t("actions.batchEnable")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => runBatchStatus(false)}
            >
              {busyAction === "disable" ? <Loader2 className="mr-1.5 inline" /> : null}
              {t("actions.batchDisable")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => setConfirmDeleteOpen(true)}
              className="border-destructive/20 bg-destructive/10 text-destructive hover:bg-destructive/20 hover:text-destructive"
            >
              {busyAction === "delete" ? <Loader2 className="mr-1.5 inline" /> : null}
              {t("actions.batchDelete")}
            </Button>
          </div>
        </Card>
      ) : null}

      {feedback ? (
        <Feedback variant={feedback.failed ? "error" : "success"}>
          {feedback.text}
        </Feedback>
      ) : null}

      <DataTable
        caption={t("actions.list")}
        columns={columns}
        rows={pagedActions}
        getRowKey={(row) => row.ba_id}
        emptyText={t("actions.empty")}
      />

      {/* 分页控制栏 */}
      <Card className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm text-foreground shadow-sm">
        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span>{t("actions.pagination.total", { total: totalItems })}</span>
          <label className="flex items-center gap-1.5">
            <span>{t("actions.pagination.perPageLabel")}</span>
            <Select
              aria-label={t("actions.pagination.perPageLabel")}
              value={pageSize}
              onChange={(e) => handlePageSizeChange(Number(e.target.value))}
              className="h-8 w-auto cursor-pointer bg-background px-2 py-1 text-xs font-normal"
            >
              {[10, 20, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {t("actions.pagination.perPage", { size })}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <nav
            aria-label={t("actions.pagination.pageInfo", {
              current: safeCurrentPage,
              total: totalPages,
            })}
            className="flex items-center gap-1"
          >
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage(1)}
              className="px-2.5"
            >
              {t("actions.pagination.first")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              className="px-2.5"
            >
              {t("actions.pagination.prev")}
            </Button>
            <span className="px-2 text-xs font-medium text-foreground tabular-nums">
              {t("actions.pagination.pageInfo", {
                current: safeCurrentPage,
                total: totalPages,
              })}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
              className="px-2.5"
            >
              {t("actions.pagination.next")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage(totalPages)}
              className="px-2.5"
            >
              {t("actions.pagination.last")}
            </Button>
          </nav>

          {totalPages > 1 ? (
            <form onSubmit={handleJumpSubmit} className="flex items-center gap-1 text-xs text-muted-foreground">
              <span>{t("actions.pagination.jumpTo")}</span>
              <NumberInput
                integer
                aria-label={t("actions.pagination.jumpTo")}
                value={jumpInput}
                onChange={(e) => setJumpInput(e.target.value)}
                placeholder={String(safeCurrentPage)}
                className="!h-8 !w-12 !px-1.5 text-center !text-xs"
              />
              {t("actions.pagination.pageUnit") ? (
                <span>{t("actions.pagination.pageUnit")}</span>
              ) : null}
            </form>
          ) : null}
        </div>
      </Card>

      <ConfirmDialog
        open={confirmDeleteOpen}
        busy={busyAction === "delete"}
        destructive
        title={t("actions.batchDeleteTitle")}
        description={t("actions.batchDeleteDescription", { count: selectedIds.size })}
        confirmLabel={t("common.confirmDelete")}
        cancelLabel={t("common.cancel")}
        onCancel={() => setConfirmDeleteOpen(false)}
        onConfirm={runBatchDelete}
      >
        {feedback && feedback.failed ? (
          <Feedback variant="error">{feedback.text}</Feedback>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}
