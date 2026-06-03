# Tasks: Skills 加载 + per-run 白名单(端到端最小纵切)

> Spec: [`./spec.md`](./spec.md)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 完成全部任务条目后勾选 |
| 已评审(`/sdd-review tasks` 通过) | ☑ | 2026-06-03(sdd-review 自动通过) |
| 已完成(所有任务 ✅ + 三层测试全绿) | ☑ | 2026-06-03(pytest 31 / vitest 4 / e2e 3 全绿) |

---

## 开发模式

- **后端 Test-First**:`SkillWhitelistMiddleware`(T3→T4)、skills 扫描纯函数 + 路由(T5→T6)按"测试 → 实现"配对,测试任务在前。SKILL.md / 装配是基础设施,无测试配对。
- **前端 Test-Alongside**:`SkillsPopover` 组件实现 + vitest 同任务(T7)。
- **E2E 强制**:UI 交互 AC-5 由末尾 Playwright fixture 任务(T8)覆盖。
- **自包含**:每个任务内联文件、逻辑、验证、AC,实现时无需回读 spec.md。

---

## 任务依赖

```
T1 (前端 patch 留底)
 └─ T2 (SKILL.md + SKILLS_ROOT + FilesystemBackend 装配)
      ├─ T3 (后端测试: 白名单, 红) ─ T4 (SkillWhitelistMiddleware + 接线 + arch 断言, 绿)
      └─ T5 (后端测试: 路由, 红) ── T6 (list_skills/get_skill 纯函数 + server 路由, 绿)
                                          └─ T7 (前端 SkillsPopover + vitest + 接线)
                                               └─ T8 (E2E + fixture + architecture.md 文档)
```

---

## 任务清单

### T1 — 前端 patch 留底

- **状态**:☑ 已完成
- **文件**:`/tmp/patches-001.diff`(产物,非仓库文件)
- **逻辑**:Step 6 第一动作。本 feature 触碰 vendored 已 patch 文件(ChatInterface.tsx / useChat.ts / config.ts),改动前先 `cd frontend && git diff > /tmp/patches-001.diff` 留底,便于日后 `git apply` 回贴。
- **验证方式**:`无`(基础设施)。`test -s /tmp/patches-001.diff` 或确认命令已执行。
- **覆盖 AC**:无(强约束守护,spec §5)
- **依赖**:无

### T2 — built-in deep-research SKILL.md + SKILLS_ROOT + FilesystemBackend 装配

- **状态**:☑ 已完成
- **文件**:`backend/data/skills/built-in/deep-research/SKILL.md`(新建)、`backend/agent.py`(改:加 `SKILLS_ROOT` 常量 + import `FilesystemBackend`)
- **逻辑**:新建内建 skill 文件——YAML frontmatter `name: deep-research`(**必须等于目录名**)、`description`(≤1024 字符,用强动词描述"何时用此 skill:用户要研究/调研/对比某主题时");body 为**附加式**研究流程指引(progressive disclosure,可复述既有研究流程要点,**但不删/不改 `prompts.py`,不搬强制语序**)。`agent.py` 加 `SKILLS_ROOT = os.path.join(os.path.dirname(__file__), "data", "skills")`,import `from deepagents.backends.filesystem import FilesystemBackend`。确认 `backend/.gitignore` 不排除 `data/`(spec §3.1 / 风险 R6)。
- **验证方式**:`无`(基础设施;加载行为由 T5/T6 路由测试 + T3 中间件测试间接覆盖)
- **覆盖 AC**:AC-2, AC-3(数据前提)
- **依赖**:T1

### T3 — 后端测试:白名单过滤(先红)

