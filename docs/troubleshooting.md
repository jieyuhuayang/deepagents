# 运行期问题排查

本文档收集 Deep Research demo 在启动与运行期可能遇到的具体问题。**架构层面的设计与决策见 [architecture.md](./architecture.md)**;本文按"问题清单"组织,只回答"我遇到 X 现象怎么办"。

## 1. 启动问题

### 1.1 langgraph dev 启动报 "checkpointer not necessary"

**现象**:后端启动失败,报错提示不需要 checkpointer。

**原因**:`langgraph dev` 是 LangGraph Platform 的本地模拟器,**自动管 checkpointer**——用户不能再传 `MemorySaver` 或 `checkpointer=...`。

**修法**:删 `agent.py` 里 `MemorySaver()` 实例化和 `create_deep_agent(..., checkpointer=...)` 参数。

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
