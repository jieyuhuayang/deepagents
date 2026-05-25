# Spec: Skills Runtime(P0)

> Feature ID: `001-skills-runtime` · 版本归属: `v0.2.0` · Owner: `lilu` · 创建日期: `2026-05-24`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-24 起草完成 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☐ | 待评审 |
| 已完成(verification.md 全绿) | ☐ | |

---

## 1. 概述与用户故事

**Feature 描述**:把 deepagents 的 Anthropic Agent Skills 能力作为一等公民引入项目。P0 范围聚焦"运行时装配":磁盘加载 → 白名单过滤 → 注入 prompt → 前端聊天框可挑选。完整 Skills 管理 UI(`/skills` 页 + .zip 上传 + 编辑器)留给后续 feature(`002-skills-management-ui`)。

**Context / 来源**:[`docs/prds/skills.md`](../../../prds/skills.md) §1-§5 + §8 P0 范围。

**用户故事**:

1. 作为 **新用户**,打开网站后看到一个 "Deep Research" skill 已默认启用,直接问 "调研 X" 仍能得到完整研究流程(从 `prompts.py` 抽出到 skill 后,行为不退化)。
2. 作为 **聊天用户**,在聊天框旁能"+ Skills" Popover 中勾选/取消 skill,激活白名单跨 thread 持久化,本轮 run 实际生效的 skill 数量可见。
3. 作为 **本地用户**,把一个写好的 `<name>/SKILL.md` 放进 `backend/data/skills/personal/`,重启后端后能在前端 Popover 看到它出现,且勾选后立即生效。

**检查点**:
- [x] 至少 1 条用户故事写明 `角色 / 能力 / 价值`(3 条均符合)
- [x] 描述里不引入新术语(skill / frontmatter / progressive disclosure 均来自 PRD,已通用)

---

## 2. 验收标准 (Acceptance Criteria)

| AC ID | 标准描述 | 验证方式 | verification.md 位置 |
|---|---|---|---|
| AC-1 | 后端启动时扫 `backend/data/skills/built-in/deep-research/SKILL.md` 并加载,backend 日志能见 `SkillsMiddleware loaded N skill(s)`(N ≥ 1) | 后端日志 | §2.AC-1 |
| AC-2 | `GET http://localhost:2024/api/skills` 返回 JSON 数组,元素含 `{name, description, source}` 字段,deep-research 在列 | curl + 浏览器 DevTools | §2.AC-2 |
| AC-3 | 前端聊天框左下角出现 "+ Skills" Popover 按钮,展开后列表含 deep-research,默认勾选;form 上方 chip 区显示 "1 skill active" | 浏览器手动 | §2.AC-3 |
| AC-4 | 取消勾选 deep-research 后,提问 "调研一下 Rust async runtime",对话流**不再**走 plan→sub-agent→ResearchCard 完整流程,变成主 agent 直接答 | 浏览器对比,需对比"勾选前"与"勾选后"两次响应 | §2.AC-4 |
| AC-5 | 重新勾选 deep-research 后,同一提问恢复完整研究流程;且 ResearchCard 仍渲染、HITL 审批卡照常弹出(强约束回归)| 浏览器手动 + §3 回归检查 | §2.AC-5 |

**检查点**:
- [x] 每条 AC 有唯一 ID,后续 tasks.md 引用同一 ID
- [x] 所有 AC 可在本地 `langgraph dev` + `yarn dev` 复现
- [x] AC 数量 5 条,在 3-7 范围内

---

## 3. 边界情况与非目标

### 3.1 边界情况

- **白名单为空数组**:前端传 `active_skills: []` → 后端不注入任何 skill 段(允许用户全关)。
- **白名单字段缺失**:前端没传 `active_skills`(初次访问 / localStorage 损坏)→ 后端走 deepagents 默认行为(全部加载到的 skill 都注入)。
- **白名单引用不存在的 skill name**:后端忽略该项,不报错,只注入命中的 skill。
- **`data/skills/` 目录不存在或为空**:后端启动不应崩溃,`/api/skills` 返回 `[]`,前端 Popover 显示 "No skills available, drop SKILL.md into backend/data/skills/personal/"。
- **`SKILL.md` frontmatter 解析失败**:后端日志 WARN 跳过该文件,不阻塞其他 skill 加载。

### 3.2 非目标(本期不做)