- **状态**:☑ 已完成
- **文件**:`backend/tests/test_skill_whitelist.py`(新建)
- **逻辑**:测 `SkillWhitelistMiddleware.modify_request` 过滤逻辑。monkeypatch `langgraph.config.get_config` 返回 `{"configurable": {"active_skills": [...]}}`,构造 fake `ModelRequest`(`state["skills_metadata"]` 含 2 个 skill metadata,name 各异),断言渲染后 system message:
  - `active_skills=["deep-research"]` → 只含 deep-research、不含另一个;
  - `active_skills=None` → 两个都在(不过滤);
  - `active_skills=[]` → 零 skill(走 "(No skills available)" 分支);
  - `active_skills=["nonexistent"]` → 零 skill(交集,静默忽略未知名)。
- **验证方式**:`pytest::test_skill_whitelist`(红→绿)→ AC-1
- **覆盖 AC**:AC-1
- **依赖**:T2

### T4 — SkillWhitelistMiddleware + agent.py 接线 + arch 断言(后红→绿)

- **状态**:☑ 已完成
- **文件**:`backend/middlewares.py`(改:加类)、`backend/agent.py`(改:接线)、`backend/tests/test_arch_invariants.py`(改:加断言)
- **逻辑**:在 `middlewares.py` 加 `SkillWhitelistMiddleware(SkillsMiddleware)`:`modify_request` 中用 `get_config()`(try/except→`None`)读 `configurable.active_skills`;非 `None` 时按 name 交集过滤 `request.state["skills_metadata"]`(浅拷贝 state 后替换),再 `super().modify_request()` 一次渲染。imports:`from deepagents.middleware.skills import SkillsMiddleware`、`from langgraph.config import get_config`。**不动 `GenerativeUIMiddleware`**。`agent.py` 的 `build_agent` 内:构造 `backend = FilesystemBackend(root_dir=SKILLS_ROOT)` + `skills_mw = SkillWhitelistMiddleware(backend=backend, sources=["/built-in/"])`,给 `create_deep_agent` 传 `backend=backend` + `middleware=[skills_mw, GenerativeUIMiddleware()]`;**不传 `skills=` / `context_schema=`**;ChatOpenAI/DashScope、checkpointer、streaming、prompts、subagents 全不动。`test_arch_invariants.py` 加断言:装配后的 middleware 栈含 `GenerativeUIMiddleware` 实例,且 `SkillWhitelistMiddleware` 索引 < `GenerativeUIMiddleware` 索引(AC-6)。
- **验证方式**:T3 全过(红→绿);`pytest::test_arch_invariants`(AC-6 新断言绿)。smoke:`python -c "from agent import build_agent; build_agent(None)"` 不报错且 deep-research 被加载(风险 R3)。
- **覆盖 AC**:AC-1, AC-6
- **依赖**:T3

### T5 — 后端测试:skills 路由契约(先红)

- **状态**:☑ 已完成
- **文件**:`backend/tests/test_skills_routes.py`(新建)
- **逻辑**:用 FastAPI `TestClient(app)`(同既有 server 测试 pattern)测两条只读路由:
  - `GET /api/skills` → 200;返回 list;含 `name=="deep-research"` 的项,键集 `{id,name,description,source,path}`,`id=="built-in/deep-research"`、`source=="built-in"`、`path` 以 `/built-in/` 开头(AC-2);
  - `GET /api/skills/built-in/deep-research` → 200;`instructions` 非空字符串(SKILL.md body)(AC-3);
  - `GET /api/skills/built-in/does-not-exist` → 404(AC-3)。
- **验证方式**:`pytest::test_skills_routes`(红→绿)→ AC-2, AC-3
- **覆盖 AC**:AC-2, AC-3
- **依赖**:T2

### T6 — list_skills/get_skill 纯函数 + server.py 路由(后红→绿)

