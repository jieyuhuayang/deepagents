/**
 * Vitest 配置 —— SDD 三层测试的前端 Test-Alongside 层。
 * 详见 docs/sdd/SDD-Guide.md §5 测试模型 ②。
 *
 * 注意:这是 vendored 副本(deep-agents-ui)上的本地新增 patch,
 * 已登记 docs/architecture.md §3.1。上游 git pull 前记得留底。
 */
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
