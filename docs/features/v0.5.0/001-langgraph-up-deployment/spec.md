# Spec: langgraph up 持久化部署(lab host 双轨) — **ABANDONED**

> ⚠️ **状态:ABANDONED(2026-05-26)** — superseded by [`../002-fastapi-postgres-checkpointer/`](../002-fastapi-postgres-checkpointer/)
>
> **撤回原因**:实施 Step 6 时发现 `langgraph up` 用的 `langchain/langgraph-api:3.11` 是 **LangChain 公司的商业产品 LangGraph Platform**,启动时强制 `LANGSMITH_API_KEY`(Plus 计划) 或 `LANGGRAPH_CLOUD_LICENSE_KEY` 验 license(`ValueError: License verification failed` exit 3,见 tasks.md §"实际偏差记录")。这与 spec 原本"零 LangSmith 依赖"的设计目标冲突,且 lab host docker container outbound HTTPS 被防火墙挡(包括 LangSmith license 验证端点)。
>
> **本 feature 保留作为踩坑 ADR**——记录 LangGraph 三层分层(核心库 OSS / langgraph dev OSS / langgraph up 商业)的认知校准 + lab host 网络限制的实测结果。新方案见 002,走 LangGraph 开源路径(自研轻量 FastAPI server + `langgraph-checkpoint-postgres`)。
>
> ---
>
> Feature ID: `001-langgraph-up-deployment` · 版本归属: `v0.5.0` · Owner: LineWalker · 创建日期: `2026-05-26`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-26 起草;Spec Discovery 4 轮决策 + sdd-review 4 处修订已固化 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☑ | 2026-05-26 · LineWalker ★ 确认 |
| 已完成(verification.md 全绿) | ☒ | **ABANDONED 2026-05-26**(见上方撤回原因);见 002 |

---

## 1. 概述与用户故事

**Feature 描述**:把 lab host (192.168.106.114) 上的 backend 从 `langgraph dev`(in-memory checkpointer)切到 `langgraph up`(docker compose 自带 Postgres + Redis),让 thread state(messages / todos / ui / files)在 backend 进程重启后仍然保留。本地 Macbook 开发不动,仍用 `langgraph dev` 保持热重载体验 —— **双轨制**。

**Context / 来源**:
- 用户口头需求 2026-05-26:lab host 上的 thread `019e5fc6-0bee-70e2-8069-ac0c1d7d7766` 出现"半截画面" bug(参考 `~/.claude/plans/image-1-http-192-168-106-114-13000-assi-fluffy-honey.md`),根因定位为 `langgraph dev` in-memory checkpointer 进程重启即丢全部数据。
- 现有部署文档(`README.md` "启动" 章节、`docs/architecture.md` §1)只写 `langgraph dev`,没有覆盖 lab host 多人访问 + 进程可重启的部署场景。

**用户故事**:

1. 作为 lab host 上访问 demo 的访客用户,我希望即便后端在我离开期间重启过,回到旧 thread 仍能看到完整的会话历史(messages / todos / ui / files),以便不丢失正在进行中的调研。
2. 作为后端开发者(lilu),我希望本地 Macbook 上 `langgraph dev` 的快速热重载 + 零 docker 依赖体验完全不变,仅 lab host 上启用 `langgraph up`,以便不为生产持久化付出本地开发流程成本。
3. 作为 6 个月后回到此项目的 maintainer,我希望 CLAUDE.md §强约束、`docs/architecture.md`、`docs/troubleshooting.md`、`README.md` 同步描述双轨部署模型,以便能快速理解"为什么 dev 和 up 都不传 checkpointer、两者底层差异在哪、什么场景该用哪个"。

**检查点**:
- [x] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [x] 描述里不引入新术语(`langgraph up`、`checkpointer`、`双轨` 均已 ground 在现有 CLAUDE.md / 上游 CLI)

---

## 2. 验收标准 (Acceptance Criteria)