- **状态**:☑ 已完成
- **文件**:`backend/agent.py`(改:加纯函数)、`backend/server.py`(改:加路由)
- **逻辑**:`agent.py` 加共享纯函数 `list_skills() -> list[dict]` 与 `get_skill(skill_id) -> dict | None`:`os.walk(SKILLS_ROOT)` 找 `SKILL.md`,正则切 `^---\n(.*?)\n---`(同上游)+ `yaml.safe_load` 解析 frontmatter,组装 `{id: "{source}/{name}", name, description, source, path}`;`get_skill` 额外带 `instructions`(frontmatter 之后的 body);frontmatter 解析失败 / 无 SKILL.md 的目录跳过(容错,spec §3.1)。`server.py` 加 `GET /api/skills`(返回 `list_skills()`)与 `GET /api/skills/{skill_id:path}`(`get_skill`,`None`→`HTTPException(404)`),置于 `/info` 附近 Assistants 段之前;`{skill_id:path}` 转换器处理 id 中的斜杠(风险 R4)。
- **验证方式**:T5 全过(红→绿)
- **覆盖 AC**:AC-2, AC-3
- **依赖**:T5

### T7 — 前端 SkillsPopover + vitest + ChatInterface/useChat 接线(Test-Alongside)

- **状态**:☑ 已完成
- **文件**:`frontend/package.json`(改:加 `@radix-ui/react-popover`)、`frontend/src/components/ui/popover.tsx`(新建)、`frontend/src/lib/config.ts`(改)、`frontend/src/app/components/SkillsPopover.tsx`(新建)、`frontend/src/app/components/SkillsPopover.test.tsx`(新建)、`frontend/src/app/components/ChatInterface.tsx`(改)、`frontend/src/app/hooks/useChat.ts`(改)
- **逻辑**:`npm install --legacy-peer-deps @radix-ui/react-popover`;`ui/popover.tsx` 薄封装(镜像 `dialog.tsx`/`switch.tsx`)。`config.ts`:`StandaloneConfig` 加 `activeSkillIds?: string[]`(存 skill **name**),加 `getActiveSkillIds()/saveActiveSkillIds(ids)` 合并进同一 `deep-agent-config` 对象(不 clobber deploymentUrl/assistantId,SSR guard)。`SkillsPopover.tsx`:PopoverTrigger 按钮(Skills 标签 + `activeCount>0` 时 chip);PopoverContent 拉 `GET {resolveDeploymentUrl}/api/skills` 渲染每行 name+description+`Switch`(reuse `ui/switch.tsx`),toggle 翻转 `activeSkillIds` 并 `saveActiveSkillIds`。`ChatInterface.tsx` 底部 bar(`flex justify-between` ~542 行)**左侧**放 `SkillsPopover`,持有 `activeSkillIds` state(init 自 `getActiveSkillIds()`)传给 hook;不碰 broadcastResumeInterrupt。`useChat.ts` **仅 ~103-119 行** `stream.submit` config 加 `configurable: { active_skills: activeSkillIds ?? [] }` 并把 `activeSkillIds` 入 useCallback deps;**52-77 行 fetch monkey-patch 绝不动**。`SkillsPopover.test.tsx`(镜像 `ResearchCard.test.tsx`):mock fetch `/api/skills` 返 2 skill,断言渲染两项 name+desc;toggle 一个 Switch → 激活态翻转 + chip 计数变 + `localStorage["deep-agent-config"].activeSkillIds` 写入。
- **验证方式**:`vitest::SkillsPopover` → AC-4
- **覆盖 AC**:AC-4(并为 AC-5 提供接线)
- **依赖**:T6

### T8 — E2E skills-whitelist + fixture + architecture.md 文档

- **状态**:☑ 已完成
- **文件**:`frontend/e2e/skills-whitelist.spec.ts`(新建)、`frontend/e2e/fixtures/skills-whitelist.ts`(新建)、`docs/architecture.md`(改 §2.5 + §3.1)
- **逻辑**:Playwright fixture 模式(扩展 `research-card.spec.ts` 的 seedConfig + mockBackend)。新增 `page.route('**/api/skills', ...)` 返 1-2 个 canned skill;复用 `researchCardStream()` 作 `/runs/stream` 的 SSE 响应。流程:`page.goto('/')` → 打开 Skills popover → 勾选 deep-research 的 Switch → 发送消息 → 拦截 `POST **/runs/stream` 请求体,断言 `config.configurable.active_skills` 含 `"deep-research"`。另跑既有 `research-card.spec.ts` 确认无回归。`architecture.md`:新增 §2.5 "Skills 系统"(加载/白名单/progressive disclosure 机制 + SkillWhitelistMiddleware 子类化决策);§3.1 patch 表加 3 条(ChatInterface 底部 bar / useChat submit config / `@radix-ui/react-popover` 依赖 + config.ts)。
- **验证方式**:`e2e::skills-whitelist`(最多 3 轮修复)→ AC-5
- **覆盖 AC**:AC-5
- **依赖**:T7

