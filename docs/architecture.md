# 技术架构

这是一个本地跑的 Deep Research demo:用户在浏览器问一个问题,主 agent 拆任务 → 派 N 个 sub-agent 并行调研 → 关键写操作触发人审 → generative UI 实时渲染调研卡 → 主 agent 汇总成报告。系统由三层构成——浏览器(`deep-agents-ui`)、`langgraph dev` 运行时、Python `deepagents` 编排,各层之间用 LangGraph SDK 的 SSE 协议联通。

本文按 "**运行机制(§2) → 跨上游适配(§3) → 演进路径(§4)**" 三层展开。**普通使用者读 README 即可**;本文是给排错、二次开发、技术选型评估的人看的。运行期具体故障定位见 [troubleshooting.md](./troubleshooting.md)。

## 1. 系统总览

```
浏览器 :3000  ──HTTP/SSE──>  langgraph dev :2024  ──>  Python: agent.py
   │                              │                          │
   │ useStream                    │ LangGraph Platform        │ create_deep_agent(
   │ (@langchain/langgraph-sdk)   │ Runtime (inmem)            │   model=ChatOpenAI(DashScope),
   │                              │                            │   tools=[...],
   │ React 19 + Next.js 16        │ checkpointer auto-managed  │   subagents=[research-agent],
   │ shadcn/ui + Tailwind         │ HumanInTheLoopMiddleware   │   middleware=[GenerativeUIMiddleware],
   │ LoadExternalComponent (本地)  │ + 内置 Todo/Filesystem/Sub  │   interrupt_on={write_file, edit_file, task})
```

**一次请求的端到端流程**:

1. 浏览器 `useStream` 把用户问题 POST 到 `:2024/runs/stream`,订阅 SSE。
2. `langgraph dev` 加载 `backend/langgraph.json` 里 graph `research`,调度 `create_deep_agent` 装配出来的图(`research` 是前端 Assistant ID 的契约,UI 设置弹窗必须填这个名字)。
3. 主 agent 思考 → 写 todo → 串行/并行调 `task` 工具委派 sub-agent 调研。
4. `task` 调用触发 HITL 拦截,前端弹审批卡,用户 Approve 后继续。
5. sub-agent 跑搜索 + 总结,通过 `emit_research_card` 推送 generative UI 消息到 `state.ui[]`,前端实时渲染。
6. 全部 sub-agent 完成后,主 agent 触发 `write_file` 汇总(再次 HITL 拦截),用户审批后落盘。

**故障与扩展定位**:启动错误或具体运行期现象先查 [troubleshooting.md](./troubleshooting.md);搞清楚某个机制能不能扩展、为什么这样设计看 §2;哪些代码因为基于 vendored 上游而不能动看 §3;评估"上游升级后能拆掉哪些适配"看 §4。

## 2. 运行机制

按 deepagents 的四字段 state schema 切分子系统:**编排**(主 agent 怎么调度)、**状态**(messages/todos/files/ui 如何承载工作记忆)、**人在回路**(关键操作如何让用户介入)、**渲染**(前端如何把进度可视化)。

### 2.1 编排层:主 agent + sub-agent + 自定义 LLM

`create_deep_agent` 装配主 agent,内置 `task` 工具自动委派 sub-agent;`subagents=[...]` 在 `agent.py` 中声明,每个 sub-agent 有独立 prompt + 工具集。主 agent 通过调用 `task(description, agent_name)` 派活,框架自动建立子上下文、跑完后把结果回填到主 agent 的 messages。

**LLM provider 锁定 ChatOpenAI + DashScope**。`init_chat_model("anthropic:...")` 会走 LangChain provider registry,没法指向 DashScope,所以必须用 `ChatOpenAI(base_url=..., api_key=..., model="deepseek-v4-pro")` 直接实例化 LLM 对象传给 `create_deep_agent`。切换模型在 `.env` 里改 `DEEPAGENTS_MODEL`(任何 DashScope OpenAI-compatible 模型)。

