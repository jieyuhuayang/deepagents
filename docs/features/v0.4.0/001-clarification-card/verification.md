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
