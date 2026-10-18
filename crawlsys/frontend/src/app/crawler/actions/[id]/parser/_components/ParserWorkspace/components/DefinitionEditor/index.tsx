// DefinitionEditor：编辑 Parser Definition 的结构化和高级 JSON 视图。
"use client";

import { useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Badge } from "@/app/_components/ui";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { Input } from "@/app/_components/ui/input";
import { Select } from "@/app/_components/ui/select";
import { Textarea } from "@/app/_components/ui/textarea";
import { t } from "@/app/i18n";
import { saveParserRevision } from "@/api/action-parser/action-parser.api";
import type { JsonValue, ParserDefinition } from "@/api/action-parser/action-parser.types";
import { formatDefinitionJson, normalizeDefinition, parseDefinitionJson, validateDefinition } from "../../utils/definition";
import { useParserWorkspace } from "../../index";
import { DATATYPE_LABELS } from "../AiSuggestion";

function updateField(definition: ParserDefinition, index: number, patch: Partial<ParserDefinition["fields"][number]>) {
  return { ...definition, fields: definition.fields.map((field, current) => current === index ? { ...field, ...patch } : field) };
}

function removeField(definition: ParserDefinition, index: number): ParserDefinition {
  if (definition.fields.length <= 1) return definition;
  return {
    ...definition,
    fields: definition.fields.filter((_, current) => current !== index),
  };
}

const initialDraftDefinition: ParserDefinition = {
  schema_version: 1,
  record_path: "",
  output: { mode: "json" },
  fields: [{ target: "/result", source: "" }],
};

function getInitialDraftDefinition(datatypes: string[]): ParserDefinition {
  if (datatypes.length === 0) {
    return initialDraftDefinition;
  }
  const defaultDatatype = datatypes.includes("content") ? "content" : datatypes[0];
  return {
    schema_version: 1,
    record_path: "",
    output: { mode: "model", datatype: defaultDatatype },
    fields: [{ target: "/title", source: "" }],
  };
}