⚠️ **历史踩坑**:早期 plan 写过 `disable_streaming=True`,依据是"DashScope tools+stream 互斥"。**这条已被证伪**:阿里云[兼容文档](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)里"暂时无法"是 2023-2024 年针对 qwen-turbo/plus/max 的老限制,现代模型(deepseek-v4-pro、qwen3.6-plus 等)支持 tools+stream 同时使用。不要把 `streaming=True` 改回 `False`。

**扩展边界**:加新 sub-agent → 在 `agent.py` 的 `subagents` 列表加配置 + 在 `prompts.py` 加对应 prompt;加新工具 → 在 `tools.py` 写,然后注册到主 agent 或某个 sub-agent 的 tools 列表。

> 模型实际行为偏差(跳过 `emit_research_card` / 重复调研等)见 [troubleshooting.md](./troubleshooting.md) 第 2 节"模型行为"。

### 2.2 状态层:四字段 state 与 generative UI 扩展

`deepagents._DeepAgentState` 暴露三个字段:`messages`(对话历史)、`todos`(主 agent 的 TODO 列表)、`files`(虚拟文件系统,`write_file/edit_file/read_file` 工具读写它)。前后端共享同一份 state 视图,LangGraph 的 reducer 机制保证多步更新原子合并。

**为什么要扩展出 `ui` 字段**:generative UI 需要后端 `push_ui_message("research_card", props)` 把组件消息推到前端。`push_ui_message` 写入路径是 `state[CONFIG_KEY_SEND]([("ui", evt)])`——**没有 `ui` reducer 注册时,evt 会被 LangGraph 默默丢弃**,`state.values.ui` 永远是 `None`。

**怎么扩展**:`deepagents` 没暴露 `state_schema` 参数,但每个 `AgentMiddleware` 类可以声明自己的 `state_schema`,框架装配 graph 时会**合并所有 middleware 的 state**。最小修法:写一个空 middleware,唯一作用是声明 `ui` 字段。

```python
# backend/middlewares.py
class GenerativeUIState(AgentState):
    ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer]

class GenerativeUIMiddleware(AgentMiddleware[GenerativeUIState, Any, Any]):
    state_schema = GenerativeUIState
```

在 `create_deep_agent(middleware=[GenerativeUIMiddleware()], ...)` 里传入即可。

**扩展边界**:想加更多 state 字段(如 `metrics`、`citations`),继续往 middleware 的 `state_schema` 里加,不要去改 deepagents 源码。

**另一个状态层约束**:`langgraph dev` 是 LangGraph Platform 的本地模拟器,**自动管 checkpointer**——用户不能在 `create_deep_agent` 里再传 `MemorySaver` 或 `checkpointer=...`,传了启动失败。

### 2.3 人在回路:interrupt_on 范围与批量审批

`interrupt_on={"write_file": True, "edit_file": True, "task": True}` 实测全部工作。其中 `task` 是 deepagents 内部生成的 sub-agent 委派工具——拦它意味着用户能在每次"主 agent 想派 sub-agent 干活"前审批。

底层 `HumanInTheLoopMiddleware` 拦截工作在**节点边界**,与 LLM streaming 独立。这点很关键:即使开了 streaming,拦截仍然可靠触发,前端弹卡片时模型已暂停。

**批量审批语义**:LangGraph 的 `interrupt()` 单次可携带多个 `action_requests`——最常见的场景是模型在一个 step 内生成 N 个 `task` tool_calls,触发 1 个 interrupt 含 N 个 action_requests。中间件期待的 resume payload `{decisions: [d1, ..., dN]}` 长度等于 N。**UI 上点一次 Approve 等于批准这一批所有 task 委派**——这个"单次决策广播为 N 个"的具体实现见 §3.2。

**局限**:批量审批是"全 approve / 全 reject"语义,**无法对单个 action_request 做不同决策**(例如 approve 第 1 个、reject 第 2 个)。要细粒度需要重写前端 `ToolApprovalInterrupt` 组件,目前没这个需求。

