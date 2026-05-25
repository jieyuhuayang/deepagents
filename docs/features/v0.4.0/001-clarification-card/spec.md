# Spec: Gen-UI 澄清卡(ClarificationCard)

> Feature ID: `001-clarification-card` · 版本归属: `v0.4.0` · Owner: LineWalker · 创建日期: `2026-05-25`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 8 轮 spec discovery 决策已固化 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☑ | 2026-05-25 · LineWalker ★ 确认 |
| 已完成(verification.md 全绿) | ☐ | — |

---

## 1. 概述与用户故事

**Feature 描述**:把当前 `ORCHESTRATOR_PROMPT` Step 0 的"打字反问"升级为可交互的 Gen-UI 澄清卡。模糊问题进来时,主 agent 调用 `request_clarification` tool,前端渲染一张带 chips 单/多选 + free-text fallback 的卡片,用户点选即可,不必手动打字。tool 内用 langgraph 原生 `interrupt()` 暂停 graph,用户提交后 `Command(resume=answers)` 把 dict 回灌,模型继续 Step 1。

**Context / 来源**:
- 用户口头需求 2026-05-25:"澄清交互门槛太高,可否用 Gen-UI 像 Claude Code 用户访谈模式那样让用户只选不打字"
- 现有 Step 0 文字反问行为已在 prompt 落地(`backend/prompts.py:11-18`),本 feature 是其结构化升级
- 复用现有 generative-ui 通道(`emit_research_card` 路径已闭环)

**用户故事**:

1. 作为 Deep Research demo 用户,我希望模糊问题进来时能用一键点选确认范围,而不是手动打字回复 1-3 个澄清问题,以便降低澄清门槛、加快进入调研。
2. 作为后续 maintainer,我希望澄清通道复用 generative-ui 同一套基础设施(`push_ui_message` + `state.ui` + `LOCAL_UI_COMPONENTS` 注册),以便未来加入更多 interactive UI tool(如 ConfirmCard / FileSelectorCard)时直接复用 `useResumeInterrupt` Context。
3. 作为 prompt 维护者,我希望 Step 0 的"必须调 tool 不要输出文字"约束写得足够硬,模型在 `temperature=0.0` 下不会偷懒走打字路径(对照 §强约束第 8 条 deepseek 跳过 `emit_research_card` 的前车之鉴)。

**检查点**:
- [x] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [x] 描述里不引入新术语(`Gen-UI` / `Card` / `chips` 在 §6 实现概要前都已 ground 在现有代码)

---

## 2. 验收标准 (Acceptance Criteria)

| AC ID | 标准描述 | 验证方式 | verification.md 位置 |
|---|---|---|---|
| AC-1 | 模糊问题("帮我研究下 LLM agent")触发 `request_clarification`,前端渲染 ClarificationCard;同一轮**不**调 `write_todos` / `think_tool`;`finish_reason` 为 `tool_calls` 而非 `stop` | 浏览器手动 + `curl /threads/<id>/state` 检查 messages 末条 `tool_calls` | §2.AC-1 |
| AC-2 | 清晰问题("调研 2025 年生产级 LLM agent 框架 LangGraph/CrewAI/AutoGen,输出对比报告,受众技术决策者")直接进入 `write_todos` plan,不触发澄清 | 浏览器手动 | §2.AC-2 |
| AC-3 | ClarificationCard 打开时,每个 question 中 `is_default=true` 的 chip 已勾选并显示 ★ 角标;蓝色 accent header "需要补充信息" + MessageCircleQuestion 图标 | 浏览器视觉(对照 §5 截图) | §2.AC-3 |
| AC-4 | 用户点"提交"后,卡片切只读总结("✓ 已提交" + question→选择 label 列表);后续 `write_todos` / `task` / `write_file` 按用户选择执行(例如 `output_formats: ["markdown", "html"]` 时跑 Step 4a + 4b,跳过 4c) | 浏览器手动 + `state.files` 检查产出文件 | §2.AC-4 |
| AC-5 | 单选 question 用户展开"+ 其他"手填非空 → dict 中该 key 的 value 是 free-text 字符串(覆盖 chip 选择);多选 question 用户既勾 chip 又填 free-text → list 包含两者 | 浏览器手动 + thread state JSON 检查 `tool_calls[].args` 与 ToolMessage content | §2.AC-5 |
| AC-6 | Max 1 round:第一次澄清后用户回答仍模糊(例如 free-text 留空 + chip 不选),模型应用 Silent Defaults 直接进入 plan,**不再**第二次调 `request_clarification` | 浏览器手动 | §2.AC-6 |
| AC-7 | re-execution 不导致重复渲染:`interrupt()` 触发后再 `Command(resume=...)`,前端 `state.ui` 中只有 1 张 `clarification_card`(靠 `id=tool_call_id` 做 reducer dedup,已 verify `ui_message_reducer` 第 51-54 行 merge 分支) | 浏览器视觉 + `curl /threads/<id>/state` 检查 `values.ui` 数组长度 | §2.AC-7 |

