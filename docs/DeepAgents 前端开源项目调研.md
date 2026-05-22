# 适配 deepagents 的开源前端方案深度调研报告

## TL;DR

- **直接尝试官方 `langchain-ai/deep-agents-ui`(1.6k★, MIT, Next.js 16 + React 19)**:它是 LangChain 团队为 deepagents 量身打造的前端,原生支持 todo 列表、虚拟文件浏览、sub-agent 执行树、tool 流式渲染与 `ToolApprovalInterrupt` 审批 UI,与 deepagents 状态 schema 零适配,5 分钟即可本地跑通(`yarn install && yarn dev` + `langgraph dev`)。
- **追求审美与定制深度**:推荐 **assistant-ui(10.1k★)+ `@assistant-ui/react-langchain` 适配器** 或 **CopilotKit(31.5k★)+ AG-UI 协议 + `CopilotKitMiddleware`**。前者交付组件化、shadcn/ui 风格的 chat 原语,后者通过官方文档化的 deep agents 集成路径(`docs.copilotkit.ai/langgraph/deep-agents`)提供 generative UI、shared state、HITL。
- **不要选 Open Agent Platform**(已于 2026-02-25 被 LangChain 官方 archive 并明确弃用);**不要硬套通用 ChatGPT 风格 UI**(LobeChat / Open WebUI / LibreChat)——它们不理解 LangGraph 的 stream/interrupt/state 协议,改造成本远高于直接 fork deep-agents-ui。

---

## Key Findings

### 第一性原理:deepagents 给前端提了什么硬约束

deepagents 不是一个普通的 chat 后端。`create_deep_agent()` 返回的是一个 **LangGraph CompiledStateGraph**,其 state 在 `messages` 之外还显式暴露了 `todos`、`files`、以及通过 SubAgentMiddleware 派生出的 subagents 流。这意味着合格的前端必须能做到:

1. **理解 LangGraph SSE/WebSocket 事件流**(`on_chat_model_stream`、`on_tool_start/end`、`updates`、`interrupt` 等),否则只能拿到完整消息,丢失流式体验。
2. **读取自定义 state key**(`stream.values.todos`、`stream.subagents`、`stream.values.files`),用于渲染规划列表、文件树、子 agent 卡片。LangChain 官方在 `docs.langchain.com/oss/python/deepagents/frontend/overview` 明确写道:"Deep agent patterns use additional useStream features like `stream.subagents`, `stream.values.todos`, and `filterSubagentMessages` to render subagent-specific UIs."
3. **处理 `interrupt()` 中断**并通过 `useChat.resumeInterrupt()` 或等价机制把审批/编辑结果送回 graph,这是 HITL 的核心。

由此可以反推出一条筛选漏斗:**第一档** = 直接消费 LangGraph SDK 的 React hooks(`@langchain/langgraph-sdk/react` 的 `useStream` / `useChat`);**第二档** = 通过 AG-UI 协议适配器(`ag-ui-langgraph`、`@copilotkit/runtime`)消费;**第三档** = 通用 chat UI 需要写大量胶水代码才能用。

### 一句话候选项目全景(按适配度从高到低)

| # | 项目 | Star | License | 与 deepagents 的关系 |
|---|------|------|---------|---------------------|
| 1 | **langchain-ai/deep-agents-ui** | 1.6k | MIT | **官方专属 UI**,Next.js 16 + React 19 + Turbopack,内置 todos/files/sub-agents/approval 视图 |
| 2 | **langchain-ai/agent-chat-ui** | 2.5k | MIT | 通用 LangGraph chat UI,生态主线,但对 deepagents 的 todos/files 没专属渲染 |
| 3 | **assistant-ui/assistant-ui** | 10.1k | MIT | React chat 原语库,有 `@assistant-ui/react-langchain` + `useLangChainState` 可读 todos/files |
| 4 | **CopilotKit/CopilotKit** | 31.5k | MIT | 通过 `CopilotKitMiddleware` + AG-UI 接入 deepagents,官方文档专章 `docs.copilotkit.ai/langgraph/deep-agents` |
| 5 | **ag-ui-protocol/ag-ui** | 13k | MIT | 协议而非 UI;`ag-ui-langgraph` Python 包提供 FastAPI 端点适配 |
| 6 | **Chainlit/chainlit** | 12.1k | Apache-2.0 | Python 原生 chat UI,可通过 LangGraph 集成,但无 deepagents 专属可视化 |
| 7 | langchain-ai/open-agent-platform | 1.9k | MIT | **已于 2026-02-25 archive,弃用,不推荐** |
| 8 | LobeChat / Open WebUI / LibreChat | 30k–80k | 各异 | ChatGPT 风格通用 UI,**不原生说 LangGraph 协议**,适配成本极高 |

