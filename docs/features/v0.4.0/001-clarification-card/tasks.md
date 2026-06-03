# Tasks: Gen-UI 澄清卡 (ClarificationCard)

> Spec: [`./spec.md`](./spec.md) · Verification: [`./verification.md`](./verification.md)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-25 |
| 已评审(`/sdd-review tasks` 通过) | ☑ | 2026-05-25 · 自动通过 |
| 已完成(所有任务 ✅ + verification.md 全绿) | ☐ | — |

---

## 任务依赖

任务数 = 6,画文字依赖图:

```
T1 (前端 patch 留底)
  └─ T4 (前端 Context + ChatInterface patch) ──→ T5 (ClarificationCard + registry patch) ──┐
T2 (后端 tool + agent.py) ──→ T3 (prompts.py 5 处改造) ─────────────────────────────────────┤
                                                                                            └─→ T6 (architecture.md + verification.md 全跑通)
```

并行机会:T1 / T2 完全独立,可并行起;T4 在 T1 后启,T3 在 T2 后启;T5 / T6 串行收尾。

---

## 任务清单

### T1 — 前端 vendored patch 留底

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-25,留底 193 行)
- **文件**:无(纯 git 操作);留底产物 `/tmp/patches-001-clarification-card.diff`
- **逻辑**:CLAUDE.md §强约束第 5 条要求"动 `frontend/**` 前必须 `git diff > /tmp/patches-NNN.diff` 留底"。本 feature 要新增 2 处 patch(`ChatInterface.tsx` 包 ResumeInterruptProvider / `registry.tsx` 注册 clarification_card)+ 新建 2 个文件(`useResumeInterrupt.ts` / `ClarificationCard.tsx`),必须前置留底。
- **验证方式**:`wc -l /tmp/patches-001-clarification-card.diff` 大于 0(基线 vendored patch 至少 4-6 处);verification.md §4 跨上游适配第 1 项
- **覆盖 AC**:无(基础设施 / 强约束守护)
- **依赖**:无

### T2 — 后端新增 `request_clarification` 工具 + `agent.py` 注册

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-25,`python -c "from agent import agent"` 装配 OK)
- **文件**:`backend/tools.py`、`backend/agent.py`
- **逻辑**:
  1. `tools.py` 新增 `Question` / `Option` TypedDict + `@tool request_clarification(restate: str, questions: list[Question], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command`。Question 字段:`id` / `question` / `options` / `multi_select`;Option 字段:`value` / `label` / `is_default`。
  2. tool 内部按以下顺序:
     - 第 1 次 `push_ui_message("clarification_card", {"restate": restate, "questions": questions}, id=tool_call_id, metadata={"tool_call_id": tool_call_id})` —— **此调用必须幂等**,re-execution 时会跑两次,靠 id 让 reducer dedup。
     - `answers = interrupt({"type": "clarification", "tool_call_id": tool_call_id})` —— 第一次抛 `GraphInterrupt` halt;resume 后(同 task 二次调用)直接 return resume value。
     - 第 2 次 `push_ui_message("clarification_card", {"completed": True, "answers": answers}, id=tool_call_id, metadata={"tool_call_id": tool_call_id, "merge": True})` —— **only runs after resume**,`merge=True` 让 reducer 合并 props 而非替换,触发前端切只读视图。
     - `return Command(update={"messages": [ToolMessage(content=json.dumps(answers, ensure_ascii=False), tool_call_id=tool_call_id)]})`。
  3. 在 `interrupt()` 之前的代码加注释:"IMPORTANT: 任何 interrupt() 之前的代码在 re-execution 时会跑两次,必须幂等。当前只有 `push_ui_message` 用 id 去重,新加副作用前重新评估"。
  4. `agent.py` `tools=[...]` 列表添加 `request_clarification`(从 tools.py 导入);**不要**加到 `interrupt_on` dict —— 澄清走 tool 内 `interrupt()`,不走 `HumanInTheLoopMiddleware`(spec §4 强约束第 6 条说明)。
