# Spec: Skills 加载 + per-run 白名单(端到端最小纵切)

> Feature ID: `001-skill-loading-whitelist` · 版本归属: `v0.6.0` · Owner: lilu · 创建日期: `2026-06-03`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 完成 §1-§6 后勾选 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☑ | 2026-06-03 / sdd-review + lilu 确认 |
| 已完成(三层测试全绿) | ☑ | 2026-06-03(pytest 31 / vitest 4 / e2e 3) |

---

## 1. 概述与用户故事

> 用一段话讲清"这个 feature 是什么、给谁用、解决什么痛点",然后列 1-3 条用户故事。可引用 `docs/prds/` 的 PRD 作为 Context。

**Feature 描述**:把 deepagents 0.6.3 内置的 `SkillsMiddleware`(Anthropic Agent Skills,progressive disclosure)接入本项目,并在其上加一层 **per-run 白名单**:用户在前端聊天框旁开关 skill,后端只把激活的 skill metadata 注入 system prompt。本期是端到端最小纵切 —— 后端机制 + 只读 API + 1 个 built-in skill + 前端 Popover 开关,验证"加载 + 白名单 + 随 run 传递"链路打通。

**Context / 来源**:[`docs/prds/0.6.0/skills.md`](../../../prds/0.6.0/skills.md)(§4 前端方案 / §5 后端 Context Engineering / §8 P0)。Step 1 采访 2026-06-03 四项决策全选推荐项:① 端到端最小纵切;② 本期**不抽取** `prompts.py` 研究流程(built-in skill 为附加内容);③ CRUD API 挂进自研 `server.py` 同端口 2024;④ 新增 `@radix-ui/react-popover` 依赖。上传/编辑/删除 CRUD、`/skills` 管理页、`.zip`、interpreter、prompts 抽取均留作 002+。

**用户故事**:

1. 作为**研究员**,我希望在聊天框旁看到可开关的 skill 列表并勾选 deep-research,以便本轮对话带上对应的领域流程指引、而闲聊时关掉以减少 prompt 噪声。
2. 作为**维护者**,我希望"激活哪些 skill"作为 per-run 白名单随请求提交、后端据此过滤注入,以便同一份已加载的 skill 集合能按对话动态取舍,不必每轮重载或改源码。

**检查点**:
- [x] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [x] 描述里不引入新术语(progressive disclosure / 白名单 均沿用 PRD 术语)

---

## 2. 验收标准 (Acceptance Criteria)

> AC 是 feature 是否"完成"的唯一裁判。每条 AC 的"验证方式"必须落到具体自动化测试。

| AC ID | 标准描述 | 验证方式 | 覆盖测试/任务 |
|---|---|---|---|
| AC-1 | `SkillWhitelistMiddleware` 按 `config.configurable.active_skills` 过滤注入:给定 2 个 skill 的 `skills_metadata`,`active_skills=["deep-research"]` 渲染的 system message 只含 deep-research;`None` 全注入;`[]` 或过滤后无命中 → 整段 skills **不注入**(system prompt 保持原样,不留 "No skills available" 空壳) | `pytest::test_skill_whitelist` | T3, T4 |
| AC-2 | `GET /api/skills` 返回 200 + 列表,含 deep-research,每项有 `{id,name,description,source,path}`,`id=="built-in/deep-research"`、`source=="built-in"` | `pytest::test_skills_routes` | T5, T6 |
| AC-3 | `GET /api/skills/built-in/deep-research` 返回 200 + 非空 `instructions`(SKILL.md body);不存在的 id 返回 404 | `pytest::test_skills_routes` | T5, T6 |
| AC-4 | `SkillsPopover` 渲染拉取到的 skill 列表;toggle 一个 Switch 翻转其激活态、active-count chip 同步、`deep-agent-config.activeSkillIds` 写入 localStorage | `vitest::SkillsPopover` | T8 |
| AC-5 | UI 流程:打开 Skills popover → 勾选 deep-research → 发送消息 → `POST /runs/stream` 请求体 `config.configurable.active_skills` 含 `"deep-research"` | `e2e::skills-whitelist` | T8, T9 |
| AC-6 | 强约束回归:装配后的 agent middleware 栈仍含 `GenerativeUIMiddleware`,且 `SkillWhitelistMiddleware` 排在其之前 | `pytest::test_arch_invariants` | T4, T10 |

**检查点**:
- [x] 每条 AC 有唯一 ID,tasks.md 引用同一 ID
- [x] 每条 AC 的验证方式指向一个可自动跑的测试(三层之一)
- [x] UI 交互类 AC 至少 1 条由 `e2e::` 覆盖(AC-5)
- [x] AC 数量 6 条(3-7 区间内)

---

## 3. 边界情况与非目标

### 3.1 边界情况

> 系统应正确处理但不属于主流程的场景。

