---
name: e2e-test
description: 为 deepagents feature 生成并运行 Playwright E2E 测试(确定性 fixture 模式)。读 spec.md 的 UI 交互类 AC,按既有 page.route 拦截 + SSE 回放 pattern 写 e2e/*.spec.ts,跑通,最多 3 轮修复。用于 SDD 6 步流程的 Step 6.5。
---

# /e2e-test

为一个 feature 生成 + 运行 E2E,覆盖 spec.md 中的 **UI 交互流程类 AC**。
机制与 pattern 见 [`docs/sdd/SDD-Guide.md §5 ③`](../../../docs/sdd/SDD-Guide.md) 与种子 [`frontend/e2e/research-card.spec.ts`](../../../frontend/e2e/research-card.spec.ts)。

---

## 调用方式

```
/e2e-test <feature_dir>
```

`<feature_dir>` 例如:`docs/features/v0.6.0/001-some-feature`。
失败校验:路径或 `spec.md` 不存在 → 报错停止。

---

## 流程

1. **读 AC**:从 `<feature_dir>/spec.md §2` 取所有 UI 交互类 AC(验证方式标 `e2e::` 的)。无此类 AC → 报告"本 feature 无 UI 交互 AC,E2E 跳过;请确认纯后端改动已有 pytest 覆盖 + 跑一遍既有 e2e 确认无回归",结束。
2. **复用 pattern**:照 `frontend/e2e/research-card.spec.ts` 的结构写新 `frontend/e2e/<flow>.spec.ts`:
   - `seedConfig`:`addInitScript` 写 localStorage key `deep-agent-config` = `{deploymentUrl, assistantId:"research", langsmithApiKey:""}`,跳过配置弹窗。
   - `mockBackend`:`page.route(`${DEPLOYMENT}/**`)` 按 pathname 回放 fixture;mount 端点(`/assistants/search`、`/threads/search`、`/threads`、`/ok`、`/info`、`*/state`、`*/history`)给 canned JSON;`*/runs/stream` 给 `text/event-stream` 的 SSE 字节流。
   - 断言 spec AC 描述的可见结果(卡片文本、审批按钮、下载触发等)。
3. **fixture**(`frontend/e2e/fixtures/<flow>.ts`,导出构造 SSE body 的函数 + canned 端点 JSON,见种子):
   - **录制法**(真后端可用时,最忠实):本地起 `uvicorn server:app`,对真后端跑一次目标流程,从浏览器 DevTools Network 的 `/runs/stream` 响应或 `curl -N` 抓下 SSE 字节,整理进 fixture。`npm run e2e:record`(置 `PLAYWRIGHT_RECORD=1`)是留给"自带录制分支的 spec"的约定入口,**默认 spec 不自动录制**,捕获是上面这步手动动作。
   - **手写法**(真后端不可用时):照种子手写最小忠实 SSE —— 形状必须对齐 `backend/server.py _sse_event`(`event: <type>\r\ndata: <json>\r\n\r\n`)与目标组件 props(generative-ui 卡片走 `push_ui_message` → state.ui[] 的 UIMessage `{type:"ui", name, metadata.tool_call_id, props}`)。
4. **跑**:`cd frontend && npx playwright test e2e/<flow>.spec.ts`。
5. **修复循环**:失败 → 看 trace / 报错改 spec 或 fixture 或选择器 → 重跑,**最多 3 轮**。3 轮仍红 → 停下,报告卡点(常见:ui 形状不对、选择器漂移、SDK 请求序列多一个未 mock 的端点),请人介入。

---

## 确定性 / 数据隔离红线

- **默认不打真 LLM**:fixture 回放保证稳定可重复;连跑 3 次结果须一致。
- **真·LLM 全栈 smoke**(可选、慢):仅在需要端到端贯通验证时,不拦截、直连 `uvicorn` + DashScope。此时必守隔离:
  - thread id 用前缀 `e2e-<feature>-`;
  - cleanup **只删该前缀** 的 thread,**绝不 wipe checkpointer 库**;
  - setup 清上次残留 + 末尾清本次,非测试数据前后完好。

---

## 与既有基建的耦合

- Playwright 配置:[`frontend/playwright.config.ts`](../../../frontend/playwright.config.ts)(`next dev` 起 webServer,免 build)。
- 种子 + fixture pattern:[`frontend/e2e/`](../../../frontend/e2e/)。
- 新增 e2e 依赖/浏览器属 vendored 副本本地 patch,改 `package.json` 记得同步 architecture.md §3.1。
