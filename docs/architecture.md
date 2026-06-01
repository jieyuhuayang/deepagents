# 技术架构

这是一个本地跑的 Deep Research demo:用户在浏览器问一个问题,主 agent 拆任务 → 派 N 个 sub-agent 并行调研 → 关键写操作触发人审 → generative UI 实时渲染调研卡 → 主 agent 汇总成报告。系统由三层构成——浏览器(`deep-agents-ui`)、`langgraph dev` 运行时、Python `deepagents` 编排,各层之间用 LangGraph SDK 的 SSE 协议联通。

本文按 "**运行机制(§2) → 跨上游适配(§3) → 演进路径(§4)**" 三层展开。**普通使用者读 README 即可**;本文是给排错、二次开发、技术选型评估的人看的。运行期具体故障定位见 [troubleshooting.md](./troubleshooting.md)。

## 1. 系统总览

```
浏览器 :3000  ──HTTP/SSE──>  langgraph dev :2024  ──>  Python: agent.py
   │                              │                          │
   │ useStream                    │ LangGraph Platform        │ create_deep_agent(
   │ (@langchain/langgraph-sdk)   │ Runtime (inmem)            │   model=ChatOpenAI(DashScope),
   │                              │                            │   tools=[web_search, think_tool,
   │ React 19 + Next.js 16        │ checkpointer auto-managed  │          emit_research_card,
   │ shadcn/ui + Tailwind         │ + 内置 Todo/Filesystem/Sub │          request_clarification,
   │ LoadExternalComponent (本地) │   (HumanInTheLoop 当前未   │          export_docx],
   │                              │   装配,见 §2.3)            │   subagents=[research-agent],
   │                              │                            │   middleware=[GenerativeUIMiddleware()])
```

**一次请求的端到端流程**:

1. 浏览器 `useStream` 把用户问题 POST 到 `:2024/runs/stream`,订阅 SSE。
2. `langgraph dev` 加载 `backend/langgraph.json` 里 graph `research`,调度 `create_deep_agent` 装配出来的图(`research` 是前端 Assistant ID 的契约,UI 设置弹窗必须填这个名字)。
3. **Step 0(可选,仅问题模糊时)**:主 agent 调 `request_clarification`,工具内调 langgraph 原生 `interrupt()` 暂停 graph,前端弹澄清卡;用户填答后 resume,主 agent 把答案 dict 用于后续(详见 §2.6)。
4. 主 agent 思考 → 写 todo(`write_todos`)→ 串行/并行调 `task` 工具委派 sub-agent 调研(当前**无 HITL 拦截**)。
5. sub-agent 跑搜索 + 总结,通过 `emit_research_card` 推送 generative UI 消息到 `state.ui[]`,前端实时渲染。
6. 全部 sub-agent 完成后,主 agent 调 `write_file` 写 `report.md`(以及可选的 `report.html` / `export_docx`)落盘到虚拟文件系统(当前**无 HITL 拦截**,详见 §2.3)。
7. 主 agent 给用户 2-3 句最终回复,列出产出文件。

**故障与扩展定位**:启动错误或具体运行期现象先查 [troubleshooting.md](./troubleshooting.md);想理解"agent 实际怎么跑"看 §2.0;搞清楚某个机制能不能扩展、为什么这样设计看 §2.x;哪些代码因为基于 vendored 上游而不能动看 §3;评估"上游升级后能拆掉哪些适配"看 §4。

**部署模型**(自 v0.5.0 全面改为自研 server,详见 `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/`):

| 场景 | 启动命令 | 端口 | Checkpointer | DB 形态 |
|---|---|---|---|---|
| 本地 Macbook | `uvicorn server:app --port 2024` | `:2024` | `AsyncSqliteSaver` | `backend/local.db`(单文件,零 docker) |
| lab host (192.168.106.114) | `./deepagents.sh start`(内部 `uvicorn server:app --port 12024`) | `:12024` | `AsyncPostgresSaver` | 独立 `deepagents-postgres` docker container + volume `deepagents_pgdata` |

两套通过 `DATABASE_URL` env 切换,`backend/server.py` 的 lifespan 自动路由 saver 类型。`backend/agent.py` 提供 `build_agent(checkpointer)` factory,由 server 启动时显式传入(强约束 §3 修订)。前端通过 `NEXT_PUBLIC_*` 环境变量切 Deployment URL(commit `93cb122` + `6155088`)。