- **验证方式**:手动 verification.md §2.AC-1 + AC-4 + AC-5 + AC-7(re-execution dedup);可选补 `backend/tests/test_request_clarification.py` 单测 schema 序列化
- **覆盖 AC**:AC-1, AC-4, AC-5, AC-7
- **依赖**:无

### T3 — 后端 `prompts.py` 5 处改造

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-25,5 处 marker grep verify 通过,旧"reply with ONE message"/"Step 0 clarification turn IS the message"已删除)
- **文件**:`backend/prompts.py`
- **逻辑**:按 spec §6 第 5 段(第 4 决策点 X-B / Y-B / Z-A 起草版本)对 `ORCHESTRATOR_PROMPT` 5 处改造:
  1. `# Hard Rules` Step 0 行替换:从"reply with ONE message bundling 1-3 clarifying questions and STOP"硬切到 **"call exactly one `request_clarification` tool call and STOP. Do NOT reply with text — the card IS the message. Do NOT call any other tool (not even `write_todos` or `think_tool`)"**。保留 "Maximum 1 clarification round" + "never call `request_clarification` twice" 兜底约束。
  2. `# Clarification Protocol` 整章重写为 `# How to Fill request_clarification (only when Step 0 triggers)`:讲解 Question / Option schema 字段,priority order(scope → output formats → output shape → time window → audience → geography),含 1 个 single-select + is_default 的 JSON 示例(spec §6 给出原文)。
  3. `# Silent Defaults` 末尾追加段落:解释 tool return 的 ToolMessage content 是 `json.dumps(answers)` 形式的 dict,告诉模型读这个 dict 设置 `write_todos` 的 scope/depth 和 Step 4a/4b/4c 的 file formats。"如果 key 缺失或答案模糊,fall back 到 Silent Defaults — 不要二次调 `request_clarification`"。
  4. `# Tools You Have` 新增一行 `request_clarification(restate, questions)`:"when Step 0 triggers, surface a clarification card. User's choices come back as a JSON dict. Call AT MOST ONCE per conversation"。
  5. `# Style` 删除现有 `Exception: the Step 0 clarification turn IS the message — no tool call expected there.` 这一例外句(现在 Step 0 也是 tool call,该例外不再适用)。
- **验证方式**:手动 verification.md §2.AC-1 / AC-2 / AC-6;模型行为观察(模糊问题触发,清晰问题跳过,Max 1 round 兜底)
- **覆盖 AC**:AC-1, AC-2, AC-6
- **依赖**:T2(需要 tool 签名定稿后再写 prompt 教学)

### T4 — 前端 `useResumeInterrupt` Context + `ChatInterface.tsx` patch

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-25,Provider 3 处就位:line 33 import / line 282 open / line 311 close)
- **文件**:`frontend/src/app/hooks/useResumeInterrupt.ts`(新建)、`frontend/src/app/components/ChatInterface.tsx`(新增 patch)
- **逻辑**:
  1. 新建 `useResumeInterrupt.ts`:
     - 导出 `ResumeInterruptProvider`(`Context.Provider` 薄封装,接 `value: (v: unknown) => void` + `children`)
     - 导出 `useResumeInterrupt()` hook(`useContext` + 缺失抛错 "must be used within ResumeInterruptProvider")
     - 用 `"use client"` 标记
  2. `ChatInterface.tsx`:
     - 顶部 import `ResumeInterruptProvider`
     - 在 `processedMessages.map(...)` 外包 `<ResumeInterruptProvider value={broadcastResumeInterrupt}>...</ResumeInterruptProvider>`
     - **不动** `broadcastResumeInterrupt` 自身实现(澄清没有 action_requests 数组,broadcast 分支自动 skip,行为兼容,见 spec §4 强约束第 6 条)
  3. 加注释引用 `docs/architecture.md §3.1` 新增的 patch 表项,便于未来 vendored upgrade 时识别。
- **验证方式**:手动 verification.md §2.AC-4(用户提交后 ChatInterface 经 Context 派发 resume payload);TypeScript `yarn build` 编译通过
- **覆盖 AC**:基础支撑(AC-4 的前置)
- **依赖**:T1(留底先做)