**检查点**:
- [x] 每条 AC 都有唯一 ID,后续 tasks.md 引用同一 ID
- [x] 每条 AC 都可在本地浏览器 + `langgraph dev` 复现,不依赖外部环境
- [x] AC 数量 7 条(在 3-7 范围内)

---

## 3. 边界情况与非目标

### 3.1 边界情况

- **用户提交瞬间立刻刷新页面**:resume 已发但 push_ui_message 第二次还没跑时,前端从服务器拉到的 props 还是 `{restate, questions}`(无 `completed`),会渲染交互态卡片。**第一版接受这个 race**(demo 级,触发要求"提交瞬间 + 网络极慢 + 手动刷新"三连组合,概率极低);用户再点一次提交,LangGraph SDK 对已 resume 过的 thread 会静默处理或报错,前端 catch 即可。
- **`langgraph dev` 进程重启**:inmem checkpointer 状态全丢,所有 interrupted thread 变 stale,用户必须新建对话。这是现状,本 feature 不引入新风险;按 CLAUDE.md §强约束第 3 条不动 checkpointer。
- **用户在 free-text 输入框留空但展开了"+ 其他"**:视作没选"其他",提交时按 chip 选择走;不阻塞 submit。
- **模型在 Step 0 触发后偷偷调了 `write_todos`**(违反 prompt 硬约束):第一版**不加**结构化拦截,靠 prompt 力度 +"Maximum 1 clarification round → Silent Defaults"兜底;上线后跑 3-5 次研究观察违反率,高了再上 middleware(对应 §4 强约束第 8 条)。
- **用户提交后想反悔**:本期不支持(见 §3.2 非目标第 1 条)。卡片切只读后无法改回交互态;用户只能在后续对话里说"换个范围",由模型在 plan 里自行调整。
- **questions 数组为空或 > 3**:tool docstring 约束 1-3 条;模型违反时,前端 ClarificationCard 仍能渲染(空数组时只有 restate + 提交按钮),不 crash。

### 3.2 非目标(本期不做)

- **澄清后用户再次修改答案**:一次澄清一锁定,提交即只读。
- **澄清卡里嵌套子问题**(question 数组单层,不支持"如果选 A 则展示更多 question")。
- **跨 thread 复用上次澄清答案**(每个 thread 独立)。
- **用户主动触发澄清**(没有"我想被澄清"按钮;仅 Step 0 自动触发)。
- **Postgres / SQLite checkpointer 支持**(继续用 `langgraph-cli[inmem]`,见 §强约束第 3 条)。
- **结构化拦截 middleware**(动态裁剪 tool list 强制只允许 `request_clarification`);留待上线后观测违反率再考虑。
- **超时机制**(interrupt 无限期等待,见第 3 决策点 (E) 项决议)。
- **卡片右上角"✕"取消按钮**(见第 3 决策点 (F) 项决议)。

**检查点**:
- [x] 边界情况包含至少 1 条"失败/异常路径"(race condition / 模型偷懒)
- [x] 非目标列出明确的、可能被误以为属于本期的事项(再次修改、超时、取消按钮)

---

