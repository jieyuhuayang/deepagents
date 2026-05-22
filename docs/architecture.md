# 技术架构与已知问题

本文档记录这个 Deep Research agent 项目的关键架构决策、上游限制的本地修法、以及踩过的坑。**普通使用者读 README 即可**；本文是给需要排错、二次开发、或评估这套技术选型的人看的。

## 1. 三层架构

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

- **前端 vendored**：`deep-agents-ui` 直接 clone 进 `frontend/`，因为我们要改它（注入本地 generative UI 组件、patch 几处 bug）。后续升级路径：`cd frontend && git pull`，然后手动 re-apply 4 处 patch。
- **后端单文件入口**：`backend/agent.py` 装配一切。`langgraph.json` 的 `graphs.research` 是前端 Assistant ID 的契约（前端 UI 设置弹窗里填 `research`）。
- **运行时 langgraph dev**：是 LangGraph Platform 的本地模拟器（端口 2024）。它**自动管 checkpointer**——用户不能再传 `MemorySaver`，传了会启动失败（plan 文件早期就栽过这跤）。

## 2. 关键技术决策

### 2.1 为什么用 OpenAI-compatible 端点（DashScope）而不是 Anthropic

用户给的现实约束。`init_chat_model("anthropic:...")` 会走 LangChain provider registry，没法指向 DashScope，所以必须用 `ChatOpenAI(base_url=..., api_key=..., model="deepseek-v4-pro")` 直接实例化 LLM 对象传给 `create_deep_agent`。

⚠️ **历史踩坑提示**：plan 文件早期写过 `disable_streaming=True`，依据是"DashScope tools+stream 互斥"。**这条已被证伪**：阿里云[兼容文档](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)里的"暂时无法"是 2023-2024 年针对 qwen-turbo/plus/max 的老限制，现代模型（deepseek-v4-pro、qwen3.6-plus 等）支持 tools+stream 同时使用，已确认。

### 2.2 为什么自定义 GenerativeUIMiddleware

`deepagents._DeepAgentState` 写死了 `messages / todos / files` 三个字段，**没有 `ui`**。如果直接调 `push_ui_message("research_card", props)`，写入操作走 `state[CONFIG_KEY_SEND]([("ui", evt)])`，但因为 reducer 没注册，evt 会被 LangGraph 默默丢弃——`state.values.ui` 永远是 `None`。

deepagents 没暴露 `state_schema` 参数让用户自定义。但每个 `AgentMiddleware` 类可以声明自己的 `state_schema`，框架在装配 graph 时会**合并所有 middleware 的 state**。所以最小修法：写一个空 middleware，唯一的作用是声明 `ui` 字段：

```python
# backend/middlewares.py
class GenerativeUIState(AgentState):
    ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer]

class GenerativeUIMiddleware(AgentMiddleware[GenerativeUIState, Any, Any]):
    state_schema = GenerativeUIState
```

在 `create_deep_agent(middleware=[GenerativeUIMiddleware()], ...)` 里传入即可。

### 2.3 为什么 generative UI 走本地组件而不是 LangSmith CDN

`LoadExternalComponent` 默认行为是从 LangSmith CDN 拉组件 JS/CSS（需要 LangSmith API key + 把组件部署到 LangSmith）。但它有个 `components` prop，**如果传入本地字典且 key 命中 `message.name`，就直接 `React.createElement(localComponent, message.props)` 不去 CDN**：

```tsx
// frontend/src/app/components/generative-ui/registry.tsx
export const LOCAL_UI_COMPONENTS = { research_card: ResearchCard };

// ChatMessage.tsx 把 LOCAL_UI_COMPONENTS 传给 ToolCallBox
// ToolCallBox.tsx 把它透传给 LoadExternalComponent
```

零 LangSmith 依赖、零 CDN 依赖、走本地 Next.js bundle。后端 `push_ui_message("research_card", props, metadata={"tool_call_id": tool_call_id})`，前端 `ChatMessage.tsx` 用 `tool_call_id` 在 `state.ui[]` 中找匹配，然后 `LoadExternalComponent` 渲染本地组件。