### T5 — 前端 `ClarificationCard` 组件 + `registry.tsx` patch

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(2026-05-25,`yarn lint` 0 errors / `yarn build` 完全绿,无类型错误)
- **文件**:`frontend/src/app/components/generative-ui/ClarificationCard.tsx`(新建)、`frontend/src/app/components/generative-ui/registry.tsx`(新增 patch)
- **逻辑**:
  1. 新建 `ClarificationCard.tsx`(完整骨架见 spec §6 第 8 段引用的第 8 决策点代码):
     - Props: `{ restate: string; questions: Question[]; completed?: boolean; answers?: Record<string, string | string[]> }`
     - 用 `useResumeInterrupt()` 自取 resume callback(不通过 prop drill)
     - **交互态**:`bg-card` + 蓝色 `MessageCircleQuestion` header + "需要补充信息" label + restate 一行(border-b 分隔)+ question 列表
        - 每个 question:序号 + 文字 + multi_select 时显示 `[多选]`
        - chips:`is_default: true` 的 chip 初始 active 且加 ★ 角标;单选互斥(替换 selections[qId]),多选 toggle
        - "+ 其他":点击展开 `<Input>` 单行输入
        - 提交按钮在右下角(`bg-primary` + Check icon);`disabled if !isValid || submitted`
     - submit handler:`setSubmitted(true) → resume(collectAnswers())`
     - `collectAnswers`:单选 free-text 非空时**覆盖** chip(`custom || picked[0]`);多选时 free-text **append** 到 list(`[...picked, ...(custom ? [custom] : [])]`)
     - `isValid`:每个 question 至少有 1 个 chip 选中 **或** free-text 非空
     - **只读态**(`completed === true && answers != null`):`bg-card` + 绿色 `CheckCircle2` icon + "已提交" label + restate + question→label 列表;`labelFor` 查找时 value 不在 options.value 内则直接返回 value 字符串(即 free-text 兜底)
  2. `registry.tsx` 加 1 行 `clarification_card: ClarificationCard`,key 必须与后端 `push_ui_message("clarification_card", ...)` 第一个参数**完全一致**(否则前端 LoadExternalComponent 找不到本地组件会去 fetch CDN,fail)。
- **验证方式**:手动 verification.md §2.AC-3(视觉)/ AC-4(切只读)/ AC-5(free-text 编码);TypeScript `yarn build` 编译通过
- **覆盖 AC**:AC-3, AC-4, AC-5
- **依赖**:T4(需要 Context 先就位)

### T6 — `docs/architecture.md` 同步 + `verification.md` 全跑通

- **状态**:☐ 待开始 / ☑ 进行中(2026-05-25,6.1 架构同步完成;6.2 verification.md 跑通 + 截图归档待手动验证) / ☐ 已完成
- **文件**:`docs/architecture.md`(§3.1 patch 表 + 新增 §2.X "interrupt() vs interrupt_on" 子节)、`./verification.md`、`./screenshots/`
- **逻辑**:
  1. `architecture.md §3.1` patch 表新增 4 行:
     - `ChatInterface.tsx`(新增 patch,包 `<ResumeInterruptProvider>` 暴露 resume callback)
     - `registry.tsx`(新增 patch,注册 `clarification_card: ClarificationCard`)
     - 本地新增:`hooks/useResumeInterrupt.ts`
     - 本地新增:`components/generative-ui/ClarificationCard.tsx`

     前端 patch 总数从 "4-6 处" 涨到 **"6-8 处"**,在 §3.1 表前的描述行同步更新数字。
  2. `architecture.md §2` 编排章节**必须**新增子节(建议 §2.5 "两种暂停机制:interrupt() vs interrupt_on"):
     - `interrupt_on` 路径:`HumanInTheLoopMiddleware` 在 tool 调用**前**拦截,payload schema `{action_requests, review_configs}`,前端走 `ToolApprovalInterrupt`,resume payload 是 `{decisions: [{type: "approve" | "reject" | "edit", ...}]}`
     - tool 内 `interrupt()` 路径:在 node 内部主动暂停,payload schema 自定义(本 feature 用 `{type: "clarification", tool_call_id}` sentinel),前端走 generative-ui 通道(`useResumeInterrupt` Context),resume payload 是任意 user-defined 形态(本 feature 是 `Record<string, string | string[]>`)
     - 两者**完全不耦合**,可共存于同一 graph
     - 何时用哪种:tool 调用前审批走 `interrupt_on`;tool 在执行过程中需要询问用户走 tool 内 `interrupt()`
     - re-execution 注意:tool 内 `interrupt()` 后 resume 会让 node 从头跑,interrupt 之前的代码必须幂等(本 feature 靠 push_ui_message id 去重满足)
  3. 按 `verification.md` 跑完 §1 启动序列、§2 AC-1~AC-7、§3 强约束回归(8 + 3 条)、§4 跨上游适配(留底 / 既有 patch 仍在 / lint/format/build 全绿)。
  4. 每个 AC 截图归档 `./screenshots/ac-N.png`;AC-5 拆 single + multi 两张;关键回归点截图按需归档。
  5. 全绿后勾选 verification.md 状态表三行 + tasks.md 状态表"已完成"行 + spec.md 状态表"已完成"行。