> 任务数 8 个(在 3-8 建议区间上限)。

---

## AC 覆盖反查

| AC | 由哪些任务覆盖 | 验证测试 |
|---|---|---|
| AC-1 | T3, T4 | `pytest::test_skill_whitelist` |
| AC-2 | T2, T5, T6 | `pytest::test_skills_routes`(list) |
| AC-3 | T2, T5, T6 | `pytest::test_skills_routes`(detail + 404) |
| AC-4 | T7 | `vitest::SkillsPopover` |
| AC-5 | T7, T8 | `e2e::skills-whitelist` |
| AC-6 | T4 | `pytest::test_arch_invariants` |

---

## 实际偏差记录

> 实现中如发现与 spec.md 不符,**立刻在此登记**,并在 PR 描述指向本节。严重偏离(改 AC、改强约束触碰判断)必须回 Step 2 重走 `/sdd-review spec`。

| 日期 | 任务 | 偏差描述 | 处理决定(回改 spec / 接受偏差 / 撤回任务) |
|---|---|---|---|
| 2026-06-03 | T4 | spec §5.1 / PRD 草图把 `backend=FilesystemBackend(...)` 传给 `create_deep_agent`。实测发现:(a) `SkillsMiddleware` 用自己构造的 `backend` 读 skill(`_get_backend`),无需 agent 级 backend;(b) 给 `create_deep_agent(backend=)` 会把 agent 的 `write_file`/`export_docx` 从默认 state 虚拟文件系统换成真磁盘,属回归。 | **接受偏差**:`backend=` 只传给 `SkillWhitelistMiddleware`,不传给 `create_deep_agent`;skill backend 加 `virtual_mode=True`(让 `/built-in/` 相对 root 解析 + 路径约束)。不改 AC、不触新强约束,故不回 Step 2。 |
| 2026-06-03 | T7 | spec §6 设想"ChatInterface 持有 activeSkillIds state 传入 hook"。实际 `useChat` 在 `ChatProvider` 里实例化(经 context 消费),逐层传 prop 需改 ChatProvider。 | **接受偏差**:改为 `SkillsPopover` 写 localStorage、`useChat.sendMessage` 提交时 `getActiveSkillIds()` 读最新值。来源同为白名单,不碰 ChatProvider、patch 更小;AC-4/AC-5 由 vitest+e2e 验证不受影响。 |
| 2026-06-03 | T8 | spec §6 写"architecture.md 新增 §2.5 Skills 系统"。 | **接受偏差**:§2.5 编号已被"多格式报告产物"占用,实际新增为 **§2.7**(§2.6 之后)。纯文档编号,无功能影响。 |
| 2026-06-03 | T4(合并后修正) | 本地体验发现:`active_skills=[]`/无命中时,基类 `SkillsMiddleware` 仍渲染一段 "(No skills available)" 空壳(~1982 字符),与 PRD §5.2"白名单为空→不注入任何 skill 段"不符。原 spec §3.1/AC-1 把这当成"走空分支"接受了。 | **回改 spec(同 feature)**:`SkillWhitelistMiddleware.modify_request` 在过滤后 `kept` 为空时直接 `return request`(整段不注入);更新 AC-1 + §3.1 措辞;`test_skill_whitelist` 改断"整段不注入"。后续修正分支 `fix/v0.6.0/001-empty-whitelist-skip-injection`。 |
