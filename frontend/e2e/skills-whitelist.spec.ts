/**
 * AC-5 — Skills 白名单端到端流程(确定性 fixture 模式)。
 *
 * 打开 Skills popover → 勾选 deep-research → 发送消息 → 拦截 POST /runs/stream,
 * 断言请求体 config.configurable.active_skills 含 "deep-research"。
 *
 * 不打真后端/真 LLM:page.route 拦截 deployment URL 的所有 API,额外桩化
 * GET /api/skills(见 fixtures/skills-whitelist.ts),SSE 复用 researchCardStream。
 */
import { test, expect, type Page, type Request } from "@playwright/test";
import {
  ASSISTANT,
  THREAD,
  EMPTY_STATE,
  SKILLS,
  researchCardStream,
} from "./fixtures/skills-whitelist";

const DEPLOYMENT = "http://localhost:2024";

async function seedConfig(page: Page) {
  await page.addInitScript((url) => {
    localStorage.setItem(
      "deep-agent-config",
      JSON.stringify({ deploymentUrl: url, assistantId: "research", langsmithApiKey: "" }),
    );
  }, DEPLOYMENT);
}

async function mockBackend(page: Page) {
  await page.route(`${DEPLOYMENT}/**`, async (route) => {
    const req = route.request();
    const { pathname } = new URL(req.url());
    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify(body),
      });

    if (req.method() === "OPTIONS") {
      return route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "*",
          "access-control-allow-headers": "*",
        },
      });
    }

    if (pathname === "/ok") return json({ ok: true });
    if (pathname === "/info") return json({});
    if (pathname === "/api/skills") return json(SKILLS);
    if (pathname === "/assistants/search") return json([ASSISTANT]);
    if (pathname.startsWith("/assistants/")) return json(ASSISTANT);
    if (pathname === "/threads/search") return json([]);
    if (pathname === "/threads" && req.method() === "POST") return json(THREAD);
    if (pathname.endsWith("/history")) return json([]);
    if (pathname.endsWith("/state")) return json(EMPTY_STATE);
    if (pathname.endsWith("/cancel")) return json({});

    if (pathname.endsWith("/runs/stream") || /\/runs\/[^/]+\/stream$/.test(pathname)) {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "access-control-allow-origin": "*", "cache-control": "no-cache" },
        body: researchCardStream(),
      });
    }

    return json({});
  });
}

test.beforeEach(async ({ page }) => {
  await seedConfig(page);
  await mockBackend(page);
});

test("勾选 skill 后提交,run 请求体携带 active_skills 白名单", async ({ page }) => {
  await page.goto("/");
  const input = page.getByPlaceholder("输入你的消息...");
  await expect(input).toBeVisible();

  // 打开 Skills popover
  await page.getByRole("button", { name: "Skills" }).click();

  // 勾选 deep-research
  const sw = page.getByRole("switch", { name: "toggle deep-research" });
  await expect(sw).toBeVisible();
  await sw.click();
  await expect(sw).toHaveAttribute("aria-checked", "true");

  // 关掉 popover(点输入框),发送消息;捕获 /runs/stream 的提交体
  const submitReq = page.waitForRequest((r: Request) => {
    if (!r.url().includes("/runs/stream") || r.method() !== "POST") return false;
    return true;
  });

  await input.click();
  await input.fill("调研一下 Topic");
  await input.press("Enter");

  const req = await submitReq;
  const body = JSON.parse(req.postData() || "{}");
  const active = body?.config?.configurable?.active_skills;
  expect(Array.isArray(active)).toBe(true);
  expect(active).toContain("deep-research");
});