### 三大核心能力对各档的支持矩阵

| 维度 | deep-agents-ui | agent-chat-ui | assistant-ui + react-langchain | CopilotKit + AG-UI | Chainlit |
|------|----------------|---------------|-------------------------------|--------------------|----|
| **Todo 列表实时可视化** | ✅ 内置 `TasksFilesSidebar`,从 `state.values.todos` 直读 | ⚠️ 需自定义渲染 | ✅ `useLangChainState<Todo[]>("todos")` 一行代码 | ✅ 通过 shared state | ⚠️ 需自己写 |
| **Sub-agent 执行树** | ✅ 内置(配合 SubAgentMiddleware 6-step workflow 展示) | ❌ 默认不渲染 | ✅ 通过 `stream.subagents` Map | ✅ Agent Inspector 显式支持 | ❌ |
| **Token / tool call 流式** | ✅ WebSocket + Turbopack | ✅ 完善 | ✅ 极佳(retries、auto-scroll、markdown、code highlight) | ✅ SSE | ✅ AIMessageChunk 流 |
| **HITL 中断 / 审批** | ✅ `ToolApprovalInterrupt` 内置,含 ReviewConfig | ✅ 通过 generic interrupt UI(有 fork 项目 `piotrgoral/agent-chat-ui-human-in-the-loop`) | ⚠️ 曾有 Issue #1280 #1899 报告 Python 后端 interrupt 实现不完整,需注意版本 | ✅ `renderAndWaitForResponse` | ⚠️ 需手动调度 |
| **文件浏览/虚拟 FS** | ✅ 文件侧边栏 + 单文件查看 | ❌ | ⚠️ 需自己写 | ✅ 通过 generative UI 渲染 | ❌ |
| **Generative UI / 自定义组件** | ✅ 支持 `uiComponent` + `LoadExternalComponent` | ✅ | ✅ Tool result → React component | ✅ 旗舰能力 | ⚠️ 弱 |

### 审美与设计系统的客观比较

- **deep-agents-ui**:基于 shadcn/ui(仓库内含 `components.json`)+ Tailwind + Radix(隐式通过 shadcn)+ Geist 字体(默认 Next.js 16 模板),布局是三栏:Thread 列表 / Chat / Tasks+Files 侧边栏,信息层次清晰。视觉风格偏开发者工具("LangSmith Studio lite"),但已具备生产级 chat UI 的所有打磨细节(虚拟列表、collapsible tool box、流式 markdown、深浅色)。
- **assistant-ui**:行业公认审美最在线的开源 React chat 框架。LangChain 官方博客《Build stateful conversational AI agents with LangGraph and assistant-ui》(blog.langchain.com/assistant-ui/)中明确写道:"assistant-ui shares a lot of our same focuses and believes, making it a seamless stack to build agents upon. We've worked with Simon (the maintainer) to add a tight integration with LangGraph Cloud。"组件原语(`Thread`、`Message`、`Composer`、`ThreadList`、`ActionBar`)是 chat UI 领域的"shadcn moment"。
- **CopilotKit**:整套设计资产更"产品化"——预制 `<CopilotChat />`、`<CopilotPopup />`、Agent Inspector 浮层;`copilotkit.ai` 主页与 enterprise 客户(Deutsche Telekom / Docusign / Cisco / S&P Global,来自 TechCrunch 2026-05-05 报道)的实际案例反映其视觉规范成熟。
- **agent-chat-ui**:UI 偏功能性,生成式 UI 通过右侧 artifacts 面板呈现,设计细节不如 deep-agents-ui 精致。
- **LobeChat / Open WebUI / LibreChat**:美感最极致(尤其 LobeChat),但完全是为通用 ChatGPT-clone 设计,没有 todos/subagents/files 的渲染槽位,改造意味着大动手术。