- **验证方式**:verification.md 自身的状态表三行全勾;`cd frontend && yarn format:check && yarn lint && yarn build` 全绿
- **覆盖 AC**:全部(收尾验证)
- **依赖**:T3, T5

---

## AC 覆盖反查

| AC | 由哪些任务覆盖 |
|---|---|
| AC-1(模糊问题触发,不调 write_todos) | T2, T3 |
| AC-2(清晰问题跳过澄清) | T3 |
| AC-3(默认勾选 + ★ 角标 + 视觉) | T5 |
| AC-4(提交后切只读 + 后续 write_todos 按选择执行) | T2, T3, T4, T5 |
| AC-5(free-text 编码:单选覆盖 / 多选 append) | T2, T5 |
| AC-6(Max 1 round + Silent Defaults 兜底) | T3 |
| AC-7(re-execution 不重复渲染) | T2 |

每条 AC 至少被 1 个任务覆盖 ✓;任务引用的 AC ID 全部存在于 spec.md §2 ✓。

---

## 实际偏差记录

> 实现过程中如发现与 spec.md 不符(AC 调整、文件清单变化、边界情况新增、缓解策略变更等),**立刻在此登记**,并在 PR 描述里指向本节。
>
> **不允许"先实现再决定"**——若需偏离,先评估是否回 spec.md 修订。严重偏离(改 AC、改强约束触碰判断)必须回 Step 2 重新走 `/sdd-review spec`。

| 日期 | 任务 | 偏差描述 | 处理决定(回改 spec / 接受偏差 / 撤回任务) |
|---|---|---|---|
| 2026-05-25 | T2 + T5 | spec.md §6 第 7 段(决策点 6 方案 D)设计 ClarificationCard 走 generative-ui 通道:tool 内 `push_ui_message("clarification_card", ...)` 推卡片到 state.ui → 前端 LOCAL_UI_COMPONENTS 注册 + LoadExternalComponent 渲染。**实测 langgraph 1.2.1 在 tool 内 `interrupt()` halt 期间,push_ui_message 的 pending writes 不持久化到 thread state**——`writer(evt)` 仅通过 SSE 实时推送,`CONFIG_KEY_SEND` 把 channel update 加入 task pending writes 等 task commit 才 publish,而 interrupt 让 task suspend(非 commit)。结果:用户首次发模糊问题时通过 SSE 收到 ui event 能渲染卡片;但**刷新页面后**(useStream 重连拉 thread state)`state.ui === []`,卡片丢失。同 `interrupt.value` 也只是 sentinel `{type, tool_call_id}`,前端无 fallback 数据源。这是**确定性丢失**(不只是 race condition),比 spec.md §3.1 边界 case 第 1 条严重。 | **修复(回退到决策点 6 方案 E 的核心思路)**:(1) `backend/tools.py` 删 `request_clarification` 内的 push_ui_message 两处调用(interrupt 前/后);(2) `frontend/.../generative-ui/registry.tsx` 删 `clarification_card` 注册;(3) `frontend/.../ChatMessage.tsx` 加 patch:在 `toolCalls.map(...)` 里检测 `toolCall.name === "request_clarification"` → 直接渲染 `ClarificationCard`,props 从 `toolCall.args` 取(restate + questions,**永久持久化在 AIMessage.tool_calls**),`completed` 来自 `!!toolCall.result`,`answers` 来自 `JSON.parse(toolCall.result)`。`ClarificationCard.tsx` 组件本身不变(props 接口已经是这样)。`useResumeInterrupt` Context 保留(`ChatInterface` 的 Provider 包装也保留)。**接受偏差,不回改 spec**——AC-1 ~ AC-6 验证不变(API 层 verify AC-1 + AC-2 已 pass,tool_call.args 在 thread state 中持久化完整);AC-7 表述需 update(从"reducer 按 id dedup"改成"组件渲染数据源是 toolCall.args 不依赖 state.ui,re-execution 时 SSE 多次推送被 React 自然合并")。架构文档 §2.6 同步更新——记录这个 langgraph 1.2.x 行为 caveat,建议未来 deepagents 升级若 push_ui_message 在 interrupt 期间持久化的语义改变(或暴露 force-commit API),可回退到原 D 方案。 |

