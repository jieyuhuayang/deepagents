"""Deep Research agent — 装配中心。

graphs.research 的对外入口在这里组装：DashScope 兼容端点的 ChatOpenAI、
tools、subagents、interrupt_on、checkpointer。
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from middlewares import GenerativeUIMiddleware
from prompts import ORCHESTRATOR_PROMPT, RESEARCH_SUBAGENT_PROMPT
from tools import duckduckgo_search, emit_research_card, export_docx, think_tool

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
    "tools": [duckduckgo_search, think_tool],
}

agent = create_deep_agent(
    model=model,
    tools=[duckduckgo_search, think_tool, emit_research_card, export_docx],
    system_prompt=ORCHESTRATOR_PROMPT,
    subagents=[research_subagent],
    middleware=[GenerativeUIMiddleware()],
    interrupt_on={
        "write_file": True,
        "edit_file": True,
        "task": True,
        "export_docx": True,
    },
)