- **白名单缺省(旧客户端 / `/info` smoke)**:请求未带 `active_skills`(key 缺失)→ 中间件读到 `None` → **不过滤,全注入**(安全默认,兼容)。
- **全部关闭**:`active_skills=[]`(或过滤后无命中)→ 整段 skills **不注入**(system prompt 保持原样,不留 "(No skills available)" 空壳,对齐 PRD §5.2),agent 正常对话不报错。
- **白名单含未知 skill 名**:`active_skills` 含磁盘上不存在的 name → 取交集,静默忽略,不报错。
- **`get_config()` 在 graph run 之外被调用**(理论上中间件不会触发)→ try/except 兜底返回 `None`(不过滤)。
- **`/api/skills/{id}` id 含斜杠**(`built-in/deep-research`)→ 用 `{skill_id:path}` 转换器匹配,避免 FastAPI 路径参数截断。
- **SKILL.md frontmatter 解析失败 / 目录无 SKILL.md**:扫描时跳过该目录,不让整个列表 500(本期只读,容错降级)。

### 3.2 非目标(本期不做)

> 显式列出"看起来相关但本期不做"的事。

- 上传 / 新建 / 编辑 / 删除 skill(`POST/PUT/DELETE`)—— 002。
- `/skills` 管理页、详情页、Source 编辑器、Tab —— 002。
- `.zip` 上传 + zip-slip 防御 —— 002。
- Interpreter skill(`module:` + 沙箱 + HITL)—— P2。
- **把 `prompts.py` 研究流程抽进 SKILL.md / prompts 瘦身** —— 独立 feature(本期 built-in skill 为附加内容,`prompts.py` 强制语序原样保留)。
- skill 跨 source 同名覆盖、使用统计、token 估算 chip —— 后续。
- subagent(research-agent)级别的 skill 注入 —— 本期仅主 agent。

**检查点**:
- [x] 边界情况含至少 1 条"失败/异常路径"(frontmatter 解析失败、未知 skill 名)
- [x] 非目标列出可能被误以为属于本期的事项(CRUD、抽取 prompts)

---

## 4. 涉及强约束

> 列出本 feature 触碰 [`CLAUDE.md` §强约束](../../../../CLAUDE.md) 的哪几条。

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☑ 是 | 保留实例,`middleware=[SkillWhitelistMiddleware(...), GenerativeUIMiddleware()]` —— 只在其前面新增,不删不改。AC-6 + `test_arch_invariants` 断言其仍在栈内且顺序正确。 |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 否 | 不动 `model` 实例化。 |
| checkpointer 传法(自研 server 必传) | ☐ 否 | `build_agent(checkpointer)` 签名与传参语义不变,仍由 server lifespan 注入。 |
| `streaming=True` 不改回 False | ☐ 否 | 不动。 |
| 前端 vendored patch(详见 §5) | ☑ 是 | 详见 §5(改 ChatInterface.tsx + useChat.ts,新增 popover 依赖)。 |
| HITL 批量审批"全 approve / 全 reject"语义 | ☐ 否 | 本期不碰 `interrupt_on` / HITL 链路。 |
| `useChat.ts` fetch monkey-patch 不删 | ☑ 是 | **仅改 `stream.submit` 的 config(~103-119 行)**,绝不动 52-77 行 fetch 拦截 `useEffect`。§5 勾选 + `/code-review` 守。 |
| `prompts.py` 强制语序不弱化 | ☐ 否 | 本期**不抽取**研究流程,`prompts.py` 一字不改;built-in SKILL.md 为附加内容。 |

**检查点**:
- [x] 凡"是"的条目缓解策略不为空
- [x] 触碰的可机检项确认 arch-guard / `test_arch_invariants` 仍覆盖:GenerativeUIMiddleware 由 AC-6 新增断言;useChat monkey-patch 由 arch-guard grep + 不改 52-77 行保证。

---

## 5. 前端 patch 影响

> 本节识别本 feature 是否影响 vendored patch,以及测试栈自身是否新增 patch。

**是否动 `frontend/**`**:☑ 是

**预计修改的已 patch 文件**(勾选):
- [x] `frontend/src/app/components/ChatInterface.tsx`(broadcastResumeInterrupt)—— 底部 bar 左侧新增 `SkillsPopover`,不碰 broadcastResumeInterrupt 逻辑
- [ ] `frontend/src/app/components/ChatMessage.tsx`
- [ ] `frontend/src/app/components/ToolCallBox.tsx`
- [x] `frontend/src/app/hooks/useChat.ts`(fetch monkey-patch + StateType.files 放宽)—— **仅** `stream.submit` config 加 `configurable.active_skills`,52-77 行 monkey-patch 不动
- [ ] `frontend/src/app/components/generative-ui/{ResearchCard,ClarificationCard,registry}.tsx`
- [x] 其他既有 patch 文件:`frontend/src/lib/config.ts`(`StandaloneConfig` 加 `activeSkillIds`)

**新增前端文件**(非 patch,新增不影响 `git apply`):`frontend/src/components/ui/popover.tsx`、`frontend/src/app/components/SkillsPopover.tsx`、`frontend/src/app/components/SkillsPopover.test.tsx`、`frontend/e2e/skills-whitelist.spec.ts`、`frontend/e2e/fixtures/skills-whitelist.ts`。

