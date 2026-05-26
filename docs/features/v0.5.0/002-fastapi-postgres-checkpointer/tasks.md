# Tasks: 自研 FastAPI server + OSS PostgresSaver 持久化

> Spec: [`./spec.md`](./spec.md) · Verification: [`./verification.md`](./verification.md) · Predecessor ADR: [`../001-langgraph-up-deployment/`](../001-langgraph-up-deployment/)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-26 |
| 已评审(`/sdd-review tasks` 通过) | ☑ | 2026-05-26 · 自动通过 |
| 已完成(所有任务 ✅ + verification.md 全绿) | ☐ | — |

---

## 任务依赖

任务数 = 6,文字依赖图:

```
T1 (frontend endpoint 审计 + agent.py 重构 factory)
  └─ T2 (backend/server.py 实现 + pyproject.toml deps)
       ├─ T3 (配置/启动脚本回滚:.env.example / langgraph.json / pip.conf / deepagents.sh)
       │    └─ T5 (lab host 起 Postgres docker + 切到 uvicorn)
       └─ T4 (文档同步:CLAUDE.md / architecture.md / troubleshooting.md / README.md)
                ↓
              T6 (verification.md 跑全 + 破坏性回归 + 截图归档)
```

并行机会:T3 / T4 在 T2 完成后可并行启动;T5 需要 T3 提交以保证 lab host pull 到新启动脚本。**不动 `frontend/`**,因此没有前端 patch 留底任务(spec §5 = 否)。

---

## 任务清单

### T1 — Frontend endpoint 审计 + `backend/agent.py` 重构为 factory

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26;endpoint 审计落在 §"实际偏差记录"第 2 行,`build_agent(checkpointer)` factory 就位,module-level `agent = build_agent(None)` fallback 兼容 langgraph dev,`grep "checkpointer=" agent.py` 命中 line 68)
- **文件**:`backend/agent.py`(修改);Frontend 文件(仅读,不改:`frontend/src/app/hooks/useChat.ts`、`useThreads.tsx`、`providers/ClientProvider.tsx`、`@langchain/langgraph-sdk` 内部 `client.threads.*` / `client.runs.*` / `client.assistants.*` 用法)
- **逻辑**:
  1. **精确审计**(read-only):grep + 阅读上述前端文件,**列出 deepagents 前端实际触发的所有 HTTP endpoints**(method + path + 请求 body 形状 + SSE 事件类型),作为 T2 实现 server 的 ground truth。把这个列表 commit 进 `backend/server.py` 顶部 docstring 或者本 tasks.md 注释。**若发现 spec §6 第 5 段列出的子集与实际有出入,在 §"实际偏差记录"登记**。
  2. **重构 `backend/agent.py`**:
     - 把 module-level `agent = create_deep_agent(...)` 改成 factory:`def build_agent(checkpointer): return create_deep_agent(model=..., tools=..., system_prompt=..., subagents=..., middleware=..., checkpointer=checkpointer)`
     - 删除 module-level `agent` 变量(自研 server 不再有上层 import 它的需求;`langgraph.json` 也会精简,见 T3)
     - 保留 `model` / `research_subagent` 等顶层定义(纯定义,无 side effect)
- **验证方式**:T1 自身手测 `python -c "from agent import build_agent"` 不报错;AC-6 中 `grep -n "checkpointer=" backend/agent.py` 应命中(在 `build_agent` 内)
- **覆盖 AC**:AC-6(部分:`agent.py` 显式接收 checkpointer);所有其他 AC 的实施依赖本任务输出的 endpoint 列表
- **依赖**:无