**调试**:如果发现 `task` 拦截后行为异常,先把 `"task": True` 注释掉缩小范围。

### 2.4 前端渲染:useStream + 本地组件 registry

前端用 `@langchain/langgraph-sdk` 的 `useStream` 订阅 graph 的 SSE,自动累积 messages / interrupt / `state.ui[]` 等所有事件。`ChatMessage.tsx` 遍历 messages 渲染对话气泡;遇到 tool_call 时调 `ToolCallBox`;遇到需要 HITL 审批的 interrupt 时弹审批卡。

**generative UI 走本地组件而非 LangSmith CDN**。`LoadExternalComponent` 默认行为是从 LangSmith CDN 拉组件 JS/CSS(需要 LangSmith API key + 把组件部署到 LangSmith)。但它有个 `components` prop,**如果传入本地字典且 key 命中 `message.name`,就直接 `React.createElement(localComponent, message.props)`,不去 CDN**:

```tsx
// frontend/src/app/components/generative-ui/registry.tsx
export const LOCAL_UI_COMPONENTS = { research_card: ResearchCard };

// ChatMessage.tsx 把 LOCAL_UI_COMPONENTS 传给 ToolCallBox
// ToolCallBox.tsx 把它透传给 LoadExternalComponent
```

零 LangSmith 依赖、零 CDN 依赖,走本地 Next.js bundle。数据流:后端 `push_ui_message("research_card", props, metadata={"tool_call_id": tool_call_id})` → 前端 `ChatMessage.tsx` 用 `tool_call_id` 在 `state.ui[]` 中找匹配 → `LoadExternalComponent` 渲染本地组件。

**扩展边界**:加新的 generative UI 卡片 = (1) 在 `frontend/src/app/components/generative-ui/` 写本地组件;(2) 加到 `LOCAL_UI_COMPONENTS` registry;(3) 后端 `tools.py` 加工具调 `push_ui_message("<新 name>", props)`。

> 前端是 `langchain-ai/deep-agents-ui` 的 vendored 副本,这套渲染机制依赖 4 处本地 patch,详见 §3.1。

### 2.5 多格式报告产物的存储与前端识别

主报告以 `report.md` 为唯一真理来源。用户可在 Step 0 clarification 同时指定 `html`、`docx` 之一或全部,会产生 `report.html`(LLM 直接生成完整 HTML+inline CSS)和/或 `report.docx`(由 `export_docx` 工具调 `pypandoc` 从 md 转换)。

**后端存储**。deepagents `FileData` 是 `{content: str, encoding: "utf-8"|"base64", created_at?, modified_at?}`。文本格式 `encoding="utf-8"`、`content` 是原文;二进制(docx)`encoding="base64"`、`content` 是 base64 字符串。

**⚠️ 不要用 `StateBackend.upload_files()` 写二进制**(2026-05-25 实证)。它内部对 bytes 做 base64 编码后调 `create_file_data(text)`,**漏传 `encoding` 参数**,FileData 仍被默认成 `encoding="utf-8"`,前端按 encoding 路由会失效,docx 被当文本显示。`export_docx`(`backend/tools.py`)的解决方案:**直接返回 `Command(update={"files": {dst: {"content": b64, "encoding": "base64", ...}}})`**,手工构造 FileData 显式设 encoding。后续升级 deepagents 时,如果 upstream 修了 `StateBackend.upload_files` 漏传 encoding 的 bug,可以回退到 backend API 路径(更干净)。

`FilesystemBackend.max_file_size_mb=10`,base64 编码会膨胀 ~33%,实际可用源字节上限约 7.5 MB,`export_docx` 内还预校验 docx 字节数 ≤ 10 MB。

**前端识别**。`useChat.ts` 的 `StateType.files` 类型放宽为 `Record<string, RawFileEntry>`,其中 `RawFileEntry = string | { content, encoding? }`(string 形态保留给旧 checkpoint 兼容)。`TasksFilesSidebar.tsx` 的 `normalizeFileEntry()` 把 `RawFileEntry` 归一成 `FileItem`(`{path, content, encoding}`),`encoding` 字段透传给 `FileViewDialog.tsx`。

