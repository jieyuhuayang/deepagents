# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库总览

Deep Research agent 本地 demo。Monorepo:
- `backend/` — Python,`deepagents` + DashScope OpenAI-compatible LLM,通过 `backend/server.py` 启动 uvicorn(端口 2024 本地 / 12024 lab host),显式 `AsyncPostgresSaver` / `AsyncSqliteSaver` 持久化(由 `DATABASE_URL` env 选择)。本地 quick smoke 仍可用 `langgraph dev`。
- `frontend/` — `langchain-ai/deep-agents-ui` 的 **vendored 副本**(Next.js 16 + React 19,端口 3000),含 4-6 处本地 patch。

详细架构、决策、跨上游适配:**`docs/architecture.md`** — 改动前先读对应章节,不要从代码反推。运行期具体故障与模型行为偏差:**`docs/troubleshooting.md`**。

## 常用命令

```bash
# 后端(终端 A) — 自研 FastAPI server,DATABASE_URL 缺省 SQLite (backend/local.db)
cd backend && source .venv/bin/activate && uvicorn server:app --port 2024 --reload    # → :2024
# 本地 quick smoke(无持久化)也可用 langgraph dev(graph 通过 module-level `agent` fallback 加载)

# 前端(终端 B)
cd frontend && npm run dev                                  # → :3000(本项目 vendored 副本用 npm,见下)
npm run lint      # eslint .
npm run format    # prettier --write .
npm run build     # next build

# SDD 三层自动化测试(详见 docs/sdd/SDD-Guide.md §5)
cd backend && source .venv/bin/activate && pip install -e ".[test]" && pytest   # ① 后端 Test-First
cd frontend && npm test                                                          # ② 组件 Test-Alongside (vitest)
cd frontend && npm run e2e                                                        # ③ E2E (Playwright, fixture 模式)
```

首次启动 + 浏览器配置见 `README.md`。Node `20`。**前端包管理用 `npm`(非 yarn)** —— yarn 1.22 在本机 SOCKS 代理下装包失败,工程实际由 `package-lock.json` 管理,装依赖用 `npm install --legacy-peer-deps`(vendored 副本有 eslint peer 冲突)。

浏览器 Assistant ID 必须填 `research`(`backend/langgraph.json` 的 graph 名)。

## 后端文件入口

| 文件 | 职责 |
|---|---|
| `agent.py` | `build_agent(checkpointer)` factory:装配 LLM / tools / subagents / middleware |
| `server.py` | 自研 FastAPI server(LangGraph SDK 协议子集 + SSE);lifespan 按 `DATABASE_URL` 实例化 saver 注入 agent |
| `tools.py` | `web_search`(按 `SEARCH_PROVIDER` 路由)/ `bisheng_retrieve` / `think_tool` / `emit_research_card` / `request_clarification` / `export_docx` |
| `web_search.py` | 可配置搜索 provider 层(DDG / Tavily / CloudSway),`tools.py` 的 `web_search` 内部按 env 选 provider |
| `prompts.py` | 主 agent + research sub-agent 的 system prompt |
| `middlewares.py` | `GenerativeUIMiddleware`(注入 `ui` state 字段) |
| `langgraph.json` | 暴露 graph `research`(langgraph dev quick smoke 用) |

## 强约束(改之前停下来读)

每条都有"详见 architecture.md §N"——动它之前必读对应章节,避免重蹈覆辙。

- **不要删 `GenerativeUIMiddleware`**。`deepagents._DeepAgentState` 没有 `ui` 字段,删了 `push_ui_message` 会被默默丢弃。升级 `deepagents` 时先验证 `_DeepAgentState` 是否补了 `ui`,确认后才能删。详见 §2.2。
- **LLM provider 锁定 `ChatOpenAI` + DashScope base_url**。不要换 `init_chat_model("anthropic:...")` 或 LangChain provider registry——它们没法指向 DashScope。详见 §2.1。
- **不要传 `checkpointer` / `MemorySaver` 给 `create_deep_agent` —— 但具体取决于启动模式**:
  - **CLI 模式**(`langgraph dev`,本项目自 v0.5.0 起不再默认使用,保留作为本地 quick smoke 工具):框架自动管 inmem checkpointer,传了启动失败。
  - **自研 server 模式**(`backend/server.py` + `uvicorn`,本项目默认):**必须显式传** `checkpointer=AsyncPostgresSaver(...) / AsyncSqliteSaver(...)`,由 server lifespan 根据 `DATABASE_URL` env 实例化注入。详见 `docs/architecture.md §2.2` + `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`。