> **历史**:v0.5.0 草案曾计划用 `langgraph up`(LangGraph Platform)做持久化部署,实施时发现这是 **LangChain 公司的商业产品**——`langchain/langgraph-api` 镜像启动时强制 LangSmith Plus key 或 Cloud license 验证;且 lab host docker bridge HTTPS 出口被防火墙挡,双重阻塞。撤回方案详见 [`docs/features/v0.5.0/001-langgraph-up-deployment/`](../features/v0.5.0/001-langgraph-up-deployment/)(ABANDONED ADR)。`langgraph` 核心库 + `langgraph-checkpoint-{postgres,sqlite}` 是 OSS(Apache),自托管完全免费——这就是 002 走的路径。`langgraph dev`(本地 quick smoke)仍可用,但 backend 默认入口换成 `uvicorn server:app`。

## 2. 运行机制

§2.0 先给出端到端调研工作流的步骤总览,作为下面各子系统的语境。然后按 deepagents 的四字段 state schema 切分子系统:**编排**(§2.1 主 agent 怎么调度,内含 §2.1.1 工具清单)、**状态**(§2.2 messages/todos/files/ui 如何承载工作记忆)、**人在回路**(§2.3 关键操作如何让用户介入)、**渲染**(§2.4 前端如何把进度可视化)。§2.5 / §2.6 则分别讲多格式报告产物和两种暂停机制——它们横跨多个子系统,单列章节方便排错与扩展时定位。

### 2.0 一次调研的工作流总览(Step 0–5)

`backend/prompts.py:ORCHESTRATOR_PROMPT` 的 Hard Rules 把主 agent 的行为约束成一条确定的 6 步流水线。**本节是 prompt 的可读视图——改 prompt 时同步本节,否则文档会快速漂移。**

```
Step 0  request_clarification   ── 仅在问题模糊时(否则跳过)
Step 1  write_todos              ── 主 agent 规划 3-6 个子主题 + 1 个"写报告" todo
Step 2  task → research-agent    ── 每个子主题一次委派(可并行)
Step 3  emit_research_card       ── 每个子主题完成立即推卡
Step 4  write reports            ── 4a) report.md(必出) / 4b) report.html(可选) /
                                    4c) export_docx(可选)
Step 5  最终文本回复             ── 列产出文件
```

每步对应的子系统:Step 0 走 §2.6 的 tool 内 `interrupt()` 通道;Step 1 / 2 / 5 是 §2.1 编排;Step 3 是 §2.4 渲染;Step 4 是 §2.5 多格式报告。

**Step 0 与 Step 1 互斥(项目独有硬约束)**。模糊问题触发 Step 0 时,主 agent 必须**只调一次 `request_clarification` 并停下**,不能同 turn 调 `write_todos` / `think_tool`,也不能用文字回复("the card IS the message")。**最多 1 轮澄清**——用户回答后若关键字段仍模糊,直接套用 Silent Defaults 继续,**永远不能调第二次 `request_clarification`**。

**Silent Defaults**(用户没说就按这套走,不询问):

| 字段 | 默认值 |
|---|---|
| `time_window` | 过去 12 个月(除非话题本质上是历史性的) |
| `audience` | 技术普及读者 |
| `depth` | 3-5 个子主题 + 1 个"写报告" todo |
| `output_language` | 跟随用户输入语言 |
| `output_formats` | **仅 `markdown`**(`html` / `docx` 必须用户显式要,不能猜) |

`request_clarification` 返回的 ToolMessage content 是 JSON dict(如 `{"scope": "both", "output_formats": ["markdown", "html"]}`);若用户在"+ 其他"里填了自由文本,值可能是任意字符串(单选)或字符串列表(多选)——主 agent 应把任意值当用户真实选择处理,不要回退到 preset value。

### 2.1 编排层:主 agent + sub-agent + 自定义 LLM

`create_deep_agent` 装配主 agent,内置 `task` 工具自动委派 sub-agent;`subagents=[...]` 在 `agent.py` 中声明,每个 sub-agent 有独立 prompt + 工具集。主 agent 通过调用 `task(description, agent_name)` 派活,框架自动建立子上下文、跑完后把结果回填到主 agent 的 messages。

