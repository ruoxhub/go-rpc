import type { NextConfig } from "next";

const apiNamespaces = ["crawler", "settings", "analysis", "llm"];

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const target =
      process.env.API_PROXY_TARGET ??
      process.env.E2E_API_PROXY_TARGET ??
      process.env.CRAWLER_API_BASE_URL?.replace(/\/api\/crawler\/?$/, "") ??
      "http://127.0.0.1:8081";
    const baseUrl = target.replace(/\/$/, "");
    return apiNamespaces.map((namespace) => ({
      source: `/api/${namespace}/:path*`,
      destination: `${baseUrl}/api/${namespace}/:path*`,
    }));
  },
};

export default nextConfig;
