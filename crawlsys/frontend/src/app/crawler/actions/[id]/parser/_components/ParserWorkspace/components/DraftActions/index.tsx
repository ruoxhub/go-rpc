// DraftActions：编排 Draft 的创建、保存、预览、发布、删除与停用，是工作台的生命周期工具条。
"use client";

import { useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { Loader2 } from "@/app/_components/Loader2";
import { ConfirmDialog } from "@/app/_components/ConfirmDialog";
import { Badge } from "@/app/_components/ui";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { t } from "@/app/i18n";
import {
  archiveParserRevision,
  deleteParserDraft,
  previewParserRevision,
  publishParserRevision,
  saveParserRevision,
} from "@/api/action-parser/action-parser.api";
import type { ParserDefinition } from "@/api/action-parser/action-parser.types";
import { CrawlerApiError } from "@/utils/crawler/crawler-api";
import { validateDefinition } from "../../utils/definition";
import { useParserWorkspace } from "../../index";

type BusyKind = "create" | "save" | "preview" | "publish" | "archive" | null;

// 可被后端 ParserDefinition 接受的最小初始定义（target 必须是 / 开头的非空指针）。
const initialDraftDefinition: ParserDefinition = {
  schema_version: 1,
  record_path: "",
  output: { mode: "json" },
  fields: [{ target: "/result", source: "" }],
};

export function DraftActions() {
  const {
    action,
    draft,
    published,
    samples,
    workingDefinition,
    dirty,
    aiReceipt,
    selectedSampleIds,
    previewReport,
    capabilities,
    conflicted,
    applySavedRevision,
    applyPreviewReport,
    replaceRevision,
    removeRevision,
    markConflict,
  } = useParserWorkspace(
    useShallow((state) => ({
      action: state.action,
      draft: state.draft,
      published: state.published,
      samples: state.samples,
      workingDefinition: state.workingDefinition,
      dirty: state.dirty,
      aiReceipt: state.aiReceipt,
      selectedSampleIds: state.selectedSampleIds,
      previewReport: state.previewReport,
      capabilities: state.capabilities,
      conflicted: state.conflicted,
      applySavedRevision: state.applySavedRevision,
      applyPreviewReport: state.applyPreviewReport,
      replaceRevision: state.replaceRevision,
      removeRevision: state.removeRevision,
      markConflict: state.markConflict,
    })),
  );

  const [busy, setBusy] = useState<BusyKind>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);

  function errorMessage(error: unknown) {
    if (error instanceof CrawlerApiError && error.code === "revision_conflict") {
      markConflict();
      return t("parser.draft.conflict");
    }
    return error instanceof CrawlerApiError
      ? error.message
      : t("api.http", { status: 500 });
  }

  async function run(
    kind: Exclude<BusyKind, null>,
    operation: () => Promise<void>,
  ) {
    setBusy(kind);
    setFeedback(null);
    try {
      await operation();
    } catch (error) {
      setFeedback(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function create() {
    await run("create", async () => {
      const baseDefinition = published ? published.definition : initialDraftDefinition;
      const revision = await saveParserRevision(action.ba_id, undefined, {
        definition: baseDefinition,
      });
      applySavedRevision(revision);
    });
  }

  async function save() {
    if (!draft || !workingDefinition) return;
    const errors = validateDefinition(workingDefinition, capabilities);
    if (errors.length > 0) {
      setFeedback(t("parser.draft.needValid"));
      return;
    }
    await run("save", async () => {
      const revision = await saveParserRevision(
        action.ba_id,
        { revision_id: draft.revision_id, lock_version: draft.lock_version },
        {
          definition: workingDefinition,
          ...(aiReceipt ? { assistReceipt: aiReceipt } : {}),
        },
      );
      applySavedRevision(revision);
    });
  }

  async function preview() {
    if (!draft || !workingDefinition) return;
    const targetSampleIds =
      selectedSampleIds.length > 0
        ? selectedSampleIds
        : samples.length > 0
          ? [samples[0].sample_id]
          : [];
    if (targetSampleIds.length === 0) {
      setFeedback(t("parser.preview.needSample") ?? "请选择至少一个样例用于预览");
      return;
    }
    await run("preview", async () => {
      let currentDraft = draft;
      if (dirty) {
        const errors = validateDefinition(workingDefinition, capabilities);
        if (errors.length > 0) {
          setFeedback(t("parser.draft.needValid"));
          return;
        }
        currentDraft = await saveParserRevision(
          action.ba_id,
          { revision_id: draft.revision_id, lock_version: draft.lock_version },
          {
            definition: workingDefinition,
            ...(aiReceipt ? { assistReceipt: aiReceipt } : {}),
          },
        );
        applySavedRevision(currentDraft);
      }
      const report = await previewParserRevision(
        action.ba_id,
        currentDraft.revision_id,
        { lock_version: currentDraft.lock_version, sample_ids: targetSampleIds },
      );
      applyPreviewReport(report);
    });
  }

  async function publish() {
    if (!draft) return;
    await run("publish", async () => {
      const revision = await publishParserRevision(
        action.ba_id,
        draft.revision_id,
      );
      replaceRevision(revision);
      setConfirmPublish(false);
    });
  }

  async function remove() {
    if (!draft) return;
    await run("save", async () => {
      await deleteParserDraft(action.ba_id, draft.revision_id);
      removeRevision(draft.revision_id);
      setConfirmDelete(false);
    });
  }

  async function archive() {
    if (!published) return;
    await run("archive", async () => {
      const revision = await archiveParserRevision(
        action.ba_id,
        published.revision_id,
      );
      replaceRevision(revision);
    });
  }

  const needsSave = dirty;
  const canPreview =
    draft !== null && (selectedSampleIds.length > 0 || samples.length > 0);
  const canPublish = draft !== null && previewReport?.passed === true;

  const activePreviewSampleId =
    selectedSampleIds.length > 0
      ? selectedSampleIds[0]
      : samples.length > 0
        ? samples[0].sample_id
        : null;

  return (
    <Card
      className="flex flex-col justify-between gap-3 p-4 shadow-sm sm:flex-row sm:items-center"
      aria-label={t("parser.draft.create")}
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-foreground">
            {draft === null
              ? "解析规则草稿"
              : `草稿版本 #${draft.revision_no}`}
          </h3>
          {draft === null ? (
            <Badge variant="muted">未创建草稿</Badge>
          ) : dirty ? (
            <Badge variant="warning">有未保存修改</Badge>
          ) : (
            <Badge variant="muted">已保存</Badge>
          )}
          {draft !== null && previewReport?.passed ? (
            <Badge variant="success">校验已通过</Badge>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          {draft === null
            ? "当前暂无草稿。可直接创建空白草稿，或在下方使用 AI 自动生成。"
            : dirty
              ? "本地规则有修改，请及时点击保存草稿。"
              : previewReport?.passed
                ? "最近一次校验已通过，可确认无误后发布到生产环境。"
                : "规则已保存，可点击运行预览测试解析数据效果。"}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {draft === null ? (
          <Button
            type="button"
            variant="gradient"
            disabled={busy !== null}
            aria-busy={busy === "create"}
            onClick={() => void create()}
            className="min-h-11 px-5"
          >
            {busy === "create" ? <Loader2 className="mr-2 inline" /> : null}
            {t("parser.draft.create")}
          </Button>
        ) : (
          <>
            <Button
              type="button"
              variant={needsSave ? "gradient" : "outline"}
              disabled={busy !== null || !needsSave}
              aria-busy={busy === "save"}
              onClick={() => void save()}
              className="min-h-11 px-4"
            >
              {busy === "save" ? <Loader2 className="mr-2 inline" /> : null}
              {t("parser.draft.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy !== null || !canPreview}
              aria-busy={busy === "preview"}
              title={
                !canPreview
                  ? "无可用样例，请先在左侧取样"
                  : needsSave
                    ? "有未保存修改，点击将自动保存并运行预览"
                    : undefined
              }
              onClick={() => void preview()}
              className={`min-h-11 px-4 ${
                !needsSave && (!previewReport || !previewReport.passed)
                  ? "border-primary bg-primary/10 text-primary hover:bg-primary/15"
                  : ""
              }`}
            >
              {busy === "preview" ? <Loader2 className="mr-2 inline" /> : null}
              {t("parser.preview.run")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy !== null || !canPublish}
              title={
                previewReport?.passed !== true
                  ? t("parser.publish.needPassed")
                  : undefined
              }
              aria-busy={busy === "publish"}
              onClick={() => setConfirmPublish(true)}
              className={`min-h-11 px-4 ${
                canPublish
                  ? "border-success bg-success/10 text-success-strong hover:bg-success/20 font-semibold"
                  : ""
              }`}
            >
              {busy === "publish" ? <Loader2 className="mr-2 inline" /> : null}
              {t("parser.publish.run")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy !== null}
              onClick={() => setConfirmDelete(true)}
              className="min-h-11 px-4 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              {t("parser.draft.delete")}
            </Button>
          </>
        )}

        {published !== null && draft === null ? (
          <Button
            type="button"
            variant="outline"
            disabled={busy !== null}
            aria-busy={busy === "archive"}
            onClick={() => void archive()}
            className="min-h-11 px-4"
          >
            {busy === "archive" ? <Loader2 className="mr-2 inline" /> : null}
            {t("parser.archive.run")}
          </Button>
        ) : null}
      </div>

      {conflicted ? (
        <p role="status" className="w-full text-sm text-destructive">
          {t("parser.draft.conflict")}
        </p>
      ) : null}
      {feedback ? (
        <p role="alert" className="w-full text-sm text-destructive">
          {feedback}
        </p>
      ) : null}

      <ConfirmDialog
        open={confirmDelete}
        title={t("parser.draft.deleteTitle")}
        description={t("parser.draft.deleteDescription")}
        confirmLabel={t("common.delete")}
        cancelLabel={t("common.cancel")}
        destructive
        busy={busy === "save"}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => void remove()}
      />
      <ConfirmDialog
        open={confirmPublish}
        title={t("parser.publish.confirmTitle")}
        description={t("parser.publish.confirmDescription")}
        confirmLabel={t("parser.publish.run")}
        cancelLabel={t("common.cancel")}
        busy={busy === "publish"}
        onCancel={() => setConfirmPublish(false)}
        onConfirm={() => void publish()}
      />
    </Card>
  );
}