- 完整 Skills 管理页(`/skills` 路由 + 详情 + 编辑器):留给 `002-skills-management-ui`。
- `.zip` 上传 + zip-slip 防御:留给 `002-skills-management-ui`。
- "Create with editor"浏览器内编辑:留给 `002-skills-management-ui`。
- Interpreter skill(`module:` 字段 + sandbox):留给 `003-skills-interpreter`。
- Skill 使用统计 / 上次触发时间:不在 v0.2.0 范围。
- 多用户隔离 / 鉴权:demo 项目,不做。
- skill 推荐/搜索/智能排序:Popover 列表按 name 字典序即可。
- `POST /api/skills/upload`(P0 仅前端只读消费 + 后端从磁盘加载;上传 P1 做)。

**检查点**:
- [x] 边界情况含至少 1 条失败/异常路径(frontmatter 解析失败)
- [x] 非目标显式列出可能被误以为属于本期的事项(管理页、上传、interpreter)

---

## 4. 涉及强约束

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☑ 是 | 在 middleware 链中**保留** `GenerativeUIMiddleware`;新增 `SkillWhitelistMiddleware` 排在它**之前**(顺序:Skills → Whitelist → GenerativeUI)。verification.md §3 会回归"ResearchCard 仍渲染"。 |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 否 | 不动 `model = ChatOpenAI(...)` 实例化。 |
| 不传 `checkpointer` 给 `create_deep_agent` | ☐ 否 | 仅追加 `backend=`、`skills=`、`context_schema=`、`middleware=` 四个 kwargs;不传 `checkpointer`。 |
| `streaming=True` 不改回 False | ☐ 否 | 不动。 |
| 前端 vendored patch(详见 §5) | ☑ 是 | 详见 §5。 |
| HITL 批量审批"全 approve / 全 reject"语义 | ☐ 否 | 不改 `ToolApprovalInterrupt` / `broadcastResumeInterrupt`;P0 不引入 interpreter skill 故不新增 `interrupt_on` 键。 |
| `useChat.ts` fetch monkey-patch 不删 | ☑ 是 | 只改 `stream.submit` 入参(第 91-106 行附近,加 `config.configurable.active_skills`);**不动** monkey-patch 区(第 44-69 行)。verification.md §3 回归"网络面板 stream_mode 不含 tools"。 |
| `prompts.py` 强制语序不弱化 | ☑ 是 | 把"MUST call `emit_research_card` before `write_file`"等强制语序**搬到** `deep-research/SKILL.md` body,`prompts.py` 主 prompt 追加"You MUST read applicable skill via `read_file` before executing tools"。verification.md §3 回归"调研类问题模型先 emit_research_card 再 write_file"。 |

**检查点**:
- [x] 凡是"是"的条目,缓解策略均非空
- [x] 触碰的条目在 verification.md §3 有对应回归项

---

## 5. 前端 patch 影响

**是否动 `frontend/**`**:☑ 是

**预计修改的已 patch 文件**(勾选):
- [x] `frontend/src/app/components/ChatInterface.tsx`(broadcastResumeInterrupt 不动;新增 Popover 入口)
- [ ] `frontend/src/app/components/ChatMessage.tsx`(不动)
- [ ] `frontend/src/app/components/ToolCallBox.tsx`(不动)
- [x] `frontend/src/app/hooks/useChat.ts`(只改 `stream.submit` 第 91-106 区,**不动** monkey-patch 第 44-69 区)
- [ ] `frontend/src/app/components/generative-ui/registry.tsx`(不动)
- [ ] `frontend/src/app/components/generative-ui/ResearchCard.tsx`(不动)
- 其他既有 patch 文件:无

**留底命令**(实施 Step 6 第一动作必须执行):

```bash
cd frontend && git diff > /tmp/patches-001.diff
```

**对 architecture.md §3.1 patch 表的预期更新**:无新增/删除 patch 条目(`ChatInterface.tsx` / `useChat.ts` 已在 §3.1 patch 表中)。但 `useChat.ts` patch 条目的描述可扩充一行"submit 入参带 `active_skills`",在 tasks.md T8 同步。

**检查点**:
- [x] 留底命令在 tasks.md 是第一个任务(T1)
- [x] 不新增/删除 patch,故 §3.1 表无结构性更新

---

## 6. 实现概要 & 文件清单

