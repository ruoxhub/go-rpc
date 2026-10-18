import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      grep: /主流程/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chromium",
      grep: /移动导航/,
      use: { ...devices["Pixel 5"] },
    },
  ],
  webServer: [
    {
      command: "..\\backend\\.venv\\Scripts\\python.exe -m uvicorn tests.e2e_app:app --app-dir ../backend --host 127.0.0.1 --port 8001",
      url: "http://127.0.0.1:8001/openapi.json",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        CRAWLER_E2E_DB: "../frontend/.e2e/crawler.sqlite3",
      },
    },
    {
      command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3001",
      url: "http://127.0.0.1:3001/crawler/platforms",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        CRAWLER_API_BASE_URL: "http://127.0.0.1:8001/api/crawler",
        E2E_API_PROXY_TARGET: "http://127.0.0.1:8001",
      },
    },
  ],
});
