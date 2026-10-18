// SampleParamsForm：编辑 Action 取样参数并执行一次真实 RPC 取样。
"use client";

import { useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Badge } from "@/app/_components/ui";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { Input } from "@/app/_components/ui/input";
import { Textarea } from "@/app/_components/ui/textarea";
import { Loader2 } from "@/app/_components/Loader2";
import { ConfirmDialog } from "@/app/_components/ConfirmDialog";
import { t } from "@/app/i18n";
import { createParserSample } from "@/api/action-parser/action-parser.api";
import { CrawlerApiError } from "@/utils/crawler/crawler-api";
import type { JsonValue } from "@/api/action-parser/action-parser.types";
import { describeBasicParams, compileParamsValidator } from "../../utils/sampleParams";
import { useParserWorkspace } from "../../index";

export function SampleParamsForm() {
  const { action, actionSchema, prependSample, samples, activeSampleId, setActiveSample } = useParserWorkspace(useShallow((state) => ({
    action: state.action,
    actionSchema: state.actionSchema,
    prependSample: state.prependSample,
    samples: state.samples,
    activeSampleId: state.activeSampleId,
    setActiveSample: state.setActiveSample,
  })));
  const description = useMemo(() => describeBasicParams(actionSchema), [actionSchema]);
  const [mode, setMode] = useState(description.mode);
  const [params, setParams] = useState<Record<string, JsonValue>>(description.initial);
  const [jsonSource, setJsonSource] = useState(() => JSON.stringify(description.initial, null, 2));
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState(0);

  useEffect(() => {
    if (retryAfter <= 0) return;
    const timer = window.setInterval(() => setRetryAfter((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [retryAfter]);

  useEffect(() => {
    setMode(description.mode);
    setParams(description.initial);
    setJsonSource(JSON.stringify(description.initial, null, 2));
  }, [description]);

  const parseParams = () => {
    if (mode === "json") {
      try {
        const parsed: unknown = JSON.parse(jsonSource);
        if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("root");
        const value = parsed as Record<string, JsonValue>;
        const errors = compileParamsValidator(actionSchema)(value);
        if (errors.length > 0) {
          setFeedback(t("parser.params.invalid"));
          return null;
        }
        return value;
      } catch {
        setFeedback(t("parser.params.invalid"));
        return null;
      }
    }
    return params;
  };

  async function submit(confirmed = false) {
    const value = parseParams();
    if (value === null) return;
    if (!action.ba_sample_safe && !confirmed) {
      setConfirmOpen(true);
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const sample = await createParserSample(action.ba_id, {
        params: value,
        confirm_side_effect: action.ba_sample_safe ? false : confirmed,
      });
      prependSample(sample);
      setConfirmOpen(false);
    } catch (error) {
      if (error instanceof CrawlerApiError && error.code === "sample_rate_limited") {
        setRetryAfter(error.retryAfter ?? 1);
      } else {
        setFeedback(error instanceof CrawlerApiError ? error.message : t("parser.sample.unknownError"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="grid gap-3 p-4 shadow-sm" aria-label={t("parser.sample.form")}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground">{t("parser.sample.form")}</h3>
            {samples.length > 0 ? (
              <Badge variant="success">已获取 {samples.length} 个样例</Badge>
            ) : (
              <Badge variant="muted">待取样</Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            输入参数发起一次真实 RPC 调用，获取脱敏响应 JSON 以供规则配置与测试。
          </p>
        </div>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto p-0 text-xs font-medium text-primary hover:underline"
          onClick={() => setMode((value) => value === "basic" ? "json" : "basic")}
        >
          {mode === "basic" ? t("parser.params.advanced") : t("parser.params.basic")}
        </Button>
      </div>

      {samples.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/40 px-3 py-2 text-xs">
          <span className="text-muted-foreground">
            当前激活样例: <strong className="text-foreground">#{activeSampleId ?? samples[0]?.sample_id}</strong>
          </span>
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => setActiveSample(activeSampleId === null ? samples[0].sample_id : null)}
            className="h-auto p-0 font-medium text-primary hover:underline"
          >
            {activeSampleId === null ? `查看样例 #${samples[0].sample_id} 数据树 ↓` : "收起数据树"}
          </Button>
        </div>
      ) : null}
      {mode === "basic" ? (
        description.mode === "basic" && description.fields.length > 0 ? (
          description.fields.map((field) => (
            <label key={field.name} className="grid gap-1 text-sm text-foreground">
              <span>{field.name}{field.required ? " *" : ""}</span>
              <Input
                aria-label={field.name}
                value={String(params[field.name] ?? "")}
                onChange={(event) => {
                  const raw = event.target.value;
                  const next: JsonValue = field.kind === "integer" ? (raw === "" ? "" : Number.parseInt(raw, 10)) : field.kind === "number" ? (raw === "" ? "" : Number.parseFloat(raw)) : raw;
                  setParams((current) => ({ ...current, [field.name]: next }));
                }}
                className="bg-background"
                inputMode={field.kind === "integer" || field.kind === "number" ? "decimal" : undefined}
              />
            </label>
          ))
        ) : <p className="text-sm text-muted-foreground">{t("parser.params.useJson")}</p>
      ) : (
        <Textarea aria-label={t("parser.params.json")} value={jsonSource} onChange={(event) => setJsonSource(event.target.value)} rows={8} className="bg-background font-mono text-sm" />
      )}
      {feedback ? <p role="alert" className="text-sm text-destructive">{feedback}</p> : null}
      {retryAfter > 0 ? <p role="status" className="text-sm text-muted-foreground">{t("parser.sample.retryAfter", { seconds: retryAfter })}</p> : null}
      <Button type="button" variant="gradient" disabled={busy || retryAfter > 0} aria-busy={busy} onClick={() => void submit()} className="min-h-11 px-4">
        {busy ? <Loader2 className="mr-2 inline" /> : null}{t("parser.sample.create")}
      </Button>
      {samples.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-xs text-muted-foreground">
          <span>已有 {samples.length} 个样例</span>
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => setActiveSample(activeSampleId === null ? samples[0].sample_id : null)}
            className="h-auto p-0 text-xs text-primary hover:underline"
          >
            {activeSampleId === null ? `查看样例 #${samples[0].sample_id} 结构` : "收起样例结构"}
          </Button>
        </div>
      ) : null}
      <ConfirmDialog open={confirmOpen} title={t("parser.sample.confirmTitle")} description={t("parser.sample.confirmDescription")} confirmLabel={t("parser.sample.confirm")} cancelLabel={t("common.cancel")} busy={busy} onCancel={() => setConfirmOpen(false)} onConfirm={() => void submit(true)} />
    </Card>
  );
}
