import { expect, test, type Request } from "@playwright/test";

const touchControlSelector = [
  "button",
  "summary",
  "select",
  "textarea",
  'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])',
  ".touch-target",
].join(", ");

async function expectAccessibleTouchTargets(page: import("@playwright/test").Page) {
  const undersizedTouchTargets = await page
    .locator(touchControlSelector)
    .evaluateAll((elements) =>
      elements
        .filter((element) => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return (
            style.visibility !== "hidden" &&
            style.display !== "none" &&
            rect.width > 0 &&
            rect.height > 0
          );
        })
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          return rect.width < 44 || rect.height < 44;
        })
        .map((element) => {
          const rect = element.getBoundingClientRect();
          return `${Math.round(rect.width * 100) / 100}x${Math.round(rect.height * 100) / 100} ${element.outerHTML}`;
        }),
    );
  expect(undersizedTouchTargets).toEqual([]);
}

function isCancelledNextPrefetch(request: Request) {
  const url = new URL(request.url());
  return (
    request.method() === "GET" &&
    request.resourceType() === "fetch" &&
    request.failure()?.errorText === "net::ERR_ABORTED" &&
    url.origin === "http://127.0.0.1:3001" &&
    url.searchParams.has("_rsc")
  );
}

test("完成采集管理主流程", async ({ page }) => {
  await page.goto("/crawler/platforms");
  await page.getByRole("link", { name: "新建平台" }).click();
  await page.getByLabel("平台名称").fill("E2E TikTok");
  await page.getByLabel("平台代码").fill("e2e_tiktok");
  await page.getByRole("button", { name: "创建平台" }).click();
  await expect(page.getByRole("cell", { name: "E2E TikTok" })).toBeVisible();

  await page.getByRole("link", { name: "接口" }).click();
  await page.getByRole("button", { name: "导入接口" }).click();
  await page.getByLabel("JSON 文件").setInputFiles({
    name: "actions.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify([{ name: "SearchVideo", params: [] }])),
  });
  await page.getByRole("button", { name: "确认导入" }).click();
  await expect(page.getByText("新增 1 个，更新 0 个")).toBeVisible();
  await page.getByRole("button", { name: "取消" }).click();

  await page.getByRole("link", { name: "关键词" }).click();
  await page.getByRole("link", { name: "新建关键词" }).click();
  await page.getByRole("textbox", { name: "关键词", exact: true }).fill("playwright-e2e");
  await page.getByRole("button", { name: "创建关键词" }).click();
  await expect(page.getByRole("cell", { name: "playwright-e2e" })).toBeVisible();

  await page.getByRole("link", { name: "任务" }).click();
  await page.getByRole("link", { name: "新建任务" }).click();
  await page.getByLabel("接口").selectOption({ label: "SearchVideo" });
  await page.getByRole("radio", { name: "Cron" }).check();
  await page.getByLabel("Cron 表达式").fill("0 2 * * *");
  const schedulePreview = page.getByText("未来执行时间（Asia/Shanghai）").locator("..");
  await expect(schedulePreview).toBeVisible();
  await expect(schedulePreview.locator("li")).toHaveCount(5);
  await page.getByRole("button", { name: "创建任务" }).click();
  await page.getByRole("button", { name: "立即执行" }).click();
  await expect(page.getByText("任务已加入队首")).toBeVisible();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await expect(page.getByText("任务已暂停")).toBeVisible();
  await page.getByRole("button", { name: "恢复", exact: true }).click();
  await expect(page.getByText("任务已恢复")).toBeVisible();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await expect(page.getByText("任务已暂停")).toBeVisible();
});

test("移动导航可访问关键页面且无阻断错误", async ({ page }) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    if (isCancelledNextPrefetch(request)) return;
    failures.push(
      `requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText ?? "unknown"}`,
    );
  });
  page.on("response", (response) => {
    if (
      response.url().includes("/api/crawler") &&
      response.status() >= 400
    ) {
      failures.push(`response: ${response.status()} ${response.url()}`);
    }
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      failures.push(`console: ${message.text()}`);
    }
  });

  await page.goto("/analysis");
  await page.getByText("菜单", { exact: true }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await expectAccessibleTouchTargets(page);

  for (const [link, heading, caption] of [
    ["平台", "平台管理", "平台列表"],
    ["接口", "接口管理", "接口列表"],
    ["关键词", "关键词管理", "关键词列表"],
    ["任务", "任务管理", "任务列表"],
  ] as const) {
    await page.goto("/crawler/platforms");
    await page.waitForLoadState("networkidle");
    await page.getByText("菜单", { exact: true }).click();
    await page.getByRole("link", { name: link, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.getByRole("table", { name: caption })).toBeVisible();
    await expect(
      page.locator('[role="alert"]:not(#__next-route-announcer__)').filter({ hasText: /\S/ }),
    ).toHaveCount(0);
    await expectAccessibleTouchTargets(page);
  }

  await page.goto("/crawler/platforms/new");
  await expect(page.getByLabel("平台名称")).toBeVisible();
  await expect(page.getByLabel("并发数")).toBeVisible();
  await expectAccessibleTouchTargets(page);

  await page.goto("/crawler/actions/new");
  const enabledCheckbox = page.getByRole("checkbox", { name: "启用接口" });
  const checkboxBox = await enabledCheckbox.boundingBox();
  const checkboxLabelBox = await enabledCheckbox.locator("xpath=..").boundingBox();
  expect(checkboxBox?.width).toBeLessThan(44);
  expect(checkboxBox?.height).toBeLessThan(44);
  expect(checkboxLabelBox?.width).toBeGreaterThanOrEqual(44);
  expect(checkboxLabelBox?.height).toBeGreaterThanOrEqual(44);
  await expectAccessibleTouchTargets(page);

  await page.goto("/crawler/keywords?platform=unknown-code");
  await expect(page.getByRole("cell", { name: "暂无关键词" })).toBeVisible();
  await expect(
    page.locator('[role="alert"]').filter({ hasText: /\S/ }),
  ).toHaveCount(0);
  await expectAccessibleTouchTargets(page);

  expect(failures).toEqual([]);
});
