# 运行期问题排查

本文档收集 Deep Research demo 在启动与运行期可能遇到的具体问题。**架构层面的设计与决策见 [architecture.md](./architecture.md)**;本文按"问题清单"组织,只回答"我遇到 X 现象怎么办"。

## 1. 启动问题

### 1.1 启动 checkpointer 相关报错(两种 mode 行为相反)

**自 v0.5.0 起,backend 的启动 checkpointer 期望取决于启动模式**(见 `docs/architecture.md §2.2`):

| 模式 | 报错 | 修法 |
|---|---|---|
| `langgraph dev`(quick smoke) | `"checkpointer not necessary"` / 启动失败 | 不要在 `create_deep_agent` 里传 `checkpointer=`。`langgraph dev` 自动管 inmem。本项目的 module-level `agent = build_agent(None)` fallback 走这条路,**不要把 None 改成具体 saver**。 |
| `uvicorn server:app`(默认) | 启动报缺 saver / lifespan 报错 | `backend/server.py` lifespan 必须实例化 `AsyncSqliteSaver` / `AsyncPostgresSaver` 并通过 `build_agent(saver)` 注入。检查 `DATABASE_URL` env 是否有效。 |

历史:v0.5.0 之前只有 `langgraph dev` 一种 mode,报错只来自"传了 checkpointer"。现在自研 server 引入了"反过来"——**必须传**——所以两条修法都要看清启动方式。

### 1.2 启动报 "Using SOCKS proxy, but socksio not installed"

**现象**:`langgraph dev` 启动时报 SOCKS 相关错误。

**原因**:环境有 `all_proxy=socks5://...`,httpx 默认不带 SOCKS 支持。

**修法**:

```bash
pip install socksio
# 或
pip install httpx[socks]
```

### 1.3 yarn install 报网络错误 / 找不到 brace-expansion@^5.0.2

**现象**:前端 `yarn install` 失败,报 "trouble with your network connection" 或 "Couldn't find brace-expansion@^5.0.2"。

**原因**:yarn 1.22 在 SOCKS 代理下无法正确解析 npm registry。

**修法**:改用 npm + 国内镜像:

```bash
npm install --registry=https://registry.npmmirror.com --legacy-peer-deps
```

### 1.4 langgraph dev startup failed 后不退出

**现象**:启动失败但进程仍在,日志停在错误处。

**原因**:watchfiles 保持监听,等文件改变重试。

**修法**:改代码会自动 reload;强制重启需 kill 进程后重新启动。

### 1.5 (lab host) backend 重启后 thread 数据丢失

**现象**:lab host (例如 192.168.106.114) 上 backend 进程重启后,回到旧 thread,浏览器**还能看到**澄清卡 + todo list (5/5 完成等),但 messages 中间过程全部缺失;按 F5 刷新后整个 thread 变空白。

**原因**:旧版 lab host 用 `langgraph dev`,checkpointer 是 in-memory,进程重启**立即清空所有 thread state**。浏览器看到的"半截画面"来自 React 内存里**断线前的 SSE 快照**(不是真实持久化的 state)——`useChat.ts:225-230` 把 todos / files / ui 从 `stream.values.*` 取(values 模式 snapshot 累积),把 messages 从 `stream.messages` 取(messages-tuple 模式独立累积),两条流在 backend 重启 + SSE 重连时"恢复完整度"不同步,所以才出现一半完整一半残缺的视觉错觉。

**诊断三步**:

```bash
# 1. backend state 真实情况(应该几乎全空)
curl -s http://<lab-host>:<port>/threads/<thread-id>/state \
  | jq '{n_messages: (.values.messages|length), n_todos: (.values.todos|length)}'

# 2. 浏览器 F5 刷新,如果"半截画面"瞬间变空白,印证浏览器内存撑场面
# 3. backend 进程启动时间
ssh root@<lab-host> 'ps -o lstart= -p $(pgrep -f "uvicorn server:app\|langgraph dev")'
# 大概率晚于 thread 创建时间
```