**FileViewDialog 路由**(`FileViewDialog.tsx`):
- `encoding === "base64"`:占位卡片"二进制文件 · X KB,请点击下载",**不**走 SyntaxHighlighter 也**不**允许编辑/复制;下载时 `atob` → `Uint8Array` → `Blob` 配正确 MIME(`MIME_BY_EXT` 表)。
- `.html` 且 utf-8:`<iframe srcDoc sandbox="allow-same-origin">` 预览。**不开** `allow-scripts`,防止报告 HTML 被注入脚本执行 —— 同时这也要求 LLM 生成的 HTML 不要依赖外部 CDN / 内联 JS,否则交互失效。`prompts.py` Step 4b 中已硬约束。
- `.md`:走现有 `MarkdownContent`,行为不变。
- 其他 utf-8:`SyntaxHighlighter` 代码高亮(回归现状)。

**扩展新格式时的同步项**:(1) `backend/tools.py` 加新 `export_*` 工具(走 `StateBackend.upload_files` 模式);(2) `backend/agent.py` 注册到 `tools=` + `interrupt_on=`(保持 HITL 一致);(3) `backend/prompts.py` Step 4 加新子项 + Step 0 同义词映射;(4) `frontend/.../FileViewDialog.tsx` 的 `MIME_BY_EXT` 加扩展名→MIME 映射;(5) 本文件本节同步更新。

## 3. 跨上游适配的硬约束

本系统基于三个上游:**deepagents**(后端编排框架)、**deep-agents-ui**(vendored 前端,直接 clone 在 `frontend/`)、**@langchain/langgraph-sdk**(前端订阅 SSE 的 SDK)。当前版本下,这三个上游各自存在需要本地适配的硬约束,本章集中记录。每条约束在 §4 都有"何时可拆"的判定。

### 3.1 前端 4 处本地 patch

`deep-agents-ui` 直接 clone 进 `frontend/`,因为我们要改它(注入本地 generative UI 组件、patch 几处 bug)。**升级路径**:`cd frontend && git pull` 前先 `git diff > /tmp/patches.diff` 留底,升级后 `git apply` 回去。

| 文件 | 修改 | 原因 |
|---|---|---|
| `ToolCallBox.tsx` | props 加 `components`,透传给 `LoadExternalComponent` | 让本地 generative UI 组件能命中 |
| `ChatMessage.tsx` | import `LOCAL_UI_COMPONENTS` 并注入;去掉 `task` 无条件 skip | 让本地组件 registry 生效;让 task HITL 审批卡能显示 |
| `ChatInterface.tsx` | 新增 `broadcastResumeInterrupt`;ui filter 兼容 `tool_call_id` | 见 §3.2 |
| `useChat.ts` | 装 fetch monkey-patch 过滤 `tools` stream_mode | 见 §3.3 |
| `generative-ui/{ResearchCard,registry}.tsx` | 新增本地组件 + registry | demo 卡片 |

#### 3.1.1 ChatMessage.tsx 第 128 行的 task skip

上游写死 `if (toolCall.name === "task") return null;`——理由是 deep-agents-ui 设计上把 `task` 工具调用渲染成 `SubAgentIndicator`(左下方折叠卡片),而不是普通 `ToolCallBox`。但这导致 `task` 触发 HITL 拦截时,审批卡(依赖 `ToolCallBox` 渲染)**永远不显示**。

我们改为:只在没有 actionRequest 时 skip,否则让第一个 task tool_call 走 `ToolCallBox` 渲染审批卡。

#### 3.1.2 actionRequestsMap 用 name 做 key 的副作用

上游 `new Map(actionRequests.map(ar => [ar.name, ar]))` 用 `ar.name` 做 key,多个同工具(如 3 次 task 委派)会被覆盖只剩 1 个。我们没修这个 Map 本身(改它会牵连 `ToolApprovalInterrupt` 的接口),而是用 §3.2 的 broadcast 机制兜底。