### T2 — `backend/server.py` 实现 + 依赖更新

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26;server.py 516 行,11 个 endpoints + SSE + lifespan,本地 SQLite smoke 全部通过;**AC-2 核心已 curl 验证**:server 重启前后同一 thread n_messages=2 + 同一 checkpoint_id;stream_mode "tools" → HTTP 422 守护 OK;完整浏览器 demo 留 T6 终验)
- **文件**:`backend/server.py`(新建);`backend/pyproject.toml`(修改)
- **逻辑**:
  1. **`pyproject.toml`**:
     - **加** `fastapi>=0.115` / `uvicorn[standard]>=0.30` / `langgraph-checkpoint-postgres>=3.1` / `langgraph-checkpoint-sqlite>=2.1` / `asyncpg>=0.29` / `aiosqlite>=0.20`
     - **移除** `langgraph-cli[inmem]>=0.1.50`(不再用 langgraph dev)
     - `python_requires` / `langgraph>=1.0` / `deepagents` / `langchain-openai` 等保留
  2. **`backend/server.py`** 实现 4 块:
     - **lifespan**:读 `DATABASE_URL` env(默认 `sqlite+aiosqlite:///./local.db`)→ 根据协议头实例化 `AsyncSqliteSaver.from_conn_string(...)` 或 `AsyncPostgresSaver.from_conn_string(...)` → `await saver.setup()` 建表 → `app.state.agent = build_agent(saver)` → yield → 退出时 close
     - **endpoints**(T1 审计后定稿,以下是 spec §6 第 5 段的初稿子集):
       - `GET /ok` → `{"ok": true}`
       - `GET /info` → graph 列表 + 版本
       - `GET /assistants` / `POST /assistants/search` → `[{assistant_id: "research", graph_id: "research", ...}]`
       - `POST /threads` / `GET /threads/{id}` / `GET /threads/{id}/state` / `POST /threads/{id}/state`(updateState)/ `POST /threads/search`
       - `POST /runs/stream` / `POST /threads/{id}/runs/stream` / `POST /threads/{id}/runs`(resume/goto)
       - 未实现 endpoints 返回 404 + WARN 日志
     - **SSE streaming**:`StreamingResponse(..., media_type="text/event-stream")`,事件 `event: <type>\ndata: <json>\n\n`;复用 `agent.astream(...)` async iterator,把 LangGraph 事件包装成 SSE
     - **stream_mode 兼容**:接受 `["values", "messages-tuple", "updates"]` 任意子集;含 `"tools"` 时返回 HTTP 422(spec §4 #7 显式要求,守护 frontend monkey-patch 的存在意义)
  3. **本地 smoke**:`cd backend && source .venv/bin/activate && uvicorn server:app --port 2024` 启动成功 + `curl /ok` 返回 200
- **验证方式**:AC-1 本地 SQLite 跑通;AC-2 本地 Ctrl-C 重启验证 thread 持久;AC-5 monkey-patch + 422 守护
- **覆盖 AC**:AC-1, AC-2, AC-5, AC-6(显式 checkpointer 传入完成)
- **依赖**:T1(必须先有精确 endpoint 列表)

### T3 — 配置 / 启动脚本回滚 + 切换到 uvicorn

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26;pip.conf 已 git rm;langgraph.json 精简到 3 字段;.env.example 改为 DATABASE_URL 默认 SQLite + lab host Postgres 注释;deepagents.sh backend 启动 `uvicorn server:app` + stop_all 兜底 pkill 兼容老 langgraph dev 进程)
- **文件**:`backend/.env.example`(修改)、`backend/langgraph.json`(修改)、`backend/pip.conf`(删除)、`deepagents.sh`(修改)
- **逻辑**:
  1. **`backend/pip.conf`** 删除(`git rm backend/pip.conf`,001 加的,不再需要)
  2. **`backend/langgraph.json`** 精简到 3 字段:
     ```json
     {
       "dependencies": ["."],
       "graphs": {"research": "./agent.py:agent"},
       "env": ".env"
     }
     ```
     **注意**:`graphs.research` 指向 `./agent.py:agent`,但 T1 已经删除 module-level `agent`。如果文件保留只为 schema descriptor 而非实际 langgraph CLI 用,这里要么 (a) 改成 factory 引用 `./agent.py:build_agent`,要么 (b) 在 agent.py 保留一个轻量 module-level `agent = build_agent(InMemorySaver())` fallback。**Step 6 实施时定**;若决定不要 langgraph.json 也可整个删除(T1 删除 module-level agent 后无强制保留理由)。本偏差登记到 §"实际偏差记录"
  3. **`backend/.env.example`**:
     - **移除** 001 加的 `LANGGRAPH_PORT / POSTGRES_PORT / REDIS_PORT` 占位段(整段 5 行)
     - **新增** `DATABASE_URL=sqlite+aiosqlite:///./local.db` 默认 + lab host 注释 `# DATABASE_URL=postgresql+asyncpg://postgres:<password>@127.0.0.1:5433/postgres`
  4. **`deepagents.sh`**:
     - `BACKEND_PORT=12024` 保留(端口不变,只换底层 server)
     - `stop_all` 中 `pkill -f "langgraph dev --host 0.0.0.0 --port ${BACKEND_PORT}"` 改成 `pkill -f "uvicorn server:app --host 0.0.0.0 --port ${BACKEND_PORT}"`;按工作目录 pgrep 兜底保留
     - `start` case 中 `setsid nohup langgraph dev --host 0.0.0.0 --port ${BACKEND_PORT} ...` 改成 `setsid nohup .venv/bin/uvicorn server:app --host 0.0.0.0 --port ${BACKEND_PORT} ...`
     - `--n-jobs-per-worker 10` 这种 langgraph dev 特有参数移除(uvicorn 自带 worker 管理,默认即可)