### 本地部署友好度

- **deep-agents-ui**:`git clone && yarn install && yarn dev`,只需要后端 `langgraph dev` 起在 :2024,UI 起在 :3000。LangSmith API Key 可选,**不强依赖云服务**。
- **agent-chat-ui**:同样 Next.js 本地起,可选 LangSmith。也提供 `npx create-agent-chat-app` 脚手架捆绑 4 个内置 agent(`react`、`memory`、`research`、`retrieval`)。
- **assistant-ui**:`npx create-assistant-ui -t langgraph` 一键脚手架,纯 Next.js,无云依赖。
- **CopilotKit**:开源自托管 runtime `@copilotkit/runtime`(MIT)。**注意**:enterprise 功能(thread persistence、analytics、self-learning layer)属于 CopilotKit Enterprise Intelligence Platform,需付费授权(虽可 self-host);但纯前端 SDK + AG-UI 协议是免费开源的。
- **Chainlit**:`pip install chainlit && chainlit run app.py`,Python 单体,部署最简单,但 deep agents 的 state 可视化需自己实现。
- **Open Agent Platform**:官方已弃用,且依赖 Supabase auth + LangGraph Platform 部署,不适合简化的本地场景。

### 与 deepagents 的具体集成证据(可引用的官方信号)

- **deepagents-quickstarts 仓库的 `deep_research/README.md` 第 43-67 行**明确写道接入步骤是先 `langgraph dev` 后 `cd deep-agents-ui && yarn dev`(deepwiki 已索引)。
- **LangChain 0.6 升级**(发布博客《New in Deep Agents v0.6》)显式宣布:`stream_events(..., version="v3")` 与 `@langchain/react` v1 框架集成 hooks (`useStream`) 是"deep agents 友好的"streaming 基线;并放出 Streaming Cookbook。
- **CopilotKit 官方文档**: `docs.copilotkit.ai/langgraph/deep-agents` 页面("Leverage LangGraph Deep Agents to build sophisticated agentic applications"),代码示例 `middleware=[CopilotKitMiddleware()]` 直接注入到 `create_deep_agent` 调用。
- **assistant-ui 文档**:`useLangChainState<Todo[]>("todos", [])` 是为 deep agent 的 todo 渲染量身列出的示例。
- **AG-UI 协议**:`ag-ui-langgraph` (PyPI 0.0.35,2026 Q1 更新)提供 `add_langgraph_fastapi_endpoint(app, graph, "/agent")` 一行代码把 `create_deep_agent` 出来的图变成 AG-UI 端点。
- **LangChain 官方论坛已有用户讨论 deepagents subagent 流的持久化**(`forum.langchain.com/t/.../2991`),侧证 useStream + subagents 是主流推荐路径。

### 已知坑(version-pinning 与协议兼容性)

1. **assistant-ui 的 LangGraph HITL interrupt 适配在历史版本有 bug**:Issue #1280("LangGraph human-in-the-loop interrupt approvals is implemented incorrectly",2024-12-28)+ Issue #1899("HITL Interrupt Flows Not Working with assistant-ui and LangGraph with Python",2025-04-23)记录了 `useLangGraphRuntime` 在 Python 后端 + interrupt 路径下 Approve/Reject 没把指令送回 graph 的问题。需要使用最新版本或参考 `assistant-ui-stockbroker` 示例对齐。
2. **AG-UI Python 集成历史上 LangGraph 侧曾偏 TypeScript**:GitHub Issue #83 (2025-06) 用户呼吁 out-of-box Python LangGraph wrapper,后续 `ag-ui-langgraph` PyPI 包补齐;部署时确认版本 ≥ 0.0.30。
3. **deepagents v0.6 的 streaming v3 / delta channels / harness profiles** 改变了事件结构。如果 fork deep-agents-ui 或 agent-chat-ui,需确认 `@langchain/langgraph-sdk` 客户端版本与后端 deepagents 版本匹配,否则 subagent 流类型推断会失败。
4. **deep-agents-ui 在 `langgraph dev` 默认端口上有两个文档版本(2024 vs 8123)**——以 langgraph CLI 实际输出为准。
5. **Open Agent Platform 已 archive**:不要再以它为基线开发,LangChain 官方推荐迁移至 LangSmith Agent Builder(闭源 SaaS)。