**LLM provider 锁定 ChatOpenAI + DashScope**。`init_chat_model("anthropic:...")` 会走 LangChain provider registry,没法指向 DashScope,所以必须用 `ChatOpenAI(base_url=..., api_key=..., model="deepseek-v4-pro")` 直接实例化 LLM 对象传给 `create_deep_agent`。切换模型在 `.env` 里改 `DEEPAGENTS_MODEL`(任何 DashScope OpenAI-compatible 模型)。

⚠️ **历史踩坑**:早期 plan 写过 `disable_streaming=True`,依据是"DashScope tools+stream 互斥"。**这条已被证伪**:阿里云[兼容文档](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)里"暂时无法"是 2023-2024 年针对 qwen-turbo/plus/max 的老限制,现代模型(deepseek-v4-pro、qwen3.6-plus 等)支持 tools+stream 同时使用。不要把 `streaming=True` 改回 `False`。

**扩展边界**:加新 sub-agent → 在 `agent.py` 的 `subagents` 列表加配置 + 在 `prompts.py` 加对应 prompt;加新工具 → 在 `tools.py` 写,然后注册到主 agent 或某个 sub-agent 的 tools 列表(见 §2.1.1 工具清单)。

> 模型实际行为偏差(跳过 `emit_research_card` / 重复调研等)见 [troubleshooting.md](./troubleshooting.md) 第 2 节"模型行为"。

#### 2.1.1 工具清单

当前 `backend/tools.py` + deepagents 内置工具一览(主 agent / research-agent / 内置三栏):

| 工具 | 调用方 | 副作用 | 详细章节 |
|---|---|---|---|
| `web_search(query)` | research-agent | 网络(provider 决定) | §2.1.1.a |
| `bisheng_retrieve(query, top_k=8)` | research-agent | 网络(私域 KB) | §2.1.1.b |
| `think_tool(reflection)` | 主 + research | 无 | §2.1.1.c |
| `emit_research_card(title, summary, sources)` | 主 | 推 generative UI 到 `state.ui[]` | §2.4 |
| `request_clarification(restate, questions)` | 主 | 暂停 graph(tool 内 `interrupt()`) | §2.6 |
| `export_docx(source_path, dest_path)` | 主 | 写 `state.files`(base64 二进制) | §2.5 |
| `write_todos` / `task` / `write_file` / `edit_file` / `read_file` / `ls` | 主 / 内置 | 写 `state.todos` / `state.messages` / `state.files` | (deepagents 提供) |

##### 2.1.1.a web_search 与可插拔 provider 层

`SEARCH_PROVIDER` env 切换 provider(默认 `duckduckgo`):

| provider | env 必填 | 备注 |
|---|---|---|
| `duckduckgo` | (无) | 默认。`langchain_community.utilities.DuckDuckGoSearchAPIWrapper`,高频访问会限流 |
| `tavily` | `TAVILY_API_KEY` | 用 tavily-python 原生 SDK,**不**用 `langchain_tavily`(后者的 `forbidden_params` 黑名单坑见下文) |
| `cloudsway` | `CLOUDSWAY_ACCESS_KEY` + `CLOUDSWAY_ENDPOINT` | `searchapi.cloudsway.net/search/{endpoint}/smart`,`base_url` 可覆盖走代理/私有部署 |

**设计模式**(`backend/web_search.py`):`SearchProvider` ABC + `_REGISTRY` dict + `init_search_provider(name)` 工厂。新增 provider 流程 = 写一个 `SearchProvider` 子类(实现 `_invoke`)+ 在 `_REGISTRY` 加一行。基类提供 `normalize_result()` 统一字段(`title / url / snippet / source`),子类只把响应 map 到 list[SearchResult]。

**`max_results` 在 `__init__` 一次性写死**,不让 LLM 通过工具参数动态控制。历史教训(memory/`project_tavily_chinese_empty.md`):`langchain_tavily` 的 `forbidden_params` 黑名单会让动态 invoke 时透传的 `max_results` silent error,返回空——所以同类隐式限制可能出现在任何 provider 上,统一在实例化层定死最安全。

**异常封装**:所有 provider 异常统一抛 `SearchProviderError`;`web_search` 工具层 catch 后把错误字符串回给 LLM,LLM 自行换词/降级重试,**不**抛 exception 中断 graph。