- **验证方式**:T3 自身手测 `./deepagents.sh stop && ./deepagents.sh start && ./deepagents.sh status`(本地或 lab host) 应看到 uvicorn 进程 + 端口 12024 LISTEN
- **覆盖 AC**:AC-1(本地启动),AC-3(lab host 启动前置)
- **依赖**:T2(uvicorn 启动入口存在才能改 deepagents.sh)

### T4 — 文档同步(CLAUDE.md + architecture.md + troubleshooting.md + README.md)

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26;CLAUDE.md §强约束 #3 拆为 CLI / 自研 server 两段 + §仓库总览 + §常用命令更新;architecture.md §1 部署模型表重写 + §2.2 + §3.3 补 002 兼容性;troubleshooting.md §1.1 拆两个 mode + §1.5 重写指向 002;README.md §2 启动 + §5 lab host 整段重写;**AC-6/AC-7 grep 全部命中**)
- **文件**:`CLAUDE.md`、`docs/architecture.md`、`docs/troubleshooting.md`、`README.md`
- **逻辑**:
  1. **`CLAUDE.md`**:
     - **§强约束第 3 条** 替换为 spec §4 第 3 条 "新表述定稿初版" 的字面文本(两种 mode 拆分)
     - **§仓库总览** backend 行 `跑在 langgraph dev 上(端口 2024)` 改成 `通过 backend/server.py 启动 uvicorn(端口 2024 本地 / 12024 lab host),显式 PostgresSaver / SqliteSaver(由 DATABASE_URL 选择)`
     - **§常用命令** 后端启动从 `langgraph dev` 改成 `uvicorn server:app --port 2024`(本地);lab host 用 `./deepagents.sh start`
  2. **`docs/architecture.md`**:
     - **§1 系统总览** 移除 v0.5.0 加的"双轨部署"表(langgraph dev/up);新写一段"统一自研 server 部署模型":本地 SQLite + lab host Postgres,两套通过 `DATABASE_URL` env 切换,backend 代码完全一致(`server.py` lifespan 路由 saver)
     - **§2.2 末尾"另一个状态层约束"段** 完整重写:从"两种 langgraph CLI 模式都自动管" → "自研 server 模式 must 显式传 saver,实例化在 `server.py` lifespan;具体 saver 类型由 `DATABASE_URL` env 决定";同时说明 "001 ADR 记录了为什么 `langgraph up` 不走(LangGraph Platform 商业 license + lab host 防火墙)"
     - **§3.3 fetch hack** 段末尾补一句:"自研 server 不依赖 langgraph-cli[inmem] OpenAPI schema,但仍兼容 SDK 客户端(server 显式实现 stream_mode 数组含 'tools' 时返回 422 守护 hack 的存在意义)。判定可删条件改成:'升级 SDK + 不再 auto-append tools 后,可拆。或在自研 server 一侧改成"忽略 tools 不报错"——但 deepagents 项目目前保留 422 行为以保持与 langgraph-api 上游一致'"
  3. **`docs/troubleshooting.md`**:
     - **§1.1 标题与正文** 整段重写:`langgraph dev` 模式下"checkpointer not necessary" 报错仍然成立;自研 server 模式则**相反**——必须显式传,缺了启动 lifespan 会报错。两种 mode 分别给修法
     - **§1.5** 整段重写:把"切到 `langgraph up`"指向"切到 `backend/server.py` + 独立 Postgres docker"。诊断三步保留(curl /state + F5 + ps -o lstart)
  4. **`README.md`**:
     - **§2 装后端依赖并启动** 命令从 `langgraph dev` 改成 `uvicorn server:app --port 2024 --reload`(本地);说明 `DATABASE_URL` 缺省 SQLite 即可
     - **§5 lab host 部署** 整段重写为"lab host 部署(uvicorn + 独立 Postgres docker)":前置 / 起 Postgres container 的 `docker run` 命令 / `.env` 配 `DATABASE_URL` / `./deepagents.sh start` / 健康检查 / 数据卷持久化;**移除** 001 加的 `langgraph up` 相关内容