---

## Details:每个候选项目的逐项评估

### 1. langchain-ai/deep-agents-ui — 最直接的选择

- **GitHub**:1.6k stars,322 forks,MIT,TypeScript 84.2%(173 commits,README 截图日期 2025-11-17,持续活跃)。
- **技术栈**:Next.js 16.1.6 (App Router) + React 19.1.0 + Turbopack + shadcn/ui + Tailwind + Radix + `@langchain/langgraph-sdk/react`(`useChat`) + SWR(线程列表)+ nuqs(URL state)。
- **专属能力**:
  - `TasksFilesSidebar.tsx`:实时映射 `state.values.todos` 与 `state.values.files`,文件点击进入查看面板。
  - `ToolCallBox.tsx`:折叠/展开 tool call,支持 `uiComponent` 字段触发 `LoadExternalComponent` 生成式 UI。
  - `ToolApprovalInterrupt.tsx`:处理 LangGraph interrupt,UI 提供 approve/reject/edit 三态(可通过 `ReviewConfig` 受后端约束)。
  - **Debug Mode**:可逐步执行,配合 LangSmith Optimizer 调优(可关闭进入端到端模式)。
- **本地部署**:零云依赖。仅 LangSmith API Key 可选,通过 settings dialog 输入。
- **缺点**:整体设计偏开发工具,而非面向最终用户的产品级体验;UI 不可拆分为组件库二次复用;线程/历史侧边栏的设计略偏调试器。
- **结论**:**就用它**(或在其基础上换主题)是回报/投入比最高的路径。

### 2. langchain-ai/agent-chat-ui — 通用底座

- **GitHub**:2.5k stars,573 forks,MIT,TypeScript 95.3%,Next.js + `@langchain/langgraph-sdk`。
- **能力**:通用 LangGraph chat,支持流式、tool call 渲染、artifacts 侧边栏、`langsmith:nostream`/`langsmith:do-not-render` 标签精细控制消息可见性、`useChat.resumeInterrupt()` HITL。可通过 `create-agent-chat-app` 一键脚手架。
- **对 deepagents 的支持**:**没有专门为 todos / subagents 设计的渲染槽位**——你能跑通对话,但要看到 todo list 进展和子 agent 卡片需要写自定义组件。社区 fork(`piotrgoral/agent-chat-ui-human-in-the-loop`)展示了 HITL 实现路径。
- **审美**:功能完备但视觉打磨弱于 deep-agents-ui 和 assistant-ui;artifacts 面板是亮点。
- **何时选择**:你已经有非 deepagents 的 LangGraph 图,想要一个统一 chat UI 入口;或你打算把 deepagents 作为多个图之一接入。

### 3. assistant-ui — 审美与定制深度的天花板

- **GitHub**:10.1k stars,~1k forks,MIT,3036 commits,最新发布 `@assistant-ui/store@0.2.7`(2026-04-13),发布频率极高(1344 个 release)。
- **技术栈**:TypeScript-first React 库,composable primitives + shadcn/ui 主题,集成包矩阵覆盖 Vercel AI SDK / LangGraph / LangChain / AG-UI / A2A / Google ADK / OpenCode。
- **集成 deepagents 的两条路径**:
  - **`@assistant-ui/react-langgraph`**(由 `npx create-assistant-ui -t langgraph` 默认模板使用):基于 ExternalStoreRuntime,功能最全(subgraph 事件、generative UI、end-to-end cancellation)。
  - **`@assistant-ui/react-langchain`**(更薄的新包):直接镜像 `useStream`,可用 `useLangChainState<T>(key)` 读取自定义 state(todos、files、plans)。