**修法**(v0.5.0 起):lab host 部署改用 **`backend/server.py`(uvicorn) + 独立 Postgres docker container**(`AsyncPostgresSaver` 持久化),具体见:

- `README.md` §5 "lab host 部署(`uvicorn server:app` + 独立 Postgres docker)" 小节
- `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`

本地 demo 自 v0.5.0 起也走 `uvicorn server:app` + `AsyncSqliteSaver`(`backend/local.db` 单文件),进程重启同样不丢数据。

**历史方案对比**(v0.5.0 草案撤回):曾计划切到 `langgraph up`(LangGraph Platform 商业产品),但 license 要求 + lab host 网络限制阻塞,详见 [`docs/features/v0.5.0/001-langgraph-up-deployment/`](../features/v0.5.0/001-langgraph-up-deployment/)(ABANDONED ADR)。背景与根因诊断详见 `~/.claude/plans/image-1-http-192-168-106-114-13000-assi-fluffy-honey.md`。

## 2. 模型行为

`deepseek-v4-pro` 是默认模型,在本项目实测有几个非显然行为。切换模型时这些经验不一定适用。

### 2.1 主动跳过 emit_research_card 直接 write_file

**现象**:即使 prompt 里写"MUST call emit_research_card",第一次跑仍可能跳过卡片渲染直接调 `write_file`。

**对策**:

- `emit_research_card` 的 docstring 写强制语序("完成一个子主题调研后必须调用")
- `ORCHESTRATOR_PROMPT` 加 "only after all N emit_research_card calls succeed may you call write_file"
- 二次 reject + 强化引导通常能让模型听话

### 2.2 重复调研同一主题

**现象**:3 个 sub-agent 跑完后,模型觉得某个结果不够好,自己再 spawn 一个 task 重做。

**对策**:prompt 里强调"sub-agent 的结果即为最终结果,不要二次调研"。这不一定是 bug,但会拖慢流程。

### 2.3 (历史) Tavily 长期返空

**状态**:2026-05-22 已修复;2026-05-23 demo 阶段已整体迁至 DuckDuckGo,记录保留作历史踩坑参考。

**现象**:sub-agent 报告里 `tavily_search` 40+ 次查询均返回空。

**误判排查方向**:当时怀疑过 SOCKS、quota、中文 query。

**实际根因**:`backend/tools.py` 里

```python
res = _tavily.invoke({"query": query, "max_results": max_results})
```

给 `invoke` 传了 `max_results`。`langchain_tavily 0.2.18` 的 `TavilySearch.invoke()` 维护了 `forbidden_params` 列表(`tavily_search.py:372-381`)——`max_results`、`include_answer`、`country` 等 9 个参数**只允许实例化时设置**,invoke 时传任何一个都会 raise ValueError。错误被工具层吞成 `{"error": ...}`,结果静默变成空字符串,工具调用看起来"成功返空"。

**修复**:`tavily_search` 工具签名只保留 `query`;`invoke` 时不再传 `max_results`,固定由 `_tavily = TavilySearch(max_results=5)` 实例化时决定。

**延伸警告**:如果未来想给 `tavily_search` 加可调参数(让 LLM 动态控制 `search_depth` / `include_domains` / `country` 等),**不能走"工具签名透传到 invoke"这条路**,会同样踩这个雷。正确做法是在工具函数内部 `client = TavilySearch(max_results=N, search_depth=...)` 每次新建实例——但要权衡性能开销。

**当前规避方案(v0.3.0-002 起)**:`backend/web_search.py` 的 `TavilyProvider` 直接用 `tavily-python` 官方 SDK(`TavilyClient.search(query, max_results=...)`),绕开 `langchain_tavily` 的 `forbidden_params` 黑名单,`max_results` 在 `search()` 调用时即可安全传。仅在切回 `langchain_tavily` 时需重新警惕上面这条。
