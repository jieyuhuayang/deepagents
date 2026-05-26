# Tasks: langgraph up 持久化部署(lab host 双轨)

> Spec: [`./spec.md`](./spec.md) · Verification: [`./verification.md`](./verification.md)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-26 |
| 已评审(`/sdd-review tasks` 通过) | ☑ | 2026-05-26 · 自动通过 |
| 已完成(所有任务 ✅ + verification.md 全绿) | ☐ | — |

---

## 任务依赖

任务数 = 5,画文字依赖图:

```
T1 (lab host langgraph up 部署体验 + README 启动小节)  ──┐
T2 (backend/.env.example 增量)                          ├──→ T5 (verification.md 全跑通 + 截图归档)
T3 (CLAUDE.md §强约束 + docs/architecture.md §1 + §2.2)  ┤
T4 (docs/troubleshooting.md §1.1 扩展 + §1.5 新增)        ┘
```

并行机会:T1 / T2 / T3 / T4 完全独立,可全部并行起;T5 收尾。**建议 T1 最先动**——实地跑 `langgraph up` 会暴露端口 / container 名 / 镜像拉取等细节,反馈给 spec.md 调整(若有偏差登记到 §"实际偏差记录")。

不动 `frontend/`,因此**没有前端 patch 留底任务**(spec §5 = 否)。

---

## 任务清单

### T1 — lab host 跑通 `langgraph up` + README 启动小节

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26)
- **文件**:`README.md`(修改)
- **逻辑**:
  1. ssh 到 lab host 192.168.106.114,确认 docker / docker compose 可用(`docker --version` / `docker compose version`)。
  2. 在 lab host 上 `cd <项目路径>/backend`,执行 `langgraph up`(首次会拉 `langchain/langgraph-api` / `postgres` / `redis` 镜像,可能慢)。等三个 container 都 `Up (healthy)`。
  3. `curl http://192.168.106.114:8123/ok` 期望 `{"ok":true}`;`docker ps` 期望看到 `langgraph-api` / `langgraph-postgres-*` / `langgraph-redis-*`(以实际名字为准——若不是 `langgraph-api`,登记到本 tasks.md §"实际偏差记录",回 spec §AC-2 修)。
  4. 把跑通的实际命令、端口、container 名、镜像 tag 固化到 `README.md`,放在现有"启动"章节之后,新增小节 `### 5. lab host 部署(`langgraph up`)`。内容包含:
     - 前置(docker / docker compose 安装,镜像可达)
     - 启动命令(若需 `--port` / `--postgres-uri` override 给出示例)
     - 健康检查(curl /ok + docker ps)
     - 前端 Deployment URL 配置(指向 commit `93cb122` 的 `NEXT_PUBLIC_*` 环境变量 + `next build`)
     - 数据卷与持久化说明(默认 docker volume,`docker compose down` 不清,只有 `down -v` 才清)
     - 与本地 `langgraph dev` 的区别一句话表(端口 8123 vs 2024 / Postgres vs inmem)
  5. README 现有"### 4. 浏览器配置"小节里 Deployment URL 写的是 `http://127.0.0.1:2024`,**不动**(这是本地 dev 默认);在新加的 lab host 小节里给 lab host 的 URL `http://192.168.106.114:8123`。
- **验证方式**:verification.md §1.2(lab host 启动序列) + §2.AC-1
- **覆盖 AC**:AC-1, AC-4(README 部分)
- **依赖**:无

### T2 — `backend/.env.example` 加端口占位

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26)
- **文件**:`backend/.env.example`(修改)
- **逻辑**:在文件末尾追加 lab host 部署可选 env 注释段:
  ```
  # ─── lab host 部署(langgraph up)可选,本地 langgraph dev 用不到 ───
  # LANGGRAPH_PORT=8123      # langgraph-api 对外端口
  # POSTGRES_PORT=5433       # 自带 Postgres 对外端口(避免与 host 已有 5432 冲突)
  # REDIS_PORT=6380          # 自带 Redis 对外端口
  ```
  全部以 `# ` 注释开头,**不给默认导出值**——`langgraph up` CLI 有自己的默认,只在端口冲突时 override。**不加** `LANGSMITH_API_KEY` 占位(spec §6 第 7 点 + §6 文件清单 .env.example 一行已说明理由)。
