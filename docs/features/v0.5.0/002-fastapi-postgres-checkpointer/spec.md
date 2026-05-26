# Spec: 自研 FastAPI server + OSS PostgresSaver 持久化

> Feature ID: `002-fastapi-postgres-checkpointer` · 版本归属: `v0.5.0` · Owner: LineWalker · 创建日期: `2026-05-26`
>
> Predecessor(ABANDONED ADR): [`../001-langgraph-up-deployment/`](../001-langgraph-up-deployment/)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-26 起草;Spec Discovery 4 轮决策 + 001 ADR 教训 + sdd-review 4 处修订(AC-5 简化 / §4 #3 给 CLAUDE.md 新表述定稿初版 / §4 #7 破坏性回归挪 verification §3 / §6 langgraph.json 处理明确)已固化 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☑ | 2026-05-26 · LineWalker ★ 确认 |
| 已完成(verification.md 全绿) | ☐ | — |

---

## 1. 概述与用户故事

**Feature 描述**:撤掉 `langgraph dev`(in-memory checkpointer,进程重启即丢数据),改成自研 **轻量 FastAPI server** + LangGraph 官方开源 `AsyncPostgresSaver` / `AsyncSqliteSaver` 持久化。**统一**本地 Macbook 与 lab host 部署模型:本地默认 SQLite(单文件零依赖),lab host 用独立 Postgres docker container,通过 `DATABASE_URL` env 切换。**完全不依赖** LangSmith API key / LangGraph Cloud license / 任何商业产品。

**Context / 来源**:
- 用户口头需求 2026-05-26:lab host backend 重启丢 thread state 的"半截画面" bug(原 plan `~/.claude/plans/image-1-http-192-168-106-114-13000-assi-fluffy-honey.md`)。
- 前置 feature 001 (`langgraph up` 持久化部署) 实施 Step 6 时发现 LangGraph Platform (`langgraph up` 用的 `langchain/langgraph-api` docker image) 是 **LangChain 公司的商业产品**,启动强制 license 验证 + lab host docker bridge HTTPS 出口被防火墙挡,双重阻塞。详见 001 spec/tasks 顶部撤回说明 + tasks.md §"实际偏差记录"末两行的完整踩坑轨迹。
- 关键认知校准:**LangGraph 三层**——核心库 OSS(含 `langgraph-checkpoint-postgres` 3.1.0)/ `langgraph dev` OSS / `langgraph up` **商业**。我们要走的是核心库 + 自写 server,绕开商业产品。

**用户故事**:

1. 作为 lab host 上的访问用户,我希望进程重启后回到旧 thread 仍能看到完整 messages / todos / ui / files,以便不丢失正在进行中的调研——**且整个 demo 链路不依赖任何商业 license / 外网验证服务**。
2. 作为后端开发者(lilu),我希望本地 Macbook 启动 backend 仍然零 docker / 零外部数据库依赖(SQLite 单文件即可),保留快速热重载/迭代的体验——**部署到 lab host 时只切一个 `DATABASE_URL`** env 就能换成 Postgres,代码层零分叉。
3. 作为 6 个月后回到此项目的 maintainer,我希望 `backend/server.py` 实现的 LangGraph SDK 协议子集**有明确边界**,只覆盖 deepagents 实际用到的 endpoints,并且 verification 显式回归 frontend `useChat.ts` fetch monkey-patch 仍能命中——避免新 server 偷偷与上游 SDK 协议漂移。

**检查点**:
- [x] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [x] 描述里不引入新术语(`AsyncPostgresSaver`/`AsyncSqliteSaver` 是 langgraph-checkpoint-postgres/sqlite 的开源接口,`DATABASE_URL` 是 SQLAlchemy 风格 URI;均已 ground 在 §6 实现思路引用的官方 docstring)

---

## 2. 验收标准 (Acceptance Criteria)

| AC ID | 标准描述 | 验证方式 | verification.md 位置 |
|---|---|---|---|
| AC-1 | 本地 Macbook 执行 `cd backend && source .venv/bin/activate && uvicorn server:app --port 2024`(或 `python -m server`)启动成功;`curl http://localhost:2024/ok` 返回 `{"ok":true}`;`backend/local.db` SQLite 文件被自动创建;前端 `localhost:3000` 浏览器配置 Deployment URL `http://127.0.0.1:2024` + Assistant ID `research`,跑一遍最小 demo 跑通 | 本地终端 + 浏览器 + `ls backend/local.db` | §2.AC-1 |
| AC-2 | 本地跑完一次完整 demo("帮我调研 bisheng 同类竞品"——澄清 → todos → emit_research_card × N → write_file)后,**Ctrl-C 杀掉 server,重新启动**,在浏览器同一 thread 重新加载,messages / todos / ui / files 全部还在;F5 刷新后画面与重启前一致 | 浏览器手动 + `curl GET /threads/<id>/state` 对比重启前后 JSON | §2.AC-2 |
| AC-3 | lab host (192.168.106.114) 上 backend 切到 `DATABASE_URL=postgresql+asyncpg://...` + 起独立 `deepagents-postgres` docker container(port 5433,docker volume `deepagents_pgdata`);`./deepagents.sh start` 启动后 `docker ps` 看到 `deepagents-postgres` healthy;`curl http://192.168.106.114:12024/ok` 返回 `{"ok":true}`;前端 Deployment URL 不变 | `docker ps` + curl + 浏览器 | §2.AC-3 |
| AC-4 | lab host 上跑完一次完整 demo 后,`docker kill <backend-pid>`(或 `./deepagents.sh stop && ./deepagents.sh start`)重启 backend,Postgres container **不重启**,同一 thread 重新加载,messages / todos / ui / files 全部还在 | 同 AC-2 但在 lab host | §2.AC-4 |
| AC-5 | Frontend `useChat.ts` 的 fetch monkey-patch **仍在源码里**且对新 server 仍然有效:`grep -n "stream_mode" frontend/src/app/hooks/useChat.ts` 命中 line 58-67 的 monkey-patch(证明本 feature 没误删);DevTools Network 看 `/runs/stream` 请求 body 中 `stream_mode` 数组**不含** `"tools"`;响应无 HTTP 422。**破坏性回归(临时注释 monkey-patch 看 server 是否 422)挪到 verification.md §3**,不在 AC 里 | `grep` + DevTools Network 面板 | §2.AC-5 |
| AC-6 | `backend/agent.py` 显式实例化 `checkpointer = AsyncPostgresSaver.from_conn_string(...) / AsyncSqliteSaver.from_conn_string(...)` 并传给 `create_deep_agent(...)`;CLAUDE.md §强约束第 3 条已被拆分为"CLI 模式不传 / 自研 server 模式必须传",grep 命中新表述 | grep + reviewer 走读 | §2.AC-6 |
| AC-7 | `docs/architecture.md` §1 + §2.2 重写双轨部署描述(不再提 langgraph up,改成"统一自研 server,本地 SQLite / lab host Postgres");`docs/troubleshooting.md` §1.5 更新到指向 002;001 dir 保留作为 ADR 不删 | grep + 目录树检查 | §2.AC-7 |

**检查点**:
- [x] 每条 AC 都有唯一 ID,可手动复现
- [x] AC-1/2 本地、AC-3/4 lab host、AC-5 跨上游兼容、AC-6/7 文档项 —— 覆盖全部改动面
- [x] AC 数量 7 条(在 3-7 范围内)

---

## 3. 边界情况与非目标

### 3.1 边界情况

- **`AsyncPostgresSaver.from_conn_string` 首次连接** 自动 `.setup()` 建表;如果 lab host 上 Postgres 重启后 schema 还在,server 应自动 reconnect,无需手动迁移
- **本地 SQLite 并发写入**:demo 场景单用户串行,SQLite 足够;并发文档化"不要在 SQLite 路径下做多浏览器并发"
- **LangGraph SDK 协议子集缺失某 endpoint**:新 server 实现的是子集,if SDK 调用未实现端点 → 返回 404 + 日志告警,不要静默成功
- **现有 `langgraph dev` 的 hot reload 体验丢失**:`uvicorn --reload` 替代,Python 改动同样自动重启
- **前端 `useChat.ts` monkey-patch 与新 server 协议漂移**:AC-5 已显式回归;如未来 SDK 升级让新 server 422,优先调 server schema,不动 monkey-patch(它是 SDK ↔ langgraph-api 的兼容补丁,不是 server 的责任)
- **deepagents 升级**:`create_deep_agent` 现在显式接 `checkpointer=`,如果上游 deepagents 改了这个参数名或语义,需要同步;架构 §3 加 deepagents upgrade checklist 项
- **lab host docker bridge HTTPS 出口仍被挡**(001 实测过):本 feature **不依赖** 任何 outbound HTTPS(LangSmith / pypi / 其他),仅 Postgres TCP 通信走 host 内网 → docker container,**不受防火墙影响**

### 3.2 非目标(本期不做)

- **不实现完整 LangGraph SDK 协议**——只覆盖 deepagents 用到的 endpoints(`/info`、`/threads/*`、`/runs/stream` + SSE,具体子集见 §6)。未来其他客户端如有需要再扩
- **不引入 Alembic / 迁移工具**——`AsyncPostgresSaver.setup()` 自管 schema;deepagents 自己的应用层 state 都在 checkpoint 里,无独立表
- **不引入认证 / 多租户**——lab host 仍是内网信任模型
- **不写 docker-compose.yml**(只起一个 Postgres container,`docker run` 命令上手敲就行,001 同样的非目标)
- **不动 frontend 任何代码**——不动 `useChat.ts` monkey-patch、不动 `next.config.ts` rewrites、不动 React 组件
- **不引入 LangSmith Tracing**——零 LangSmith 依赖目标不变
- **不实现 cron / scheduled runs**——LangGraph SDK 协议有 cron endpoint,deepagents 不用,跳过
- **不实现 store / assistants endpoint**(deepagents 不主动用 `langgraph_store`,只用 checkpoint;前端可能 GET `/assistants` 拿列表,提供最小返回足矣)
- **不做完整压测**——demo 项目,功能验证为先

**检查点**:
- [x] 边界情况含失败/异常路径(SQLite 并发、SDK 协议漂移、endpoint 缺失、deepagents 升级、防火墙)
- [x] 非目标明确列出(完整协议、迁移工具、认证、docker-compose、frontend 改动、LangSmith、cron、store、压测)

---

## 4. 涉及强约束

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☐ 否 | 不动 middleware / 不动 graph 装配 |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 否 | 不动 |
| **不传 `checkpointer` 给 `create_deep_agent`** | ☑ 是 | **本 feature 主动修订这条强约束** —— `agent.py:45-51` 必须显式传 `checkpointer=AsyncPostgresSaver(...) / AsyncSqliteSaver(...)`,因为自研 server 不再有"CLI 自动管 checkpointer"的语义。<br><br>**CLAUDE.md §强约束 #3 新表述定稿初版**(本 feature Step 6 实施时落到 CLAUDE.md,字面照抄):<br><br>> **不要传 `checkpointer` / `MemorySaver` 给 `create_deep_agent` —— 但具体取决于启动模式**:<br>> - **CLI 模式**(`langgraph dev`,本项目自 v0.5.0 起不再默认使用,保留作为本地 quick smoke 工具):框架自动管 inmem checkpointer,传了启动失败<br>> - **自研 server 模式**(`backend/server.py` + `uvicorn`,本项目默认):**必须显式传** `checkpointer=AsyncPostgresSaver(...) / AsyncSqliteSaver(...)`,由 server lifespan 根据 `DATABASE_URL` env 实例化注入。详见 `docs/architecture.md §2.2` + `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`<br><br>**verification.md §3 回归项**:(a) `grep -n "checkpointer=" backend/agent.py` 应至少 1 处命中(显式接收注入);(b) `grep CLAUDE.md` 命中 "CLI 模式" + "自研 server 模式" 两段 |
| `streaming=True` 不改回 False | ☐ 否 | 不动 `agent.py:24` |
| 前端 vendored patch | ☐ 否 | 不动 frontend |
| HITL 批量审批语义 | ☐ 否 | 不动 — HITL dormant 状态保持(`interrupt_on=` 仍不传) |
| **`useChat.ts` fetch monkey-patch 不删** | ☑ 是 | **不动 monkey-patch 本身**,本 feature 实施 server 时**必须**显式实现"`stream_mode` 数组里没有 `\"tools\"` 时正常 SSE 流式响应;有 `\"tools\"` 时返回 422"的 schema 兼容。AC-5 验证 monkey-patch 仍在源码里 + DevTools 看请求体已被 patch 过滤;**verification.md §3 单列破坏性回归**:临时把 monkey-patch 整段注释 → 浏览器发起 run → 新 server 应返回 422 → 立即取消注释 + `git diff frontend/src/app/hooks/useChat.ts` 应无变化 |
| `prompts.py` 强制语序 | ☐ 否 | 不动 prompt |

**检查点**:
- [x] 凡是"是"的条目,缓解策略不为空
- [x] 触碰的 2 条(#3、#7)都在 verification.md §3 加回归项

---

## 5. 前端 patch 影响

**是否动 `frontend/**`**:☐ 否

不动 frontend 任何代码。

但本 feature 与 frontend 既有 patch (`useChat.ts` fetch monkey-patch、`ChatInterface.tsx` `broadcastResumeInterrupt`、`ChatMessage.tsx` `LOCAL_UI_COMPONENTS` 注入、`registry.tsx`、`ToolCallBox.tsx`)**存在协议层耦合**:新 server 必须实现一组 endpoints + SSE 事件 schema 让既有 patch 仍能工作。这层验证集中在 §2.AC-5 + verification.md §3 回归检查。

**对 `architecture.md §3.1` patch 表的预期更新**:无新增/删除,但 §3.3 "stream_mode 'tools' 兼容性 fetch hack" 那段的"何时可删条件"需要补一句:"自研 server 已不依赖 langgraph-cli[inmem] 的 OpenAPI schema,但仍需兼容 SDK 客户端 — 拆 hack 之前先看新 server 是否拒掉 stream_mode tools"。

**检查点**:
- [x] 不动 frontend,留底命令不必出现
- [x] §3.1 patch 表无新增/删除,只补 §3.3 表述

---

## 6. 实现概要 & 文件清单

**实现思路**(Spec Discovery 4 轮决策固化):

1. **实现路径 B**:自写 FastAPI server。架构清晰、可控,不依赖 `langgraph_runtime_inmem` 内部 API。代码量预估:**`server.py` 250-400 行**(含 SSE / state CRUD / run 触发)。
2. **Persistence 切换**:`DATABASE_URL` env 决定:`sqlite+aiosqlite:///./local.db` → `AsyncSqliteSaver`;`postgresql+asyncpg://...` → `AsyncPostgresSaver`。两个 saver 都是 OSS,接口几乎一致,工厂函数选一。
3. **Server 启动入口**:`uvicorn server:app --host 0.0.0.0 --port 2024`(本地) / `--port 12024`(lab host)。代替 `langgraph dev`。
4. **`agent.py` 改造**:`create_deep_agent(...)` 增加 `checkpointer=` 参数,值由 server.py 在启动 lifespan 里实例化后注入(避免 import 时 side effect)。
5. **协议子集**(对照 frontend `useChat.ts` 实际用法):
   - `GET /ok` — 健康检查(deepagents 自定,简单 ping)
   - `GET /info` — 返回 graph 列表 + 版本(SDK 启动时 fetch)
   - `GET /assistants` / `POST /assistants/search` — 返回 `[{assistant_id: "research", graph_id: "research", ...}]`(SDK 列出 assistants 用)
   - `POST /threads` — 创建空 thread,返回 `{thread_id, ...}`
   - `GET /threads/{id}` — 拿 thread metadata
   - `GET /threads/{id}/state` — 拿 state values(messages / todos / ui / files)+ next + interrupts(从 checkpointer 读)
   - `POST /threads/{id}/runs/stream`(以及 `POST /runs/stream` 无 thread)— 触发 graph + SSE 流(`values` / `messages-tuple` / `updates` 三种 stream_mode,见前端 `useChat.ts:95`;`tools` mode 直接 422 让 monkey-patch 触发)
   - `POST /threads/{id}/runs` — resume(`command: {resume: ...}`)/ goto(`command: {goto: "__end__"}`)
   - `POST /threads/{id}/state` — `updateState`(前端 `useChat.ts:154` 给 files 改写用)
   - `POST /threads/search` — 用于会话列表(`useThreads`)
   - 其他端点(cron / store / 多 graph)不实现,SDK 调到时 404
6. **SSE 实现**:`StreamingResponse` + `text/event-stream`,事件类型 `event: values\ndata: {...}\n\n` 等。复用 `langgraph.pregel` 的 `astream()` 接口拿事件流,在 server 层包装成 SSE 格式。
7. **CLAUDE.md §强约束 #3 拆分**(本 feature 主动修订):新文本两段——"**CLI 模式**(`langgraph dev`)**不传**`checkpointer=`,framework 自动管 inmem" / "**自研 server 模式**(`backend/server.py`)**必须显式传**,实例化从 `DATABASE_URL` env 决定 saver 类型"。同步 docs/architecture.md §2.2 描述。
8. **lab host 部署**:`docker run -d --name deepagents-postgres --restart unless-stopped -p 5433:5432 -e POSTGRES_PASSWORD=... -v deepagents_pgdata:/var/lib/postgresql/data postgres:16-alpine`(Postgres image 已在 lab host 缓存,无需拉);`backend/.env` 设 `DATABASE_URL=postgresql+asyncpg://postgres:...@127.0.0.1:5433/postgres`;`deepagents.sh` backend 启动命令换成 `uvicorn server:app --host 0.0.0.0 --port 12024`。
9. **001 部分文件回滚处理(明确每个的去留)**:
   - `backend/pip.conf` — **删除**(自研 server 不走 docker build,不需要)
   - `backend/langgraph.json` — **保留但精简**到 `dependencies` / `graphs` / `env` 三个核心字段——这文件是 schema descriptor,LangSmith Studio / LangGraph CLI 工具未来仍可能读;但移除 001 加的 `pip_config_file` / `dockerfile_lines`(都跟 langgraph up build 路径绑定)
   - `README.md §5` "lab host 部署(`langgraph up`)" 整段**重写**为"lab host 部署(`uvicorn server:app` + 独立 Postgres docker container)"
   - `backend/.env.example` **移除** 001 加的 `LANGGRAPH_PORT/POSTGRES_PORT/REDIS_PORT` 占位段,改为 `DATABASE_URL=sqlite+aiosqlite:///./local.db`(本地默认)+ lab host 注释示例

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/server.py` | 新建 | FastAPI app + LangGraph SDK 协议子集 + SSE + lifespan(实例化 saver 注入 agent) |
| `backend/agent.py` | 修改 | `create_deep_agent(...)` 加 `checkpointer=` 参数,值由 server 启动时注入;module-level 不再直接 instantiate `agent`,改成 factory `build_agent(checkpointer)` |
| `backend/pyproject.toml` | 修改 | 加 `langgraph-checkpoint-postgres>=3.1` / `langgraph-checkpoint-sqlite>=2.1` / `fastapi>=0.115` / `uvicorn[standard]>=0.30` / `asyncpg>=0.29` / `aiosqlite>=0.20`;**移除** `langgraph-cli[inmem]`(不再用 langgraph dev) |
| `backend/.env.example` | 修改 | 加 `DATABASE_URL=sqlite+aiosqlite:///./local.db` 默认 + lab host 注释示例 `# DATABASE_URL=postgresql+asyncpg://...`;**移除** 001 加的 `LANGGRAPH_PORT/POSTGRES_PORT/REDIS_PORT` 占位 |
| `backend/langgraph.json` | 修改 | **移除** 001 加的 `pip_config_file` / `dockerfile_lines`(自研 server 不再走 docker build);**或整个删除**(因为不再用 langgraph CLI) |
| `backend/pip.conf` | 删除 | 001 加的,自研 server 不需要 |
| `deepagents.sh` | 修改 | backend 启动命令从 `langgraph dev --port ${BACKEND_PORT}` 改成 `uvicorn server:app --host 0.0.0.0 --port ${BACKEND_PORT}`;`stop_all` 兜底匹配规则跟着改 |
| `CLAUDE.md` | 修改 §强约束 + §仓库总览 | (1) §强约束 #3 拆分两种 mode;(2) §仓库总览 backend 行从"跑在 langgraph dev 上"改"通过 backend/server.py 启动 uvicorn + 自带 PostgresSaver / SqliteSaver" |
| `docs/architecture.md` | 修改 §1 + §2.2 + §3.3 | §1 总览图替换 langgraph dev/up 部分为自研 server;§2.2 末尾段重写(从"两种 langgraph CLI 模式都自动管 checkpointer" → "自研 server 显式传 saver");§3.3 fetch hack 段补一句"自研 server 不强依赖 SDK schema,但仍兼容,见 002 AC-5" |
| `docs/troubleshooting.md` | 修改 §1.1 + §1.5 | §1.1 整段重写(原"checkpointer not necessary"现象在 dev 模式下还有,在 server 模式下不再适用);§1.5 重写,把"切到 langgraph up"指向"切到自研 server" |
| `README.md` | 修改 启动 + lab host 章节 | "启动" §2 命令从 `langgraph dev` 改成 `uvicorn server:app --port 2024`(等价默认);§5 lab host 部署小节重写,内容改为"起独立 Postgres docker + uvicorn server"(001 加的整个 langgraph up 说明回滚) |
| `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/{spec,tasks,verification}.md` | 新建 | SDD 三件套(本文 + Step 4) |

**检查点**:
- [x] 文件清单与 §4-§5 标记一致(不动 frontend / 触碰强约束 #3 #7 都有具体改动文件)
- [x] 引入新机制(自研 FastAPI server + 显式 checkpointer),architecture 同步项已列(§1 + §2.2 + §3.3)
- [x] 不出现大段代码块(具体 endpoint 代码骨架留 tasks.md / 实施时)
