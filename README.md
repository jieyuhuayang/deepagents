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
- **工具**：`web_search`（联网搜索，provider 走 `SEARCH_PROVIDER` env，默认 duckduckgo，可选 tavily）+ `think_tool`（强制反思）+ `emit_research_card`（推 UI 卡片）
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

### 5. lab host 部署(`langgraph up`,Postgres 持久化)

> **仅 lab host (例如 192.168.106.114) 用。本地 Macbook 仍走 `langgraph dev` (上面 §2),不要在本地起 `langgraph up`,会拉镜像 + 占资源。** 详见 `docs/features/v0.5.0/001-langgraph-up-deployment/spec.md`。

**为什么不在 lab host 上继续用 `langgraph dev`?** `langgraph dev` 用 in-memory checkpointer,进程重启就丢全部 thread state——多人共享 / 服务可能被重启的场景下不可接受。`langgraph up` 用 docker compose 起 langgraph-api + Postgres + Redis 三个 container,Postgres 持久化 thread state,重启后状态完整保留。背景见 `docs/troubleshooting.md §1.5`。

#### 5.1 前置

- lab host 上已装 Docker (≥ 24) + Docker Compose v2
- lab host 能拉 `langchain/langgraph-api` / `postgres` / `redis` 镜像(国内网络可能要先配 registry mirror)
- 已有的 lab host 部署用 `./deepagents.sh start` 跑 `langgraph dev :12024`;切到 `langgraph up` 前必须先 `./deepagents.sh stop` 释放端口

#### 5.2 启动

```bash
ssh root@192.168.106.114
cd /root/deepagents

# 1. 停掉旧的 langgraph dev + next-server(deepagents.sh 不动,仅适用于 dev 模式)
./deepagents.sh stop

# 2. 切到 backend 目录,启动 langgraph up
cd backend
langgraph up                       # 默认 :8123;首次拉镜像可能慢
# 或者 override 端口(端口冲突时):
# langgraph up --port 8123         # 端口可改

# 3. 起前端(prod build,见 memory feedback-next-prod-for-lan-deploy)
cd ../frontend
npm run build                      # 改完代码必跑
NEXT_PUBLIC_LANGGRAPH_API_URL=http://192.168.106.114:8123 \
NEXT_PUBLIC_ASSISTANT_ID=research \
  npm run start -- -H 0.0.0.0 -p 13000
```

#### 5.3 健康检查

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'   # 应看到 langgraph-api / langgraph-postgres-* / langgraph-redis-* 全部 (healthy)
curl http://192.168.106.114:8123/ok                  # 应返回 {"ok":true}
```

#### 5.4 端口配置(冲突时 override)

lab host 上已有 redis (host 装的,`:6379`)。`langgraph up` 自带 redis 默认也是 `:6379`,**冲突,必须 override**。在 `backend/.env` 里:

```
REDIS_PORT=6380       # 自带 Redis 改用 6380(默认 6379 与 host 上已有 redis 冲突)
POSTGRES_PORT=5433    # 自带 Postgres 改用 5433(如 host 已有 Postgres 在 5432)
LANGGRAPH_PORT=8123   # 默认 8123,与 host 上其他服务都不冲突
```

实际可用占位见 `backend/.env.example` 末尾段。

#### 5.5 数据持久化

`langgraph up` 默认用 docker volume 存 Postgres 数据,`docker compose down` **不**清数据,**只有** `docker compose down -v` 才清。重启 backend 用 `docker restart langgraph-api`,不会丢 thread。

#### 5.6 与本地 `langgraph dev` 的差异

| 项 | 本地 (`langgraph dev`) | lab host (`langgraph up`) |
|---|---|---|
| Checkpointer | in-memory | Postgres (docker volume 持久化) |
| 后端端口 | `:2024` | `:8123` |
| 启动方式 | `langgraph dev` 命令直接跑 | docker compose 起 3 个 container |
| 进程重启影响 | thread state 全丢 | thread state 保留 |
| 适用 | 本机开发、单人 demo | 多人共享、可被重启的环境 |

详细对比 + 决策见 `docs/architecture.md §1` 末尾"双轨部署模型"表 + `docs/features/v0.5.0/001-langgraph-up-deployment/`。

---

## 验证:一次性触发 5 大能力

把这段贴进对话框：

> 调研 2025-2026 年 AI agent 编排框架现状，对比 LangGraph / AutoGen / CrewAI 三家。每个框架做成一张 research_card 显示。最后写一份 markdown 总结到 `report.md`。

预期：

| # | 能力 | 你会看到 |
|---|---|---|
| 1 | 实时 todo | 右侧 sidebar 出现 ≥4 条任务，随对话推进打勾 |
| 2 | Sub-agent 流 | 主对话出现 3 个 SubAgentIndicator（每框架一个），点可展开 |
| 3 | Tool call 折叠 | `web_search` 调用框可点 ▶ 展开看 query 和返回 |
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