### 3.2 HITL 批量审批 — broadcastResumeInterrupt

§2.3 讲了批量审批的语义("UI 点一次 Approve 等于 N 个 approve"),具体实现是:`HumanInTheLoopMiddleware` 期待 resume payload `{decisions: [d1, ..., dN]}` 长度等于 N,但 deep-agents-ui 的 `ToolApprovalInterrupt` 组件硬编码 `decisions: [{type:"approve"}]`(永远 length=1)。当一个 interrupt 携带 N>1 个 action_requests 时,原生 resume 会漏决策。

修法在 `ChatInterface.tsx` 包一层 `broadcastResumeInterrupt`:

```ts
const broadcastResumeInterrupt = useCallback((value) => {
  const n = interrupt?.value?.action_requests?.length ?? 0;
  if (n > 1 && value?.decisions?.length === 1) {
    value = { ...value, decisions: Array(n).fill(value.decisions[0]) };
  }
  resumeInterrupt(value);
}, [interrupt, resumeInterrupt]);
```

UI 点一次 Approve,自动复制成 N 个 approve 提交。Reject/Edit 同理。

### 3.3 stream_mode "tools" 兼容性 fetch hack

**现象**:`useStream` 提交 run 时附 `stream_mode: ["values", "messages-tuple", "tools", "updates"]`,但 `langgraph-cli[inmem]` 的 OpenAPI schema 不包含 `"tools"` 这个 enum 值,后端返回 **HTTP 422**。

**根因**:`@langchain/langgraph-sdk` 的 `useStream` 内部,只要任何 getter 读到 `stream.toolProgress`,就会调 `trackStreamMode("tools")` 把它加入下次 submit 的 stream_mode 列表。SDK 内部某处隐式访问了 toolProgress(grep 应用代码找不到,应在 message manager 或 subagent 处理逻辑里)。`useStream` 配置的 `streamMode` 选项只是**追加**到内部累积 ref,不能屏蔽。

**修法**:在 `useChat.ts` 装 fetch monkey-patch,在请求出口处过滤掉 `tools`:

```ts
useEffect(() => {
  const orig = window.fetch;
  window.fetch = function(...args) {
    if (urlStr.includes("/runs/stream") && body.stream_mode) {
      body.stream_mode = body.stream_mode.filter(m => m !== "tools");
      args[1].body = JSON.stringify(body);
    }
    return orig.apply(this, args);
  };
  return () => { window.fetch = orig; };
}, []);
```

**可删条件**:删 hack,跑一次 HITL approve;如果不再 422,说明 SDK 与 `langgraph-api` 后端已同步,可以删了。

## 4. 演进路径

每个适配层都有"上游修好之后,本地可以拆掉"的判定条件。下面按 §3 顺序列出。

### 4.1 deepagents 升级

```bash
pip install -U deepagents
```

跑一次完整 prompt,检查:

1. **`_DeepAgentState` 是否新加了 `ui` 字段**——如果有,可以删 `GenerativeUIMiddleware`(§2.2)。
2. **`task` 工具 interrupt 行为是否改变**——拦截语义如果调整,需要重新评估 §2.3 的拦截范围与 §3.2 的 broadcast 是否还需要。

### 4.2 deep-agents-ui 升级

```bash
cd frontend
git diff > /tmp/patches.diff     # 必须先留底
git pull origin main
git apply /tmp/patches.diff      # 处理 conflict
```

升级后检查上游 issue 是否 fix 了:

- **task 渲染问题**(#45 #97)——若 fix,可以删 §3.1.1。
- **actionRequestsMap key 问题**——若 fix,可以删 §3.2 的 broadcast。

### 4.3 @langchain/langgraph-sdk 升级

跑一次 HITL approve,如果不再 422,删 `useChat.ts` 的 fetch monkey-patch(§3.3)。