##### 2.1.1.b bisheng_retrieve(私域知识检索)

调中粮(COFCO)内部 Bisheng 知识库的 `/api/v2/filelib/retrieve` 端点(纯向量+全文混合检索,无 LLM 生成)。env 必填:`BISHENG_BASE_URL` + `BISHENG_KB_IDS`(逗号分隔的 int)。

**research-agent 自选工具**(`backend/prompts.py:RESEARCH_SUBAGENT_PROMPT`):sub-agent 读 `web_search` 和 `bisheng_retrieve` 的 docstring,按 subtopic 性质决定调哪个——内部域问题走 `bisheng_retrieve`,公开 web 问题走 `web_search`,跨域问题两个都调。**双源调研不再是硬性逐主题强制**(自 commit `bea9731 docs(bisheng): make bisheng_retrieve mandatory, web_search optional` 改为按 subtopic 选择),由模型判断,减少冗余调用。

返回 chunk 在 LLM 视角等同于 `web_search` 结果,但 source 字段标 `document_name` 而非 URL。

**扩展边界**:多租户化(同一 graph 服务多个团队的不同 KB)需要重构 env 硬编码为 per-request config。当前不支持。

##### 2.1.1.c think_tool

强制 LLM 把规划/反思写下来,**无副作用**(只把 reflection 文本 echo 回 ToolMessage)。research-agent 工作流里"几次搜索 → `think_tool` 反思 → 是否再搜一轮"作为节奏控制(`prompts.py:153-157`)。主 agent prompt 也鼓励在 sub-agent 返回弱数据时调一次 `think_tool` 再决定是否 re-delegate。

### 2.2 状态层:四字段 state 与 generative UI 扩展

`deepagents._DeepAgentState` 暴露三个字段:`messages`(对话历史)、`todos`(主 agent 的 TODO 列表)、`files`(虚拟文件系统,`write_file/edit_file/read_file` 工具读写它——这几个是 deepagents 内置工具,本项目未额外覆盖)。前后端共享同一份 state 视图,LangGraph 的 reducer 机制保证多步更新原子合并。

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

**另一个状态层约束(随启动模式而变)**:
- **CLI 模式** (`langgraph dev` quick smoke):框架自动管 inmem checkpointer,`create_deep_agent` 里**不要**再传 `checkpointer=`,传了启动失败。
- **自研 server 模式** (`backend/server.py` + `uvicorn`,自 v0.5.0 默认): **必须**显式传 `checkpointer=AsyncSqliteSaver(...) / AsyncPostgresSaver(...)`,由 server lifespan 根据 `DATABASE_URL` env 实例化注入。`backend/agent.py` 暴露 `build_agent(checkpointer)` factory + module-level `agent = build_agent(None)` fallback(仅供 `langgraph dev` 加载 `langgraph.json:graphs.research`,不参与正式部署)。

何时该用哪种、切换怎么操作详见 §1 末尾部署模型表 + `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`。

### 2.3 人在回路:当前 dormant + 重启路径

**当前状态(2026-05-26):HITL 通道未装配。** commit `ab928b5 chore(hitl): drop interrupt_on — none of the wrapped tools have external side effects` 把整个 `interrupt_on=` 参数从 `create_deep_agent` 里删掉。`backend/agent.py:45-51` 当前不传 `interrupt_on=`,deepagents 内部据此跳过 `HumanInTheLoopMiddleware` 的装配——所以 `write_file` / `edit_file` / `task` / `export_docx` **一律不拦**,主 agent 调一个执行一个。

**撤销的论证**:这些 wrapped tools 都没有真实外部副作用——`write_file` / `edit_file` 写到 deepagents 的虚拟文件系统(state 内,不动 host 磁盘),`task` 委派的 sub-agent 跑搜索而已,`export_docx` 在 tempfile 里跑 pandoc。当时为它们弹审批卡是纯 noise,用户每次都 Approve,既减慢调研也不增加任何安全/数据完整性保障。

**为什么前端 patch 仍保留**:`ChatMessage.tsx` 的 task-skip override、`ChatInterface.tsx` 的 `broadcastResumeInterrupt`、`ToolCallBox.tsx` 的 `components` props 透传——这些都没删,作为"重启 HITL 时零成本恢复路径"。当前 dormant,详见 §3.1 表对应行。

