# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库总览

Deep Research agent 本地 demo。Monorepo:
- `backend/` — Python,`deepagents` + DashScope OpenAI-compatible LLM,跑在 `langgraph dev` 上(端口 2024)。
- `frontend/` — `langchain-ai/deep-agents-ui` 的 **vendored 副本**(Next.js 16 + React 19,端口 3000),含 4 处本地 patch。

详细架构、决策、踩坑日志:**`docs/architecture.md`** — 改动前先读对应章节,不要从代码反推。

## 常用命令

```bash
# 后端(终端 A)
cd backend && source .venv/bin/activate && langgraph dev    # → :2024

# 前端(终端 B)
cd frontend && yarn dev                                     # → :3000
yarn lint      # eslint .
yarn format    # prettier --write .
yarn build     # next build
```

首次启动 + 浏览器配置见 `README.md`。Node `20`,yarn `1.22.22`。后端无测试套件。

浏览器 Assistant ID 必须填 `research`(`backend/langgraph.json` 的 graph 名)。

## 后端文件入口

| 文件 | 职责 |
|---|---|
| `agent.py` | 装配 LLM / tools / subagents / middleware / HITL 拦截 |
| `tools.py` | `tavily_search` / `think_tool` / `emit_research_card` |
| `prompts.py` | 主 agent + research sub-agent 的 system prompt |
| `middlewares.py` | `GenerativeUIMiddleware`(注入 `ui` state 字段) |
| `langgraph.json` | 暴露 graph `research` 给前端 |

## 强约束(改之前停下来读)

每条都有"详见 architecture.md §N"——动它之前必读对应章节,避免重蹈覆辙。

- **不要删 `GenerativeUIMiddleware`**。`deepagents._DeepAgentState` 没有 `ui` 字段,删了 `push_ui_message` 会被默默丢弃。升级 `deepagents` 时先验证 `_DeepAgentState` 是否补了 `ui`,确认后才能删。详见 §2.2。
- **LLM provider 锁定 `ChatOpenAI` + DashScope base_url**。不要换 `init_chat_model("anthropic:...")` 或 LangChain provider registry——它们没法指向 DashScope。详见 §2.1。
- **不要在 `create_deep_agent` 里传 `checkpointer` / `MemorySaver`**。`langgraph dev` 自动管 checkpointer,传了启动失败。
- **不要把 `streaming=True` 改回 `False`**(`agent.py:24`)。曾有"DashScope tools+stream 互斥"的判断已证伪,现代模型支持。详见 §2.1 历史踩坑提示。
- **前端是 vendored 副本,有 4-6 处本地 patch**。`cd frontend && git pull` 前必须 `git diff > /tmp/patches.diff` 留底再 `git apply` 回去。详见 §3。
- **HITL 批量审批是"全 approve / 全 reject"语义**。`broadcastResumeInterrupt` 把单决策广播到 N 个 action_requests,**无法对单个 action 做不同决策**。要细粒度要重写 `ToolApprovalInterrupt`。详见 §4。
- **`useChat.ts` 的 fetch monkey-patch 不要随手删**。它过滤 `stream_mode: "tools"` 解决 SDK 与 `langgraph-cli[inmem]` 的 422 兼容性。判定可删条件见 §5。
- **`prompts.py` 的强制语序不要弱化**("MUST call `emit_research_card` before `write_file`" 等)。`deepseek-v4-pro` 会跳过卡片渲染直接写文件。详见 §7。

切换模型:`.env` 里 `DEEPAGENTS_MODEL=qwen-max-latest`(或其他 DashScope OpenAI-compatible 模型)。

## 进一步阅读

- `docs/architecture.md` — 三层架构 / 4 处 patch 详情 / HITL 批量审批机制 / stream_mode hack 根因与删除条件 / 升级路径 / 模型行为备忘。**遇到任何"为什么这样设计"、"能不能换 X"、"升级时要注意什么"的问题,先读它。**
- `docs/DeepAgents 前端开源项目调研.md` — 前端技术选型档案(评估"要不要换栈"时读)。
- `README.md` — 给最终用户的快速上手 + 验证步骤(本地跑通 demo)。

## SDD 开发流程(轻量版)

任何非琐碎 feature 走 SDD。完整指南:[`docs/sdd/SDD-Guide.md`](docs/sdd/SDD-Guide.md)。

**6 步流程**:

```
1. Spec Discovery           ──★ 用户确认 ──>
2. 起草 spec.md             ──>
3. /sdd-review <dir> spec   ──★ 用户确认 ──>
4. 起草 tasks.md + verification.md 骨架  ──>
5. /sdd-review <dir> tasks  (自动)       ──>
6. 拉分支 → 前端 patch 留底(如需)→ 实现 → verification.md 全绿 → /code-review → PR → 合并
```

**产物布局**:

- 指南与模板:`docs/sdd/`(`SDD-Guide.md` + `_templates/{spec,tasks,verification}.md`)
- 单 feature 产物:`docs/features/vX.Y.Z/NNN-feature-slug/{spec,tasks,verification}.md` + `screenshots/`
- 审查 skill:`.claude/skills/sdd-review/SKILL.md`,用法 `/sdd-review <feature_dir> {spec|tasks}`

**强约束**:`spec.md §4` 必须填全本文件 §强约束 8 行 checkbox;改动若动 `frontend/**`,Step 6 第一步必须 `cd frontend && git diff > /tmp/patches-NNN.diff` 留底。

**两个 ★ 暂停点不能跳过**(Step 1 后的需求理解确认、Step 3 后的 spec 评审通过确认)。
