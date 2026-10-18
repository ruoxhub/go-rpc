// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ParserCapabilities,
  ParserRevision,
  ParserSample,
} from "@/api/action-parser/action-parser.types";
import type { Action, Platform } from "@/utils/crawler/crawler-types";

import ParserError from "./error";
import ParserLoading from "./loading";
import ParserPage from "./page";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
});

const action: Action = {
  ba_id: 9,
  bs_id: 7,
  ba_action: "getUser",
  ba_desc: "用户信息",
  ba_params_schema: "[]",
  ba_api_url: "/user",
  ba_api_method: "GET",
  ba_enabled: true,
  ba_sample_safe: true,
  create_time: null,
  update_time: null,
};

const platform: Platform = {
  bs_id: 7,
  bs_name: "TikTok",
  bs_platform_code: "tiktok",
  bs_url: null,
  bs_remark: null,
  bs_status: "1",
  bs_concurrency: 1,
  bs_rps: 1,
  bs_burst: 3,
  bs_cooldown: 300,
};

const capabilities: ParserCapabilities = {
  model_datatypes: ["post"],
  field_types: ["string"],
  model_fields: {
    post: [{ target: "/id", required: true, value_types: ["string"] }],
  },
};

const sample: ParserSample = {
  sample_id: 1,
  ba_id: action.ba_id,
  response_sha256: "sample",
  response_bytes: 10,
  sanitizer_version: "1",
  rpc_duration_ms: 5,
  created_at: "2026-08-13T00:00:00Z",
};

function revision(
  revisionId: number,
  status: ParserRevision["status"],
): ParserRevision {
  return {
    revision_id: revisionId,
    ba_id: action.ba_id,
    revision_no: revisionId,
    status,
    definition: {
      schema_version: 1,
      record_path: "/data",
      output: { mode: "json" },
      fields: [{ target: "/id", source: "/id" }],
    },
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

const draft = revision(1, "draft");
const published = revision(2, "published");

function responseFor(url: string, actionStatus = 200) {
  const requestUrl = new URL(url, "http://localhost");
  const pathname = requestUrl.pathname;
  const search = requestUrl.search;
  if (pathname.endsWith("/actions/9") && search === "") {
    return actionStatus === 404
      ? Response.json({ detail: "接口不存在" }, { status: 404 })
      : Response.json(action);
  }
  if (pathname.endsWith("/platforms")) {
    return Response.json({ items: [platform] });
  }
  if (pathname.endsWith("/tasks/meta/action-schemas/9")) {
    return Response.json({ schema: { type: "object", properties: {} } });
  }
  if (pathname.endsWith("/parser-capabilities")) {
    return Response.json(capabilities);
  }
  if (pathname.endsWith("/actions/9/parser-samples")) {
    return Response.json({ items: [sample] });
  }
  if (pathname.endsWith("/actions/9/parser-revisions")) {
    return Response.json({ items: [draft, published] });
  }
  if (pathname.endsWith("/tasks/meta/llm-models")) {
    return Response.json({
      llm_models: [
        { id: 3, display_name: "GPT", litellm_model: "openai/gpt" },
      ],
    });
  }
  return Response.json({ detail: `unexpected request: ${url}` }, { status: 500 });
}

describe("Parser RSC 页面", () => {
  it("并行装配首屏契约并渲染真实 Action 状态", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      requests.push(url);
      return responseFor(url);
    });

    const page = await ParserPage({ params: Promise.resolve({ id: "9" }) });
    render(page);

    expect(
      screen.getByRole("heading", { name: /getUser.*Parser/ }),
    ).toBeTruthy();
    expect(screen.getByText(/TikTok/)).toBeTruthy();
    expect(requests).toEqual(
      expect.arrayContaining([
        expect.stringContaining("/actions/9"),
        expect.stringContaining("/platforms?include_deleted=false"),
        expect.stringContaining("/tasks/meta/action-schemas/9"),
        expect.stringContaining("/parser-capabilities"),
        expect.stringContaining(
          "/actions/9/parser-samples?offset=0&limit=20",
        ),
        expect.stringContaining(
          "/actions/9/parser-revisions?offset=0&limit=20",
        ),
        expect.stringContaining("/tasks/meta/llm-models"),
      ]),
    );
    expect(requests).toHaveLength(7);
  });

  it.each(["0", "-1", "1.5", "9007199254740992"])(
    "非法 ID %s 进入 not-found 且不发请求",
    async (id) => {
      const request = vi.spyOn(globalThis, "fetch");
      await expect(
        ParserPage({ params: Promise.resolve({ id }) }),
      ).rejects.toThrow("NEXT_NOT_FOUND");
      expect(request).not.toHaveBeenCalled();
    },
  );

  it("只将 Action 404 转为 not-found，且七个请求都已启动", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      requests.push(url);
      return responseFor(url, 404);
    });

    await expect(
      ParserPage({ params: Promise.resolve({ id: "9" }) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(requests).toHaveLength(7);
  });
});

describe("Parser 路由边界", () => {
  it("loading 提供状态、工作台和历史三个可识别骨架区", () => {
    render(<ParserLoading />);
    expect(screen.getAllByRole("status")).toHaveLength(3);
    expect(document.querySelector("main")?.getAttribute("aria-busy")).toBe(
      "true",
    );
  });

  it("error 重试按钮调用 reset", () => {
    const reset = vi.fn();
    render(<ParserError reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: /重试/ }));
    expect(reset).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});