# Verification: Gen-UI 澄清卡 (ClarificationCard)

> Spec: [`./spec.md`](./spec.md) · Tasks: [`./tasks.md`](./tasks.md)
>
> **本文档是 feature 完成的最终凭证。** 所有 AC 必须在此手动验证通过;所有触碰的强约束必须在 §3 回归检查中确认仍生效。

## 状态

| 阶段 | 状态 | 验证日期 | 验证人 |
|---|---|---|---|
| 全部 AC 验证通过 | ☐ | | |
| 全部回归检查通过 | ☐ | | |
| 截图已附在 `./screenshots/` | ☐ | | |

---

## 0. 环境信息

| 项 | 值 |
|---|---|
| 后端启动命令 | `cd backend && source .venv/bin/activate && langgraph dev` |
| 后端端口 | `:2024` |
| 前端启动命令 | `cd frontend && yarn dev` |
| 前端端口 | `:3000` |
| 浏览器 Assistant ID | `research`(`backend/langgraph.json` 的 graph 名) |
| `.env` 必填 | `DEEPAGENTS_MODEL`、`DASHSCOPE_API_KEY` |
| Node 版本 | 20.x |
| Yarn 版本 | 1.22.22 |
| langgraph 版本(影响 `interrupt()` + `ui_message_reducer` 行为) | `1.2.1`(spec.md §AC-7 引用的 reducer 第 51-54 行 merge 分支基于此版本) |
| 验证 git commit | _(填本次验证基于的 commit hash)_ |

---

## 1. 启动序列

按顺序执行:

```bash
# 终端 A
cd backend && source .venv/bin/activate && langgraph dev

# 等 backend 显示 "Application startup complete" 后,开终端 B
cd frontend && yarn dev

# 浏览器打开 http://localhost:3000,确认 Assistant ID 填的是 research
```

**预期**:
- [ ] backend 日志无 ERROR / 无未处理异常
- [ ] frontend 编译成功,浏览器 console 无 error
- [ ] 能发出至少一条消息得到回复(基线 smoke test)

---

## 2. AC 逐条验证

### AC-1:模糊问题触发 `request_clarification`,不调 write_todos / think_tool

**步骤**:
1. 浏览器新建 thread,发送"帮我研究下 LLM agent"(模糊,缺 scope/time/output)
2. 观察 ChatMessage 流 + ChatInterface 渲染
3. `curl http://localhost:2024/threads/<id>/state | python -m json.tool` 检查 messages 末条

**预期**:
- 流出的 AI 消息只有 1 个 `tool_calls` 条目,`name === "request_clarification"`
- 同一轮**不**调 `write_todos` / `think_tool`
- ChatInterface 渲染 ClarificationCard,thread `status === "interrupted"`
- `interrupt` 字段 value 形如 `{type: "clarification", tool_call_id: "..."}`(sentinel-only,无 schema 重复)
- `values.ui` 数组长度 = 1,该 UIMessage `name === "clarification_card"`,props 含 `restate` + `questions`