| AC ID | 标准描述 | 验证方式 | verification.md 位置 |
|---|---|---|---|
| AC-1 | 在 lab host 上按 README 文档化的命令启动 `langgraph up`,langgraph-api / Postgres / Redis 三个 container 全部 healthy;`http://192.168.106.114:8123/ok` 返回 `{"ok":true}`(8123 是 `langgraph up` 默认端口) | `docker ps` + `curl /ok` | §2.AC-1 |
| AC-2 | 在 lab host 上跑一遍完整 demo("帮我调研 bisheng 同类竞品"——澄清 → todos → emit_research_card × 3 → write_file)直到完结;`docker kill langgraph-api` 后再 `docker start langgraph-api` 恢复(container 名固定为 `langgraph-api`);同一 thread 重新加载,`messages / todos / ui / files` 全部还在;F5 刷新后画面与重启前一致 | 浏览器手动 + `curl GET /threads/<id>/state` 对比重启前后 JSON | §2.AC-2 |
| AC-3 | 本地 Macbook 上 `cd backend && source .venv/bin/activate && langgraph dev` 仍能正常启动(inmem 模式),不依赖 docker,任何 `langgraph dev` 流程跟改动前完全一致 | 本地终端 + 浏览器 `localhost:3000` | §2.AC-3 |
| AC-4 | `README.md` 的"启动" 章节新增 lab host 部署小节,内容能让一个没看过本 feature 的 reviewer 按步骤把 lab host 部署起来,无歧义;`docs/troubleshooting.md` §1.1 同步扩展到 langgraph up 语境 + 新增 §1.5「backend 重启 thread 数据丢失」条目 | code-review 阶段由 reviewer 试着按文档跑一遍 + `grep -n "langgraph up" README.md docs/troubleshooting.md` 命中预期段落 | §2.AC-4 |
| AC-5 | `CLAUDE.md §强约束` 中"不传 checkpointer"那条更新为"两种 langgraph CLI 模式都自动管,都不要传",并在 `docs/architecture.md §1` 总览图加一段双轨部署说明(`langgraph dev` for local · `langgraph up` for lab host) | `diff` 这几个文件,确认更新点都到位 | §2.AC-5 |

**检查点**:
- [x] 每条 AC 都有唯一 ID
- [x] AC-1/2/3 可手动复现验证;AC-4/5 是文档项,靠 grep + reviewer 走读核对
- [x] AC 数量 5 条(在 3-7 范围内)

---

## 3. 边界情况与非目标

### 3.1 边界情况

- **lab host 端口冲突**:lab host 已跑 bisheng / 1panel / shougang-portal,`langgraph up` 默认端口可能冲突。README 文档化 `--port` / Postgres / Redis 端口可配置的环境变量,部署前先 `lsof -i :<port>` 探活。
- **`docker pull` 拉镜像失败**:lab host 可能没配 registry mirror。README 写明可用 `--base-image <local-cached-image>` 或预先 `docker pull` 镜像。
- **Postgres container 重启后 langgraph-api 短暂不可用**:langgraph 框架内部应有重连,如不自动恢复,文档化 `docker restart <langgraph-api>` 的兜底动作。
- **前端 Deployment URL 漂移**:lab host 上前端通过 `NEXT_PUBLIC_LANGGRAPH_API_URL` 等环境变量配 backend URL(commit `93cb122` / `6155088` 已实装),切到 `langgraph up` 后只需改这个 env var 重新 `next build` 即可;不需要前端代码改动。
- **`langgraph up` 进程被意外重启**:Postgres 数据卷应通过 docker volume 持久化(默认行为),`docker compose down` 不会清数据,只有 `docker compose down -v` 才会清——README 显式提示这点。
- **本地 Macbook 误跑了 `langgraph up`**:理论上能跑,但会拉镜像 + 占资源,不是本期目标。README 在 lab host 小节顶部明确"仅 lab host";本地仍是 `langgraph dev`。

### 3.2 非目标(本期不做)