- **审美**:LangChain 官方在 blog.langchain.com/assistant-ui/ 撰文背书:"assistant-ui shares a lot of our same focuses and believes, making it a seamless stack to build agents upon. We've worked with Simon (the maintainer) to add a tight integration with LangGraph Cloud."组件原语风格与 shadcn/ui 一致,流式、自动滚动、retry、附件、markdown、code highlight、语音听写、键盘快捷键、a11y "out of the box"。Examples 页面包含 `assistant-ui-stockbroker`(HITL 教科书示例)、Open Source Claude Artifacts 复刻、Open Canvas 复刻、原生 iOS/Android chat app 等参考实现。
- **HITL 历史问题**:Issue #1280 与 #1899(详见上文坑)需用新版规避。
- **何时选择**:你打算把 deepagents 包装成一个独立产品(而非内部调试工具),需要顶级的视觉与交互细节,并愿意花 1-2 周用 `useLangChainState` 把 todos/subagents/files 自己渲染成漂亮组件。

### 4. CopilotKit + AG-UI — 最丰富的 Generative UI 与 enterprise 路径

- **GitHub**:31.5k stars,4k forks,MIT,9029 commits,latest release v1.57.1(2026-05-07)。CopilotKit 自己在 series-a 公告页中称"over 40,000 GitHub stars"(CopilotKit + AG-UI 合计)。
- **融资与生态**:据 TechCrunch 2026-05-05 独家报道,"CopilotKit raises $27M in a Series A round led by Glilot Capital, NFX, and SignalFire"(GeekWire 进一步拆分为 $20M Series A + $7M 先前未公开 seed)。Google / Microsoft / Amazon / Oracle / LangChain / Mastra / PydanticAI / Agno 均背书 AG-UI 协议;Fortune 500 客户公开包括 Deutsche Telekom / Docusign / Cisco / S&P Global。
- **集成 deepagents**:官方文档 `docs.copilotkit.ai/langgraph/deep-agents`,代码示例如下:
  ```python
  from copilotkit import CopilotKitMiddleware
  agent = create_deep_agent(
      model="openai:gpt-4o",
      tools=[get_weather],
      middleware=[CopilotKitMiddleware()],
      system_prompt="...",
  )
  ```
  前端通过 `@copilotkit/react-core` + `@copilotkit/react-ui` 的 `useCoAgent` / `useCoAgentStateRender` / `useCopilotReadable` hooks,把 deepagents 的 todos/files 实时映射成 React 组件。已有官方 showcase `CopilotKit/deep-agents-job-search-assistant`(monorepo `examples/showcases/deep-agents-job-search`)与博客《How to build a Frontend for LangChain Deep Agents with CopilotKit》提供完整端到端代码。
- **强项**:
  - **Generative UI** 是头部能力(`renderAndWaitForResponse` 收集 HITL 同意、`useCopilotAction` 注册 frontend tool、Backend Tool Rendering 把后端 tool result 直接渲染成 React)。
  - **AG-UI 协议** 解耦前后端,未来想换 Agent 框架不用动 UI 层。
  - **Agent Inspector** 浮层提供运行时调试。
- **本地部署**:核心 framework MIT 自托管;`@copilotkit/runtime` 是开源 SDK。**注意**:Enterprise Intelligence Platform(thread persistence、analytics、self-learning)是商业产品,虽然官方声明"can be self-hosted",但需购买授权。
- **何时选择**:你的目标是把 deepagents 作为 in-app copilot 嵌入到已有 React/Next.js 应用里,且需要 generative UI / shared state / 富 HITL。
- **缺点**:学习曲线比 deep-agents-ui 陡峭;协议层抽象带来概念栈较深(CopilotKit + AG-UI + LangGraph 三层)。

### 5. ag-ui-protocol/ag-ui — 协议,不是 UI

- **GitHub**:13k stars,1.2k forks,MIT,multi-language SDK,最新发布 `Release 2026-04-06`。
- **定位**:开放协议(~16 个标准事件:`RunStarted`、`TextMessageStart/Content/End`、`ToolCallStart/Args/End`、`StateSnapshot/Delta`、`MessagesSnapshot` 等)。`ag-ui-langgraph` Python 包提供 FastAPI 一行接入。
- **何时直接基于协议开发**:你不想绑 CopilotKit 的 React 组件,而要自己写 UI(Vue / Angular / Svelte 等),或要写跨 backend 适配器。

