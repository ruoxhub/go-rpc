import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CrawlerApiError,
  crawlerRequest,
  getCrawlerApiBaseUrl,
  updateTaskPriority,
} from "./crawler-api";
import { isTaskPriority } from "./crawler-types";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("getCrawlerApiBaseUrl", () => {
  it("浏览器使用同源 API 路径", () => {
    vi.stubGlobal("window", {});
    expect(getCrawlerApiBaseUrl()).toBe("/api/crawler");
  });

  it("服务端使用环境变量并移除末尾斜杠", () => {
    vi.stubEnv(
      "CRAWLER_API_BASE_URL",
      "https://crawler.example.com/api/crawler/",
    );
    expect(getCrawlerApiBaseUrl()).toBe("https://crawler.example.com/api/crawler");
  });
});

describe("crawlerRequest", () => {
  it("更新任务优先级使用 PATCH 契约", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ task_id: 7, priority: "high" })),
    );

    await updateTaskPriority(7, "high");

    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8081/api/crawler/tasks/7/priority",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ priority: "high" }),
      }),
    );
  });

  it("优先级守卫拒绝非法值", () => {
    expect(isTaskPriority("critical")).toBe(false);
  });

  it("公共请求器避免基址尾斜杠产生双斜杠", async () => {
    vi.stubEnv(
      "CRAWLER_API_BASE_URL",
      "https://crawler.example.com/api/crawler///",
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ ok: true })),
    );

    await crawlerRequest("/platforms");

    expect(fetch).toHaveBeenCalledWith(
      "https://crawler.example.com/api/crawler/platforms",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("浏览器请求保持原有 crawler 路径", async () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ ok: true })),
    );

    await crawlerRequest("/platforms");

    expect(fetch).toHaveBeenCalledWith(
      "/api/crawler/platforms",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("解码 JSON 响应", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: 7 }), {
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(crawlerRequest<{ id: number }>("/platforms/7")).resolves.toEqual({
      id: 7,
    });
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8081/api/crawler/platforms/7",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("将 204 空成功响应解码为 undefined", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    await expect(
      crawlerRequest<void>("/platforms/7", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });

  it("拒绝 200 空响应", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 200 })),
    );

    await expect(crawlerRequest("/platforms")).rejects.toMatchObject({
      kind: "invalid-response",
      status: 200,
    });
  });

  it("非 JSON 响应携带状态码与响应片段", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html><title>404: Not Found</title></html>", {
          status: 404,
          headers: { "content-type": "text/html" },
        }),
      ),
    );

    await expect(crawlerRequest("/platforms")).rejects.toMatchObject({
      kind: "invalid-response",
      status: 404,
      message: "采集服务返回了无法识别的响应（404）",
      responseSnippet: "<html><title>404: Not Found</title></html>",
    });
  });

  it("响应片段超长时截断", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(`<html>${"x".repeat(400)}</html>`, {
          status: 502,
          headers: { "content-type": "text/html" },
        }),
      ),
    );

    const error = await crawlerRequest("/platforms").catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(CrawlerApiError);
    expect(error).toMatchObject({ status: 502 });
    expect((error as CrawlerApiError).responseSnippet).toHaveLength(201);
    expect((error as CrawlerApiError).responseSnippet).toBe(
      `<html>${"x".repeat(194)}…`,
    );
  });

  it("无效 JSON 携带状态码与原始片段", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>gateway</html>", {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(crawlerRequest("/platforms")).rejects.toMatchObject({
      kind: "invalid-response",
      status: 200,
      message: "采集服务返回了无效 JSON（200）",
      responseSnippet: "<html>gateway</html>",
    });
  });

  it("将网络错误包装为稳定错误类型", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(crawlerRequest("/platforms")).rejects.toMatchObject({
      name: "CrawlerApiError",
      kind: "network",
      status: null,
    });
  });

  it("拒绝非 JSON 响应", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>error</html>", {
          headers: { "content-type": "text/html" },
        }),
      ),
    );

    await expect(crawlerRequest("/platforms")).rejects.toMatchObject({
      kind: "invalid-response",
      status: 200,
    });
  });

  it("保留错误状态和后端消息", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({ detail: "平台不存在" }, { status: 404 }),
      ),
    );

    await expect(crawlerRequest("/platforms/99")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      message: "平台不存在",
    });
  });

  it("保留 Parser 稳定错误码、白名单详情与 Retry-After", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            code: "sample_rate_limited",
            message: "采样过于频繁",
            details: {
              sample_id: 3,
              retry_after_seconds: 2.8,
              raw_object_key: "private/raw.json",
            },
          },
          { status: 429, headers: { "Retry-After": "4" } },
        ),
      ),
    );

    await expect(crawlerRequest("/actions/7/parser-samples")).rejects.toMatchObject({
      kind: "http",
      status: 429,
      code: "sample_rate_limited",
      details: { sample_id: 3, retry_after_seconds: 2.8 },
      retryAfter: 4,
      message: "采样过于频繁",
    });
  });

  it.each([
    [undefined, 2.2, 3],
    ["invalid", 0.2, 1],
  ])("Retry-After 为 %s 时回退到 details", async (header, seconds, expected) => {
    const headers = header === undefined ? undefined : { "Retry-After": header };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            code: "sample_rate_limited",
            message: "rate limited",
            details: { retry_after_seconds: seconds },
          },
          { status: 429, headers },
        ),
      ),
    );

    await expect(crawlerRequest("/actions/7/parser-samples")).rejects.toMatchObject({
      retryAfter: expected,
    });
  });

  it.each([
    ["null", null],
    ["数组", []],
    ["异常 detail", { detail: { message: "bad" } }],
    [
      "异常校验路径",
      { detail: [{ loc: null, msg: "Invalid", type: "value_error" }] },
    ],
  ])("将%s错误体稳定映射为 HTTP 错误", async (_label, body) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(body, { status: 422 })),
    );

    await expect(crawlerRequest("/platforms")).rejects.toMatchObject({
      name: "CrawlerApiError",
      kind: "http",
      status: 422,
      message: "采集服务请求失败（422）",
    });
  });

  it("将 422 校验详情映射为字段错误", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            detail: [
              { loc: ["body", "ba_name"], msg: "Field required", type: "missing" },
              { loc: ["body", "config", "url"], msg: "Invalid URL", type: "value_error" },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    try {
      await crawlerRequest("/platforms", { method: "POST" });
      throw new Error("预期请求失败");
    } catch (error) {
      expect(error).toBeInstanceOf(CrawlerApiError);
      expect(error).toMatchObject({
        kind: "validation",
        status: 422,
        fieldErrors: {
          ba_name: "Field required",
          "config.url": "Invalid URL",
        },
      });
    }
  });
});
