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
# 自 v0.5.0:自研 FastAPI server + AsyncSqliteSaver(本地默认 SQLite,无 docker 依赖)
uvicorn server:app --port 2024 --reload      # → http://127.0.0.1:2024
# 本地 quick smoke(无持久化)也可用:langgraph dev → :2024(模块层 `agent` fallback)
```

启动后 `backend/local.db` 自动创建。这是 SQLite 持久化文件——后端进程重启不会丢 thread state(对比 `langgraph dev` 的 in-memory)。

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

### 5. lab host 部署(`uvicorn server:app` + 独立 Postgres docker)

> **仅 lab host (例如 192.168.106.114) 用。本地 Macbook 走 `uvicorn server:app + SQLite`(上面 §2,零 docker 依赖)。** 详见 `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`。

**为什么 lab host 用 Postgres 而非 SQLite?** SQLite 文件单进程写入足够本地 demo,但多 worker / 远程访客 / 服务可能被重启的场景下,Postgres 独立 docker container 更稳。本地 + lab host **一套代码两套配置**,只通过 `DATABASE_URL` env 区分。背景见 `docs/troubleshooting.md §1.5`。

> **撤回历史**:v0.5.0 草案曾计划用 LangGraph Platform 的 `langgraph up`(docker compose 起 langgraph-api + postgres + redis 三个 container),但发现 `langchain/langgraph-api` 是商业产品需 LangSmith Plus 或 Cloud license,且 lab host docker bridge HTTPS 出口被防火墙挡。详见 [`docs/features/v0.5.0/001-langgraph-up-deployment/`](docs/features/v0.5.0/001-langgraph-up-deployment/)(ABANDONED ADR)。

#### 5.1 前置

- lab host 上已装 Docker(≥ 24) + Docker Compose v2(用于跑 Postgres container)
- `postgres:16-alpine` 镜像已在 lab host 缓存(没缓存的话 `docker pull` 即可,通常 docker hub 走 lab host 内的 registry mirror)
- 已有 lab host 部署用 `./deepagents.sh start`;v0.5.0 起 backend 启动命令已改成 `uvicorn server:app`(`deepagents.sh` 已同步)

#### 5.2 起独立 Postgres docker container(一次性)

```bash
ssh root@192.168.106.114

PGPWD=$(openssl rand -hex 16)
docker run -d \
  --name deepagents-postgres \
  --restart unless-stopped \
  -p 5433:5432 \
  -e POSTGRES_PASSWORD="$PGPWD" \
  -v deepagents_pgdata:/var/lib/postgresql/data \
  postgres:16-alpine

# 把生成的密码写到 .env(后面 backend 启动时会读)
echo "DATABASE_URL=postgresql+asyncpg://postgres:${PGPWD}@127.0.0.1:5433/postgres" \
  >> /root/deepagents/backend/.env
```

#### 5.3 切到自研 server + 起服务

```bash
cd /root/deepagents
./deepagents.sh stop                                         # 停旧 backend + frontend
git pull origin feat/v0.5.0/001-langgraph-up-deployment      # 含 001 abandoned + 002 实施
./deepagents.sh start                                        # 内部跑 uvicorn server:app --port 12024
```

#### 5.4 健康检查

```bash
docker ps --filter "name=deepagents-postgres" --format 'table {{.Names}}\t{{.Status}}'   # 应 Up healthy
curl http://192.168.106.114:12024/ok                                                     # 应 {"ok":true}
./deepagents.sh status                                                                   # 应看到 uvicorn + next-server 端口
```

#### 5.5 端口配置(冲突时 override)

lab host 上已有原生 redis `:6379`,但 002 方案**不用 Redis**(没有 langgraph-api / langgraph-redis container),所以无冲突。

Postgres 用 `:5433` 对外(避让 host 可能已有的 `:5432`)。如要改,改 `docker run -p` 端口 + `.env` 的 `DATABASE_URL` 端口。

#### 5.6 数据持久化

Postgres 数据存在 docker volume `deepagents_pgdata`,`docker stop deepagents-postgres` **不**清数据,**只有** `docker volume rm deepagents_pgdata` 才清。重启 backend 用 `./deepagents.sh stop && start`,不会动 Postgres container。

#### 5.7 与本地 SQLite 的差异

| 项 | 本地 Macbook | lab host |
|---|---|---|
| Checkpointer | `AsyncSqliteSaver` (`backend/local.db`) | `AsyncPostgresSaver`(独立 docker container) |
| 后端启动 | `uvicorn server:app --port 2024 --reload` | `./deepagents.sh start`(内部 uvicorn --port 12024) |
| 后端端口 | `:2024` | `:12024` |
| docker 依赖 | 无 | 仅 `deepagents-postgres` container |
| 进程重启影响 | thread state 保留(SQLite 文件持久化) | thread state 保留(Postgres volume 持久化) |
| 适用 | 本机开发、单人 demo | 多人共享 / 远程访客 / 服务可被重启的环境 |

详细对比 + 决策见 `docs/architecture.md §1` 末尾"部署模型"表 + `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/`。

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