- **验证方式**:AC-6 grep `checkpointer=` agent.py + grep CLAUDE.md 两种 mode 文本;AC-7 grep `langgraph up` 应零命中(已被回滚),grep `uvicorn server:app` 应命中 architecture/CLAUDE/README/troubleshooting
- **覆盖 AC**:AC-6, AC-7
- **依赖**:T2(具体命令、saver 实例化形式定下来才能写文档)

### T5 — lab host 起 Postgres docker container + 切到自研 server

- **状态**:☐ 待开始 / ☐ 进行中 / ☐ 已完成
- **文件**:无源码改动(仅 lab host 上的 `/root/deepagents/backend/.env` + docker 状态)
- **逻辑**:
  1. ssh root@192.168.106.114
  2. `docker run -d --name deepagents-postgres --restart unless-stopped -p 5433:5432 -e POSTGRES_PASSWORD=<生成的强密码> -v deepagents_pgdata:/var/lib/postgresql/data postgres:16-alpine`(image 已在 lab host 缓存,无需拉)
  3. 编辑 `/root/deepagents/backend/.env`:加 `DATABASE_URL=postgresql+asyncpg://postgres:<密码>@127.0.0.1:5433/postgres`
  4. `cd /root/deepagents && ./deepagents.sh stop && git pull origin feat/v0.5.0/001-langgraph-up-deployment && ./deepagents.sh start`
  5. 等几秒让 uvicorn lifespan 跑完 saver.setup()
  6. `docker ps` 验证 `deepagents-postgres` healthy + uvicorn 进程跑;`curl http://192.168.106.114:12024/ok` 返回 200
- **验证方式**:AC-3 lab host 启动;AC-4 后续 verification 时 docker kill + 重启验证持久
- **覆盖 AC**:AC-3, AC-4(部分:启动部分)
- **依赖**:T2, T3, T4(都需要一套完整代码 + 配置 + 文档先 commit + push)

### T6 — `verification.md` 全跑通 + 破坏性回归 + 截图归档

- **状态**:☐ 待开始 / ☐ 进行中 / ☐ 已完成
- **文件**:`./verification.md`(填充)、`./screenshots/`(填充)
- **逻辑**:
  1. 按 `verification.md §1.1` 本地启动 → 跑一次完整 demo 跑通 → 验证 **AC-1**
  2. Ctrl-C 杀本地 server,重新 `uvicorn server:app` 启动 → 同一 thread F5 加载验证 **AC-2**
  3. ssh lab host,按 T5 步骤起 Postgres + 切自研 server → 验证 **AC-3**
  4. lab host 上跑一次完整 demo + `./deepagents.sh stop && start`(Postgres 保留)→ 验证 **AC-4**
  5. DevTools Network 看 `/runs/stream` body `stream_mode` 不含 `"tools"`;`grep -n "stream_mode" frontend/src/app/hooks/useChat.ts` 命中 → 验证 **AC-5**
  6. `grep -n "checkpointer=" backend/agent.py` + `grep "CLI 模式\|自研 server 模式" CLAUDE.md` → 验证 **AC-6**
  7. `grep "langgraph up" CLAUDE.md docs/architecture.md docs/troubleshooting.md README.md` 应零命中(已回滚);`grep "uvicorn server:app" CLAUDE.md docs/architecture.md README.md` 应命中 → 验证 **AC-7**
  8. **破坏性回归**(verification.md §3 单列):临时把 `frontend/src/app/hooks/useChat.ts:52-77` 整段 useEffect 注释 → frontend 重 build → 浏览器发起 run → 期望 server 返回 422 → **立即取消注释 + `git diff frontend/src/app/hooks/useChat.ts` 应空** → 重 build 恢复
  9. 截图归档到 `./screenshots/`:`ac-1-local-sqlite.png` / `ac-2-local-restart.png` / `ac-3-lab-postgres-docker.png` / `ac-4-lab-restart.png` / `ac-5-devtools-stream-mode.png` / `regression-monkey-patch-422.png`
  10. 全绿后勾 verification.md 状态表三行 + 本 tasks.md "已完成" 行 + spec.md "已完成" 行
