// AiSuggestion：基于脱敏样例调用 AI 生成候选解析规则，接受后随保存回执写入 source=ai。
"use client";

import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { Loader2 } from "@/app/_components/Loader2";
import { Badge } from "@/app/_components/ui";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { Select } from "@/app/_components/ui/select";
import { t } from "@/app/i18n";
import {
  assistParserDefinition,
  suggestParserDefinition,
} from "@/api/action-parser/action-parser.api";
import type { ParserOutput } from "@/api/action-parser/action-parser.types";
import { CrawlerApiError } from "@/utils/crawler/crawler-api";
import { JsonTree } from "../JsonTree";
import { useParserWorkspace } from "../../index";

export const DATATYPE_LABELS: Record<string, string> = {
  content: "内容 / 帖子 / 视频 (content)",
  user: "用户资料 (user)",
  comment: "互动评论 (comment)",
  job: "招聘职位 (job)",
  media: "媒体资源 (media)",
  challenge: "话题活动 (challenge)",
  follow: "关注关系 (follow)",
};
export function AiSuggestion() {
  const {
    action,
    llmModels,
    samples,
    capabilities,
    draft,
    aiCandidate,
    aiPreview,
    applyAiCandidate,
    acceptAiCandidate,
    clearAiCandidate,
  } = useParserWorkspace(
    useShallow((state) => ({
      action: state.action,
      llmModels: state.llmModels,
      samples: state.samples,
      capabilities: state.capabilities,
      draft: state.draft,
      aiCandidate: state.aiCandidate,
      aiPreview: state.aiPreview,
      applyAiCandidate: state.applyAiCandidate,
      acceptAiCandidate: state.acceptAiCandidate,
      clearAiCandidate: state.clearAiCandidate,
    })),
  );

  const defaultDatatype = capabilities.model_datatypes.includes("content")
    ? "content"
    : capabilities.model_datatypes[0] ?? "";
  const [mode, setMode] = useState<"json" | "model">(
    capabilities.model_datatypes.length > 0 ? "model" : "json",
  );
  const [datatype, setDatatype] = useState(defaultDatatype);
  const [modelChoice, setModelChoice] = useState<number | null>(null);
  const [sampleChoice, setSampleChoice] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState(0);

  // 列表异步到达，未选择时回落到第一项，避免用 effect 回写 state。
  const modelId = modelChoice ?? llmModels[0]?.id ?? null;
  const sampleId = sampleChoice ?? samples[0]?.sample_id ?? null;

  useEffect(() => {
    if (retryAfter <= 0) return;
    const timer = window.setInterval(
      () => setRetryAfter((value) => Math.max(0, value - 1)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [retryAfter]);

  const output: ParserOutput =
    mode === "model" ? { mode: "model", datatype: datatype || undefined } : { mode: "json" };

  async function generate() {
    if (modelId === null || sampleId === null) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result =
        draft === null
          ? await suggestParserDefinition(action.ba_id, {
              sample_id: sampleId,
              model_id: modelId,
              output,
            })
          : await assistParserDefinition(action.ba_id, draft.revision_id, {
              lock_version: draft.lock_version,
              sample_id: sampleId,
              model_id: modelId,
              output,
            });
      applyAiCandidate(result);
    } catch (error) {
      if (error instanceof CrawlerApiError && error.code === "assist_rate_limited") {
        setRetryAfter(error.retryAfter ?? 1);
        setFeedback(t("parser.ai.rateLimited", { seconds: error.retryAfter ?? 1 }));
      } else {
        setFeedback(
          error instanceof CrawlerApiError ? error.message : t("parser.ai.unknownError"),
        );
      }
    } finally {
      setBusy(false);
    }
  }

  const firstPreview = aiPreview && aiPreview.length > 0 ? aiPreview[0] : null;
  const targetModelFields =
    mode === "model" && datatype ? capabilities.model_fields[datatype] ?? [] : [];
  const requiredFields = targetModelFields.filter((f) => f.required);
  return (
    <Card
      id="parser-ai-suggestion"
      className="grid gap-4 p-5 shadow-sm scroll-mt-6"
      aria-label={t("parser.ai.title")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground">{t("parser.ai.title")}</h3>
            <Badge variant="primary">AI 智能辅助</Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            根据采集到的响应样例，自动分析 JSON 结构并推导记录提取路径与字段映射。
          </p>
        </div>
        {draft === null ? (
          <Badge variant="muted">可直接推导新草稿</Badge>
        ) : (
          <Badge variant="info">草稿辅助优化</Badge>
        )}
      </div>
      {llmModels.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("parser.ai.emptyModel")}</p>
      ) : samples.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("parser.ai.emptySample")}</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm text-foreground">
              <span>{t("parser.ai.outputMode")}</span>
              <Select
                aria-label={t("parser.ai.outputMode")}
                value={mode}
                onChange={(event) =>
                  setMode(event.target.value === "model" ? "model" : "json")
                }
                className="bg-background"
              >
                <option value="model">{t("parser.ai.modeModel")}</option>
                <option value="json">{t("parser.ai.modeJson")}</option>
              </Select>
            </label>

            {mode === "model" ? (
              <label className="grid gap-1 text-sm text-foreground">
                <span>{t("parser.ai.datatype")}</span>
                <Select
                  aria-label={t("parser.ai.datatype")}
                  value={datatype}
                  onChange={(event) => setDatatype(event.target.value)}
                  className="bg-background"
                >
                  {capabilities.model_datatypes.map((value) => (
                    <option key={value} value={value}>
                      {DATATYPE_LABELS[value] ?? value}
                    </option>
                  ))}
                </Select>
              </label>
            ) : null}

            <label className="grid gap-1 text-sm text-foreground">
              <span>{t("parser.ai.model")}</span>
              <Select
                aria-label={t("parser.ai.model")}
                value={modelId ?? ""}
                onChange={(event) => setModelChoice(Number(event.target.value))}
                className="bg-background"
              >
                {llmModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name}
                  </option>
                ))}
              </Select>
            </label>

            <label className="grid gap-1 text-sm text-foreground">
              <span>{t("parser.ai.sample")}</span>
              <Select
                aria-label={t("parser.ai.sample")}
                value={sampleId ?? ""}
                onChange={(event) => setSampleChoice(Number(event.target.value))}
                className="bg-background"
              >
                {samples.map((sample) => (
                  <option key={sample.sample_id} value={sample.sample_id}>
                    #{sample.sample_id} · {sample.response_bytes} bytes
                  </option>
                ))}
              </Select>
            </label>
          </div>

          {mode === "model" && datatype ? (
            <div className="rounded-md border border-primary/20 bg-primary/5 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-1 font-medium text-foreground">
                <span className="flex items-center gap-1.5">
                  <span>🎯 目标数据模型：</span>
                  <span className="font-semibold text-primary">{DATATYPE_LABELS[datatype] ?? datatype}</span>
                  <span className="text-muted-foreground">({targetModelFields.length} 个模型字段)</span>
                </span>
                {requiredFields.length > 0 ? (
                  <span className="text-muted-foreground">
                    包含 {requiredFields.length} 个必填项
                  </span>
                ) : null}
              </div>
              <p className="mt-1 leading-relaxed text-muted-foreground">
                {t("parser.ai.modelContractHint")}
              </p>
              {requiredFields.length > 0 ? (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-muted-foreground">核心必填：</span>
                  {requiredFields.map((f) => (
                    <span
                      key={f.target}
                      className="rounded border border-primary/20 bg-background px-1.5 py-0.5 font-mono text-[11px] font-medium text-primary"
                    >
                      {f.target}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <Button
            type="button"
            variant="gradient"
            disabled={busy || retryAfter > 0 || modelId === null || sampleId === null}
            aria-busy={busy}
            onClick={() => void generate()}
            className="min-h-11 w-fit px-4"
          >
            {busy ? <Loader2 className="mr-2 inline" /> : null}
            {aiCandidate ? t("parser.ai.regenerate") : t("parser.ai.generate")}
          </Button>

          {retryAfter > 0 ? (
            <p role="status" className="text-sm text-muted-foreground">
              {t("parser.ai.rateLimited", { seconds: retryAfter })}
            </p>
          ) : null}
          {feedback ? (
            <p role="alert" className="text-sm text-destructive">
              {feedback}
            </p>
          ) : null}
        </>
      )}

      {aiCandidate ? (
        <div className="grid gap-2 rounded-md border border-border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="font-medium text-foreground">{t("parser.ai.candidateTitle")}</h4>
            {aiCandidate.output.mode === "model" && aiCandidate.output.datatype ? (
              <div className="flex items-center gap-2">
                <Badge variant="primary">
                  {t("parser.ai.candidateModelAligned")}: {aiCandidate.output.datatype}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {t("parser.ai.fieldsCount", { count: aiCandidate.fields.length })}
                </span>
              </div>
            ) : null}
          </div>
          {firstPreview !== null ? (
            <div className="grid gap-1">
              <span className="text-xs text-muted-foreground">{t("parser.ai.preview")}</span>
              <JsonTree
                value={firstPreview}
                onSelect={() => undefined}
              />
            </div>
          ) : null}
          <div className="flex gap-2">
            <Button
              type="button"
              variant="gradient"
              onClick={acceptAiCandidate}
              className="min-h-11 px-4"
            >
              {t("parser.ai.accept")}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={clearAiCandidate}
              className="min-h-11 px-4"
            >
              {t("parser.ai.discard")}
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}