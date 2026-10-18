import { describe, expect, it } from "vitest";

import type {
  ParserAssistResult,
  ParserCapabilities,
  ParserDefinition,
  ParserPreviewReport,
  ParserRevision,
  ParserSample,
  ParserSampleDetail,
} from "@/api/action-parser/action-parser.types";
import type { Action } from "@/utils/crawler/crawler-types";

import { createParserWorkspaceStore } from "./parserWorkspaceStore";
import {
  createInitialWorkspaceState,
  type ParserWorkspaceState,
} from "../types";

const action: Action = {
  ba_id: 9,
  bs_id: 7,
  ba_action: "getUser",
  ba_desc: null,
  ba_params_schema: null,
  ba_api_url: "/user",
  ba_api_method: "GET",
  ba_enabled: true,
  ba_sample_safe: true,
  create_time: null,
  update_time: null,
};

const capabilities: ParserCapabilities = {
  model_datatypes: ["post"],
  field_types: ["string", "integer"],
  model_fields: {
    post: [{ target: "/id", required: true, value_types: ["string"] }],
  },
};

const baseDefinition: ParserDefinition = {
  schema_version: 1,
  record_path: "/data",
  output: { mode: "json" },
  fields: [{ target: "/id", source: "/id" }],
};

const changedDefinition: ParserDefinition = {
  ...baseDefinition,
  fields: [
    { target: "/id", source: "/id" },
    { target: "/name", source: "/name" },
  ],
};

const candidateDefinition: ParserDefinition = {
  ...baseDefinition,
  fields: [{ target: "/profile", value: { name: "Ada", id: 1 } }],
};

const equivalentCandidateDefinition: ParserDefinition = {
  fields: [{ value: { id: 1, name: "Ada" }, target: "/profile" }],
  output: { mode: "json", datatype: null },
  record_path: "/data",
  schema_version: 1,
};

const previewReport: ParserPreviewReport = {
  definition_sha256: "definition",
  samples: [{ sample_id: 1, sample_sha256: "sample-1" }],
  sample_ids: [1],
  source_records: 1,
  valid_records: 1,
  invalid_records: 0,
  passed: true,
  errors: [],
  errors_truncated: false,
  preview: [{ id: "1" }],
};

function revision(
  revisionId: number,
  definition = baseDefinition,
  status: ParserRevision["status"] = "draft",
  lockVersion = 1,
): ParserRevision {
  return {
    revision_id: revisionId,
    ba_id: action.ba_id,
    revision_no: revisionId,
    status,
    definition,
    definition_sha256: `definition-${revisionId}`,
    source: "manual",
    source_sample_id: null,
    restored_from_revision_id: null,
    validation_report: previewReport,
    lock_version: lockVersion,
    generation_metadata: null,
    created_at: "2026-08-13T00:00:00Z",
    updated_at: "2026-08-13T00:00:00Z",
    published_at: status === "published" ? "2026-08-13T00:00:00Z" : null,
  };
}

function sample(sampleId: number): ParserSample {
  return {
    sample_id: sampleId,
    ba_id: action.ba_id,
    response_sha256: `sample-${sampleId}`,
    response_bytes: 10,
    sanitizer_version: "1",
    rpc_duration_ms: 5,
    created_at: "2026-08-13T00:00:00Z",
  };
}

const draft = revision(1);
const published = revision(2, baseDefinition, "published");

function initialState(): ParserWorkspaceState {
  return createInitialWorkspaceState({
    action,
    platformName: "TikTok",
    capabilities,
    actionSchema: { type: "object" },
    llmModels: [{ id: 3, display_name: "GPT", litellm_model: "gpt" }],
    samples: [sample(1)],
    sampleServerCount: 1,
    samplesExhausted: true,
    revisions: [draft, published],
    revisionServerCount: 2,
    revisionsExhausted: true,
    draft,
    published,
  });
}

const candidate: ParserAssistResult = {
  definition: candidateDefinition,
  preview: [{ id: 1 }],
  assistReceipt: "receipt",
};

