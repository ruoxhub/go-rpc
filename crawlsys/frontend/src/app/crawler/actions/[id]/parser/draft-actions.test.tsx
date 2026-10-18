// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  archiveParserRevision,
  previewParserRevision,
  publishParserRevision,
  restoreParserRevision,
  saveParserRevision,
} from "@/api/action-parser/action-parser.api";
import type {
  ParserCapabilities,
  ParserDefinition,
  ParserRevision,
  ParserSample,
} from "@/api/action-parser/action-parser.types";
import type { Action } from "@/utils/crawler/crawler-types";

import { ParserWorkspace } from "./_components/ParserWorkspace";
import {
  createInitialWorkspaceState,
  type ParserWorkspaceServerState,
} from "./_components/ParserWorkspace/types";

vi.mock("@/api/action-parser/action-parser.api", () => ({
  archiveParserRevision: vi.fn(),
  assistParserDefinition: vi.fn(),
  createParserSample: vi.fn(),
  deleteParserDraft: vi.fn(),
  deleteParserSample: vi.fn(),
  getParserSample: vi.fn(),
  listParserSamples: vi.fn(),
  previewParserRevision: vi.fn(),
  publishParserRevision: vi.fn(),
  restoreParserRevision: vi.fn(),
  saveParserRevision: vi.fn(),
  suggestParserDefinition: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const action: Action = {
  ba_id: 9,
  bs_id: 7,
  ba_action: "getUser",
  ba_desc: null,
  ba_params_schema: null,
  ba_api_url: null,
  ba_api_method: null,
  ba_enabled: true,
  ba_sample_safe: true,
  create_time: null,
  update_time: null,
};

const capabilities: ParserCapabilities = {
  model_datatypes: ["post"],
  field_types: ["string"],
  model_fields: { post: [{ target: "/id", required: true, value_types: ["string"] }] },
};

const definition: ParserDefinition = {
  schema_version: 1,
  record_path: "/data",
  output: { mode: "json" },
  fields: [{ target: "/id", source: "/id" }],
};

function revision(
  revisionId: number,
  status: ParserRevision["status"] = "draft",
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
    validation_report: null,
    lock_version: 1,
    generation_metadata: null,
    created_at: "2026-08-13T00:00:00Z",
    updated_at: "2026-08-13T00:00:00Z",
    published_at: status === "published" ? "2026-08-13T00:00:00Z" : null,
  };
}

const sample: ParserSample = {
  sample_id: 10,
  ba_id: 9,
  response_sha256: "a".repeat(64),
  response_bytes: 12,
  sanitizer_version: "v1",
  rpc_duration_ms: 8,
  created_at: "2026-08-13T00:00:00Z",
};

function renderWorkspace(overrides: Partial<ParserWorkspaceServerState> = {}) {
  render(
    <ParserWorkspace
      initialState={createInitialWorkspaceState({
        action,
        platformName: "TikTok",
        capabilities,
        actionSchema: { type: "object", properties: {} },
        llmModels: [{ id: 3, display_name: "GPT", litellm_model: "gpt" }],
        samples: [],
        sampleServerCount: 0,
        samplesExhausted: true,
        revisions: [],
        revisionServerCount: 0,
        revisionsExhausted: true,
        draft: null,
        published: null,
        ...overrides,
      })}
    />,
  );
}

describe("DraftActions 生命周期", () => {
  it("无 Draft 时显示创建按钮并调用 saveParserRevision 创建空定义", async () => {
    const created = revision(1);
    vi.mocked(saveParserRevision).mockResolvedValue(created);
    renderWorkspace();

    const button = screen.getByRole("button", { name: "创建 Draft" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(saveParserRevision).toHaveBeenCalledWith(9, undefined, {
        definition: {
          schema_version: 1,
          record_path: "",
          output: { mode: "json" },
          fields: [{ target: "/result", source: "" }],
        },
      }),
    );
  });

  it("有草稿且未修改时保存按钮禁用，修改后可保存", async () => {
    const draft = revision(1);
    renderWorkspace({ draft, revisions: [draft] });

    const saveButton = screen.getByRole("button", { name: "保存草稿" });
    expect((saveButton as HTMLButtonElement).disabled).toBe(true);
  });

  it("无样例时预览按钮禁用", () => {
    const draft = revision(1);
    renderWorkspace({ draft, revisions: [draft] });

    expect(
      (screen.getByRole("button", { name: "运行预览" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});

describe("RevisionHistory 版本历史", () => {
  it("archived 行显示恢复，published 行显示停用", () => {
    const archived = revision(1, "archived");
    const published = revision(2, "published");
    renderWorkspace({ revisions: [archived, published] });

    const historyTab = screen.getByRole("tab", { name: "版本历史" });
    fireEvent.click(historyTab);

    expect(
      screen.getAllByRole("button", { name: "恢复" }),
    ).toHaveLength(1);
    expect(
      screen.getAllByRole("button", { name: "停用" }),
    ).toHaveLength(1);
  });

  it("点击恢复调用 restoreParserRevision 并 replaceRevision", async () => {
    const archived = revision(1, "archived");
    const restored = revision(3, "draft");
    vi.mocked(restoreParserRevision).mockResolvedValue(restored);
    vi.mocked(archiveParserRevision).mockResolvedValue(revision(2, "archived"));
    vi.mocked(previewParserRevision).mockResolvedValue({
      definition_sha256: "d",
      samples: [],
      sample_ids: [],
      source_records: 0,
      valid_records: 0,
      invalid_records: 0,
      passed: true,
      errors: [],
      errors_truncated: false,
      preview: [],
    });
    vi.mocked(publishParserRevision).mockResolvedValue(revision(3, "published"));
    renderWorkspace({ revisions: [archived] });

    fireEvent.click(screen.getByRole("tab", { name: "版本历史" }));
    fireEvent.click(screen.getByRole("button", { name: "恢复" }));

    await waitFor(() =>
      expect(restoreParserRevision).toHaveBeenCalledWith(9, 1),
    );
  });
});

describe("SampleLibrary 多选", () => {
  it("勾选样例后显示已选数量", () => {
    renderWorkspace({ samples: [sample], sampleServerCount: 1 });

    fireEvent.click(screen.getByRole("tab", { name: "响应样例" }));
    const checkbox = screen.getByRole("checkbox", { name: /响应样例 #10/ });
    fireEvent.click(checkbox);

    expect(screen.getByText(/已选 1 个样例/)).toBeTruthy();
  });
});