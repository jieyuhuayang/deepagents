# Verification: 自研 FastAPI server + OSS PostgresSaver 持久化

> Spec: [`./spec.md`](./spec.md) · Tasks: [`./tasks.md`](./tasks.md)
>
> **本文档是 feature 完成的最终凭证。** 所有 AC 必须在此手动验证通过;所有触碰的强约束必须在 §3 回归检查中确认仍生效;**破坏性回归(临时注释 monkey-patch)**必须跑且完成后 `git diff` 必须为空。
>
> **当前是骨架版**(Step 4 起草),§1 / §2 步骤细节在 Step 6 实施过程中补全。

## 状态

| 阶段 | 状态 | 验证日期 | 验证人 |
|---|---|---|---|
| 全部 AC 验证通过 | ☐ | | |
| 全部回归检查通过 | ☐ | | |
| 截图已附在 `./screenshots/` | ☐ | | |

---

## 0. 环境信息

**双 saver 部署**:本地 Macbook 默认 SQLite(单文件),lab host 用独立 Postgres docker container。两套通过 `DATABASE_URL` env 切换,backend 代码完全一致。

| 项 | 本地 Macbook | lab host (192.168.106.114) |
|---|---|---|
| 后端启动 | `cd backend && source .venv/bin/activate && uvicorn server:app --port 2024 --reload` | `cd /root/deepagents && ./deepagents.sh start`(内部跑 `uvicorn server:app --port 12024`) |
| 后端端口 | `:2024` | `:12024` |
| Checkpointer | `AsyncSqliteSaver`(`backend/local.db`) | `AsyncPostgresSaver`(独立 docker container) |
| Container 名(若有) | 无 | `deepagents-postgres`(只此一个,langgraph-api/redis 都不再起) |
| Postgres 端口 | N/A | `:5433`(对外,避让 host 已有 5432 风险) |
| Docker volume | N/A | `deepagents_pgdata`(`/var/lib/postgresql/data`) |
| 前端启动 | `cd frontend && yarn dev` | `./deepagents.sh start`(内部跑 `npm run start -p 13000`) |
| 前端端口 | `:3000` | `:13000` |
| 浏览器 Deployment URL | `http://127.0.0.1:2024` | `http://192.168.106.114:13000`(前端通过 `next.config.ts` rewrites 反代到 `:12024`) |
| 浏览器 Assistant ID | `research` | `research` |
| `.env` 关键变量 | `DATABASE_URL=sqlite+aiosqlite:///./local.db` + `DASHSCOPE_API_KEY` | `DATABASE_URL=postgresql+asyncpg://postgres:<pwd>@127.0.0.1:5433/postgres` + `DASHSCOPE_API_KEY` |
| Node / Yarn / Python | 20.x / 1.22.22 / 3.11+ | 同左 |
| 验证 git commit | _(填本次验证基于的 commit hash)_ | _(同左)_ |

---

## 1. 启动序列

### 1.1 本地 Macbook(SQLite)

```bash
# 终端 A
cd backend && source .venv/bin/activate
# 首次:pip install -e . 装上 fastapi/uvicorn/langgraph-checkpoint-* 等新依赖
# DATABASE_URL 缺省即 SQLite,可不设
uvicorn server:app --host 0.0.0.0 --port 2024 --reload

# 终端 B
cd frontend && yarn dev

# 浏览器 http://localhost:3000,Deployment URL 填 http://127.0.0.1:2024,Assistant ID 填 research
```

**预期**:
- [ ] backend 日志含 `Lifespan: created AsyncSqliteSaver / setup ok`(具体文本可在 Step 6 调整),无 ERROR
- [ ] `ls backend/local.db` 文件被自动创建
- [ ] frontend 编译成功,console 无 error,smoke demo("你好"→ AI 一句回复)走通

### 1.2 lab host(Postgres docker)

> Step 6 实施时补完整命令、密码生成、镜像缓存确认。

