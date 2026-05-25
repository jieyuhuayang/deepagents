"""自定义工具:web_search / bisheng_retrieve / think_tool / emit_research_card / request_clarification / export_docx。"""

import base64
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, TypedDict

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.graph.ui import push_ui_message
from langgraph.types import Command, interrupt

from web_search import SearchProvider, SearchProviderError

# 进程级懒加载缓存。Tavily/DDG 客户端内部维护 HTTP session,重建有开销;
# env 变更需重启 langgraph dev(dev 模式 hot reload 会自动重置)。
_search_provider: SearchProvider | None = None


def _get_provider() -> SearchProvider:
    global _search_provider
    if _search_provider is None:
        name = os.environ.get("SEARCH_PROVIDER", "duckduckgo")
        _search_provider = SearchProvider.init_search_provider(name)
    return _search_provider


@tool
def web_search(query: str) -> str:
    """搜索互联网。输入搜索关键词,返回标题 + URL + 摘要的列表(最多 5 条)。

    Provider 由环境变量 SEARCH_PROVIDER 决定(duckduckgo / tavily / cloudsway,默认 duckduckgo)。
    """
    try:
        results = _get_provider().invoke(query)
    except SearchProviderError as e:
        # 限流 / quota / 网络异常都走这里,直接把错误回传给 LLM 让它降级/换词重试
        return f"搜索失败:{e}(常见于限流、quota 用尽或网络异常,稍后重试或更换关键词)"
    except Exception as e:
        return f"搜索失败:{e}"
    if not results:
        return "无搜索结果。试着换更具体或更通用的关键词。"
    return "\n\n".join(
        f"[{i + 1}] {r['title']}\nURL: {r['url']}\n{r['snippet'][:500]}"
        for i, r in enumerate(results)
    )