**测试栈新增 patch**:
- [x] 新增 `@radix-ui/react-popover` 运行时依赖(`package.json`)—— 算 vendored 副本本地新增,登记到 architecture.md §3.1。

**留底命令**(实施 Step 6 第一动作):
```bash
cd frontend && git diff > /tmp/patches-001.diff
```

**对 architecture.md §3.1 patch 表的预期更新**:新增 3 处条目 —— (a) ChatInterface.tsx 底部 bar 加 Skills popover;(b) useChat.ts submit config 注入 `active_skills`;(c) 新增 `@radix-ui/react-popover` 依赖 + `config.ts` `activeSkillIds`。另新增 §2.5 "Skills 系统"小节描述加载/白名单机制。

**检查点**:
- [x] 若动 `frontend/`,留底命令是 tasks.md 第一个任务(T1)
- [x] 改动/新增的前端组件有配对 `vitest::` 测试(`SkillsPopover.test.tsx`,见 §2 AC-4)

---

## 6. 实现概要 & 文件清单

> 概要描述实现思路(3-5 句话),列出新增/修改的文件。

**实现思路**:后端用 `FilesystemBackend(root_dir=backend/data/skills)` + 自定义 `SkillWhitelistMiddleware(SkillsMiddleware)` 子类接入 —— 子类在 `modify_request` 渲染前按 `langgraph.config.get_config()` 里的 `active_skills` 过滤 `state["skills_metadata"]`,做到"一次渲染、按 run 取舍"(避开"注入后再 strip"的脆弱路径);**不传 `skills=` 给 `create_deep_agent`**(否则会自动多插一个全量 SkillsMiddleware),改为自己构造实例放进 `middleware=[...]`,排在 `GenerativeUIMiddleware` 之前。`agent.py` 同时提供共享纯函数 `list_skills()/get_skill(id)`(os.walk + pyyaml frontmatter 解析),给 `server.py` 的两条只读路由复用、并可脱离 TestClient 单测。前端在聊天框底部加 `SkillsPopover`(新 popover 依赖),拉 `GET /api/skills` 渲染开关、持久化 `activeSkillIds` 到 `deep-agent-config`,经 `useChat` 的 `stream.submit` config 以 `configurable.active_skills` 提交。

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/data/skills/built-in/deep-research/SKILL.md` | 新建 | 内建 skill(frontmatter `name`/`description` + 附加式研究流程指引;不动 prompts.py) |
| `backend/middlewares.py` | 修改 | 新增 `SkillWhitelistMiddleware(SkillsMiddleware)`;`GenerativeUIMiddleware` 不动 |
| `backend/agent.py` | 修改 | `SKILLS_ROOT` 常量、`FilesystemBackend`、中间件接线、`list_skills()/get_skill()` 纯函数 |
| `backend/server.py` | 修改 | 新增 `GET /api/skills`、`GET /api/skills/{skill_id:path}` 两条只读路由 |
| `backend/tests/test_skill_whitelist.py` | 新建 | AC-1 白名单过滤三分支 pytest(先红) |
| `backend/tests/test_skills_routes.py` | 新建 | AC-2/AC-3 路由契约 pytest(TestClient,先红) |
| `backend/tests/test_arch_invariants.py` | 修改 | AC-6 新增"GenerativeUI 仍在栈 + 顺序"断言 |
| `frontend/package.json` | 修改 | 加 `@radix-ui/react-popover` |
| `frontend/src/components/ui/popover.tsx` | 新建 | Radix Popover 薄封装 |
| `frontend/src/lib/config.ts` | 修改 | `activeSkillIds` 持久化(`get/saveActiveSkillIds`) |
| `frontend/src/app/components/SkillsPopover.tsx` | 新建 | 列表 + Switch + active-count chip |
| `frontend/src/app/components/SkillsPopover.test.tsx` | 新建 | 组件 vitest(AC-4) |
| `frontend/src/app/components/ChatInterface.tsx` | 修改 | 底部 bar 接入 SkillsPopover + 持有 activeSkillIds |
| `frontend/src/app/hooks/useChat.ts` | 修改 | submit config 加 `configurable.active_skills`(仅 ~103-119 行) |
| `frontend/e2e/skills-whitelist.spec.ts` + `fixtures/skills-whitelist.ts` | 新建 | UI 交互 E2E(AC-5,fixture 模式) |
| `docs/architecture.md` | 修改 §2.5 + §3.1 | 新增 Skills 系统小节 + patch 表 3 条 |

**检查点**:
- [x] 文件清单与 §2(测试文件)、§4-§5(强约束/patch 文件)一致
- [x] 引入新机制(SkillWhitelistMiddleware + 新前端组件树)→ architecture.md §2.5/§3.1 同步项已列
- [x] 无大段代码块(长度控制在 2 屏内)
