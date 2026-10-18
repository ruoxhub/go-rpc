import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "../../../../next.config";

describe("settings development proxy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("proxies browser settings requests to the configured API target", async () => {
    vi.stubEnv("E2E_API_PROXY_TARGET", "http://127.0.0.1:8081/");

    const rewrites = await nextConfig.rewrites?.();

    expect(rewrites).toContainEqual({
      source: "/api/settings/:path*",
      destination: "http://127.0.0.1:8081/api/settings/:path*",
    });
  });

  it("开发环境默认代理浏览器 crawler 请求到本地后端", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const rewrites = await nextConfig.rewrites?.();

    expect(rewrites).toContainEqual({
      source: "/api/crawler/:path*",
      destination: "http://127.0.0.1:8081/api/crawler/:path*",
    });
  });

  it("生产环境代理全部后端 API 命名空间", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("API_PROXY_TARGET", "http://backend:8081/");

    const rewrites = await nextConfig.rewrites?.();

    expect(rewrites).toEqual(
      ["crawler", "settings", "analysis", "llm"].map((namespace) => ({
        source: `/api/${namespace}/:path*`,
        destination: `http://backend:8081/api/${namespace}/:path*`,
      })),
    );
  });
});
