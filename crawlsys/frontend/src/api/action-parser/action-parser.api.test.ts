import { afterEach, describe, expect, it, vi } from "vitest";

import {
  archiveParserRevision,
  assistParserDefinition,
  createParserSample,
  deleteParserDraft,
  deleteParserSample,
  getParserCapabilities,
  getParserRevision,
  getParserSample,
  listParserRevisions,
  listParserSamples,
  previewParserRevision,
  publishParserRevision,
  restoreParserRevision,
  saveParserRevision,
  suggestParserDefinition,
} from "./action-parser.api";
import type { ParserDefinition, ParserRevision } from "./action-parser.types";

const definition: ParserDefinition = {
  schema_version: 1,
  record_path: "items",
  output: { mode: "json" },
  fields: [],
};
const draft = { revision_id: 11, lock_version: 2 } as Pick<
  ParserRevision,
  "revision_id" | "lock_version"
>;

afterEach(() => vi.unstubAllGlobals());

function mockJson(body: unknown = {}) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(Response.json(body))));
}

describe("Action Parser API", () => {
  it("以编码分页参数列出样本与修订", async () => {
    mockJson({ items: [] });
    await listParserSamples(7, { offset: 20, limit: 20 });
    await listParserRevisions(7, { offset: 0, limit: 10 });

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8081/api/crawler/actions/7/parser-samples?offset=20&limit=20",
      expect.anything(),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8081/api/crawler/actions/7/parser-revisions?offset=0&limit=10",
      expect.anything(),
    );
  });

  it("读写和删除样本使用稳定契约", async () => {
    mockJson({ sample_id: 3 });
    await getParserSample(7, 3);
    await createParserSample(7, { params: { cursor: 1 }, confirm_side_effect: true });
    await deleteParserSample(7, 3);

    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain("/actions/7/parser-samples/3");
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1]?.[1]?.body))).toEqual({
      params: { cursor: 1 },
      confirm_side_effect: true,
    });
    expect(vi.mocked(fetch).mock.calls[2]?.[1]?.method).toBe("DELETE");
  });

  it("创建和更新修订仅在 API 边界映射 receipt", async () => {
    mockJson({ revision_id: 11 });
    await saveParserRevision(7, undefined, { definition, assistReceipt: "create-receipt" });
    await saveParserRevision(7, draft, { definition, assistReceipt: undefined });
    await deleteParserDraft(7, 11);

    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0]?.[1]?.body))).toEqual({
      definition,
      assist_receipt: "create-receipt",
    });
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1]?.[1]?.body))).toEqual({
      definition,
      lock_version: draft.lock_version,
    });
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.method).toBe("PATCH");
    expect(vi.mocked(fetch).mock.calls[2]?.[1]?.method).toBe("DELETE");
  });

  it("读取能力、修订详情、预览和修订状态变更", async () => {
    mockJson({});
    await getParserCapabilities();
    await getParserRevision(7, 11);
    await previewParserRevision(7, 11, { lock_version: 2, sample_ids: [3] });
    await publishParserRevision(7, 11);
    await archiveParserRevision(7, 11);
    await restoreParserRevision(7, 11);

    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain("/parser-capabilities");
    expect(String(vi.mocked(fetch).mock.calls[1]?.[0])).toContain("/parser-revisions/11");
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[2]?.[1]?.body))).toEqual({
      lock_version: 2,
      sample_ids: [3],
    });
    expect(vi.mocked(fetch).mock.calls.slice(3).map(([, init]) => init?.method)).toEqual([
      "POST",
      "POST",
      "POST",
    ]);
  });

  it("suggest 和 assist 将 wire receipt 映射为页面字段", async () => {
    const wire = { definition, preview: [{ id: 3 }], assist_receipt: "opaque-receipt" };
    mockJson(wire);

    await expect(
      suggestParserDefinition(7, { sample_id: 3, model_id: 9, output: { mode: "json" } }),
    ).resolves.toEqual({ definition, preview: [{ id: 3 }], assistReceipt: "opaque-receipt" });
    await expect(
      assistParserDefinition(7, 11, {
        sample_id: 3,
        model_id: 9,
        output: { mode: "json" },
        lock_version: 2,
      }),
    ).resolves.toEqual({ definition, preview: [{ id: 3 }], assistReceipt: "opaque-receipt" });
  });
});