## 4. 涉及强约束

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☐ 否 | 反而**强依赖** —— ClarificationCard 走 `push_ui_message` → `state.ui` 通道,缺了 middleware 整个 feature 不工作。verification.md §3 加回归项:确认 `agent.py:43` 仍 `middleware=[GenerativeUIMiddleware()]` |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 否 | 不动 |
| 不传 `checkpointer` 给 `create_deep_agent` | ☐ 否 | 不动;`langgraph dev` 自动管 checkpointer,`interrupt()` 依赖它 |
| `streaming=True` 不改回 False | ☐ 否 | 不动 |
| 前端 vendored patch(详见 §5) | ☑ 是 | 新增 1 处 patch(`ChatInterface.tsx` 包 `ResumeInterruptProvider`)+ 1 处 patch(`registry.tsx` 加 `clarification_card` 映射);Step 6 第一步 `git diff > /tmp/patches-001.diff` 留底;`docs/architecture.md §3.1` patch 表需新增登记 |
| HITL 批量审批"全 approve / 全 reject"语义 | ☐ 否 | 澄清走 `interrupt()` tool 内暂停,不走 `interrupt_on` → `HumanInTheLoopMiddleware`,**完全不耦合**现有 HITL 通道。前端 `broadcastResumeInterrupt` 检测到无 `action_requests` 时自动 skip 广播,行为不变 |
| `useChat.ts` fetch monkey-patch 不删 | ☑ 是 | **不删、不动**;只确认 `stream_mode: "tools"` 过滤逻辑不影响 interrupt payload(interrupt 走 `values` / `updates` 通道,monkey-patch 只过滤 `stream_mode` 字段不参与 interrupt 序列化)。verification.md §3 加回归项:`grep -n "stream_mode" frontend/src/app/hooks/useChat.ts` 仍命中第 58-67 行 |
| `prompts.py` 强制语序不弱化 | ☑ 是 | 本 feature **反而加强**:Step 0 从"输出 ONE 文字 message"硬切到"调 exactly one `request_clarification` tool call and STOP",措辞强度参考 `emit_research_card` 的"You MUST immediately call"力度。verification.md §3 加回归项:`prompts.py` 中保留所有 `**Do NOT reply with text**` / `Maximum 1 clarification round` / `never call request_clarification twice` 等硬约束句 |

**检查点**:
- [x] 凡是"是"的条目,缓解策略不为空
- [x] 触碰的条目都在 verification.md §3 加回归项(待 SDD Step 4 起草 verification.md 骨架时落地)

---

## 5. 前端 patch 影响

**是否动 `frontend/**`**:☑ 是

**预计修改的已 patch 文件**:
- [ ] `frontend/src/app/components/ChatInterface.tsx`(broadcastResumeInterrupt) —— **新增 1 处 patch**(在 `processedMessages.map(...)` 外包 `<ResumeInterruptProvider value={broadcastResumeInterrupt}>`);**不动** broadcastResumeInterrupt 自身
- [ ] `frontend/src/app/components/ChatMessage.tsx`(LOCAL_UI_COMPONENTS 注入) —— **不动**
- [ ] `frontend/src/app/components/ToolCallBox.tsx`(components prop) —— **不动**(ClarificationCard 通过 React Context 自取 `onResume`,不需要 ToolCallBox 透传)
- [ ] `frontend/src/app/hooks/useChat.ts`(fetch monkey-patch,过滤 stream_mode "tools") —— **不动**
- [x] `frontend/src/app/components/generative-ui/registry.tsx`(本地新增) —— **改 1 行**:加 `clarification_card: ClarificationCard`
- [ ] `frontend/src/app/components/generative-ui/ResearchCard.tsx`(本地新增) —— **不动**(参考模式)

**本 feature 新增的非 patch 文件**(类似 ResearchCard.tsx,登记到 §3.1 表格的"本地新增"行):
- `frontend/src/app/hooks/useResumeInterrupt.ts` —— Context + Provider + hook
- `frontend/src/app/components/generative-ui/ClarificationCard.tsx` —— UI 组件(交互态 + 只读态)

**留底命令**(实施 Step 6 第一动作必须执行):

```bash
cd frontend && git diff > /tmp/patches-001.diff
```

**对 `architecture.md §3.1` patch 表的预期更新**:
- **新增 1 行**:`ChatInterface.tsx` —— 用 `<ResumeInterruptProvider>` 包 `processedMessages.map(...)`,把 `broadcastResumeInterrupt` 通过 React Context 暴露给 generative-ui 组件
- **新增 1 行**:`registry.tsx` —— 注册 `clarification_card: ClarificationCard`
- **新增 2 行 "本地新增" 条目**:`useResumeInterrupt.ts` / `ClarificationCard.tsx`

前端 patch 总数从 "4-6 处" 涨到 **"6-8 处"**。

**检查点**:
- [x] 动 `frontend/`,留底命令在 tasks.md 是第一个任务(待起草 tasks.md 时落地)
- [x] 新增 patch 已在本节登记后续如何更新 §3.1

---

## 6. 实现概要 & 文件清单

**实现思路**(8 轮 spec discovery 决策固化):