- **验证方式**:`grep -c "^# LANGGRAPH_PORT" backend/.env.example` ≥ 1 且 `grep -c "LANGSMITH_API_KEY" backend/.env.example` = 0
- **覆盖 AC**:AC-1(部署可定制),AC-4(文档完整性)
- **依赖**:无

### T3 — `CLAUDE.md` §强约束第 3 条 contextualize + `docs/architecture.md` §1 + §2.2 同步

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26)
- **文件**:`CLAUDE.md`(修改 §强约束)、`docs/architecture.md`(修改 §1 + §2.2)
- **逻辑**:
  1. `CLAUDE.md` §强约束第 3 条 "不要在 `create_deep_agent` 里传 `checkpointer` / `MemorySaver`。`langgraph dev` 自动管 checkpointer,传了启动失败。" 重写为:**两种 langgraph CLI 模式(`langgraph dev` 内置 inmem checkpointer / `langgraph up` 自带 Postgres checkpointer)都会自动管,都不要传**。指向 `docs/architecture.md §2.2` 末尾段的完整解释。
  2. `docs/architecture.md` §1 系统总览图末尾追加段落,讲双轨部署:
     - 本地 Macbook 开发: `langgraph dev`(:2024,inmem,热重载,无 docker)
     - lab host 多人共享: `langgraph up`(:8123,Postgres 持久化,docker compose 起 3 个 container)
     - 两种模式下 `backend/agent.py` 代码完全一致(`create_deep_agent` 不传 `checkpointer`),仅启动命令不同
  3. `docs/architecture.md` §2.2 末尾 "另一个状态层约束" 段(当前讲 `langgraph dev` 自动管 checkpointer 那句)改写为:
     - 通用表述:**`langgraph dev` 与 `langgraph up` 都自动管 checkpointer**,前者 inmem(进程重启即丢)、后者 Postgres(持久化),用户在 `create_deep_agent` 里**任一模式都不要再传** `checkpointer=`,传了启动失败。
     - 加一句"何时该用哪个": 本地开发用 dev、多人共享或要持久化用 up,详见 `docs/features/v0.5.0/001-langgraph-up-deployment/spec.md`。
- **验证方式**:`grep -n "langgraph up" CLAUDE.md docs/architecture.md` 命中预期段落 + verification.md §2.AC-5 reviewer 走读
- **覆盖 AC**:AC-4(architecture.md 部分),AC-5
- **依赖**:无

### T4 — `docs/troubleshooting.md` §1.1 扩展 + 新增 §1.5

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-26)
- **文件**:`docs/troubleshooting.md`(修改 §1.1 + 新增 §1.5)
- **逻辑**:
  1. §1.1 标题保留"langgraph dev 启动报 'checkpointer not necessary'";正文最后追加一句:**`langgraph up` 同理**——`langgraph up` 内部也自动管 Postgres checkpointer,`agent.py` 里**不要**传 `checkpointer=`,传了同样启动失败。
  2. 新增 §1.5「(lab host)backend 重启后 thread 数据丢失」,内容:
     - **现象**:lab host 上 backend 重启后,旧 thread 在浏览器还能看到部分 UI(澄清卡 / todo list),但 messages 中间过程全部缺失;F5 后整个 thread 变空白。
     - **根因**:`langgraph dev` 用 in-memory checkpointer,进程重启即清空所有 thread state。浏览器看到的旧数据来自 React 内存里"断线前的 SSE 快照",并非真实持久化的 state。详见 plan `~/.claude/plans/image-1-http-192-168-106-114-13000-assi-fluffy-honey.md` 的根因诊断。
     - **诊断三步**:
       1. `curl GET http://<lab-host>:<port>/threads/<id>/state | jq '{n_messages: (.values.messages|length), n_todos: (.values.todos|length)}'` —— 如果 messages/todos 都是 0,说明 backend 这边确实没了。
       2. F5 刷新前端页面 —— 如果之前的"半截画面"变空白,说明确实是浏览器 React 内存快照在撑场面。
       3. `docker ps --filter name=langgraph-api --format '{{.Status}}'` 或 `ps -o lstart` 看 backend 进程启动时间 —— 大概率晚于 thread 创建时间。
     - **解决**:lab host 部署改用 `langgraph up`(切到 Postgres 持久化),具体见 `docs/features/v0.5.0/001-langgraph-up-deployment/` + `README.md` "lab host 部署" 小节。本地 demo 接受 inmem 限制(重启就重来即可)。
