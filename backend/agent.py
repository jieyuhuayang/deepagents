"""Deep Research agent — 装配中心。

提供 `build_agent(checkpointer)` factory:由 `backend/server.py` lifespan
显式传入 `AsyncPostgresSaver` / `AsyncSqliteSaver` 实例(根据 `DATABASE_URL`
路由)。详见 `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`
+ CLAUDE.md §强约束 #3 "自研 server 模式必须显式传 checkpointer"。

`agent = build_agent(None)` module-level fallback 保留供 `langgraph dev`
quick smoke 用(此时 langgraph dev 框架自动 attach inmem checkpointer,
checkpointer=None 等价于不传)。
"""

import os
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from middlewares import GenerativeUIMiddleware
from prompts import ORCHESTRATOR_PROMPT, RESEARCH_SUBAGENT_PROMPT
from tools import (
    bisheng_retrieve,
    emit_research_card,
    export_docx,
    request_clarification,
    think_tool,
    web_search,
)

load_dotenv()

model = ChatOpenAI(
    model=os.environ.get("DEEPAGENTS_MODEL", "deepseek-v4-pro"),
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0.0,
    streaming=True,
    timeout=120,
)

research_subagent = {
    "name": "research-agent",
    "description": (
        "对单个研究主题做深度调研。输入：明确的研究问题。"
        "输出：要点摘要 + 引用 URL 列表。"
    ),
    "system_prompt": RESEARCH_SUBAGENT_PROMPT,
    "tools": [web_search, bisheng_retrieve, think_tool],
}


def build_agent(checkpointer: Any | None = None):
    """构造 deep research agent。

    Args:
        checkpointer: `AsyncPostgresSaver` / `AsyncSqliteSaver` 实例,由 server
            lifespan 根据 `DATABASE_URL` env 选择并 `.setup()` 后传入。
            `None` 仅用于 `langgraph dev` quick smoke——框架会自动 attach
            inmem checkpointer。自研 server 模式下必须显式传。
    """
    return create_deep_agent(
        model=model,
        tools=[web_search, think_tool, emit_research_card, request_clarification, export_docx],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=[research_subagent],
        middleware=[GenerativeUIMiddleware()],
        checkpointer=checkpointer,
    )


# Module-level fallback:让 langgraph dev / langgraph.json 仍可加载 graph
# (quick smoke 用,无持久化,与 langgraph dev 内置 inmem 兼容)。
# 自研 server (backend/server.py) 启动时会显式调 build_agent(saver) 拿带
# 持久化能力的 agent,不使用这个 module-level fallback。
agent = build_agent(None)