**何时应重启 HITL**(在 `create_deep_agent(...)` 重新传 `interrupt_on={...}`):

- 新增工具有**真实外部副作用**(写 host 盘 / 调远程会改状态的 API / 发邮件 / 写数据库……)
- `write_file` 被改成绕过虚拟文件系统直接落 host 磁盘
- `task` 委派外部高成本模型且单次成本敏感

重启后前端 patch 直接生效,无需再改前端。

#### 重启后的批量审批语义

底层 `HumanInTheLoopMiddleware` 拦截工作在**节点边界**,与 LLM streaming 独立。即使开了 streaming,拦截仍可靠触发,前端弹卡片时模型已暂停。

LangGraph 的 `interrupt()` 单次可携带多个 `action_requests`——常见场景是模型在一个 step 内生成 N 个 `task` tool_calls,触发 1 个 interrupt 含 N 个 action_requests。中间件期待的 resume payload `{decisions: [d1, ..., dN]}` 长度等于 N。**UI 上点一次 Approve 等于批准这一批所有委派**——这个"单次决策广播为 N 个"的具体实现见 §3.2。

**局限**:批量审批是"全 approve / 全 reject"语义,**无法对单个 action_request 做不同决策**(例如 approve 第 1 个、reject 第 2 个)。要细粒度需要重写前端 `ToolApprovalInterrupt` 组件,目前没这个需求。

**调试**:重启后若发现某个工具拦截后行为异常,先把对应 key 从 `interrupt_on` 字典里注释掉缩小范围。

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

> 前端是 `langchain-ai/deep-agents-ui` 的 vendored 副本,这套渲染机制依赖多处本地 patch,详见 §3.1。

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

**扩展新格式时的同步项**:(1) `backend/tools.py` 加新 `export_*` 工具(若产物是二进制,参考 `export_docx` 直接返回 `Command(update={"files": ...})` 手工构造 FileData,**不**走 `StateBackend.upload_files`);(2) `backend/agent.py` 把工具注册到 `tools=`(若未来重新启用 `interrupt_on=`,见 §2.3 重启路径,按现有惯例同步加入);(3) `backend/prompts.py` Step 4 加新子项 + Step 0 同义词映射(`prompts.py:74-76` 的 `word/文档 → docx`、`网页/网页版 → html` 等);(4) `frontend/.../FileViewDialog.tsx` 的 `MIME_BY_EXT` 加扩展名→MIME 映射;(5) 本文件本节同步更新。

### 2.6 两种暂停机制:`interrupt_on` vs tool 内 `interrupt()`

本系统在两种语义不同的场景都需要"graph 暂停等用户输入"——它们走两条独立的 LangGraph 通道,**不耦合、可共存于同一 thread**。下表对照两条通道:**`interrupt_on` 通道当前未配置(见 §2.3 HITL dormant)**,表中相应内容描述"启用后"的语义;`tool 内 interrupt()` 通道则始终活跃,本项目通过 `request_clarification` 使用它。

| 维度 | `interrupt_on=…`(§2.3 HITL 通道) | tool 内 `interrupt()`(本节) |
|---|---|---|
| 触发位置 | tool 调用**前**,middleware 在节点边界拦截 | tool 节点内部,代码主动调 `langgraph.types.interrupt(value)` |
| 中间件 | `HumanInTheLoopMiddleware` | 无,langgraph 原生 |
| **何时被装配进 graph** | 仅当 `create_deep_agent(interrupt_on=…)` 传入时;**当前未传**(§2.3) | 总是被装配,与 wiring 无关 |
| 用途 | 审批(approve / reject / edit) | 询问(问用户拿信息再继续做事) |
| `interrupt.value` schema | `{action_requests, review_configs}` | 任意用户自定义(本项目 `request_clarification` 用 `{type, tool_call_id}` sentinel,**仅作触发标志**,前端不从这里拿渲染数据) |
| Resume payload | `{decisions: [{type:"approve"\|"reject"\|"edit", ...}]}` | 任意用户自定义(本项目是 `Record<string, string \| string[]>` answers dict) |
| 前端入口组件 | `ToolApprovalInterrupt`(action_requests 存在则渲染) | `ChatMessage.tsx` 内的 `toolCall.name === "request_clarification"` 分支(详见 §3.1 表中 ChatMessage 行) |
| 前端渲染数据源 | `interrupt.value.action_requests`(短生命周期,resume 后即消失) | **`toolCall.args`**(持久化在 `AIMessage.tool_calls` 里的 messages 数组,checkpointer 永久保存) + `toolCall.result`(对应 `ToolMessage.content`,resume 后被填上) |
| 前端如何回调 resume | `broadcastResumeInterrupt`(§3.2) prop-drill 给 `ToolApprovalInterrupt` | `useResumeInterrupt()` React Context(§3.1 patch);`ClarificationCard` 自取 callback |
| 当前用例 | (dormant)启用后将拦 `write_file` / `edit_file` / `task` / `export_docx` | `request_clarification`(Step 0 澄清卡,见 `docs/features/v0.4.0/001-clarification-card/`) |