- **验证方式**:`grep -n "§1.5\|backend 重启" docs/troubleshooting.md` 命中 + verification.md §2.AC-4
- **覆盖 AC**:AC-4(troubleshooting 部分),AC-5
- **依赖**:无

### T5 — `verification.md` 全跑通 + 截图归档

- **状态**:☐ 待开始 / ☑ 进行中(2026-05-26,等 lab host 实地操作 + 用户对齐切换方式) / ☐ 已完成
- **文件**:`./verification.md`、`./screenshots/`(填充)
- **逻辑**:
  1. 按 verification.md §1.1 跑本地 `langgraph dev` smoke test → 验证 AC-3
  2. 按 verification.md §1.2 跑 lab host `langgraph up` 启动序列 → 验证 AC-1
  3. 按 verification.md §2.AC-2 跑完整 demo + `docker kill langgraph-api` + 重启 + F5 验证 thread 持久 → 验证 AC-2
  4. 按 verification.md §3 跑强约束回归(grep `checkpointer` agent.py 应零命中 + lab host 切到新 thread 发起 run 无 422)
  5. 按 verification.md §2.AC-4/5 文档项:reviewer(或自己再扮演 reviewer)按 README + troubleshooting 的步骤走一遍,确认无歧义;grep CLAUDE.md / architecture.md 应命中"langgraph up"
  6. 截图归档 `./screenshots/`:`ac-1-docker-ps.png`、`ac-2-thread-persist-before.png`、`ac-2-thread-persist-after.png`、`ac-3-langgraph-dev-local.png`
  7. 全绿后勾选 verification.md 状态表三行 + 本 tasks.md "已完成" 行 + spec.md "已完成" 行
- **验证方式**:verification.md 自身的状态表三行全勾
- **覆盖 AC**:全部(AC-1 ~ AC-5,收尾验证)
- **依赖**:T1, T2, T3, T4

---

## AC 覆盖反查

| AC | 由哪些任务覆盖 |
|---|---|
| AC-1(lab host langgraph up 起得来) | T1, T2, T5(verify) |
| AC-2(docker kill + restart 后 thread state 完整) | T1, T5(verify) |
| AC-3(本地 langgraph dev 不受影响) | T5(verify) |
| AC-4(README + troubleshooting 文档同步) | T1, T4, T5(verify) |
| AC-5(CLAUDE.md + architecture.md 文档同步) | T3, T5(verify) |

每条 AC 至少被 1 个任务覆盖 ✓;任务引用的 AC ID 全部存在于 spec.md §2 ✓。

---

## 实际偏差记录

> 实现过程中如发现与 spec.md 不符(AC 调整、文件清单变化、边界情况新增、缓解策略变更等),**立刻在此登记**,并在 PR 描述里指向本节。
>
> **不允许"先实现再决定"**——若需偏离,先评估是否回 spec.md 修订。严重偏离(改 AC、改强约束触碰判断)必须回 Step 2 重新走 `/sdd-review spec`。

