import { afterEach, describe, expect, it, vi } from "vitest";

import { getActionParamSchema, getParserLlmModels } from "./task-metadata.api";

afterEach(() => vi.unstubAllGlobals());

describe("任务元数据 API", () => {
  it("请求 Action 参数 schema", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ schema: {} })));

    await getActionParamSchema(7);

    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8081/api/crawler/tasks/meta/action-schemas/7",
      expect.anything(),
    );
  });

  it("请求 Parser 可用模型", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ llm_models: [] })));

    await getParserLlmModels();

    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8081/api/crawler/tasks/meta/llm-models",
      expect.anything(),
    );
  });
});