### 6. Chainlit — Python 单体最快路径

- **GitHub**:~12.1k stars,~1.7k forks,Apache-2.0,Python。**重要警示**:Chainlit README 原文写明:"As of May 1st 2025, the original Chainlit team has stepped back from active development. The project is maintained by @Chainlit/chainlit-maintainers under a formal Maintainer Agreement. Chainlit SAS provides no warranties on future updates."最新版本 v2.11.1(2026-04-22)显示发布频率仍正常。
- **能力**:Python 装饰器风格(`@cl.on_chat_start` / `@cl.on_message`)极易上手;官方文档有 LangGraph 集成示例;支持 token streaming、tool 调用展示、文件附件、buttons/sliders 自定义 UI、MCP 集成。
- **对 deepagents 的限制**:**没有 todos / sub-agents 的标准化渲染**——需手写消息分发逻辑读 graph state。不如 React 阵营对 deepagents state 的"对位"自然。
- **何时选择**:团队全 Python、不想引入 Node.js;原型阶段或内部 demo;不需要追求顶级 UI 审美。

### 7. langchain-ai/open-agent-platform — ⚠️ 已弃用

- **状态**:仓库于 2026-02-25 被 owner archive,README 声明 "This repository has been deprecated",官方推荐迁移至 LangSmith Agent Builder(闭源 SaaS)。
- **结论**:**不要选**。即使曾经有"Agent Supervisor 多智能体编排"等亮点,生态维护已停止。

### 8. LobeChat / Open WebUI / LibreChat / Big-AGI / chatbot-ui — 不推荐

这些都是 ChatGPT-clone 风格的通用 chat 前端,设计精美(LobeChat 尤其),但它们消费的都是 OpenAI-compatible REST API。**对接 LangGraph 流(SSE 多事件类型、interrupt 协议、自定义 state)需要写大量适配层**,而你写完适配层之后,仍然无处展示 todos/files/subagents——因为它们的视觉模板里就没这块布局槽位。改造成本远超直接 fork deep-agents-ui。

### 9. assistant-ui-langgraph-fastapi(Yonom 维护)

参考性 demo 仓库,展示 FastAPI + LangGraph + assistant-stream + assistant-ui 的完整骨架。可作为 assistant-ui 路径的起点工程。

### 10. LangGraph Studio

LangSmith 内置 Studio UI(`https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`)是开发者调试工具,**不适合作为最终用户面向的 UI**。但和 deep-agents-ui 是天然互补的:Studio 看 graph topology + trace,deep-agents-ui 看对话和工作产物。

---

## Recommendations

### 路径 A:7 天内出可用 demo(快速接入)

1. `git clone https://github.com/langchain-ai/deep-agents-ui` + `yarn install && yarn dev`
2. 后端 `langgraph dev` 起 deepagents 实例(参考 `deepagents-quickstarts/deep_research`)
3. UI 里填 Deployment URL + Assistant ID,直接跑通 todo / files / approval 全链路
4. 想换皮:基于 shadcn/ui 改主题色、字体、Logo;无需动 stream 逻辑

**判断切换路径的阈值**:如果 PoC 跑通后,你发现需要嵌入到现有 React 应用 / 需要 brand 化的产品级 UI / 需要 generative UI 渲染 charts 等富组件——切到路径 B。

### 路径 B:3-6 周内出产品级体验

- 前端基座:**assistant-ui**(`npx create-assistant-ui -t langgraph`),用 `@assistant-ui/react-langchain` + `useLangChainState<Todo[]>("todos")` / `useLangChainState<File[]>("files")` 自定义 sidebar
- HITL 路径:参考 `assistant-ui-stockbroker` 示例,注意采用最新版本规避 Issue #1280/#1899
- Generative UI:用 assistant-ui 的 tool-call → React component 模式

### 路径 C:深度集成到现有应用(企业级)