### 2.4 HITL 拦截：write_file/edit_file/task 三选

`interrupt_on={"write_file": True, "edit_file": True, "task": True}` 实测全部工作。其中 `task` 是 deepagents 内部生成的 sub-agent 委派工具——拦它意味着用户能在每次"主 agent 想派 sub-agent 干活"前审批。

注：如果发现 `task` 拦截后行为异常，先把 `"task": True` 注释掉缩小范围；底层 `HumanInTheLoopMiddleware` 拦截工作在节点边界，与 LLM streaming 独立。

## 3. deep-agents-ui 的 4 处本地 patch

| 文件 | 修改 | 原因 |
|---|---|---|
| `ToolCallBox.tsx` | props 加 `components`，透传给 `LoadExternalComponent` | 让本地 generative UI 组件能命中 |
| `ChatMessage.tsx` | import `LOCAL_UI_COMPONENTS` 并注入；去掉 `task` 无条件 skip | 让本地组件 registry 生效；让 task HITL 审批卡能显示 |
| `ChatInterface.tsx` | 新增 `broadcastResumeInterrupt`；ui filter 兼容 `tool_call_id` | 见 §4 |
| `useChat.ts` | 装 fetch monkey-patch 过滤 `tools` stream_mode | 见 §5 |
| `generative-ui/{ResearchCard,registry}.tsx` | 新增本地组件 + registry | demo 卡片 |

### 3.1 ChatMessage.tsx 第 128 行的 task skip

上游写死 `if (toolCall.name === "task") return null;`——理由是 deep-agents-ui 设计上把 `task` 工具调用渲染成 `SubAgentIndicator`（左下方折叠卡片），而不是普通 `ToolCallBox`。但这导致 `task` 触发 HITL 拦截时，审批卡（依赖 `ToolCallBox` 渲染）**永远不显示**。

我们改为：只在没有 actionRequest 时 skip，否则让第一个 task tool_call 走 `ToolCallBox` 渲染审批卡。

### 3.2 actionRequestsMap 用 name 做 key 的副作用

上游 `new Map(actionRequests.map(ar => [ar.name, ar]))` 用 `ar.name` 做 key，多个同工具（如 3 次 task 委派）会被覆盖只剩 1 个。我们没修这个 Map 本身（改它会牵连 ToolApprovalInterrupt 的接口），而是用 §4 的 broadcast 机制兜底。

## 4. HITL Batch Approval — broadcastResumeInterrupt

LangGraph 的 `interrupt()` 单次可携带多个 `action_requests`（最常见：模型在一个 step 内生成 N 个 `task` tool_calls，触发 1 个 interrupt 含 N 个 action_requests）。

`HumanInTheLoopMiddleware` 期待 resume payload `{decisions: [d1, d2, ..., dN]}` 长度等于 N。但 deep-agents-ui 的 `ToolApprovalInterrupt` 组件硬编码 `decisions: [{type:"approve"}]`（永远 length=1）。

我们在 `ChatInterface.tsx` 包了一层 `broadcastResumeInterrupt`：

```ts
const broadcastResumeInterrupt = useCallback((value) => {
  const n = interrupt?.value?.action_requests?.length ?? 0;
  if (n > 1 && value?.decisions?.length === 1) {
    value = { ...value, decisions: Array(n).fill(value.decisions[0]) };
  }
  resumeInterrupt(value);
}, [interrupt, resumeInterrupt]);
```

UI 点一次 Approve，自动复制成 N 个 approve 提交。语义上等于"批准这一批所有 task 委派"。Reject/Edit 同理。

⚠️ 局限：这是"批量"语义，无法对单个 action_request 做不同决策（例如 approve 第 1 个、reject 第 2 个）。要做细粒度需要重写 ToolApprovalInterrupt 组件——目前没这个需求所以没做。

## 5. stream_mode "tools" 兼容性 hack

### 现象
`useStream` 提交 run 时附 `stream_mode: ["values", "messages-tuple", "tools", "updates"]`，但 langgraph-cli[inmem] 的 OpenAPI schema 不包含 `"tools"` 这个 enum 值，后端返回 **HTTP 422**。