describe("ParserWorkspace store", () => {
  it("从服务端 Draft 初始化编辑基线和报告", () => {
    expect(initialState()).toMatchObject({
      baseDefinition,
      workingDefinition: baseDefinition,
      dirty: false,
      conflicted: false,
      previewReport,
      pendingOutput: baseDefinition.output,
      selectedSampleIds: [],
      activeSection: "workspace",
    });
  });

  it("保存成功更新基线并使旧报告失效", () => {
    const store = createParserWorkspaceStore(initialState());
    const savedRevision = revision(3, changedDefinition);
    store.getState().updateDefinition(changedDefinition);
    expect(store.getState().dirty).toBe(true);

    store.getState().applySavedRevision(savedRevision);

    expect(store.getState()).toMatchObject({
      baseDefinition: savedRevision.definition,
      workingDefinition: savedRevision.definition,
      dirty: false,
      conflicted: false,
      previewReport: null,
      pendingOutput: savedRevision.definition.output,
    });
    expect(store.getState().revisions[0]).toEqual(savedRevision);
  });

  it("任何人工修改立即清除 AI receipt", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().applyAiCandidate(candidate);
    store.getState().updateDefinition(changedDefinition);

    expect(store.getState()).toMatchObject({
      aiCandidate: null,
      aiPreview: null,
      aiReceipt: null,
    });
  });

  it("只改变 JSON 格式或对象属性顺序不清除 receipt", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().applyAiCandidate(candidate);
    store.getState().acceptAiCandidate();
    const receipt = store.getState().aiReceipt;

    store.getState().updateDefinition(equivalentCandidateDefinition);

    expect(store.getState().aiReceipt).toBe(receipt);
  });

  it("独立维护待选 output", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().setPendingOutput({ mode: "model", datatype: "post" });
    expect(store.getState().pendingOutput).toEqual({
      mode: "model",
      datatype: "post",
    });
  });

  it("本地插入记录不污染服务端分页 offset", () => {
    const store = createParserWorkspaceStore({
      ...initialState(),
      sampleServerCount: 20,
    });
    store.getState().prependSample(sample(2));

    expect(store.getState()).toMatchObject({
      sampleServerCount: 20,
      activeSampleId: 2,
      selectedSampleIds: [2],
    });
  });

  it("追加样例按 ID 去重并使用服务端累计 offset", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().appendSamples([sample(1), sample(2), sample(2)], 22, false);

    expect(store.getState().samples.map((item) => item.sample_id)).toEqual([1, 2]);
    expect(store.getState()).toMatchObject({
      sampleServerCount: 22,
      samplesExhausted: false,
    });
  });

  it("服务端样例对账清除失效选择、详情和 active ID", () => {
    const detail: ParserSampleDetail = {
      ...sample(1),
      redacted_preview: { id: 1 },
    };
    const store = createParserWorkspaceStore(initialState());
    store.getState().setSampleDetail(detail);
    store.getState().setActiveSample(1);
    store.getState().toggleSelectedSample(1);

    store.getState().replaceSamplesFromServer([sample(2)]);

    expect(store.getState()).toMatchObject({
      samples: [sample(2)],
      sampleServerCount: 1,
      samplesExhausted: true,
      activeSampleId: null,
      selectedSampleIds: [],
      sampleDetails: {},
    });
  });

  it("样例详情可缓存，删除样例同步清理关联状态", () => {
    const detail: ParserSampleDetail = {
      ...sample(1),
      redacted_preview: { id: 1 },
    };
    const store = createParserWorkspaceStore(initialState());
    store.getState().setSampleDetail(detail);
    store.getState().setActiveSample(1);
    store.getState().toggleSelectedSample(1);
    expect(store.getState().sampleDetails[1]).toEqual(detail);

    store.getState().removeSample(1);

    expect(store.getState()).toMatchObject({
      samples: [],
      activeSampleId: null,
      selectedSampleIds: [],
      sampleDetails: {},
    });
  });

  it("样例选择最多保留 50 个 ID", () => {
    const store = createParserWorkspaceStore({
      ...initialState(),
      selectedSampleIds: Array.from({ length: 50 }, (_, index) => index + 1),
    });
    store.getState().toggleSelectedSample(51);
    expect(store.getState().selectedSampleIds).toHaveLength(50);
    store.getState().toggleSelectedSample(1);
    expect(store.getState().selectedSampleIds).not.toContain(1);
  });

  it("预览报告同步写入 Draft 与 revisions 列表", () => {
    const store = createParserWorkspaceStore(initialState());
    const report = { ...previewReport, definition_sha256: "new-report" };

    store.getState().applyPreviewReport(report);

    expect(store.getState().previewReport).toEqual(report);
    expect(store.getState().draft?.validation_report).toEqual(report);
    expect(store.getState().revisions[0]?.validation_report).toEqual(report);
  });

  it("追加 Revision 按 ID 去重并使用服务端累计 offset", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().appendRevisions([draft, revision(3), revision(3)], 23, false);

    expect(store.getState().revisions.map((item) => item.revision_id)).toEqual([
      1, 2, 3,
    ]);
    expect(store.getState()).toMatchObject({
      revisionServerCount: 23,
      revisionsExhausted: false,
    });
  });

  it("无本地修改时按服务端 Revision 列表更新编辑基线", () => {
    const store = createParserWorkspaceStore(initialState());
    const serverDraft = revision(3, changedDefinition, "draft", 2);

    store.getState().replaceRevisionsFromServer([serverDraft]);

    expect(store.getState()).toMatchObject({
      draft: serverDraft,
      published: null,
      baseDefinition: changedDefinition,
      workingDefinition: changedDefinition,
      dirty: false,
      conflicted: false,
    });
  });

  it.each(["dirty", "conflicted"] as const)(
    "%s 时服务端 Draft 变化只标记冲突并保留 working Definition",
    (mode) => {
      const store = createParserWorkspaceStore(initialState());
      if (mode === "dirty") store.getState().updateDefinition(changedDefinition);
      else store.getState().markConflict();
      const workingDefinition = store.getState().workingDefinition;

      store
        .getState()
        .replaceRevisionsFromServer([revision(1, baseDefinition, "draft", 2)]);

      expect(store.getState().workingDefinition).toEqual(workingDefinition);
      expect(store.getState().conflicted).toBe(true);
    },
  );

  it("用户确认丢弃后无条件采用服务端版本并清空冲突和 AI 内存", () => {
    const store = createParserWorkspaceStore(initialState());
    const serverDraft = revision(3, changedDefinition, "draft", 2);
    store.getState().updateDefinition(changedDefinition);
    store.getState().applyAiCandidate(candidate);
    store.getState().markConflict();

    store.getState().discardLocalAndReplaceRevisions([serverDraft]);

    expect(store.getState()).toMatchObject({
      baseDefinition: changedDefinition,
      workingDefinition: changedDefinition,
      dirty: false,
      conflicted: false,
      aiCandidate: null,
      aiPreview: null,
      aiReceipt: null,
    });
  });

  it("删除 Draft 时清除 Definition、报告、冲突和 AI 内存", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().applyAiCandidate(candidate);
    store.getState().markConflict();

    store.getState().removeRevision(draft.revision_id);

    expect(store.getState()).toMatchObject({
      draft: null,
      baseDefinition: null,
      workingDefinition: null,
      dirty: false,
      conflicted: false,
      previewReport: null,
      aiCandidate: null,
      aiPreview: null,
      aiReceipt: null,
    });
  });

  it("替换 Draft 更新基线，替换 Published 更新发布引用", () => {
    const store = createParserWorkspaceStore(initialState());
    const nextDraft = revision(1, changedDefinition, "draft", 2);
    const nextPublished = revision(4, changedDefinition, "published");
    store.getState().replaceRevision(nextDraft);
    store.getState().replaceRevision(nextPublished);

    expect(store.getState()).toMatchObject({
      draft: nextDraft,
      published: nextPublished,
      baseDefinition: changedDefinition,
      workingDefinition: changedDefinition,
      dirty: false,
    });
  });

  it("切换编辑视图、唯一展开行、指针目标和一级区域", () => {
    const store = createParserWorkspaceStore(initialState());
    store.getState().setDefinitionView("json");
    store.getState().setExpandedFieldIndex(2);
    store.getState().setExpandedFieldIndex(5);
    store
      .getState()
      .setActivePointerTarget({ kind: "source", fieldIndex: 5 });
    store.getState().setActiveSection("history");

    expect(store.getState()).toMatchObject({
      definitionView: "json",
      expandedFieldIndex: 5,
      activePointerTarget: { kind: "source", fieldIndex: 5 },
      activeSection: "history",
    });
  });
});