- **不要把 `streaming=True` 改回 `False`**(`agent.py` 的 `model = ChatOpenAI(...)`)。曾有"DashScope tools+stream 互斥"的判断已证伪,现代模型支持。详见 §2.1 历史踩坑提示。
- **前端是 vendored 副本,有 4-6 处本地 patch**。`cd frontend && git pull` 前必须 `git diff > /tmp/patches.diff` 留底再 `git apply` 回去。详见 §3.1。
- **HITL 批量审批是"全 approve / 全 reject"语义**。`broadcastResumeInterrupt` 把单决策广播到 N 个 action_requests,**无法对单个 action 做不同决策**。要细粒度要重写 `ToolApprovalInterrupt`。语义说明见 §2.3,实现细节见 §3.2。
- **`useChat.ts` 的 fetch monkey-patch 不要随手删**。它过滤 `stream_mode: "tools"` 解决 SDK 与 `langgraph-cli[inmem]` 的 422 兼容性。判定可删条件见 §3.3。
- **`prompts.py` 的强制语序不要弱化**("MUST call `emit_research_card` before `write_file`" 等)。`deepseek-v4-pro` 会跳过卡片渲染直接写文件。详见 `docs/troubleshooting.md` 第 2 节"模型行为"。

切换模型:`.env` 里 `DEEPAGENTS_MODEL=qwen-max-latest`(或其他 DashScope OpenAI-compatible 模型)。

## L0 arch-guard(自动)

`.claude/settings.json` 配了 `PostToolUse` hook,每次 Write/Edit 后跑 `scripts/arch-guard.sh`,对上面 8 条强约束中**可机检的 5 条**(GenerativeUIMiddleware / ChatOpenAI+DashScope / streaming=True / MemorySaver / useChat monkey-patch + prompts 语序)做 grep 守护:无违规静默,命中把 ⚠️ 打到 stderr 提醒(非阻断)。同组不变量镜像在 `backend/tests/test_arch_invariants.py`(pre-PR / CI 执行点)。改强约束时,**CLAUDE.md / spec 模板 §4 / arch-guard.sh / test_arch_invariants.py 四处同步**。

## SDD 开发流程

任何非琐碎 feature 走 SDD。完整指南:[`docs/sdd/SDD-Guide.md`](docs/sdd/SDD-Guide.md)。蓝本是 OpenOntology 完整版方法论,适配为 **2 件套 + 三层自动化测试 + 采访模式**。

**6 步流程**:

```
1. Spec Discovery(采访模式:一轮批量提问)        ──★ 选项式确认 ──>
2. 起草 spec.md                                    ──>
3. /sdd-review <dir> spec                           ──★ 选项式确认 ──>
4. 起草 tasks.md(Test-First 配对 + Test-Alongside + E2E 任务)──>
5. /sdd-review <dir> tasks(自动)                   ──>
6. 拉分支/worktree → 前端 patch 留底(如需) → 实现 → 6.5 强制 E2E → 三层测试全绿 → /code-review → PR → 合并
```

**强约束**:
- 产物:`docs/features/vX.Y.Z/NNN-slug/{spec,tasks}.md`(**2 件套,无独立 verification.md**;AC 由三层测试追溯)。
- **三层测试**(详见 SDD-Guide §5):① 后端 `pytest`(Test-First,`backend/tests/`)② 前端组件 `vitest`(Test-Alongside,`*.test.tsx`)③ E2E `playwright`(强制,`frontend/e2e/`,确定性 fixture 模式 —— `page.route` 拦截 `/runs/stream` 回放录制 SSE,不打真 LLM)。
- spec.md §4 必须填全本文件 §强约束 8 行 checkbox;改动若动 `frontend/**`,Step 6 第一步 `cd frontend && git diff > /tmp/patches-NNN.diff` 留底。
- 并发 ≥2 feature 或单任务长跑 >10min 用 `git worktree`(SDD-Guide §7;各 worktree 改 `DATABASE_URL` + 端口避冲突)。
- **两个 ★ 暂停点不能跳过**(Step 1 采访后确认、Step 3 spec 评审后确认),但都用 AskUserQuestion 选项式轻量确认。
- 审查 skill:[`/sdd-review`](.claude/skills/sdd-review/SKILL.md)(spec/tasks)、[`/e2e-test`](.claude/skills/e2e-test/SKILL.md)(生成跑 E2E)。

## 进一步阅读

- `docs/sdd/SDD-Guide.md` — SDD 开发流程完整指南(何时走 / 6 步 / 采访模式 / 三层测试 / arch-guard / worktree)。开新 feature 前读。

- `docs/architecture.md` — 三层架构总览(§1)/ 四个子系统的运行机制与决策(§2 编排/状态/人在回路/渲染)/ 跨上游适配的硬约束(§3 前端 patch / HITL broadcast / stream_mode hack)/ 演进路径(§4)。**遇到任何"为什么这样设计"、"能不能换 X"、"上游升级时能不能拆掉这层适配"的问题,先读它。**
- `docs/troubleshooting.md` — 启动报错 / 环境兼容性 / 模型行为偏差等运行期问题清单。遇到具体现象(报错、空返回、卡片不显示)先查这里。
- `docs/DeepAgents 前端开源项目调研.md` — 前端技术选型档案(评估"要不要换栈"时读)。
- `README.md` — 给最终用户的快速上手 + 验证步骤(本地跑通 demo)。