### 根因
`@langchain/langgraph-sdk` 的 `useStream` 内部，只要任何 getter 读到 `stream.toolProgress`，就会调 `trackStreamMode("tools")` 把它加入下次 submit 的 stream_mode 列表。SDK 内部某处隐式访问了 toolProgress（grep 应用代码找不到，应在 message manager 或 subagent 处理逻辑里）。useStream 配置的 `streamMode` 选项只是**追加**到内部累积 ref，不能屏蔽。

### 修法
在 `useChat.ts` 装 fetch monkey-patch，在请求出口处过滤掉 `tools`：

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

这个 hack 应该在 SDK 后续版本与 langgraph-api 后端同步后可以移除。判定方法：删 hack，跑一次 HITL approve；如果不再 422，说明可以删了。

## 6. 环境兼容性踩坑

| 现象 | 原因 | 修法 |
|---|---|---|
| `langgraph dev` 启动报"checkpointer not necessary" | LangGraph Platform 自动管 checkpointer，禁用户传 | 删 agent.py 的 `MemorySaver`、`checkpointer=` |
| `langgraph dev` 启动报 `Using SOCKS proxy, but socksio not installed` | 用户环境有 `all_proxy=socks5://...`，httpx 默认不带 SOCKS 支持 | `pip install socksio`（或 `pip install httpx[socks]`） |
| `yarn install` "trouble with your network connection" + "Couldn't find brace-expansion@^5.0.2" | yarn 1.22 在 SOCKS 代理下无法正确解析 npm registry | 改用 npm + 国内镜像：`npm install --registry=https://registry.npmmirror.com --legacy-peer-deps` |
| `langgraph dev` startup failed 后不退出 | watchfiles 保持监听，等文件改变重试 | 改完代码自动 reload；如果想强制重启，kill 进程后重启 |

## 7. 模型行为：prompt engineering 备忘

`deepseek-v4-pro` 在本项目实测有几个非显然行为：

1. **会主动跳过 `emit_research_card`**：即使在 prompt 里写"MUST call emit_research_card"，第一次跑仍可能跳过直接 write_file。第二次 reject + 强化引导后才听话。**对策**：把 emit_research_card 的 docstring 写得更强制（"完成一个子主题调研后必须调用"），并在 ORCHESTRATOR_PROMPT 里加"only after all N emit_research_card calls succeed may you call write_file"。

2. **会想重复调研同一个主题**：3 个 sub-agent 跑完后，模型可能觉得某个结果不够好，自己再 spawn 一个 task 重做。这不一定是 bug，但会拖慢流程。**对策**：在 prompt 里强调"sub-agent 的结果即为最终结果，不要二次调研"。

3. **Tavily 搜索常常返回空**：sub-agent 报告里多次出现"tavily_search 40+ 次查询均返回空"。**未排查根因**——可能 SOCKS 代理影响、可能 API key/quota 问题、可能 Tavily 对中文 query 不友好。当前 sub-agent 在搜索全空时会用训练数据兜底（自动 fallback），结果勉强可用但失去时效性。**待办**。

## 8. 升级路径

- **deepagents 升级**：`pip install -U deepagents` 后跑一次完整 prompt，检查：(1) `_DeepAgentState` 是否新加了 `ui` 字段（如果有，可以删 GenerativeUIMiddleware）；(2) `task` 工具 interrupt 行为是否改变。
- **deep-agents-ui 升级**：`cd frontend && git pull origin main` 后会丢失本地 4 处 patch。建议升级前 `git diff > /tmp/patches.diff`，升级后 `git apply /tmp/patches.diff`，处理 conflict。同时检查上游 issue 是否 fix 了 task 渲染（#45 #97）或 actionRequestsMap key（如果 fix 了可以删 broadcastResumeInterrupt）。
- **@langchain/langgraph-sdk 升级**：跑一次 HITL approve，如果不再 422，删 useChat.ts 的 fetch monkey-patch。