**何时用哪种**:

- 用户已经明确说要做 X、tool 已经决定参数(`write_file(path, content)`),只需要审批同不同意 → 走 `interrupt_on`(简单、复用现有 `ToolApprovalInterrupt`)
- 用户**没**给够信息、tool 需要先反问("research LLM agent"——研究哪方面?输出什么格式?)→ 走 tool 内 `interrupt()`(自由设计 args schema + 前端渲染,不耦合审批语义)

**⚠️ langgraph 1.2.x `push_ui_message` 在 interrupt 期间的 caveat**(2026-05-25 实证):`push_ui_message` 内部 (1) 通过 `writer(evt)` 实时 SSE 推送、(2) 通过 `CONFIG_KEY_SEND` 把 channel update 加入 task pending writes。**但在 `interrupt()` halt 期间,pending writes 不持久化到 thread state**(task 没 commit,要等 resume 后才会写到 checkpointer)。直接结果:`GET /threads/{id}` 看到 `values.ui === []`,**用户刷新页面就丢卡片**。这是为什么 `request_clarification` **不走** generative-ui 通道渲染(原本设计是 D 方案——push_ui_message + LOCAL_UI_COMPONENTS),改成从 `toolCall.args` 直接渲染(方案 E)——args 永久持久化在 `AIMessage.tool_calls` 里。未来若 langgraph 修了"interrupt 期间 force-commit channel updates"(或暴露相应 API),可考虑回 D 方案。

**`interrupt()` 的 re-execution 陷阱**(普适知识):`interrupt(value)` 在同一 task 内第一次调用抛 `GraphInterrupt` halt,resume 后 node **从头重跑**,直到这次调用直接 return resume value(不再抛)。这意味着 **`interrupt()` 之前的代码会跑两次**。本项目 `request_clarification` 在 interrupt 之前**无副作用**(已删除原本的 push_ui_message,见上方 caveat),所以无幂等性顾虑。但**未来若在 `interrupt()` 之前加新副作用(写文件 / 调外部 API)前,必须重新评估幂等性**(参考 §2.5 的 dedup 模式)。

## 3. 跨上游适配的硬约束

本系统基于三个上游:**deepagents**(后端编排框架)、**deep-agents-ui**(vendored 前端,直接 clone 在 `frontend/`)、**@langchain/langgraph-sdk**(前端订阅 SSE 的 SDK)。当前版本下,这三个上游各自存在需要本地适配的硬约束,本章集中记录。每条约束在 §4 都有"何时可拆"的判定。

### 3.1 前端本地 patch

`deep-agents-ui` 直接 clone 进 `frontend/`,因为我们要改它(注入本地 generative UI 组件、patch 几处 bug、增多格式文件预览)。**升级路径**:`cd frontend && git pull` 前先 `git diff > /tmp/patches.diff` 留底,升级后 `git apply` 回去。

> **截至 2026-05-26 §2.3 HITL 已 dormant**,表中 `ToolCallBox.tsx` 的 `components` 透传、`ChatMessage.tsx` 的 task-skip override、`ChatInterface.tsx` 的 `broadcastResumeInterrupt` 当前不会被触发——保留它们作为重启 HITL 的零成本回路。**Step 0 澄清卡走的是另一条通道(tool 内 `interrupt()`,见 §2.6),不受 HITL dormant 影响,当前活跃。**

