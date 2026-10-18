import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDatatypeRow,
  deleteDatatypeRow,
  getDatatype,
  getDatatypeRowsMeta,
  getDatatypes,
  listDatatypeRows,
  syncDatatypes,
  updateDatatypeRow,
  updateDatatypeStatus,
} from "./datatype.api";

afterEach(() => vi.unstubAllGlobals());

function mockJson(body: unknown = {}) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(Response.json(body))));
}

describe("Datatype API", () => {
  it("列表请求支持可选 is_active 过滤", async () => {
    mockJson({ items: [], total: 0 });
    await getDatatypes();
    await getDatatypes(false);

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8081/api/crawler/datatypes",
      expect.anything(),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8081/api/crawler/datatypes?is_active=false",
      expect.anything(),
    );
  });

  it("详情与同步使用稳定契约", async () => {
    mockJson({ datatype_key: "content" });
    await getDatatype("content");
    await syncDatatypes();

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8081/api/crawler/datatypes/content",
      expect.anything(),
    );
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.method).toBe("POST");
  });

  it("状态更新使用 PATCH 并携带 is_active", async () => {
    mockJson({ datatype_key: "follow" });
    await updateDatatypeStatus("follow", false);

    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8081/api/crawler/datatypes/follow/status",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ is_active: false }),
      }),
    );
  });

  it("行元数据与列表编码过滤、排序与分页参数", async () => {
    mockJson({ items: [], total: 0, page: 1, page_size: 20 });
    await getDatatypeRowsMeta("follow");
    await listDatatypeRows("follow", {
      page: 2,
      pageSize: 50,
      keyword: "alpha",
      sort: "follow_name",
      order: "asc",
      filters: [{ field: "platform", operator: "eq", value: "bilibili" }],
    });

    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain(
      "/api/crawler/datatypes/follow/rows/meta",
    );
    const listUrl = String(vi.mocked(fetch).mock.calls[1]?.[0]);
    expect(listUrl).toContain("page=2");
    expect(listUrl).toContain("page_size=50");
    expect(listUrl).toContain("keyword=alpha");
    expect(listUrl).toContain("sort=follow_name");
    expect(listUrl).toContain("order=asc");
    expect(listUrl).toContain("filters=");
  });

  it("创建、更新与删除行记录使用稳定契约", async () => {
    mockJson({ item: {} });
    await createDatatypeRow("follow", { values: { follow_id: "f1" } });
    await updateDatatypeRow("follow", { id: 3 }, { values: { follow_name: "N" } });
    await deleteDatatypeRow("follow", { id: 3 });

    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0]?.[1]?.body))).toEqual({
      values: { follow_id: "f1" },
    });
    expect(String(vi.mocked(fetch).mock.calls[1]?.[0])).toContain(
      `/rows?pk=${encodeURIComponent(JSON.stringify({ id: 3 }))}`,
    );
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.method).toBe("PUT");
    expect(vi.mocked(fetch).mock.calls[2]?.[1]?.method).toBe("DELETE");
  });
});
