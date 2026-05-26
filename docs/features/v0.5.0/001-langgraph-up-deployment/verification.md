# Verification: langgraph up 持久化部署(lab host 双轨)

> Spec: [`./spec.md`](./spec.md) · Tasks: [`./tasks.md`](./tasks.md)
>
> **本文档是 feature 完成的最终凭证。** 所有 AC 必须在此手动验证通过;所有触碰的强约束必须在 §3 回归检查中确认仍生效。
>
> **当前是骨架版**(Step 4 起草),§1 / §2 / §3 步骤细节在 Step 6 实施过程中补全。

## 状态

| 阶段 | 状态 | 验证日期 | 验证人 |
|---|---|---|---|
| 全部 AC 验证通过 | ☐ | | |
| 全部回归检查通过 | ☐ | | |
| 截图已附在 `./screenshots/` | ☐ | | |

---

## 0. 环境信息

**双轨部署**:本地 Macbook 走 `langgraph dev`(inmem),lab host 走 `langgraph up`(Postgres)。两套都要 verify。

| 项 | 本地 Macbook | lab host (192.168.106.114) |
|---|---|---|
| 后端启动命令 | `cd backend && source .venv/bin/activate && langgraph dev` | `cd backend && langgraph up` |
| 后端端口 | `:2024` | `:8123`(默认,可 `--port` override) |
| Checkpointer | langgraph-runtime-inmem(进程内) | langgraph-api docker container + 自带 Postgres docker container |
| Container 名(若有) | 无 | `langgraph-api` / `langgraph-postgres-*` / `langgraph-redis-*` |
| 前端启动命令 | `cd frontend && yarn dev` | `cd frontend && yarn build && yarn start`(或前端单独部署;参考 commit `bd486e1`/`6155088`) |
| 前端端口 | `:3000` | `:13000`(参考现有 lab host 部署) |
| 浏览器 Assistant ID | `research` | `research` |
| `.env` 必填 | `DEEPAGENTS_MODEL`、`DASHSCOPE_API_KEY` | 同左 |
| Node / Yarn | 20.x / 1.22.22 | 20.x / 1.22.22 |
| 验证 git commit | _(填本次验证基于的 commit hash)_ | _(同左)_ |

---

## 1. 启动序列

### 1.1 本地 Macbook(`langgraph dev`,验证未受改动影响)

```bash
# 终端 A
cd backend && source .venv/bin/activate && langgraph dev

# 等 backend 显示 "Application startup complete" 后,开终端 B
cd frontend && yarn dev

# 浏览器打开 http://localhost:3000,Assistant ID 填 research
```

**预期**:
- [ ] backend 日志无 ERROR / 无未处理异常,启动到 `:2024`
- [ ] frontend 编译成功,浏览器 console 无 error
- [ ] 发出一条 smoke 消息("hi")得到回复

### 1.2 lab host (`langgraph up`)

> Step 6 实施时补完整命令、镜像拉取耗时、可能的端口冲突调整。

```bash
# ssh 到 lab host
ssh <user>@192.168.106.114

# 切到项目路径
cd <project-path>/backend

# 启动(首次拉镜像可能慢)
langgraph up   # → :8123

# 健康检查
curl http://192.168.106.114:8123/ok           # 预期 {"ok":true}
docker ps --format 'table {{.Names}}\t{{.Status}}'  # 预期看到 langgraph-api / langgraph-postgres-* / langgraph-redis-* 全部 (healthy)
```

**预期**:
- [ ] 三个 docker container 都 Up (healthy)
- [ ] `/ok` 返回 200 + `{"ok":true}`
- [ ] 浏览器打开 `http://192.168.106.114:13000`(或 lab host 上前端的实际地址),Deployment URL 配置指向 `http://192.168.106.114:8123`,能加载会话列表

---

## 2. AC 逐条验证

### AC-1: lab host 起得来 + 三 container healthy

**步骤**(Step 6 补):
1. 按 §1.2 启动 `langgraph up`
2. `docker ps` 看三 container 状态
3. `curl /ok`

**预期**:三 container 都 `Up (healthy)`,`/ok` 返回 `{"ok":true}`

**截图**:`./screenshots/ac-1-docker-ps.png`

**结果**:☐ 通过 / ☐ 不通过(备注:______)

---

### AC-2: docker kill langgraph-api 后,thread state 仍完整

**步骤**(Step 6 补):
1. 浏览器在 lab host 前端发起完整 demo("帮我调研 bisheng 同类竞品"),走完澄清 → todos → emit_research_card × N → write_file 直到完结
2. 记录 thread id;`curl GET http://192.168.106.114:8123/threads/<id>/state` 存档 JSON(命名 `ac-2-state-before.json`)
3. `docker kill langgraph-api` 然后 `docker start langgraph-api`(等 healthy)
4. 浏览器重新打开同一 thread URL(或 F5)
5. 对比:messages / todos / ui / files 数组长度是否与 step 2 一致;`curl GET .../state` 与 `ac-2-state-before.json` diff 应只有 timestamp 差异