- **验证方式**:verification.md 自身的状态表三行全勾
- **覆盖 AC**:全部(AC-1 ~ AC-7,收尾验证)
- **依赖**:T1, T2, T3, T4, T5

---

## AC 覆盖反查

| AC | 由哪些任务覆盖 |
|---|---|
| AC-1(本地 SQLite 启动 + smoke demo) | T2, T3, T6(verify) |
| AC-2(本地重启后 thread state 完整) | T2, T6(verify) |
| AC-3(lab host Postgres 启动) | T2, T3, T5, T6(verify) |
| AC-4(lab host 重启后 thread state 完整) | T5, T6(verify) |
| AC-5(monkey-patch 仍在源码 + DevTools 验证 + 422 守护) | T2, T6(verify) |
| AC-6(显式 checkpointer + CLAUDE.md 两种 mode 文本) | T1, T2, T4, T6(verify) |
| AC-7(architecture/troubleshooting/README 同步更新) | T4, T6(verify) |

每条 AC 至少被 1 个任务覆盖 ✓;任务引用的 AC ID 全部存在于 spec.md §2 ✓。

---

## 实际偏差记录

> 实现过程中如发现与 spec.md 不符,**立刻在此登记**,并在 PR 描述里指向本节。
>
> **不允许"先实现再决定"**——若需偏离,先评估是否回 spec.md 修订。严重偏离(改 AC、改强约束触碰判断)必须回 Step 2 重新走 `/sdd-review spec`。

| 日期 | 任务 | 偏差描述 | 处理决定(回改 spec / 接受偏差 / 撤回任务) |
|---|---|---|---|
| _(YYYY-MM-DD)_ | T_(N)_ | _(在此填写)_ | _(在此填写)_ |
| 2026-05-26 | T1 | 精确审计 frontend 实际触发的 endpoint 共 **11 个 + 4 个隐藏调用**。spec.md §6 第 5 段的子集列表与实际有 4 处出入:**漏列** (a) `POST /threads/{id}/history`(useStream `fetchStateHistory: true` 拉历史)、(b) `GET /threads/{id}/runs/{run_id}/stream`(reconnectOnMount 重连用)、(c) `POST /threads/{id}/runs/{run_id}/cancel`(`stream.stop()` 用,`useChat.ts:219`)、(d) `DELETE /threads/{id}`(`useDeleteThread.ts:14`);**表述误差** spec 写"POST /threads/{id}/runs(resume/goto)"实际是通过 `POST /threads/{id}/runs/stream` 路径 + body 含 `command` 字段(resume / goto),不是单独 endpoint。 | **接受偏差,不回 spec(不改 AC、不改强约束触碰)** —— spec.md §6 第 5 段措辞本就标"以下是 spec §6 第 5 段的初稿子集",T1 任务承诺"对照实际更新偏差",此处即为兑现。最终 endpoint 全集落到 `backend/server.py` 顶部 docstring(T2 实施),作为 server 实现的 ground truth:**11 个 endpoint** = 2 Assistants(`GET /assistants/{id}` + `POST /assistants/search`)+ 6 Threads(`POST /threads` + `POST /threads/search` + `DELETE /threads/{id}` + `GET /threads/{id}/state` + `POST /threads/{id}/state` + `POST /threads/{id}/history`)+ 3 Runs(`POST /runs/stream` + `POST /threads/{id}/runs/stream` + `GET /threads/{id}/runs/{run_id}/stream` + `POST /threads/{id}/runs/{run_id}/cancel`)。**fetch monkey-patch 拦截 path pattern** = 包含 `/runs/stream`(覆盖两个 POST 变体)。**stream_mode 期望事件类型** = `values`(完整 state snapshot) / `messages-tuple`(单消息事件)/ `updates`(增量节点更新)。 |
