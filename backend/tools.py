"""自定义工具:duckduckgo_search / think_tool / emit_research_card / export_docx。"""

import base64
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.graph.ui import push_ui_message
from langgraph.types import Command

# DuckDuckGo 无需 API key。limit 在实例化时设置,不要在 .results() 里再传
# 一次性参数 —— 行为与 Tavily 时期保持一致(单一可信入口,避免静默失败)。
_ddg = DuckDuckGoSearchAPIWrapper(max_results=5)


@tool
def duckduckgo_search(query: str) -> str:
    """搜索互联网(DuckDuckGo,无需 API key)。输入搜索关键词,返回标题 + URL + 摘要的列表(最多 5 条)。"""
    try:
        results = _ddg.results(query, max_results=5)
    except Exception as e:
        # DuckDuckGo 高频访问会触发 Ratelimit,直接把错误回传给 LLM 让它降级/换词重试
        return f"搜索失败:{e}(常见于限流,稍后重试或更换关键词)"
    if not results:
        return "无搜索结果。试着换更具体或更通用的关键词。"
    return "\n\n".join(
        f"[{i + 1}] {r.get('title', '')}\nURL: {r.get('link', '')}\n{(r.get('snippet') or '')[:500]}"
        for i, r in enumerate(results)
    )


@tool
def think_tool(reflection: str) -> str:
    """强制慢思考。把当前规划/反思写下来,便于审视。返回原文以便链路追踪。"""
    return f"Reflection logged: {reflection}"


@tool
def emit_research_card(
    title: str,
    summary: str,
    sources: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """渲染一张"研究卡片"到前端(generative UI)。

    完成一个子主题调研后必须调用此工具,把结论结构化展示给用户。

    Args:
        title: 卡片标题,例如 "LangGraph 框架概述"。
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


# StateBackend 走 LangGraph CONFIG_KEY_READ/SEND,只能在 graph 执行上下文里实例化。
# 注意:**不要**用 backend.upload_files 写二进制 —— deepagents 0.6.x 的实现里
# 它虽然会 base64 编码字节流,但调 create_file_data() 时漏传 encoding 参数,
# FileData.encoding 仍会被默认成 "utf-8"。前端按 encoding 路由会失效。
# 这里直接返回 Command(update={"files": {...}}) 手工构造 FileData,显式设
# encoding="base64",绕过上游 bug。
_MAX_DOCX_BYTES = 10 * 1024 * 1024


def _binary_file_data(b64_content: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "content": b64_content,
        "encoding": "base64",
        "created_at": now,
        "modified_at": now,
    }


@tool
def export_docx(
    source_path: str = "report.md",
    dest_path: str = "report.docx",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """把虚拟文件系统里的 markdown 转成 docx,base64 编码后存回同一文件系统。

    LLM 不能直接产出二进制,这里用 pandoc 做 md→docx 转换,然后把 base64
    编码的字节流以 FileData(encoding="base64") 形式写入 state.files。前端按
    encoding 字段识别后,二进制走"下载占位 + atob 解码下载"路径。

    Args:
        source_path: 源 markdown 路径(虚拟文件系统),默认 report.md。必须先存在。
        dest_path: 目标 docx 路径,必须以 .docx 结尾,默认 report.docx。
    """
    # 延迟导入:让 langgraph dev 在缺依赖时仍能启动,只在真正调用时报错
    from deepagents.backends.state import StateBackend
    from deepagents.backends.utils import validate_path

    import pypandoc

    def _err(msg: str) -> Command:
        return Command(
            update={
                "messages": [
                    ToolMessage(content=msg, tool_call_id=tool_call_id, status="error"),
                ],
            }
        )

    try:
        src = validate_path(source_path)
        dst = validate_path(dest_path)
    except ValueError as e:
        return _err(f"export_docx failed: invalid path — {e}")

    if not dst.endswith(".docx"):
        return _err(f"export_docx failed: dest_path must end with .docx (got {dst!r})")

    backend = StateBackend()

    downloads = backend.download_files([src])
    if downloads[0].error or downloads[0].content is None:
        return _err(
            f"export_docx failed: source file {src!r} not found in state.files. "
            "Make sure write_file(report.md, ...) succeeded before exporting."
        )

    md_text = downloads[0].content.decode("utf-8", errors="replace")

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        pypandoc.convert_text(md_text, "docx", format="md", outputfile=tmp_path)
        docx_bytes = Path(tmp_path).read_bytes()
    except Exception as e:
        return _err(f"export_docx failed: pandoc conversion error — {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if len(docx_bytes) > _MAX_DOCX_BYTES:
        kb = len(docx_bytes) // 1024
        return _err(
            f"export_docx failed: docx size {kb} KB exceeds 10 MB limit. "
            "Shorten the markdown report and retry."
        )

    b64 = base64.b64encode(docx_bytes).decode("ascii")
    return Command(
        update={
            "files": {dst: _binary_file_data(b64)},
            "messages": [
                ToolMessage(
                    content=(
                        f"Exported {src!r} to {dst!r} "
                        f"({len(docx_bytes) // 1024} KB, base64-encoded in state)"
                    ),
                    tool_call_id=tool_call_id,
                    status="success",
                ),
            ],
        }
    )