@tool
def bisheng_retrieve(query: str, top_k: int = 8) -> str:
    """从中粮知识库做纯向量+全文检索,返回 top-k 个文档片段(无 LLM 生成)。

    适合查中粮集团内部私域知识。输入自然语言 query,返回带文档名的片段列表。
    """
    base_url = os.environ["BISHENG_BASE_URL"].rstrip("/")
    kb_ids = [int(x) for x in os.environ["BISHENG_KB_IDS"].split(",") if x.strip()]
    try:
        resp = httpx.post(
            f"{base_url}/api/v2/filelib/retrieve",
            json={"query": query, "knowledge_base_ids": kb_ids, "top_k": top_k},
            timeout=30.0,
        )
        body = resp.json()
    except Exception as e:
        return f"BiSheng 检索失败:{e}"
    if body.get("status_code") != 200:
        return f"BiSheng 检索失败:{body.get('status_message')}"
    chunks = body["data"]["chunks"]
    if not chunks:
        return "BiSheng 知识库未命中相关内容。"
    return "\n\n".join(
        f"[{i + 1}] {c['document_name']} (chunk #{c['chunk_index']}, kb={c['knowledge_id']})\n"
        f"{c['content'][:15000]}"
        for i, c in enumerate(chunks)
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


# ─── Step 0 澄清通道:tool 内 langgraph 原生 interrupt() ─────────────────────
# spec: docs/features/v0.4.0/001-clarification-card/spec.md
# 何时用本工具 vs interrupt_on (HumanInTheLoopMiddleware):见 docs/architecture.md
# §2.6 "两种暂停机制 interrupt() vs interrupt_on" 子节。
#
# 设计偏离记录(2026-05-25):本工具最初设计走 push_ui_message → state.ui channel
# 渲染卡片,但实测 langgraph 1.2.1 在 interrupt() halt 期间 pending writes
# **不持久化**到 thread state(只通过 SSE writer 实时推送)。如果用户在 interrupted
# 状态下刷新页面,前端拉 thread state 拿到 ui=[],卡片丢失。
#
# 修复:删 push_ui_message,完全依赖 `tool_call.args` 持久化(AIMessage.tool_calls
# 是 messages 数组的一部分,checkpointer 永久保存)。前端 ChatMessage.tsx 检测
# `toolCall.name === "request_clarification"` 直接渲染 ClarificationCard,
# props 从 tool_call.args 取(restate / questions),completed/answers 从
# tool_call.result(即对应 ToolMessage.content 的 JSON)取。
# 完整偏差说明见 tasks.md 实际偏差记录。


class Option(TypedDict):
    """澄清卡里的一个选项。

    is_default: 标记为默认时,前端 ClarificationCard 打开时该 chip 已 active 且
        加 ★ 角标。每个 question 恰好 ONE 个 option 应设为 is_default=True
        (对应 prompt 里的 Silent Default)。
    """

    value: str
    label: str
    is_default: bool


class Question(TypedDict):
    """澄清卡里的一个问题。

    id: 短 snake_case identifier(如 "scope" / "time_window" / "output_formats")。
        模型自己生成;tool return 的 dict 以此为 key,模型后续读取这个 key 拿用户答案。
    options: 2-4 个,其中恰好 ONE 个 is_default=True。
    multi_select: false 单选(替换语义)/ true 多选(append 语义)。
    """

    id: str
    question: str
    options: list[Option]
    multi_select: bool


@tool
def request_clarification(
    restate: str,
    questions: list[Question],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """当用户的研究请求模糊时(Step 0),弹出澄清卡,等待用户答案。

    Use ONLY when the user's question lacks BOTH (a) a concrete topic AND
    (b) any scoping signal (time window / output formats / output shape /
    audience / geography / "quick/overview" hint). Call AT MOST ONCE per
    conversation — if the user's answer is still ambiguous, fall back to
    Silent Defaults from the system prompt and proceed; never call this
    tool twice.

    Args:
        restate: ONE sentence restating what you understood about the topic
            (appears at the top of the card).
        questions: 1-3 Question dicts. Priority order when picking which gaps
            to ask: scope / sub-topic count → output formats → output shape →
            time window → audience → geography. Exactly ONE option per
            question must have `is_default: true`.

    Returns:
        A ToolMessage whose content is the user's answers as a JSON dict,
        e.g. `{"scope": "both", "output_formats": ["markdown", "html"]}`.
        Free-text answers (user opens "+ 其他" and types) are surfaced as
        plain string values:
        - single-select: free-text REPLACES any chip selection
        - multi-select: free-text is APPENDED to the list
        Read the dict to drive `write_todos` scope/depth and Step 4 file
        formats; if a key is missing or ambiguous, fall back to Silent
        Defaults.
    """
    # Halts on first run (raises GraphInterrupt). On resume within the same
    # task, returns the value passed by Command(resume=...) — see langgraph
    # `interrupt()` docstring: "On subsequent invocations within the same
    # node, returns the value provided during the first invocation".
    #
    # No push_ui_message before/after — pending writes during interrupt halt
    # don't persist to thread state (verified on langgraph 1.2.1). Frontend
    # renders the card directly from this tool_call's args (persistent in
    # AIMessage.tool_calls) and the returned ToolMessage content (answers).
    answers = interrupt({"type": "clarification", "tool_call_id": tool_call_id})

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(answers, ensure_ascii=False),
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
# raw bytes cap;base64 编码后膨胀 ~33%,7.5 MB raw → 10 MB b64,刚好压在
# deepagents FilesystemBackend.max_file_size_mb=10 状态层硬上限之下。
_MAX_DOCX_BYTES = 7_500_000


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

    try:
        md_text = downloads[0].content.decode("utf-8")
    except UnicodeDecodeError as e:
        return _err(
            f"export_docx failed: source file {src!r} is not valid UTF-8 ({e}). "
            "Refusing to silently corrupt the docx output."
        )

    # 检测 dst 是否已存在(Command(update=) 路径会覆盖,但 backend.write 内置
    # 「already exists」守卫,这里复刻语义,但允许覆盖并在结果消息里明示)
    existing = backend.download_files([dst])
    will_overwrite = existing[0].content is not None

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
    overwrite_note = " [overwrote existing file]" if will_overwrite else ""
    return Command(
        update={
            "files": {dst: _binary_file_data(b64)},
            "messages": [
                ToolMessage(
                    content=(
                        f"Exported {src!r} to {dst!r} "
                        f"({len(docx_bytes) // 1024} KB, base64-encoded in state)"
                        f"{overwrite_note}"
                    ),
                    tool_call_id=tool_call_id,
                    status="success",
                ),
            ],
        }
    )