| 文件 | 修改 | 原因 |
|---|---|---|
| `ToolCallBox.tsx` | props 加 `components`,透传给 `LoadExternalComponent` | 让本地 generative UI 组件能命中(HITL dormant 期间不活跃) |
| `ChatMessage.tsx` | import `LOCAL_UI_COMPONENTS` 并注入;去掉 `task` 无条件 skip;`toolCalls.map` 内加 `request_clarification` 分支,直接渲染 `ClarificationCard` 从 `toolCall.args`(不走 LOCAL_UI_COMPONENTS) | 让本地组件 registry 生效;让 task HITL 审批卡能显示(HITL dormant 期间不活跃);让 Step 0 澄清卡用持久化数据源渲染(见 §2.6 caveat) |
| `ChatInterface.tsx` | 新增 `broadcastResumeInterrupt`(HITL dormant 期间不活跃);ui filter 兼容 `tool_call_id`;用 `<ResumeInterruptProvider>` 包 `processedMessages.map`,把 resume callback 通过 React Context 暴露给 generative-ui 组件 | 见 §3.2;Context 让 `ClarificationCard` 不依赖 prop drill onResume(`LoadExternalComponent` 不透传 onResume) |
| `useChat.ts` | (1) 装 fetch monkey-patch 过滤 `tools` stream_mode;(2) `StateType.files` 类型放宽为 `Record<string, RawFileEntry>`,`RawFileEntry = string \| { content: string \| string[]; encoding?: "utf-8" \| "base64" }`(string 形态保留给旧 checkpoint 兼容) | (1) 见 §3.3;(2) 让前端能消费 §2.5 的多格式 FileData |
| `generative-ui/{ResearchCard,ClarificationCard,registry}.tsx` | 新增本地组件 + registry。**`ResearchCard` 注册到 `LOCAL_UI_COMPONENTS` 走 generative-ui 通道**(后端 `emit_research_card` 调 `push_ui_message`,无 interrupt,正常持久化)。**`ClarificationCard` 不注册到 registry**,由 `ChatMessage.tsx` 直接渲染——`request_clarification` tool 内调 `interrupt()`,push_ui_message 在 interrupt 期间不持久化(§2.6 caveat),所以改从 `toolCall.args` 取数据渲染 | demo 卡片 |
| `hooks/useResumeInterrupt.tsx` | 新增 React Context + Provider + hook | 让 generative-ui 组件不通过 prop drill 自取 resume callback;见 §2.6 |
| `components/sidebar/TasksFilesSidebar.tsx` | 新增 `normalizeFileEntry()` 把 `RawFileEntry` 归一成 `FileItem`(`{path, content, encoding}`),encoding 字段透传给 `FileViewDialog`;多格式文件图标(html / docx / md 等) | 让前端能消费 §2.5 的多格式 FileData(string 旧形态 + `{content, encoding}` 新形态) |
| `components/dialog/FileViewDialog.tsx` | encoding 路由(`encoding === "base64"` 走二进制占位卡 + atob 下载;`.html` 走 `<iframe srcDoc sandbox="allow-same-origin">`,**不**开 `allow-scripts`;`.md` 走 `MarkdownContent`;其他 utf-8 走 `SyntaxHighlighter`)+ `MIME_BY_EXT` 表(md / html / docx / pptx / pdf / json / txt) | §2.5 多格式渲染的前端核心路由 |
| **SDD 测试基建(新增)**:`package.json`(test/e2e scripts + vitest/playwright/testing-library devDeps)、`vitest.config.ts`、`test/setup.ts`、`*.test.tsx`(组件 Test-Alongside)、`playwright.config.ts`、`e2e/`(E2E + fixtures) | 本地新增,vendored 副本上层 | SDD 三层测试落地(见 `docs/sdd/SDD-Guide.md §5`)。**上游 `git pull` 前同样要 `git diff` 留底**,否则这些新增文件 + package.json 改动会与上游冲突 |

#### 3.1.1 ChatMessage.tsx 第 128 行的 task skip

上游写死 `if (toolCall.name === "task") return null;`——理由是 deep-agents-ui 设计上把 `task` 工具调用渲染成 `SubAgentIndicator`(左下方折叠卡片),而不是普通 `ToolCallBox`。但这导致 `task` 触发 HITL 拦截时,审批卡(依赖 `ToolCallBox` 渲染)**永远不显示**。