```bash
ssh root@192.168.106.114

# 1) (一次性) 起独立 Postgres docker container
PGPWD=$(openssl rand -hex 16)
docker run -d --name deepagents-postgres \
  --restart unless-stopped \
  -p 5433:5432 \
  -e POSTGRES_PASSWORD="$PGPWD" \
  -v deepagents_pgdata:/var/lib/postgresql/data \
  postgres:16-alpine
echo "DATABASE_URL=postgresql+asyncpg://postgres:${PGPWD}@127.0.0.1:5433/postgres" >> /root/deepagents/backend/.env

# 2) pull feature branch + 重启 backend
cd /root/deepagents
./deepagents.sh stop
git pull origin feat/v0.5.0/001-langgraph-up-deployment   # (该分支含 001 abandoned + 002 实施)
./deepagents.sh start

# 3) 健康检查
docker ps --filter "name=deepagents-postgres" --format "table {{.Names}}\t{{.Status}}"   # 应 Up healthy
curl http://192.168.106.114:12024/ok                                                     # 应 {"ok":true}
ss -ltn | grep -E ":(12024|13000|5433)"                                                  # 三端口都在 LISTEN
```

**预期**:
- [ ] `deepagents-postgres` container Up + healthy
- [ ] uvicorn 进程在 `:12024` LISTEN(`./deepagents.sh status`)
- [ ] `:13000` next-server 仍在(deepagents.sh 也起前端)
- [ ] curl `/ok` 200

---

## 2. AC 逐条验证

### AC-1: 本地 SQLite 启动 + smoke demo

**步骤**(Step 6 补):
1. 按 §1.1 启动
2. 浏览器 smoke:`localhost:3000` 发"你好"
3. `ls backend/local.db` 应存在

**预期**:有 AI 回复;`local.db` 自动创建

**截图**:`./screenshots/ac-1-local-sqlite.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-2: 本地重启后 thread state 完整

**步骤**(Step 6 补):
1. 跑一次完整 demo("帮我调研 bisheng 同类竞品"——澄清 → todos → emit_research_card × N → write_file)直到完结;记录 `thread_id`
2. `curl GET http://127.0.0.1:2024/threads/<id>/state | jq` 存档(`ac-2-state-before.json`)
3. Ctrl-C 杀 backend → 重新 `uvicorn server:app --port 2024`(等 lifespan 完成)
4. 浏览器 F5 同一 thread
5. 对比新 curl 结果与 `ac-2-state-before.json`(忽略 timestamp 差异)

**预期**:state 字段全部一致;画面渲染与重启前一致

**截图**:`./screenshots/ac-2-local-restart.png`(F5 后画面)

**结果**:☐ 通过 / ☐ 不通过

---

### AC-3: lab host Postgres 启动

**步骤**(Step 6 补):按 §1.2 步骤完成 lab host 部署 + 三个健康检查

**预期**:`deepagents-postgres` healthy + uvicorn LISTEN :12024 + curl /ok 200

**截图**:`./screenshots/ac-3-lab-postgres-docker.png`(`docker ps` 全图)

**结果**:☐ 通过 / ☐ 不通过

---

### AC-4: lab host 重启后 thread state 完整

**步骤**(Step 6 补):
1. lab host 浏览器(`http://192.168.106.114:13000`)跑一次完整 demo,记录 `thread_id` + state snapshot
2. ssh lab host:`./deepagents.sh stop && ./deepagents.sh start`(注意 `deepagents-postgres` container **不要碰**)
3. 浏览器 F5 同一 thread
4. 对比 state snapshot

**预期**:state 完整;画面一致

**截图**:`./screenshots/ac-4-lab-restart.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-5: monkey-patch 仍在源码 + DevTools 验证

**步骤**(Step 6 补):
1. `grep -n "stream_mode" frontend/src/app/hooks/useChat.ts` → 应命中 line 58-67 区间
2. 浏览器 DevTools Network → 发起一次 run → 查 `/runs/stream` 请求 body 中 `stream_mode` 数组 → 应**不含** `"tools"`
3. Response 应是 200 + SSE stream(无 422)

**预期**:grep 命中 + body 数组干净 + 200

**截图**:`./screenshots/ac-5-devtools-stream-mode.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-6: 显式 checkpointer + CLAUDE.md 拆分

**步骤**(Step 6 补):
1. `grep -n "checkpointer=" backend/agent.py` → 应命中(在 `build_agent` 内传给 `create_deep_agent`)
2. `grep -A 8 "不要传 \`checkpointer\`" CLAUDE.md` → 应命中"**CLI 模式**" + "**自研 server 模式**" 两段
3. reviewer 走读 CLAUDE.md §强约束 #3 全文,无歧义

**预期**:两个 grep 都命中;reviewer pass

**结果**:☐ 通过 / ☐ 不通过

---

### AC-7: architecture / troubleshooting / README 同步

