# Deep Research Agent — 本地可跑的端到端示例

基于 [`langchain-ai/deepagents`](https://github.com/langchain-ai/deepagents)（Python 后端）+ [`langchain-ai/deep-agents-ui`](https://github.com/langchain-ai/deep-agents-ui)（Next.js 前端）的本地交互式 Deep Research agent。

打开浏览器即可在一个对话里同时看到：实时 todo 列表 / 工具调用流式渲染 / sub-agent 执行流 / HITL 中断审批 / 自定义 generative UI 卡片。

## 架构一图流

```
浏览器  http://localhost:3000  ──┐
                                  │ useStream (LangGraph SDK)
                                  ↓
langgraph dev  http://127.0.0.1:2024
                                  │
                                  ↓
backend/agent.py   create_deep_agent(model=ChatOpenAI(DashScope), tools, subagents, interrupt_on)
```

- **LLM**：DashScope OpenAI-compatible 端点（默认 `deepseek-v4-pro`，可换 `qwen-max-latest` 等）
- **工具**：`duckduckgo_search`（联网搜索，无需 API key）+ `think_tool`（强制反思）+ `emit_research_card`（推 UI 卡片）
- **Sub-agent**：声明式 `research-agent`，主 agent 通过 `task` 工具委派
- **HITL 拦截点**：`write_file` / `edit_file` / `task`
- **Generative UI**：本地 React 组件，零 LangSmith CDN 依赖

## 目录

```
deepagents/
├── backend/         # Python 后端
│   ├── agent.py
│   ├── tools.py
│   ├── prompts.py
│   ├── langgraph.json
│   ├── pyproject.toml
│   └── .env.example
├── frontend/        # deep-agents-ui 的 vendored 副本（git clone 来的）
│   └── src/app/components/generative-ui/   ← 本地新增的 generative UI 组件
└── docs/
```

`frontend/` 内本地修改 4 处（已 apply）：

- `src/app/components/generative-ui/ResearchCard.tsx`（新增）
- `src/app/components/generative-ui/registry.tsx`（新增）
- `src/app/components/ToolCallBox.tsx`（加 `components` prop 透传）
- `src/app/components/ChatMessage.tsx`（注入 `LOCAL_UI_COMPONENTS`）

## 准备 API key

只需要一个 key：

- **DASHSCOPE_API_KEY**：[阿里云百炼控制台](https://bailian.console.aliyun.com/) → API-KEY 管理

联网搜索用 DuckDuckGo，无需 API key（注意：高频访问会限流，适合 demo，不适合压测）。LangSmith key 也 **不需要**（本地 generative UI 走本地 bundle）。

## 启动

### 1. 配 env

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY
```

### 2. 装后端依赖并启动（终端 A）

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
langgraph dev      # → http://127.0.0.1:2024
```

### 3. 装前端依赖并启动（终端 B）

```bash
cd frontend
yarn install
yarn dev           # → http://localhost:3000
```

### 4. 浏览器配置

打开 <http://localhost:3000>，点右上角设置（齿轮）：

- **Deployment URL**：`http://127.0.0.1:2024`
- **Assistant ID**：`research`
- **LangSmith API Key**：留空

保存。

## 验证：一次性触发 5 大能力

把这段贴进对话框：

> 调研 2025-2026 年 AI agent 编排框架现状，对比 LangGraph / AutoGen / CrewAI 三家。每个框架做成一张 research_card 显示。最后写一份 markdown 总结到 `report.md`。

预期：

| # | 能力 | 你会看到 |
|---|---|---|
| 1 | 实时 todo | 右侧 sidebar 出现 ≥4 条任务，随对话推进打勾 |
| 2 | Sub-agent 流 | 主对话出现 3 个 SubAgentIndicator（每框架一个），点可展开 |
| 3 | Tool call 折叠 | `duckduckgo_search` 调用框可点 ▶ 展开看 query 和返回 |
| 4 | HITL 审批 | 委派 sub-agent 前弹审批卡（task 拦截）+ 写 `report.md` 前再弹（write_file 拦截），可 Approve/Reject/Edit |
| 5 | Generative UI | 对话流出现 3 张 ResearchCard，样式来自 `frontend/src/app/components/generative-ui/ResearchCard.tsx` |

## 常见问题

**模型不愿意调 `task` 委派 sub-agent**
→ 在 `backend/prompts.py` 的 `ORCHESTRATOR_PROMPT` 里加更强的指令；或换 `DEEPAGENTS_MODEL=qwen-max-latest`。

**HITL 审批卡不出现**
→ 检查后端 `langgraph dev` 日志是否有 `interrupt` 字样。如果 `task` 拦截有兼容问题，先注释掉 `backend/agent.py` 里 `interrupt_on={"task": True}` 那一行。

**Generative UI 卡片不出现**
→ 模型可能忘了调 `emit_research_card`。看 `tool_calls` 日志确认；在 prompt 里强化"after each subagent completes, you MUST call emit_research_card"。

**前端 :3000 端口冲突**
→ `yarn dev -p 3001`。

**升级 deep-agents-ui**
→ `cd frontend && git pull origin main`，然后手动 re-apply `generative-ui/` 目录 + `ToolCallBox.tsx` + `ChatMessage.tsx` 的改动。建议用 `git diff` 留底。

## 风险与回退

| 风险 | 回退 |
|---|---|
| `deepseek-v4-pro` 拒绝 / 不会 function calling | 切 `DEEPAGENTS_MODEL=qwen-max-latest` |
| DashScope 在 `stream=True` 下意外丢 tool_calls（理论上不会） | `backend/agent.py` 里加 `streaming=False` |
| `interrupt_on={"task": True}` 触发后无法继续 | 注释掉这行；保留 `write_file`/`edit_file` |
| 模型忽略 `emit_research_card` 工具 | 在 `prompts.py` 强化指令；最差直接拒答让模型重试 |

## 深入了解

排错、二次开发、或评估这套技术选型？看 [`docs/architecture.md`](docs/architecture.md)：

- 三层架构总览与端到端请求流程（§1）
- 四个子系统的运行机制与决策——编排 / 状态 / 人在回路 / 渲染（§2,含为什么 OpenAI-compat、为什么 vendored 前端、`GenerativeUIMiddleware` 怎么扩）
- 跨上游适配的硬约束——4 处前端 patch / HITL `broadcastResumeInterrupt` / `stream_mode "tools"` fetch hack（§3）
- 演进路径:每个适配层"何时可拆"的判定条件（§4）

遇到具体的启动报错、环境兼容性问题（SOCKS 代理 / yarn vs npm / checkpointer 限制）或模型行为偏差,看 [`docs/troubleshooting.md`](docs/troubleshooting.md)。