我们改为:只在没有 actionRequest 时 skip,否则让第一个 task tool_call 走 `ToolCallBox` 渲染审批卡。**当前 dormant**(HITL 通道未装配,见 §2.3);保留为重启 HITL 的零成本回路。

#### 3.1.2 actionRequestsMap 用 name 做 key 的副作用

上游 `new Map(actionRequests.map(ar => [ar.name, ar]))` 用 `ar.name` 做 key,多个同工具(如 3 次 task 委派)会被覆盖只剩 1 个。我们没修这个 Map 本身(改它会牵连 `ToolApprovalInterrupt` 的接口),而是用 §3.2 的 broadcast 机制兜底。**当前 dormant**(HITL 通道未装配,见 §2.3)。

### 3.2 HITL 批量审批 — broadcastResumeInterrupt

> **截至 2026-05-26 `interrupt_on=` 未配置**(见 §2.3),本节 broadcast 当前**不会触发** —— 代码保留作为重启 HITL 的零成本回路。

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

**自研 server (002) 兼容性补充**:v0.5.0 起 backend 默认走 `backend/server.py` 而非 `langgraph-cli[inmem]`,但 server 显式实现 "stream_mode 数组含 `"tools"` 时返回 HTTP 422" 的 schema 兼容(见 `server.py` 的 `_validate_stream_mode`),**仍守护这个 hack 的存在意义**。判定可删条件相应改为:"升级 SDK 让它不再 auto-append `tools` 后,本 hack 可拆;同时 server.py 那段 422 校验可以一起改为'忽略 tools 不报错'"。本期 002 verification 含**破坏性回归**(临时注释 monkey-patch 跑一次确认 server 仍 422)守护住这条契约。

## 4. 演进路径

每个适配层都有"上游修好之后,本地可以拆掉"的判定条件。下面按 §3 顺序列出。

### 4.1 deepagents 升级

```bash
pip install -U deepagents
```

跑一次完整 prompt,检查:

1. **`_DeepAgentState` 是否新加了 `ui` 字段**——如果有,可以删 `GenerativeUIMiddleware`(§2.2)。
2. **上游是否开始默认对某些工具 interrupt**——若有变化,需要重新评估 §2.3 的撤销决定(当前 HITL dormant 是基于"wrapped tools 无外部副作用"的假设,若上游加入了有副作用的内置工具就需要重启)。

### 4.2 deep-agents-ui 升级

```bash
cd frontend
git diff > /tmp/patches.diff     # 必须先留底
git pull origin main
git apply /tmp/patches.diff      # 处理 conflict
```

升级后检查上游 issue 是否 fix 了:

- **task 渲染问题**(#45 #97)——若 fix,可以删 §3.1.1(当前 HITL dormant 但前端 patch 还在,upstream fix 后可同步删除)。
- **actionRequestsMap key 问题**——若 fix,可以删 §3.2 的 broadcast(当前 dormant,同上)。

### 4.3 @langchain/langgraph-sdk 升级

跑一次 HITL approve,如果不再 422,删 `useChat.ts` 的 fetch monkey-patch(§3.3)。

### 4.4 工具供给侧演进

§2.1.1 工具清单的三个新工具各有不同的演化方向:

1. **`web_search` provider 注册表**(§2.1.1.a)。`backend/web_search.py:_REGISTRY` 是开放的:新增 provider = 写一个 `SearchProvider` 子类(实现 `_invoke` + 异常封装成 `SearchProviderError`)+ `_REGISTRY` 加一行 + `.env.example` 加对应 env 变量。基类的 `normalize_result()` 已提供 `title/url/snippet/source` 统一字段,子类只负责把响应映射成 list[SearchResult]。
2. **`bisheng_retrieve` 当前 env 硬编码**(§2.1.1.b)。`BISHENG_BASE_URL` + `BISHENG_KB_IDS` 是进程级单一配置。若要服务多团队/多 KB(同一 graph 多租户化),需重构为 per-request config(读 `RunnableConfig` 里的 user 信息路由)。当前不支持。
3. **`think_tool` 的弱介入特性**(§2.1.1.c)。无副作用、纯日志,保留即可。若未来想接入"反思质量评估"或"反思链路可视化",可在工具内调 `push_ui_message` 推一个 reflection 卡片到 generative UI——但要小心 §2.6 caveat:仅在非 interrupt 路径上 push 才能持久化。