**步骤**(Step 6 补):
1. `grep -n "langgraph up" CLAUDE.md docs/architecture.md docs/troubleshooting.md README.md` → 应零命中(只 `docs/features/v0.5.0/001-langgraph-up-deployment/` ADR 目录里可命中)
2. `grep -n "uvicorn server:app" CLAUDE.md docs/architecture.md README.md` → 应命中
3. reviewer 走读 README §5 部署小节 + architecture.md §1 总览 + troubleshooting.md §1.5 是否通顺

**预期**:grep 命中预期;reviewer pass

**结果**:☐ 通过 / ☐ 不通过

---

## 3. 回归检查(强约束守护)

> spec.md §4 触碰"是"的条目:**第 3 条**(不传 checkpointer,本 feature 修订为两种 mode 拆分)、**第 7 条**(`useChat.ts` fetch monkey-patch 不删,本 feature 加 422 守护 + 破坏性回归)。

### 必跑回归(对应 spec §4 触碰条目)

- [ ] **第 3 条回归 - 显式 checkpointer**:`grep -n "checkpointer=" backend/agent.py` 至少 1 处命中
- [ ] **第 3 条回归 - CLAUDE.md 拆分文本**:`grep "CLI 模式\|自研 server 模式" CLAUDE.md` 命中两种 mode 各一段
- [ ] **第 7 条回归 - monkey-patch 仍在**:`grep -n "stream_mode" frontend/src/app/hooks/useChat.ts` 命中 line 58-67 区间 + `git diff` 该文件应为空(本 feature 不动它)
- [ ] **第 7 条破坏性回归(关键!)**:
  1. 临时把 `frontend/src/app/hooks/useChat.ts` line 52-77 整段 `useEffect` **手动注释**
  2. `cd frontend && yarn build`(prod build)
  3. 浏览器加载 → 发起一次 run → DevTools 看 `/runs/stream` 响应应是 **HTTP 422**(server 拒掉 stream_mode 含 tools)
  4. **立即取消注释**,`git diff frontend/src/app/hooks/useChat.ts` **必须为空**
  5. `yarn build` 重新 build → 浏览器再发起 run 应回到 200
  - 截图归档 `./screenshots/regression-monkey-patch-422.png`

### 常规回归(其他强约束未触碰,跑一遍兜底)

- [ ] **GenerativeUI 卡片仍渲染**:发出一个会触发 `emit_research_card` 的请求,对话流中 ≥ 1 张 ResearchCard
- [ ] **HITL 仍 dormant**:`grep -n "interrupt_on" backend/agent.py` 应零命中(本 feature 未误启 HITL)
- [ ] **GenerativeUIMiddleware 仍装配**:`grep -n "GenerativeUIMiddleware()" backend/agent.py` 命中
- [ ] **DashScope 模型未被换**:`grep -n "base_url" backend/agent.py` 仍指 dashscope
- [ ] **`streaming=True` 未被改**:`grep -n "streaming" backend/agent.py` 仍为 `True`
- [ ] **prompts.py 强制语序未弱化**:`grep -c "MUST" backend/prompts.py` 与改动前一致(本 feature 不动 prompts.py)

---

## 4. 跨上游适配验证

> spec.md §5 = 否(不动 frontend/),本节整体 **N/A**(破坏性回归已纳入 §3)。

---

## 5. 后端单测

> 本 feature 无新增单测(`server.py` 协议层手动验证 + AC-2/AC-4 重启回归足以保证关键路径)。
>
> **可选**:未来若 server.py 改动频繁,可补 `backend/tests/test_server_endpoints.py`(用 `httpx.AsyncClient` 测 endpoint 子集)。

---

## 6. 截图归档

所有截图放在 `./screenshots/`,命名:
- `ac-1-local-sqlite.png` — 本地 uvicorn + SQLite 启动后 smoke demo
- `ac-2-local-restart.png` — 本地 Ctrl-C 重启后 F5 看到的 thread 完整
- `ac-3-lab-postgres-docker.png` — lab host `docker ps` 看到 `deepagents-postgres` healthy
- `ac-4-lab-restart.png` — lab host `./deepagents.sh stop/start` 后 thread 完整
- `ac-5-devtools-stream-mode.png` — DevTools `/runs/stream` body 不含 "tools"
- `regression-monkey-patch-422.png` — 临时注释 monkey-patch 后 server 返回 422

提 PR 时把这些图附在 PR 描述里给 reviewer。
