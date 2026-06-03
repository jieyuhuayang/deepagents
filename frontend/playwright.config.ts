/**
 * Playwright 配置 —— SDD 三层测试的 E2E 层(确定性 fixture 模式)。
 * 详见 docs/sdd/SDD-Guide.md §5 测试模型 ③。
 *
 * webServer 用 `next dev`(免 next build,避开 vendored 副本的预存 TS build 报错);
 * E2E 不打真后端/真 LLM —— 用 page.route 拦截 deployment URL 回放 fixture(见 e2e/)。
 *
 * 本文件是 vendored 副本上的本地新增 patch,已登记 docs/architecture.md §3.1。
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