1. **暂停机制**:tool 内 langgraph 原生 `interrupt()`(决策点 1 选项 A1);抛 `GraphInterrupt` 后前端 `Command(resume=...)` 恢复;node re-execution 时 `interrupt()` 二次调用直接 return resume value(已 verify langgraph 1.2.1 行为)。
2. **questions schema**:自定义带 `is_default` + `multi_select`(决策点 2 选项 A);Option 的 `is_default: boolean` 让前端能渲染 ★ 角标 + 默认勾选;`multi_select: boolean` 让 `output_formats` 这种场景天然多选。
3. **free-text fallback**:前端组件层自动追加"+ 其他"展开 Input(决策点 2 sub-(a)/(c));free-text 直接作为 value 平铺到 dict(单选覆盖 chip,多选 append)。
4. **race / 兜底**:`langgraph dev` 重启后 stale interrupt 完全不管(决策点 3 选项 i);不超时,不加取消按钮(决策点 3 (E)(F))。
5. **prompt 改造**:`ORCHESTRATOR_PROMPT` 改 5 处 —— Step 0 行 / Clarification Protocol 整章重写 / Silent Defaults 末尾追加 tool return 解读规则 / Tools You Have 新增条目 / Style 删除"Step 0 IS the message"例外句(决策点 4 选项 X-B / Y-B / Z-A)。
6. **完成态切换**:tool 内 `interrupt()` 之后第二次 `push_ui_message(merge=True, props={completed: True, answers})`(决策点 7 选项 i);ClarificationCard 内部 `if (completed && answers) return <ReadOnlySummary />;` 切只读视图。
7. **前端集成**:走 generative-ui 通道(决策点 6 选项 D);新增 `useResumeInterrupt` React Context 让 ClarificationCard 不通过 prop drill 自取 `broadcastResumeInterrupt` callback;`ChatInterface.tsx` 包 `<ResumeInterruptProvider>` 暴露;`registry.tsx` 注册组件。
8. **组件视觉**:`bg-card` + 蓝色 `MessageCircleQuestion` header(决策点 5 选项 a);chips 自己写 `<button>`(决策点 8 (A));free-text 用 `<Input>` 单行(决策点 8 (B));submit 时 local `submitted` boolean disable 按钮(决策点 8 (D));只读态 `bg-card` + 绿色 `CheckCircle2` + question→label 列表。

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/tools.py` | 修改 | 新增 `request_clarification(restate, questions, tool_call_id)` tool + `Question` / `Option` TypedDict;tool 内 `push_ui_message`(id=tool_call_id)→ `interrupt()` → 第二次 `push_ui_message`(merge=True)→ `Command(update={"messages": [ToolMessage(json.dumps(answers))]})` |
| `backend/agent.py` | 修改 | `tools=[...]` 列表添加 `request_clarification` |
| `backend/prompts.py` | 修改 | `ORCHESTRATOR_PROMPT` 5 处改造(详见决策点 4 起草的完整文本) |
| `frontend/src/app/hooks/useResumeInterrupt.ts` | 新建 | `ResumeInterruptProvider` + `useResumeInterrupt()` hook |
| `frontend/src/app/components/generative-ui/ClarificationCard.tsx` | 新建 | UI 组件(主交互态 + ReadOnlySummary 子组件) |
| `frontend/src/app/components/generative-ui/registry.tsx` | 修改(新 patch) | 注册 `clarification_card: ClarificationCard` |
| `frontend/src/app/components/ChatInterface.tsx` | 修改(新 patch) | 用 `<ResumeInterruptProvider value={broadcastResumeInterrupt}>` 包 `processedMessages.map(...)` |
| `docs/architecture.md` | 修改 §3.1 + 新增 §2.X | (1) §3.1 patch 表新增 4 行(2 个新 patch 文件 + 2 个本地新增文件);(2) §2 编排章节**必须**追加"interrupt() vs interrupt_on" 子节,解释两种暂停机制的差异(`interrupt_on` 走 HumanInTheLoopMiddleware 拦截 tool 调用前;tool 内 `interrupt()` 是 graph 暂停在 node 内部,两者 payload schema 不同,不耦合) |

**检查点**:
- [x] 文件清单与 §4-§5 标记一致(动 frontend 的 patch 文件 ChatInterface.tsx / registry.tsx 已列出)
- [x] 引入新机制(`useResumeInterrupt` Context + tool 内 `interrupt()`),架构文档同步项已列出
- [x] 不出现大段代码块(代码骨架细节留给 tasks.md 起草时引用第 7-8 决策点)