**预期**:thread state 字段全部一致,画面渲染与重启前一致

**截图**:`./screenshots/ac-2-thread-persist-before.png`、`./screenshots/ac-2-thread-persist-after.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-3: 本地 langgraph dev 不受影响

**步骤**(Step 6 补):
1. 按 §1.1 启动本地 `langgraph dev` + `yarn dev`
2. 发起一次完整 demo 跑通(不必长时间)
3. 确认 backend 日志无新报错,前端无异常

**预期**:与改动前体验完全一致(零回归)

**截图**:`./screenshots/ac-3-langgraph-dev-local.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-4: README + troubleshooting 文档完整可执行

**步骤**(Step 6 补):
1. 让一个没参与本 feature 的 reviewer(或自己扮演)按 `README.md` 新增的 "lab host 部署" 小节走一遍命令
2. 让 reviewer 在遇到"backend 重启数据丢失"现象时按 `docs/troubleshooting.md §1.5` 排查
3. `grep -n "langgraph up" README.md docs/troubleshooting.md` 命中预期段落
4. `grep -n "§1.5\|backend 重启" docs/troubleshooting.md` 命中

**预期**:reviewer 无歧义、无卡住;grep 全部命中

**结果**:☐ 通过 / ☐ 不通过

---

### AC-5: CLAUDE.md + architecture.md 文档同步

**步骤**(Step 6 补):
1. `grep -n "langgraph up" CLAUDE.md docs/architecture.md` 命中预期段落(§强约束第 3 条 + §1 总览图 + §2.2 末尾)
2. reviewer 走读:CLAUDE.md §强约束第 3 条新文本是否清晰区分"dev / up 都不要传 checkpointer"
3. docs/architecture.md §1 总览图后是否能看到双轨部署说明
4. docs/architecture.md §2.2 末尾是否同步更新

**预期**:三处文档都命中,reviewer 走读无歧义

**结果**:☐ 通过 / ☐ 不通过

---

## 3. 回归检查(强约束守护)

> spec.md §4 触碰"是"的条目:**第 3 条**(不传 checkpointer)。本 feature 是通过 contextualize 文档来覆盖,核心代码不动。
> spec.md §4 表第 7 条标"否"但有 verification 回归项(spec §4 第 7 条缓解策略列说明),需要在 lab host 切到新 thread 验证 fetch monkey-patch 仍生效。

### 必跑回归(对应 spec §4 触碰条目)

- [ ] **未传 checkpointer(回归核心)**:`grep -n "checkpointer" backend/agent.py` 应零命中(确认本 feature 没误加 `checkpointer=`)
- [ ] **fetch monkey-patch 仍生效**(spec §4 第 7 条回归项):lab host 部署后,浏览器打开新 thread 发起 run,DevTools Network 查看 `/runs/stream` 请求 body,`stream_mode` 数组**不含** `"tools"`;响应**不是** 422

### 常规回归(其他强约束未触碰,跑一遍兜底)

- [ ] **GenerativeUI 卡片仍渲染**:发出一个会触发 `emit_research_card` 的请求,对话流中看到 ≥ 1 张 ResearchCard
- [ ] **HITL 仍 dormant**(架构 §2.3):`grep -n "interrupt_on" backend/agent.py` 应零命中(确认本 feature 没误启 HITL)
- [ ] **DashScope 模型未被换**:`grep -n "ChatOpenAI\|base_url" backend/agent.py` 仍命中 DashScope `base_url`
- [ ] **`streaming=True` 未被改**:`backend/agent.py` 中 `streaming` 参数仍为 `True`
- [ ] **prompts.py 强制语序未弱化**:`grep -n "MUST" backend/prompts.py` 命中数与改动前一致(本 feature 不动 prompts.py)
- [ ] **GenerativeUIMiddleware 仍装配**:`grep -n "GenerativeUIMiddleware()" backend/agent.py` 命中

---

## 4. 跨上游适配验证

> spec.md §5 = 否(不动 frontend/),本节整体 **N/A**。

---

## 5. 后端单测

> 本 feature 无新增单测(纯部署模式 + 文档变更)。

---

## 6. 截图归档

所有截图放在 `./screenshots/`,命名:
- `ac-1-docker-ps.png` — lab host 三 container healthy
- `ac-2-thread-persist-before.png` / `ac-2-thread-persist-after.png` — docker kill 重启前后的 thread 渲染对比
- `ac-3-langgraph-dev-local.png` — 本地 dev 模式不受影响
- `ac-4-readme-walkthrough.png`(可选)— README 步骤走读
- `ac-5-claude-md-diff.png`(可选)— CLAUDE.md §强约束第 3 条 diff

提 PR 时把这些图附在 PR 描述里给 reviewer。