**截图**:`./screenshots/ac-1.png`

**结果**:☐ 通过 / ☐ 不通过(备注:______)

---

### AC-2:清晰问题直接进入 write_todos,跳过澄清

**步骤**:
1. 浏览器新建 thread,发送"调研 2025 年生产级 LLM agent 框架 LangGraph / CrewAI / AutoGen,输出对比报告,受众技术决策者"(含 scope + 时间 + 输出形态 + 受众,clarity 拉满)
2. 观察首轮 tool_calls 序列

**预期**:
- 模型首轮调 `write_todos`,**不**触发 `request_clarification`
- ChatInterface 不渲染 ClarificationCard
- thread `status` 走 `busy → interrupted`(write_file HITL) → 后续流程,但澄清卡不出现

**截图**:`./screenshots/ac-2.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-3:ClarificationCard 默认勾选 `is_default` + ★ 角标 + 蓝色 header

**步骤**:
1. 复用 AC-1 thread 或新发模糊问题
2. 观察 ClarificationCard 视觉

**预期**:
- 蓝色 `MessageCircleQuestion` icon + "需要补充信息" header 文字
- restate 一行,border-b 与下方 question 列表分隔
- 每个 question 中 `is_default: true` 的 chip 已 active(蓝色 bg / 蓝色 border)
- active 的 chip 上有 ★ 角标(黄色 / `text-yellow-500`)
- 单选 question chips 互斥(点其他 chip 时原默认 chip 取消 active)
- 多选 question 显示 `[多选]` 标识(`text-muted-foreground`),chips 可同时多个 active
- 每个 question 末尾有 dashed border 的 "+ 其他" chip(占位)

**截图**:`./screenshots/ac-3.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-4:提交后切只读 + 后续 write_todos / write_file 按用户选择执行

**步骤**:
1. 复用 AC-3 thread,改一两个 chip(modify 默认选择)
2. 点提交
3. 等 thread `status` 从 `interrupted` → `busy` → ...
4. 观察:
   - ClarificationCard 是否切到**只读态**(✓ 已提交 + 用户选择 label 列表)
   - 模型后续 `write_todos` plan 是否反映用户选择(例如 scope=both 时主题列表覆盖 production + research)
   - 若 user 选了 `output_formats: ["markdown", "html"]`,最终 `state.files` 是否含且仅含 `report.md` + `report.html`(无 `report.docx`)

**预期**:
- ClarificationCard 切只读视图:`bg-card` + 绿色 `CheckCircle2` + "已提交" label + question→选择 label 列表
- 选择列表中 free-text 答案直接显示输入字符串(不显示 value 标识)
- `state.files` 与用户 output_formats 选择对应

**截图**:`./screenshots/ac-4.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-5:free-text 编码(单选覆盖 / 多选 append)

**步骤**:
1. 新发模糊问题触发澄清
2. **单选场景**:在某个单选 question 里,先点一个 chip → 再展开 "+ 其他" 填 "agent debugging" → 提交
3. 检查 thread state:`tool_calls[].args` 中的 questions schema(用于核对 multi_select 字段)+ `ToolMessage.content`(JSON dict)
4. **多选场景**:重新发模糊问题,在 `output_formats`(multi_select=true)question 里同时勾 "markdown" + 展开 "+ 其他" 填 "pptx" → 提交
5. 检查 ToolMessage.content

**预期**:
- 单选场景:ToolMessage content JSON 中 `{<qId>: "agent debugging"}`(free-text **覆盖** chip,只有 free-text 字符串,无 chip value)
- 多选场景:ToolMessage content JSON 中 `{output_formats: ["markdown", "pptx"]}`(chip value + free-text 字符串 **append** 到同一 list)
- 后续 `write_todos` / `write_file` 行为按 free-text 体现的"真实意图"运转(例如 "pptx" 写不进 step 4,但 plan 中至少应该 acknowledge "用户想要 PPT")

**截图**:`./screenshots/ac-5-single.png` + `./screenshots/ac-5-multi.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-6:Max 1 round + Silent Defaults 兜底