- 后端:`create_deep_agent(..., middleware=[CopilotKitMiddleware()])`
- 协议层:AG-UI(`ag-ui-langgraph` FastAPI endpoint 或 CopilotKit Runtime)
- 前端:**CopilotKit React SDK**(`@copilotkit/react-core` + `@copilotkit/react-ui`)
- 参考实现:`CopilotKit/deep-agents-job-search-assistant` 与官方 deeplearning.ai 课程《Build Interactive Agents with Generative UI》(Atai Barkai 讲师,2026)
- 何时升级到 enterprise:需要 thread persistence / user analytics / self-learning,**评估 CopilotKit Enterprise Intelligence Platform**(可 self-host,商业授权)

### 路径 D:Python-only 团队的最小化方案

- Chainlit + LangGraph 集成,接受不会渲染 todos/subagents 的 UI 限制
- 仅当真的不能引入 Node.js 工具链才采用

### 升级路径切换信号

| 触发条件 | 从 → 到 |
|----------|---------|
| 需要把 UI 嵌入已有 React 应用 | 路径 A → 路径 B/C |
| 需要 generative UI(charts、forms、custom widgets) | 路径 A → 路径 C |
| 需要为最终用户做品牌化设计 | 路径 A → 路径 B |
| 需要 thread 持久化 + 用户分析 | 路径 C 开源 → CopilotKit Enterprise |
| 团队不会 TypeScript | 任何 → 路径 D(Chainlit) |

### 实施清单

- [ ] 锁定 deepagents 版本(强烈建议 ≥0.6,以匹配 streaming v3 / `useStream` subagent API)
- [ ] 锁定 `@langchain/langgraph-sdk` 客户端版本与后端兼容
- [ ] 不依赖 LangSmith API Key 跑本地链路(deep-agents-ui 支持纯本地)
- [ ] 在 LangGraph `interrupt()` 节点显式约束 `ReviewConfig`(approve/reject/edit),前端才能正确渲染
- [ ] 用 `langsmith:nostream` / `langsmith:do-not-render` tag 控制中间链路 LLM 的可见性
- [ ] 不要用 Open Agent Platform(已 archive)

---

## Caveats

1. **deepagents 与 LangChain 生态都在快速迭代**。本文版本基线:deepagents v0.6(2026 Q1 发布)、Next.js 16、React 19、`@assistant-ui/store` 0.2.7、CopilotKit v1.57.1、`ag-ui-langgraph` 0.0.35。后续版本可能改变 stream event schema(尤其 v3 → v4 时)。
2. **assistant-ui HITL 在历史版本(2024 Q4 – 2025 Q2)曾不正确处理 LangGraph Python 后端的 interrupt**。Issue #1280 / #1899 已关闭但需用新版本并对齐 `assistant-ui-stockbroker` 模式。
3. **CopilotKit "self-host" 的范围**需厘清:核心 framework 与 runtime 是 MIT 开源,但 Enterprise Intelligence Platform(thread persistence / analytics / self-learning)是商业产品,虽然官方声明可"self-host",但需购买授权。
4. **agent-chat-ui 在生产部署需要 API Passthrough**,默认配置仅适合本地;若要支持多用户线上访问,需用 `NEXT_PUBLIC_API_URL=https://my-website.com/api` 把请求代理过服务端,LangSmith API Key 由服务端注入。
5. **deep-agents-ui 的视觉风格偏调试器**。如果目标是面向最终用户的"产品",直接用它可能感觉太"开发者向",建议至少做主题色/字体/Logo 替换。
6. **Generative UI 渲染**依赖 LLM 输出结构化 JSON 或 HTML。模型能力不足时(开源小模型)效果有限——官方 CopilotKit 的 OpenGenerativeUI README 明确写"Strong models required"。
7. **本报告未实测**所有方案的完整对比 demo;UI 审美是基于设计系统选择(shadcn/ui、Radix、Tailwind)、官方截图与社区评价的综合判断,不构成主观偏好背书。
8. **Chainlit 维护状态有变**(原团队 2025-05 退出,社区接管),长期生命力需观望;近期发布频率仍正常。
9. **不推荐的 LobeChat / Open WebUI / LibreChat 阵营**,本身是优秀产品但目标用例不同——它们解决的是"私有化部署 ChatGPT 替代品",而非"为复杂 LangGraph agent 提供可视化"。强行套用会浪费工程预算。
10. 部分搜索结果带未来时间戳(2026 年发布),已交叉验证为真实发布而非预测。