**实现思路**:
1. 后端 `agent.py` 装配时把 `FilesystemBackend` 注入 `create_deep_agent`,通过 `skills=["/built-in/", "/personal/"]` 与 `context_schema=AgentContext` 让 deepagents 自动扫盘加载并支持 per-run 白名单。
2. 新增 `SkillWhitelistMiddleware` 在 `middlewares.py`,排在 `GenerativeUIMiddleware` 之前;读 `context.active_skills` 过滤 `SkillsMiddleware` 注入的 frontmatter 段。
3. 在 langgraph dev 同端口挂 FastAPI 子路由 `/api/skills`(GET 单复数),用 `langgraph.json` 的 `http.app` 字段自定义 ASGI 入口扩展(若不支持,改用独立 `uvicorn` 第 2025 端口,前端配置 `skillsApiUrl`——P0 先做同端口,失败则降级)。
4. 把 `prompts.py` 的研究流程 + emit_research_card 强制语序整段抽到 `backend/data/skills/built-in/deep-research/SKILL.md`;`ORCHESTRATOR_PROMPT` 末尾追加"必须读 skill"指引段。
5. 前端 `ChatInterface.tsx` 表单底部 bar 加 "+ Skills" Popover(用 shadcn/radix Popover,需 `yarn add @radix-ui/react-popover` + 写 `popover.tsx`);Popover 列表从 `/api/skills` 拉。
6. `useChat.ts` 在 `stream.submit` 入参 `config.configurable` 中加 `active_skills`(从 `lib/config.ts` 新增的 localStorage 字段读)。

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/agent.py` | 修改 | 加 `FilesystemBackend(root_dir=...)` + `skills=[...]` + `context_schema=` + 把 `SkillWhitelistMiddleware` 加进 `middleware=` 链 |
| `backend/middlewares.py` | 修改 | 新增 `SkillWhitelistMiddleware` + `AgentContext` Pydantic schema(字段 `active_skills: list[str] \| None`) |
| `backend/prompts.py` | 修改 | 主 prompt 抽研究流程到 skill + 追加"必须读 skill"指引段 |
| `backend/api/__init__.py` | 新建 | API 子模块占位 |
| `backend/api/skills.py` | 新建 | FastAPI Router:`GET /api/skills`、`GET /api/skills/{name}`(P0 只读,不含 POST/PUT/DELETE)|
| `backend/langgraph.json` | 修改 | 加 `http.app` 字段挂自定义 ASGI(若 langgraph dev 不支持,改 backend/.env.example 加 `SKILLS_API_PORT` 走独立端口) |
| `backend/data/skills/built-in/deep-research/SKILL.md` | 新建 | 内建 skill,装 `prompts.py` 抽出来的研究流程 + emit_research_card 强制语序 |
| `backend/.env.example` | 修改 | 加 `DEEPAGENTS_SKILLS_ROOT=./data/skills` |
| `backend/pyproject.toml` | 可能修改 | 若 `langgraph.json` 自定义 ASGI 需要,加 `fastapi` 依赖(确认 deepagents 是否已传递依赖) |
| `frontend/src/app/components/ChatInterface.tsx` | 修改 | 表单底部 bar 加 "+ Skills" Popover 按钮 + active 数量 chip |
| `frontend/src/app/components/Skills/SkillsPopover.tsx` | 新建 | Popover 子组件(从 `/api/skills` 拉列表 + 勾选切换 + 写 localStorage) |
| `frontend/src/components/ui/popover.tsx` | 新建 | shadcn 风格 Popover 包装(基于 `@radix-ui/react-popover`) |
| `frontend/package.json` | 修改 | 加 `@radix-ui/react-popover` 依赖 |
| `frontend/src/app/hooks/useChat.ts` | 修改 | `stream.submit` 入参 `config.configurable.active_skills`(**不动** 44-69 monkey-patch) |
| `frontend/src/lib/config.ts` | 修改 | 加 `activeSkillIds: string[]` localStorage 字段 |
| `docs/architecture.md` | 修改 §2 + §3.1 | 新增 §2.5 "Skills 系统"(中间件链 / 加载流程 / 白名单语义);§3.1 patch 表中 `useChat.ts` 条目描述追加 "submit 带 active_skills" |
| `docs/troubleshooting.md` | 可能修改 | 若 P0 实施时碰到 `langgraph dev` 不支持自定义 ASGI 的故障,新增对应排错条目 |

**检查点**:
- [x] 文件清单与 §4-§5 标记一致(`ChatInterface.tsx`、`useChat.ts` 已列出;`GenerativeUIMiddleware` 保留体现在"middleware 链不删")
- [x] 引入新机制(`SkillWhitelistMiddleware` / Skills API / `/built-in/deep-research/`),架构文档同步项(§2.5 + §3.1)已列出
- [x] 不出现大段代码块,长度控制在合理范围