export function DefinitionEditor() {
  const {
    action,
    published,
    samples,
    activeSampleId,
    capabilities,
    workingDefinition,
    definitionView,
    expandedFieldIndex,
    activePointerTarget,
    updateDefinition,
    applySavedRevision,
    setDefinitionView,
    setExpandedFieldIndex,
    setActivePointerTarget,
  } = useParserWorkspace(
    useShallow((state) => ({
      action: state.action,
      published: state.published,
      samples: state.samples,
      activeSampleId: state.activeSampleId,
      capabilities: state.capabilities,
      workingDefinition: state.workingDefinition,
      definitionView: state.definitionView,
      expandedFieldIndex: state.expandedFieldIndex,
      activePointerTarget: state.activePointerTarget,
      updateDefinition: state.updateDefinition,
      applySavedRevision: state.applySavedRevision,
      setDefinitionView: state.setDefinitionView,
      setExpandedFieldIndex: state.setExpandedFieldIndex,
      setActivePointerTarget: state.setActivePointerTarget,
    })),
  );
  const [creatingDraft, setCreatingDraft] = useState(false);
  const [jsonSource, setJsonSource] = useState(workingDefinition ? formatDefinitionJson(workingDefinition) : "");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const jsonRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (definitionView === "json" && workingDefinition) setJsonSource(formatDefinitionJson(workingDefinition));
  }, [definitionView, workingDefinition]);

  if (!workingDefinition) {
    return (
      <Card
        className="grid gap-4 p-5 shadow-sm"
        aria-label={t("parser.definition.title")}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
          <div>
            <h3 className="font-semibold text-foreground">
              {t("parser.definition.title")}
            </h3>
            <p className="text-xs text-muted-foreground">
              {t("parser.definition.empty")}
            </p>
          </div>
          <Badge variant="muted">草稿未创建</Badge>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {/* 路径 1：AI 智能生成 */}
          <div className="flex flex-col justify-between rounded-lg border border-primary/20 bg-primary/5 p-4 transition-colors">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">
                  🤖 AI 智能推导
                </span>
                <Badge variant="primary">推荐</Badge>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {samples.length > 0
                  ? `基于样例 #${activeSampleId ?? samples[0]?.sample_id} 的响应数据，由 AI 分析 JSON 结构并自动生成与系统数据模型对应的字段映射与记录提取规则。`
                  : "先在左侧输入参数并获取样例响应，即可使用 AI 自动生成对应数据模型的解析规则。"}
              </p>
            </div>
            <div className="mt-4">
              <a
                href="#parser-ai-suggestion"
                className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-gradient-back px-4 text-xs font-medium text-gradient-foreground shadow-sm hover:opacity-95"
              >
                使用 AI 自动生成规则 ↓
              </a>
            </div>
          </div>

          {/* 路径 2：手动创建 */}
          <div className="flex flex-col justify-between rounded-lg border border-border bg-card p-4">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">
                  ✍️ 手动配置规则
                </span>
                <Badge variant="outline">从零开始</Badge>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                创建一个绑定系统数据模型（如 content/user）的空白规则草稿，手动配置记录路径并映射字段来源。
              </p>
            </div>
            <div className="mt-4">
              <Button
                type="button"
                variant="outline"
                disabled={creatingDraft}
                onClick={async () => {
                  setCreatingDraft(true);
                  try {
                    const base = published
                      ? published.definition
                      : getInitialDraftDefinition(capabilities.model_datatypes);
                    const rev = await saveParserRevision(action.ba_id, undefined, { definition: base });
                    applySavedRevision(rev);
                  } finally {
                    setCreatingDraft(false);
                  }
                }}
                className="min-h-11 w-full px-4 text-xs"
              >
                {creatingDraft ? "正在创建草稿…" : "创建空白 Draft"}
              </Button>
            </div>
          </div>
        </div>

        {published ? (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            💡 当前线上已有运行版本 #{published.revision_no}。创建草稿将自动继承其已发布的解析规则。
          </div>
        ) : null}
      </Card>
    );
  }

  const switchToStructured = () => {
    try {
      const parsed = normalizeDefinition(parseDefinitionJson(jsonSource));
      const errors = validateDefinition(parsed, capabilities);
      if (errors.length > 0) {
        setJsonError(t("parser.definition.invalid"));
        jsonRef.current?.focus();
        return;
      }
      updateDefinition(parsed);
      setJsonError(null);
      setDefinitionView("structured");
    } catch {
      setJsonError(t("parser.definition.invalid"));
      jsonRef.current?.focus();
    }
  };

  const patch = (next: ParserDefinition) => updateDefinition(normalizeDefinition(next));

  const modelFields =
    workingDefinition.output.mode === "model" && workingDefinition.output.datatype
      ? capabilities.model_fields[workingDefinition.output.datatype] ?? []
      : [];

  return (
    <Card className="grid gap-4 p-4 shadow-sm" aria-label={t("parser.definition.title")}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label={t("parser.definition.views")}>
          <button
            type="button"
            role="tab"
            aria-selected={definitionView === "structured"}
            onClick={() => definitionView === "json" ? switchToStructured() : undefined}
            className={`min-h-11 cursor-pointer rounded-md px-3 text-sm font-medium ${
              definitionView === "structured"
                ? "border border-primary bg-primary/10 text-primary"
                : "border border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {t("parser.definition.structured")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={definitionView === "json"}
            onClick={() => { setJsonSource(formatDefinitionJson(workingDefinition)); setJsonError(null); setDefinitionView("json"); }}
            className={`min-h-11 cursor-pointer rounded-md px-3 text-sm font-medium ${
              definitionView === "json"
                ? "border border-primary bg-primary/10 text-primary"
                : "border border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {t("parser.definition.json")}
          </button>
        </div>
        <a
          href="#parser-ai-suggestion"
          className="text-xs text-primary hover:underline flex items-center gap-1"
        >
          🤖 AI 辅助生成/优化
        </a>
      </div>
      {definitionView === "json" ? (
        <div className="grid gap-2">
          <Textarea ref={jsonRef} aria-label="Definition JSON" value={jsonSource} onChange={(event) => setJsonSource(event.target.value)} rows={18} className="bg-background p-3 font-mono text-sm" />
          {jsonError ? <p role="alert" className="text-sm text-destructive">{jsonError}</p> : null}
          <Button type="button" variant="outline" onClick={() => setJsonSource(() => { try { return formatDefinitionJson(parseDefinitionJson(jsonSource)); } catch { return jsonSource; } })} className="min-h-11 w-fit px-3">{t("parser.definition.format")}</Button>
        </div>
      ) : (
        <div className="grid gap-3">
          <label className="grid gap-1 text-sm text-foreground">
            <span className="flex items-center justify-between">
              <span>{t("parser.definition.recordPath")}</span>
              {activePointerTarget?.kind === "record_path" ? (
                <span className="text-xs text-primary font-medium animate-pulse">
                  🎯 聚焦中：点击左侧树节点填入
                </span>
              ) : null}
            </span>
            <Input
              aria-label="记录路径"
              value={workingDefinition.record_path}
              onFocus={() => setActivePointerTarget({ kind: "record_path" })}
              onChange={(event) => patch({ ...workingDefinition, record_path: event.target.value })}
              placeholder="例如 /data/result，或聚焦后点击左侧样例节点"
              className={`bg-background font-mono text-sm transition-all ${
                activePointerTarget?.kind === "record_path"
                  ? "border-primary ring-2 ring-primary/20"
                  : ""
              }`}
            />
          </label>
          <label className="grid gap-1 text-sm text-foreground">
            <span>{t("parser.definition.outputMode")}</span>
            <Select aria-label="输出模式" value={workingDefinition.output.mode} onChange={(event) => { const mode = event.target.value === "model" ? "model" : "json"; const defaultDt = capabilities.model_datatypes.includes("content") ? "content" : capabilities.model_datatypes[0]; patch({ ...workingDefinition, output: mode === "model" ? { mode, datatype: defaultDt } : { mode } }); }} className="bg-background">
              <option value="model">数据模型模式 (推荐，严格对齐系统模型)</option>
              <option value="json">自由 JSON 模式</option>
            </Select>
          </label>
          {workingDefinition.output.mode === "model" ? (
            <label className="grid gap-1 text-sm text-foreground">
              <span>{t("parser.definition.datatype")}</span>
              <Select aria-label="数据模型" value={workingDefinition.output.datatype ?? ""} onChange={(event) => patch({ ...workingDefinition, output: { mode: "model", datatype: event.target.value || undefined } })} className="bg-background">
                {capabilities.model_datatypes.map((datatype) => <option key={datatype} value={datatype}>{DATATYPE_LABELS[datatype] ?? datatype}</option>)}
              </Select>
            </label>
          ) : null}
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-foreground">{t("parser.definition.fields")} ({workingDefinition.fields.length})</h3>
            </div>
            {workingDefinition.fields.map((field, index) => (
              <section key={index} className="rounded-md border border-border">
                <div className="flex items-center justify-between gap-2 px-3 py-1">
                  <button
                    id={`parser-field-${index}-summary`}
                    type="button"
                    aria-expanded={expandedFieldIndex === index}
                    onClick={() => setExpandedFieldIndex(expandedFieldIndex === index ? null : index)}
                    className="min-h-11 flex-1 cursor-pointer text-left text-sm text-foreground"
                  >
                    <span className="font-medium">{index + 1}. {field.target || t("parser.definition.untitledField")}</span>
                    {field.source ? (
                      <span className="ml-2 font-mono text-xs text-muted-foreground">
                        ← {field.source}
                      </span>
                    ) : field.value !== undefined ? (
                      <span className="ml-2 font-mono text-xs text-muted-foreground">
                        = {JSON.stringify(field.value)}
                      </span>
                    ) : null}
                  </button>
                  {workingDefinition.fields.length > 1 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`删除字段 ${index + 1}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        patch(removeField(workingDefinition, index));
                        if (expandedFieldIndex === index) setExpandedFieldIndex(null);
                      }}
                      className="min-h-9 px-2 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                    >
                      {t("common.delete")}
                    </Button>
                  ) : null}
                </div>
                {expandedFieldIndex === index ? (
                  <div className="grid gap-2 border-t border-border p-3">
                    <label className="grid gap-1 text-sm">
                      <span>{t("parser.definition.target")}</span>
                      <Input
                        aria-label={`目标字段 ${index + 1}`}
                        list={modelFields.length > 0 ? `model-fields-${index}` : undefined}
                        value={field.target}
                        onChange={(event) => patch(updateField(workingDefinition, index, { target: event.target.value }))}
                        placeholder={modelFields.length > 0 ? "选择或输入模型字段，如 /title" : "例如 /title"}
                        className="bg-background font-mono text-sm"
                      />
                      {modelFields.length > 0 ? (
                        <datalist id={`model-fields-${index}`}>
                          {modelFields.map((f) => (
                            <option key={f.target} value={f.target}>
                              {f.target} ({f.value_types.join("|")}{f.required ? ", 必填" : ""})
                            </option>
                          ))}
                        </datalist>
                      ) : null}
                    </label>
                    {field.value === undefined ? (
                      <label className="grid gap-1 text-sm">
                        <span className="flex items-center justify-between">
                          <span>{t("parser.definition.source")}</span>
                          {activePointerTarget?.kind === "source" && activePointerTarget.fieldIndex === index ? (
                            <span className="text-xs text-primary font-medium animate-pulse">
                              🎯 聚焦中：点击左侧树节点填入
                            </span>
                          ) : null}
                        </span>
                        <Input
                          aria-label={`来源路径 ${index + 1}`}
                          value={field.source ?? ""}
                          onFocus={() => setActivePointerTarget({ kind: "source", fieldIndex: index })}
                          onChange={(event) => patch(updateField(workingDefinition, index, { source: event.target.value, value: undefined }))}
                          placeholder="例如 /title，或聚焦后点击左侧样例节点"
                          className={`bg-background font-mono text-sm transition-all ${
                            activePointerTarget?.kind === "source" && activePointerTarget.fieldIndex === index
                              ? "border-primary ring-2 ring-primary/20"
                              : ""
                          }`}
                        />
                      </label>
                    ) : (
                      <div className="grid gap-1 text-sm">
                        <span className="text-muted-foreground">固定常量值:</span>
                        <span className="font-mono text-xs">{JSON.stringify(field.value)}</span>
                      </div>
                    )}
                    <div className="flex gap-2">
                      {field.value === undefined ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => patch(updateField(workingDefinition, index, { value: null, source: undefined }))}
                          className="min-h-9 w-fit px-3 text-xs text-muted-foreground hover:text-foreground"
                        >
                          {t("parser.definition.useNull")}
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => patch(updateField(workingDefinition, index, { source: "", value: undefined }))}
                          className="min-h-9 w-fit px-3 text-xs text-primary"
                        >
                          改用来源路径
                        </Button>
                      )}
                    </div>
                  </div>
                ) : null}
              </section>
            ))}
          </div>
          {workingDefinition.fields.length < 500 ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                const newIndex = workingDefinition.fields.length;
                patch({ ...workingDefinition, fields: [...workingDefinition.fields, { target: "", source: "" }] });
                setExpandedFieldIndex(newIndex);
              }}
              className="min-h-11 w-fit px-3 text-sm"
            >
              {t("parser.definition.addField")}
            </Button>
          ) : null}
        </div>
      )}
    </Card>
  );
}
