// SampleInspector：按需展示当前样例的脱敏响应树，并把选中节点回填为当前字段的来源指针。
"use client";

import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Badge } from "@/app/_components/ui";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { Select } from "@/app/_components/ui/select";
import { Loader2 } from "@/app/_components/Loader2";
import { getParserSample } from "@/api/action-parser/action-parser.api";
import { CrawlerApiError } from "@/utils/crawler/crawler-api";
import { t } from "@/app/i18n";
import { JsonTree } from "../JsonTree";
import { relativePointer, representativeRecord } from "../../utils/jsonPointer";
import { useParserWorkspace } from "../../index";
export function SampleInspector() {
  const {
    action,
    samples,
    activeSampleId,
    sampleDetails,
    workingDefinition,
    activePointerTarget,
    expandedFieldIndex,
    setSampleDetail,
    setActiveSample,
    setActivePointerTarget,
    updateDefinition,
  } = useParserWorkspace(
    useShallow((state) => ({
      action: state.action,
      samples: state.samples,
      activeSampleId: state.activeSampleId,
      sampleDetails: state.sampleDetails,
      workingDefinition: state.workingDefinition,
      activePointerTarget: state.activePointerTarget,
      expandedFieldIndex: state.expandedFieldIndex,
      setSampleDetail: state.setSampleDetail,
      setActiveSample: state.setActiveSample,
      setActivePointerTarget: state.setActivePointerTarget,
      updateDefinition: state.updateDefinition,
    })),
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const detail = activeSampleId === null ? undefined : sampleDetails[activeSampleId];

  useEffect(() => {
    if (activeSampleId === null || detail !== undefined) return;
    let cancelled = false;
    const promise = getParserSample(action.ba_id, activeSampleId);
    if (promise && typeof promise.then === "function") {
      promise
        .then((value) => { if (!cancelled) setSampleDetail(value); })
        .catch((error) => {
          if (!cancelled) {
            setFeedback(error instanceof CrawlerApiError ? error.message : t("parser.sample.detailUnknownError"));
            if (error instanceof CrawlerApiError && error.status === 404) setActiveSample(null);
          }
        });
    }
    return () => { cancelled = true; };
  }, [action.ba_id, activeSampleId, detail, setActiveSample, setSampleDetail]);

  const recordPath = workingDefinition?.record_path ?? "";

  function handleSelect(pointer: string) {
    if (workingDefinition === null || detail === undefined) return;

    if (activePointerTarget?.kind === "record_path") {
      updateDefinition({
        ...workingDefinition,
        record_path: pointer,
      });
      setActivePointerTarget(null);
      return;
    }

    const targetIndex =
      activePointerTarget?.kind === "source"
        ? activePointerTarget.fieldIndex
        : expandedFieldIndex !== null && expandedFieldIndex < workingDefinition.fields.length
          ? expandedFieldIndex
          : null;

    if (targetIndex !== null) {
      const base = representativeRecord(detail.redacted_preview, recordPath);
      const relative =
        base === null ? null : relativePointer(base.absoluteBase, pointer);
      const source = relative ?? pointer;
      updateDefinition({
        ...workingDefinition,
        fields: workingDefinition.fields.map((field, index) =>
          index === targetIndex
            ? { ...field, source, value: undefined }
            : field,
        ),
      });
      setActivePointerTarget(null);
    }
  }

  if (activeSampleId === null) {
    return (
      <Card className="flex flex-col items-center justify-center p-8 text-center shadow-sm">
        <span className="text-xl">🔍</span>
        <h4 className="mt-2 text-sm font-semibold text-foreground">未选择样例数据</h4>
        <p className="mt-1 text-xs text-muted-foreground">{t("parser.sample.select")}</p>
      </Card>
    );
  }
  if (detail === undefined) {
    return (
      <Card className="flex flex-col items-center justify-center p-8 text-center shadow-sm">
        <Loader2 className="h-5 w-5 text-primary" />
        <p role="status" className="mt-2 text-xs text-muted-foreground">
          {t("parser.sample.loading")}
        </p>
      </Card>
    );
  }

  const activeTargetName =
    activePointerTarget?.kind === "record_path"
      ? t("parser.definition.recordPath")
      : activePointerTarget?.kind === "source"
        ? `${t("parser.definition.source")} #${activePointerTarget.fieldIndex + 1}`
        : expandedFieldIndex !== null
          ? `${t("parser.definition.source")} #${expandedFieldIndex + 1}`
          : null;

  return (
    <Card
      className="grid gap-3 p-4 shadow-sm"
      aria-label={t("parser.sample.inspector")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-foreground">
            {t("parser.sample.inspector")}
          </h3>
          <Badge variant="muted">样例 #{activeSampleId}</Badge>
          <span className="text-xs text-muted-foreground font-mono">
            {detail.response_bytes} B
          </span>
        </div>
        {samples.length > 1 ? (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>切换样例:</span>
            <Select
              value={activeSampleId ?? ""}
              onChange={(e) => setActiveSample(Number(e.target.value))}
              className="h-8 w-auto bg-background px-2 py-0 text-xs text-foreground"
            >
              {samples.map((s) => (
                <option key={s.sample_id} value={s.sample_id}>
                  #{s.sample_id} · {s.response_bytes} B · {s.rpc_duration_ms} ms
                </option>
              ))}
            </Select>
          </label>
        ) : null}
      </div>

      {activeTargetName ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/20 bg-primary/10 px-3 py-2 text-xs text-primary font-medium">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-ping" />
            🎯 正在为【{activeTargetName}】选取节点，点击下方树节点即可填入！
          </span>
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => setActivePointerTarget(null)}
            className="h-auto p-0 text-xs text-primary underline hover:opacity-80"
          >
            清除目标
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
          <span>💡 展开右侧字段或聚焦输入框后，点击节点可快速回填路径</span>
        </div>
      )}
      {feedback ? <p role="alert" className="text-sm text-destructive">{feedback}</p> : null}
      <div className="max-h-[36rem] overflow-auto rounded-lg border border-border bg-muted/15 p-3">
        <JsonTree value={detail.redacted_preview} recordPath={recordPath} onSelect={handleSelect} />
      </div>
    </Card>
  );
}