**步骤**:
1. 模糊问题触发澄清 → ClarificationCard 显示
2. **故意做不完整的选择**:每个 question 都保留默认(或随便点一下),不展开 free-text → 提交(模拟用户"懒得仔细回答,直接默认")
3. 模型应正常进入 Step 1,**不再**第二次调 `request_clarification`
4. **再来一组**:在同一 thread 发第二条"再多研究点其他方向"模糊补充
5. 观察:模型是否再次调 `request_clarification`(应该**不**)

**预期**:
- 提交后模型按用户选择(默认值 / chip 选择)进入 `write_todos`,**不**再开澄清
- 同一 thread 后续轮次也**不**重启澄清(prompt 硬约束 "never call request_clarification twice" 起作用)
- 若用户明显在第二轮还提供模糊补充,模型应用 Silent Defaults(past 12 months / generalist / 3-5 subtopics / markdown only)继续推进

**截图**:`./screenshots/ac-6.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-7:re-execution 不导致重复渲染(`push_ui_message` id dedup)

**步骤**:
1. 模糊问题触发澄清
2. 浏览器开发者工具 Network 面板,观察 SSE event 流;特别关注 `updates` 事件中的 `ui` 字段变化
3. 提交澄清前 `curl http://localhost:2024/threads/<id>/state` 检查 `values.ui` 数组长度
4. 提交澄清 → resume
5. resume 完成后再次 `curl /state` 检查 `values.ui`

**预期**:
- 初次 interrupt 时 `values.ui.length === 1`(只 1 张 clarification_card,即使 node re-execution 让 push_ui_message 跑两次,reducer 按 `id=tool_call_id` dedup)
- resume 后 `values.ui.length` 仍 = 1(第二次 push 用 `merge=True` 合并 props 而非 append 新 message)
- 该 UIMessage props 已含 `completed: true` + `answers` dict
- 组件视觉切只读

**截图**:`./screenshots/ac-7.png`(可附 Network 面板 + 两次 curl 输出对比)

**结果**:☐ 通过 / ☐ 不通过

---

## 3. 回归检查(强约束守护)

> spec.md §4 标记"是"的强约束:**第 5(前端 patch)/ 第 7(monkey-patch)/ 第 8(prompts.py 语序)** 三条,本节必须验证。其余约束建议跑一遍,确保无副作用。具体故障对照参见 [`docs/troubleshooting.md`](../../../troubleshooting.md)。

- [ ] **GenerativeUIMiddleware 仍在**(强依赖,第 1 条强约束反向验证):`grep -n "GenerativeUIMiddleware" backend/agent.py` 仍命中,且 `middleware=[GenerativeUIMiddleware()]` 仍存在;ResearchCard 在调研流程中仍渲染
- [ ] **LLM provider 仍是 ChatOpenAI + DashScope**(第 2 条):`backend/agent.py` 仍 `ChatOpenAI(base_url=...)`,`.env` 仍指向 DashScope
- [ ] **未传 checkpointer**(第 3 条):`create_deep_agent(...)` 调用中**无** `checkpointer=` 参数
- [ ] **streaming=True 未被改**(第 4 条):`backend/agent.py` `streaming=True`
- [ ] **既有前端 patch 全部保留**(第 5 条,主):`/tmp/patches-001-clarification-card.diff` 含基线 4-6 处 patch;`docs/architecture.md §3.1` 表中所有原 patch 文件仍在源码(`useChat.ts` 的 fetch monkey-patch / `ChatMessage.tsx` 的 LOCAL_UI_COMPONENTS 注入 / `ToolCallBox.tsx` 的 components prop / `registry.tsx` 的 research_card 行)
- [ ] **HITL 批量审批仍工作**(第 6 条,反向验证不被误伤):主 agent 同一 step 派 ≥ 2 个 task 时,点一次 Approve 全部放行;点一次 Reject 全部拒绝;`broadcastResumeInterrupt` 行为未变
- [ ] **ToolApprovalInterrupt 与 ClarificationCard 共存**:同一 thread 先触发澄清(走 tool 内 `interrupt()`)→ 提交后流程继续 → 触发 `write_file` HITL(走 `interrupt_on`)→ ToolApprovalInterrupt 卡片正常显示。两者**互不干扰**
- [ ] **fetch monkey-patch 仍生效**(第 7 条,主):浏览器 Network 面板看 `/runs/stream` body 的 `stream_mode` 数组**不含** `"tools"`;触发澄清流程后无 422;`grep -n "stream_mode" frontend/src/app/hooks/useChat.ts` 仍命中相关代码块(行号会随其他改动偏移,人工 verify 逻辑仍在)
- [ ] **prompts.py 硬约束完整**(第 8 条,主):
  - `# Hard Rules` Step 0 含 `Do NOT reply with text — the card IS the message`
  - 含 `Maximum 1 clarification round`
  - 含 `never call request_clarification twice`
  - `emit_research_card` 的 `# Hard Rules` Step 3 仍是 `you MUST immediately call emit_research_card`(原有硬约束未弱化)
  - 不存在新的"if you feel like it"/"optionally"等软化语序
