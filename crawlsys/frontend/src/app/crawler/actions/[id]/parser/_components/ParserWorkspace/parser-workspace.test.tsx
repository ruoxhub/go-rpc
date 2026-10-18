// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createParserSample } from "@/api/action-parser/action-parser.api";
import type { ParserSample } from "@/api/action-parser/action-parser.types";
import type { Action } from "@/utils/crawler/crawler-types";

import { JsonTree } from "./components/JsonTree";
import { ParserWorkspace } from "./index";
import {
  createInitialWorkspaceState,
  type ParserWorkspaceServerState,
} from "./types";

vi.mock("@/api/action-parser/action-parser.api", () => ({
  createParserSample: vi.fn(),
  deleteParserSample: vi.fn(),
  getParserSample: vi.fn(),
  listParserSamples: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const action: Action = {
  ba_id: 9,
  bs_id: 1,
  ba_action: "getUser",
  ba_desc: null,
  ba_params_schema: null,
  ba_api_url: null,
  ba_api_method: null,
  ba_enabled: true,
  ba_sample_safe: false,
  create_time: null,
  update_time: null,
};

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
        capabilities: { model_datatypes: [], field_types: [], model_fields: {} },
        actionSchema: {
          type: "object",
          properties: { cursor: { type: "integer" } },
        },
        llmModels: [],
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

describe("ParserWorkspace 样例", () => {
  it("不安全 Action 未确认时不调用取样，确认后只发送一次控制字段", async () => {
    vi.mocked(createParserSample).mockResolvedValue(sample);
    renderWorkspace({ action: { ...action, ba_sample_safe: false } });

    fireEvent.change(screen.getByLabelText("cursor"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建样例" }));

    expect(createParserSample).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: /确认真实调用/ })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "确认取样" }));
    await waitFor(() =>
      expect(createParserSample).toHaveBeenCalledWith(9, {
        params: { cursor: 1 },
        confirm_side_effect: true,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "创建样例" }));
    expect(screen.getByRole("dialog", { name: /确认真实调用/ })).toBeTruthy();
  });
});

describe("JsonTree", () => {
  it("树节点按文本渲染并用 Enter 返回绝对 Pointer", () => {
    const onSelect = vi.fn();
    render(
      <JsonTree
        value={{ data: { items: [{ content: { id: 1 } }] } }}
        recordPath="/data/items"
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /展开 data/ }));
    fireEvent.click(screen.getByRole("button", { name: /展开 items/ }));
    fireEvent.click(screen.getByRole("button", { name: /展开 0/ }));
    fireEvent.click(screen.getByRole("button", { name: /展开 content/ }));
    const node = screen.getByRole("button", { name: /选择节点 \/data\/items\/0\/content\/id/ });
    fireEvent.keyDown(node, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("/data/items/0/content/id");
  });

  it("支持全部展开、全部折叠和搜索高亮", () => {
    const onSelect = vi.fn();
    render(
      <JsonTree
        value={{ code: 0, data: { name: "test" } }}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByText(/全部展开/)).toBeTruthy();
    expect(screen.getByText(/全部折叠/)).toBeTruthy();
    expect(screen.getByText(/复制 JSON/)).toBeTruthy();

    // 点击全部展开后，原本折叠的 data 下的 name 节点应该可见
    fireEvent.click(screen.getByRole("button", { name: "全部展开" }));
    expect(screen.getByRole("button", { name: /选择节点 \/data\/name/ })).toBeTruthy();
    // 搜索过滤
    const searchInput = screen.getByPlaceholderText(/搜索字段名或数值/);
    fireEvent.change(searchInput, { target: { value: "test" } });
    expect(screen.getByText(/1 处匹配/)).toBeTruthy();
  });
});
