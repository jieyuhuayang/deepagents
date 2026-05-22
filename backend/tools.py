"""自定义工具：tavily_search / think_tool / emit_research_card。"""

import os
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langchain_tavily import TavilySearch
from langgraph.graph.ui import push_ui_message
from langgraph.types import Command

_tavily = TavilySearch(max_results=5, api_key=os.environ.get("TAVILY_API_KEY"))


@tool
def tavily_search(query: str, max_results: int = 5) -> str:
    """搜索互联网。输入搜索关键词，返回标题 + URL + 摘要的列表。"""
    res = _tavily.invoke({"query": query, "max_results": max_results})
    return "\n\n".join(
        f"[{i + 1}] {r['title']}\nURL: {r['url']}\n{r['content'][:500]}"
        for i, r in enumerate(res.get("results", []))
    )


@tool
def think_tool(reflection: str) -> str:
    """强制慢思考。把当前规划/反思写下来，便于审视。返回原文以便链路追踪。"""
    return f"Reflection logged: {reflection}"


@tool
def emit_research_card(
    title: str,
    summary: str,
    sources: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """渲染一张"研究卡片"到前端（generative UI）。

    完成一个子主题调研后必须调用此工具，把结论结构化展示给用户。

    Args:
        title: 卡片标题，例如 "LangGraph 框架概述"。
        summary: 1-3 句话结论。
        sources: 引用的 URL 列表。
    """
    push_ui_message(
        "research_card",
        {"title": title, "summary": summary, "sources": sources},
        metadata={"tool_call_id": tool_call_id},
    )
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"Card rendered: {title}",
                    tool_call_id=tool_call_id,
                ),
            ],
        }
    )
