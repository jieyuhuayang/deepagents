/**
 * E2E 种子(确定性 fixture 模式)—— 演示 SDD 测试模型 ③。
 *
 * 不打真后端/真 LLM:page.route 拦截 deployment URL(http://localhost:2024)
 * 的所有 API,fulfill 录制好的 canned 响应 + SSE 流(见 fixtures/research-card.ts)。
 * 前端真实运行(next dev)。
 *
 * 真实 feature 照此 pattern 写:pre-seed localStorage 跳过配置 → 拦截端点 →
 * 断言 UI 交互。fixture 用 `npm run e2e:record` 对真后端录制后落盘。
 */
import { test, expect, type Page } from "@playwright/test";
import {
  ASSISTANT,
  THREAD,
  EMPTY_STATE,
  CARD,
  researchCardStream,
} from "./fixtures/research-card";

const DEPLOYMENT = "http://localhost:2024";

// 把 deployment URL 指到一个本测试拦截的地址,跳过配置弹窗直接进聊天界面。
async function seedConfig(page: Page) {
  await page.addInitScript((url) => {
    localStorage.setItem(
      "deep-agent-config",
      JSON.stringify({ deploymentUrl: url, assistantId: "research", langsmithApiKey: "" }),
    );
  }, DEPLOYMENT);
}

// 拦截 deployment URL 的所有 API,按 pathname 回放 fixture。
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

    // CORS preflight
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
    if (pathname === "/assistants/search") return json([ASSISTANT]);
    if (pathname.startsWith("/assistants/")) return json(ASSISTANT);
    if (pathname === "/threads/search") return json([]);
    if (pathname === "/threads" && req.method() === "POST") return json(THREAD);
    if (pathname.endsWith("/history")) return json([]);
    if (pathname.endsWith("/state")) return json(EMPTY_STATE);
    if (pathname.endsWith("/cancel")) return json({});

    // SSE:POST .../runs/stream(新建)或 GET 重连
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

test("boots into chat shell under fixture mode (no config dialog)", async ({ page }) => {
  await page.goto("/");
  // 配置已 pre-seed,应直接进聊天界面:输入框可见
  await expect(page.getByPlaceholder("输入你的消息...")).toBeVisible();
});

test("renders ResearchCard from a replayed SSE stream", async ({ page }) => {
  await page.goto("/");
  const input = page.getByPlaceholder("输入你的消息...");
  await expect(input).toBeVisible();

  await input.fill("调研一下 Topic");
  await input.press("Enter");

  // SSE 回放里 push 了一张 research_card,断言其内容渲染
  await expect(page.getByText(CARD.title)).toBeVisible();
  await expect(page.getByText(CARD.summary)).toBeVisible();
});