| 日期 | 任务 | 偏差描述 | 处理决定(回改 spec / 接受偏差 / 撤回任务) |
|---|---|---|---|
| _(YYYY-MM-DD)_ | T_(N)_ | _(在此填写)_ | _(在此填写)_ |
| 2026-05-26 | T2 | 实施前发现 `backend/.env.example` line 21-23 已有 `LANGSMITH_API_KEY` 注释占位(从仓库历史看,跟本 feature 无关,原本就在)。spec §6 第 7 点写"不加 LANGSMITH_API_KEY 占位"指的是本 feature **不新增**,与"现状已有"不冲突。 | **接受偏差,不回改 spec** —— 本 feature T2 实施时仅追加 lab host 端口段(`LANGGRAPH_PORT` / `POSTGRES_PORT` / `REDIS_PORT`),**不动**已有的 LANGSMITH 占位行。若未来要拆掉 LANGSMITH 占位,单开 feature 处理。 |
| 2026-05-26 | T1 | lab host 侦察(ssh root@192.168.106.114)发现:(1)现有 backend 跑在 `langgraph dev :12024`(由 `/root/deepagents/deepagents.sh start` 起);(2)host 装了原生 redis-server `:6379`,与 `langgraph up` 自带 Redis 容器默认端口冲突,必须 `REDIS_PORT=6380` override;(3)`:8123`/:5432 空闲。spec.md §3.1 边界情况"lab host 端口冲突"和 §6 第 7 点已经预留处理空间,但具体冲突点(redis :6379)需要 README 显式写出。 | **接受偏差,不回改 spec** —— T1 README "lab host 部署" 小节增加 §5.4 "端口配置(冲突时 override)" 子节,显式说明 `REDIS_PORT=6380` 是 lab host 必需。`deepagents.sh` **不动**(仍可用于 dev 模式;只新增"切换到 up 前先 `./deepagents.sh stop`" 一行说明),保留双轨可切换能力。verification.md §1.2 启动序列已包含 `./deepagents.sh stop` 前置步骤。 |
| 2026-05-26 | T5 | T5 verification 跑通需要 lab host 上从 `langgraph dev` 切到 `langgraph up`(停现有 backend / 拉镜像 / 起 3 个 container / 改前端 build 用新 Deployment URL),会停摆部署 5-30 分钟。memory `feedback_shared_lab_host_scope.md` 要求"kill/重启 lab host 上的进程"前先问用户。 | **暂停 T5,等用户对齐切换方案** —— 关键决策点:(a) 这次只是"实地验证"还是"永久切到 up"?(b) 镜像拉取要不要 registry mirror?(c) 拉完测完是否要保留 langgraph up 作为常驻部署、还是验证完切回 langgraph dev。等用户答复后再 ssh 操作。**用户答复:(a) 永久切换 (b) 直接拉先试 (c) 永久部署。开始实施 lab host 操作。** |
| 2026-05-26 | T5 | 首次跑 `langgraph up` 在 docker build step "pip install" 失败:container 内 `https://pypi.org/simple/ddgs/` 连接被拒(`Connection refused`)。诊断:host 能直连 pypi.org(HTTP 200, 0.96s),container 内不能(被防火墙挡);国内 mirror (tuna/aliyun/tencent) 全部可达。**spec.md §6 文件清单没列 `pip.conf` 或 `langgraph.json` 改动**,但这是实施时发现的真实约束——docker container 在 lab host 网络下必须走国内 pip mirror。 | **接受偏差,不回改 spec** —— 范围内最小修复:(1) 新建 `backend/pip.conf`,index-url 指向 `pypi.tuna.tsinghua.edu.cn`;(2) `backend/langgraph.json` 加 `"pip_config_file": "./pip.conf"`,让 `langgraph build` / `langgraph up` 在 docker container 内用这套 pip 配置。本地 Macbook `langgraph dev` 不走 docker build,pip.conf 对本地无影响。AC 不变(AC-1 仍是"三 container healthy");这条偏差是部署环境网络限制的"修复路径",可写进 README §5.2 注脚补充说明,但不在本期范围。 |
| 2026-05-26 | T5 | 加了 `pip_config_file` 后第二次跑 `langgraph up` 仍失败:`PIP_CONFIG_FILE=/pipconfig.txt` env 已正确注入 container,但 build 内用的是 **`uv pip install`**(`langgraph-api:3.11` base image 强制 uv),**uv 不读 pip.conf**,继续连 pypi.org failed。 | **接受偏差,在已登记的"实际偏差记录"基础上加 `dockerfile_lines` 字段** —— `backend/langgraph.json` 增加 `"dockerfile_lines": ["ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/"]`,让 uv 在 docker build 时走 tuna mirror。pip.conf 保留(作为非 uv 路径的兜底),`UV_INDEX_URL` 是真正生效的设置。架构 §3 没有提到 langgraph build 用的是 uv 而非 pip 这个细节(因为之前都用 langgraph dev,不走 build);完成后建议在 architecture.md 加一句说明。 |