- **不写 `docker-compose.yml` / `Makefile` / 自动化部署脚本**——`langgraph up` 命令上手敲就行,下个 feature 再考虑复用化。
- **不引入外部 Postgres**——lab host 上已有的 bisheng / 1panel 数据库本期不复用,避免范围蔓延;默认让 `langgraph up` 自带 Postgres container,资源独立。
- **不做 thread 历史数据迁移**——当前 lab host inmem 已丢空,N/A。
- **不改本地开发流程**——本地 Macbook 维持 `langgraph dev`,双轨。
- **不引入 LangSmith Tracing / LangGraph Cloud**——本地 generative UI 还是走本地 bundle(零 CDN 依赖,见 architecture.md §2.4)。
- **不改 backend 业务代码**——`backend/agent.py / tools.py / prompts.py / middlewares.py` 零改动。
- **不引入认证 / 多租户 / 用户隔离**——lab host 仍是内网信任模型,任何访客都能看到所有 thread。
- **不动 frontend/**`** 任何代码**——仅通过 env var 切 Deployment URL。
- **不引入新的强约束**——`CLAUDE.md` 第 3 条只是 contextualize(从"langgraph dev 自动管"扩展为"两种 CLI 模式都自动管"),不是放宽或新增。

**检查点**:
- [x] 边界情况包含至少 1 条"失败/异常路径"(端口冲突、镜像拉取、Postgres 重启)
- [x] 非目标列出明确的、可能被误以为属于本期的事项(docker-compose、外部 Postgres、数据迁移、认证)

---

## 4. 涉及强约束

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☐ 否 | 不动 middleware / `agent.py`。verification.md §3 加回归项:`grep -n "GenerativeUIMiddleware()" backend/agent.py` 仍命中 |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 否 | 不动 `agent.py:26-33` 的 ChatOpenAI 实例化 |
| 不传 `checkpointer` 给 `create_deep_agent` | ☑ 是 | 仍然不传 —— `langgraph up` 跟 `langgraph dev` 一样会自动管 checkpointer(区别仅在底层从 inmem 换 Postgres)。本 feature 通过 `CLAUDE.md` + `docs/architecture.md §2.2` + `docs/troubleshooting.md §1.1` 同步 contextualize 这条约束的语境("两种 langgraph CLI 模式都不要传"),**不放宽约束本身**。verification.md §3 加回归项:`grep -n "checkpointer" backend/agent.py` 应零命中 |
| `streaming=True` 不改回 False | ☐ 否 | 不动 |
| 前端 vendored patch(详见 §5) | ☐ 否 | 不动 frontend `,` |
| HITL 批量审批"全 approve / 全 reject"语义 | ☐ 否 | 不动 |
| `useChat.ts` fetch monkey-patch 不删 | ☐ 否 | N/A(不动 useChat.ts)。但 verification.md §3 加回归项:lab host 部署后切换到一个新 thread,发起 run,无 HTTP 422(确认 `langgraph up` 用的 `langgraph-api` server 仍兼容此 hack,见 `architecture.md §3.3`) |
| `prompts.py` 强制语序不弱化 | ☐ 否 | 不动 prompt |

**检查点**:
- [x] 凡是"是"的条目,缓解策略不为空
- [x] 触碰的条目(第 3 条 + 第 7 条)都在 verification.md §3 加回归项(Step 4 起草 verification.md 骨架时落地)

---

## 5. 前端 patch 影响

**是否动 `frontend/**`**:☐ 否

> 不动 frontend/ 任何代码。Lab host 部署改 backend URL 通过 `NEXT_PUBLIC_*` 环境变量(commit `93cb122` / `6155088` 已实装),不需要任何 patch 改动。

**预计修改的已 patch 文件**:无。

**对 `architecture.md §3.1` patch 表的预期更新**:无(本 feature 不增不删 patch)。

**检查点**:
- [x] 不动 `frontend/`,留底命令在 tasks.md 不必出现(Step 6 第一步可跳过)
- [x] 不新增/不删除 patch,§3.1 表无需更新

---

## 6. 实现概要 & 文件清单

**实现思路**(Spec Discovery 4 轮决策固化):

1. **部署模式**:lab host 用 `langgraph up`(决策点 1 选项"双轨保留"),本地 Macbook 保留 `langgraph dev`,两套并存。
2. **Postgres 来源**:让 `langgraph up` 自带(决策点 2 选项"先用自带"),不复用 lab host 已有 Postgres,避免引入外部依赖。
3. **资源分配**:接受默认 3 个 container 模式(决策点 3 选项"可以起",langgraph-api + Postgres + Redis),不做最小化定制。
4. **部署产物形态**:本期不写 `docker-compose.yml` 或 `Makefile`(决策点 4 选项"只改启动命令 + README"),用 `langgraph up` 原生 CLI;下次需要复用化再单独立项。
5. **零代码改动**:`backend/agent.py / tools.py / prompts.py / middlewares.py / langgraph.json` 全部不动 —— `create_deep_agent` 不传 `checkpointer` 在 `langgraph up` 模式下仍然正确(`langgraph up` 也自动管)。
6. **文档同步是本 feature 的实质工作量**:CLAUDE.md §强约束第 3 条 contextualize、`docs/architecture.md §1` 总览图加双轨说明、`docs/architecture.md §2.2` 末尾加"`langgraph up` 与 `langgraph dev` 都自动管 checkpointer"小节、`docs/troubleshooting.md §1.1` 扩展语境 + 新增 §1.5「backend 重启 thread 数据丢失」、`README.md` 启动章节加 lab host 小节。
7. **`.env.example` 增量**:加 `LANGGRAPH_PORT`、`POSTGRES_PORT`、`REDIS_PORT` 占位(均带默认值,可不改)。**不加** `LANGSMITH_API_KEY` 占位 —— `docs/architecture.md §2.4` 已明确"零 LangSmith 依赖、零 CDN 依赖",加占位会让后人误以为需要接入。未来若真需要接 LangSmith,单独开 feature 再加。
8. **验证策略**:AC-1/2/3 是 lab host 实际部署 + 浏览器跑通 + docker kill 重启验证;AC-4/5 是文档 grep + reviewer 走读。

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `README.md` | 修改 | "启动" 章节新增 "lab host 部署(`langgraph up`)" 小节:命令、端口、Postgres 数据卷、Deployment URL env var 配置、F5 验证持久化 |
| `backend/.env.example` | 修改 | 加 `LANGGRAPH_PORT` / `POSTGRES_PORT` / `REDIS_PORT` 占位与说明(不加 `LANGSMITH_API_KEY`,理由见 §6 实现思路第 7 点) |
| `CLAUDE.md` | 修改 §强约束 | 第 3 条 "不要在 `create_deep_agent` 里传 `checkpointer`" 重写 —— 明确"`langgraph dev` 跟 `langgraph up` 都自动管,任一模式都不要传" |
| `docs/architecture.md` | 修改 §1 + §2.2 | §1 系统总览图末尾加"双轨部署"段(本地 dev / lab host up);§2.2 末尾"另一个状态层约束"段语境扩展,补充 `langgraph up` 也自动管 |
| `docs/troubleshooting.md` | 修改 §1.1 + 新增 §1.5 | §1.1 标题与说明扩展到 langgraph up 语境;新增 §1.5「(lab host) backend 重启后 thread 数据丢失」——给出诊断步骤(curl GET /state、F5 验证、ps -o lstart 看启动时间)+ 解决方案(切 langgraph up 或接受 demo 限制) |
| `docs/features/v0.5.0/001-langgraph-up-deployment/{spec,tasks,verification}.md` | 新建 | SDD 三件套(本文 + Step 4 起草) |

**检查点**:
- [x] 文件清单与 §4-§5 标记一致(动 frontend 的 patch 文件无,§5 已声明)
- [x] 不引入新机制(纯部署模式切换 + 文档同步),架构文档同步项已列(§1 + §2.2)
- [x] 不出现大段代码块(具体命令文本留给 tasks.md 起草 Step 4)