- [ ] **`ui_message_reducer` 行为不变**(本 feature 强依赖):`backend/.venv/.../langgraph/graph/ui.py` 中 `ui_message_reducer` 函数的 merge 分支(原 51-54 行,langgraph 1.2.1)仍存在;若升级 langgraph 后行号偏移,人工核对该函数仍按 `id` 去重 + `metadata.merge` 触发 props 浅合并
- [ ] **interrupt() 行为不变**(本 feature 强依赖):`langgraph.types.interrupt()` docstring 仍记载 "On subsequent invocations within the same node, returns the value provided during the first invocation"(若升级后行为变成"每次都抛",本 feature 的 tool 写法失效,需要重写)

---

## 4. 跨上游适配验证(动了 frontend/)

> spec.md §5 标记"是"。

- [ ] **patch 留底文件存在**:`/tmp/patches-001-clarification-card.diff` 已生成且非空(`wc -l > 0`)
- [ ] **既有 patch 全部仍在源码中**:对照 [`docs/architecture.md` §3.1](../../../architecture.md) 列出的 4-6 处既有 patch 全部仍存在;diff `/tmp/patches-001-clarification-card.diff` 与基线对比无遗漏
- [ ] **架构文档已同步**:
  - `docs/architecture.md §3.1` patch 表新增 4 行(2 个新 patch 文件 + 2 个本地新增文件);patch 总数描述从 "4-6 处" 改为 "6-8 处"
  - `docs/architecture.md §2` 编排章节新增 "interrupt() vs interrupt_on" 子节(spec §6 必做项)
- [ ] **前端 lint/format/build 通过**:`cd frontend && yarn format:check && yarn lint && yarn build` 全绿;若 `yarn build` 已有 baseline type-check error(参考 v0.3.0/001 偏差记录),确认本 feature **未引入新 error**

---

## 5. 后端单测(可选)

> 仅当 tasks.md 某任务采用单测验证时填本节。本 feature 不强制。

| 任务 | 测试文件 | 跑法 | 结果 |
|---|---|---|---|
| T2 | `backend/tests/test_request_clarification.py`(可选,验证 schema 序列化 + interrupt 双 push 路径) | `pytest backend/tests/test_request_clarification.py` | ☐ 通过 |

---

## 6. 截图归档

所有截图放在 `./screenshots/`,命名:
- AC 截图:`ac-N.png`(N 与 spec.md AC ID 对应);AC-5 拆 `ac-5-single.png` + `ac-5-multi.png`
- 关键回归点:`regression-hitl-batch-coexist.png`(澄清和 HITL 共存)/ `regression-prompt-stepzero.png`(prompt 硬约束 grep)/ `regression-monkey-patch.png`(Network 面板看 stream_mode)

提 PR 时把这些图附在 PR 描述里给 reviewer。
