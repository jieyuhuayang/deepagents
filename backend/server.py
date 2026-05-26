"""自研 FastAPI server — LangGraph SDK 兼容协议子集 + OSS PostgresSaver/SqliteSaver。

详见 `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`。

----
**Endpoint 全集**(由 tasks.md T1 frontend 审计精确确定):

Assistants (2):
  GET   /assistants/{id}              ← page.tsx
  POST  /assistants/search            ← page.tsx

Threads (6):
  POST  /threads                       ← useStream 首次 submit
  POST  /threads/search                ← useThreads.ts
  DELETE /threads/{id}                 ← useDeleteThread.ts
  GET   /threads/{id}/state            ← useChat.ts
  POST  /threads/{id}/state            ← useChat.ts (updateState files)
  POST  /threads/{id}/history          ← useStream fetchStateHistory

Runs (4):
  POST  /runs/stream                                ← useStream submit (no thread)
  POST  /threads/{id}/runs/stream                   ← useStream submit (with thread)
  GET   /threads/{id}/runs/{run_id}/stream          ← useStream reconnectOnMount
  POST  /threads/{id}/runs/{run_id}/cancel          ← stream.stop()

Health (1):
  GET   /ok                                         ← deployment health check

----
**stream_mode 兼容**:接受 `["values", "messages-tuple", "updates"]` 任意子集;
含 `"tools"` 时返回 HTTP 422(守护 `frontend/src/app/hooks/useChat.ts` fetch
monkey-patch 的存在意义,见 CLAUDE.md §强约束 #7)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from langchain_core.runnables.config import RunnableConfig
from langgraph.types import Command

from agent import build_agent

load_dotenv()

logger = logging.getLogger("deepagents.server")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

# ---------------------------------------------------------------------------
# DATABASE_URL 解析
# ---------------------------------------------------------------------------

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./local.db"


def _parse_db_url(url: str) -> tuple[str, str]:
    """剥去 SQLAlchemy 风格的 `+asyncpg` / `+aiosqlite` 后缀,返回 (kind, normalized)。

    Examples:
        "sqlite+aiosqlite:///./local.db"     → ("sqlite", "./local.db")
        "sqlite:///./local.db"               → ("sqlite", "./local.db")
        "postgresql+asyncpg://u:p@h:5433/db" → ("postgres", "postgresql://u:p@h:5433/db")
        "postgresql://u:p@h:5433/db"         → ("postgres", "postgresql://u:p@h:5433/db")
    """
    if url.startswith("postgresql+asyncpg://"):
        return "postgres", "postgresql://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgresql://"):
        return "postgres", url
    if url.startswith("sqlite+aiosqlite:///"):
        return "sqlite", url[len("sqlite+aiosqlite:///"):]
    if url.startswith("sqlite:///"):
        return "sqlite", url[len("sqlite:///"):]
    raise ValueError(
        f"Unsupported DATABASE_URL: {url!r}. Expected sqlite[+aiosqlite]:///... "
        f"or postgresql[+asyncpg]://..."
    )


# ---------------------------------------------------------------------------
# Lifespan:实例化 saver + agent,注入 app.state
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    kind, normalized = _parse_db_url(db_url)

    if kind == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(normalized) as saver:
            await saver.setup()
            app.state.saver = saver
            app.state.agent = build_agent(saver)
            app.state.db_kind = "postgres"
            print(f"[lifespan] AsyncPostgresSaver ready ({normalized.split('@')[-1]})")
            yield
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(normalized) as saver:
            await saver.setup()
            app.state.saver = saver
            app.state.agent = build_agent(saver)
            app.state.db_kind = "sqlite"
            print(f"[lifespan] AsyncSqliteSaver ready ({normalized})")
            yield


# ---------------------------------------------------------------------------
# FastAPI app + CORS(前端跨 origin 调用 SSE)
# ---------------------------------------------------------------------------

app = FastAPI(title="deepagents OSS server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# JSON 编码:datetime / UUID 等需要 default 处理
# ---------------------------------------------------------------------------


def _json_default(o: Any) -> Any:
    if isinstance(o, (datetime,)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "dict"):
        return o.dict()
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


def _jsonify(obj: Any) -> JSONResponse:
    return JSONResponse(content=json.loads(_json_dumps(obj)))


def _sse_event(event_type: str, data: Any) -> bytes:
    """LangGraph SDK SSE 格式:`event: <type>\\r\\ndata: <json>\\r\\n\\r\\n`。"""
    return f"event: {event_type}\r\ndata: {_json_dumps(data)}\r\n\r\n".encode()


# ---------------------------------------------------------------------------
# 校验 / Helpers
# ---------------------------------------------------------------------------

# langgraph 本地 Pregel StreamMode Literal(verified: langgraph.types.StreamMode.__args__)
# 不含 'events';"messages-tuple" 是 LangGraph SDK 客户端的 alias,需要翻译。
VALID_STREAM_MODES = {"values", "messages-tuple", "messages", "updates", "debug", "custom"}

# LangGraph SDK 客户端名 → 本地 Pregel 内部 stream_mode 名。
_CLIENT_TO_LG_MODE = {"messages-tuple": "messages"}


def _validate_stream_mode(stream_mode: Any) -> list[tuple[str, str]]:
    """规范化为 list[(client_name, langgraph_name)];含 "tools" 则 422。

    去重:client 名重复时只保留首次出现;两个 client 名映射到同一 langgraph 名时
    (例如同时传 "messages" + "messages-tuple")显式 422 拒掉 ambiguous duplicate。
    """
    if stream_mode is None:
        return [("values", "values")]
    raw = stream_mode if isinstance(stream_mode, list) else [stream_mode]
    modes = list(dict.fromkeys(raw))  # client 名 dedup,保留首次顺序
    if "tools" in modes:
        raise HTTPException(
            status_code=422,
            detail={
                "msg": "stream_mode 'tools' is not supported by this server; "
                "frontend useChat.ts monkey-patch should have filtered it. "
                "See CLAUDE.md §强约束 #7 + 002 spec.md AC-5.",
                "got": raw,
            },
        )
    unknown = set(modes) - VALID_STREAM_MODES
    if unknown:
        raise HTTPException(
            status_code=422, detail={"msg": "unknown stream_mode", "unknown": list(unknown)}
        )
    lg_seen: dict[str, str] = {}
    pairs: list[tuple[str, str]] = []
    for m in modes:
        lg = _CLIENT_TO_LG_MODE.get(m, m)
        if lg in lg_seen:
            raise HTTPException(
                status_code=422,
                detail={
                    "msg": (
                        f"stream_mode {m!r} maps to langgraph {lg!r}, which was "
                        f"already requested via {lg_seen[lg]!r}; pick one."
                    ),
                },
            )
        lg_seen[lg] = m
        pairs.append((m, lg))
    return pairs


def _build_config(thread_id: str | None, extra: dict[str, Any] | None = None) -> RunnableConfig:
    configurable: dict[str, Any] = {"graph_id": "research"}
    if thread_id:
        configurable["thread_id"] = thread_id
    cfg: RunnableConfig = {"configurable": configurable}
    if extra:
        cfg = {**cfg, **{k: v for k, v in extra.items() if k != "configurable"}}
        cfg["configurable"] = {**configurable, **(extra.get("configurable") or {})}
    # F6 守护:URL 路径里的 thread_id 永远胜过 extra/body 中的同名字段——
    # 防止 body.config.configurable.thread_id 跨 thread 写入。
    if thread_id:
        cfg["configurable"]["thread_id"] = thread_id
    return cfg


def _map_command(cmd: dict[str, Any] | None) -> Command | None:
    if not cmd:
        return None
    return Command(
        resume=cmd.get("resume"),
        goto=cmd.get("goto") or (),
        update=cmd.get("update"),
    )


# LangGraph SDK Checkpoint shape:{thread_id, checkpoint_ns, checkpoint_id, checkpoint_map}
# 不应回流 server 内部的 graph_id 等字段。
_CHECKPOINT_KEYS = ("thread_id", "checkpoint_ns", "checkpoint_id", "checkpoint_map")


def _thin_checkpoint(configurable: dict[str, Any] | None) -> dict[str, Any] | None:
    if not configurable:
        return None
    return {k: configurable[k] for k in _CHECKPOINT_KEYS if k in configurable}


# Sort-by 白名单:防 sort_by="metadata"(dict)在 dict<dict 比较时触发 TypeError 500。
_ALLOWED_SORT_BY = {"thread_id", "created_at", "updated_at"}


def _safe_int(raw: Any, *, default: int, field: str) -> int:
    """body 里的整数字段:None → default;不可转 int 则 422。`0` 被视为合法显式输入,
    不会回落到 default(避免 limit=0 走 falsy 转默认的语义反转)。"""
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail={"msg": f"{field} must be int", "got": raw},
        ) from e


def _serialize_state(state: Any) -> dict[str, Any]:
    """StateSnapshot → JSON-serializable dict (LangGraph SDK ThreadState 形状)。"""
    if state is None:
        return {"values": {}, "next": [], "tasks": [], "checkpoint": None, "metadata": {}}
    tasks = []
    for t in getattr(state, "tasks", ()) or ():
        tasks.append({
            "id": getattr(t, "id", None),
            "name": getattr(t, "name", None),
            "interrupts": [
                {"id": getattr(i, "id", None), "value": getattr(i, "value", None)}
                for i in (getattr(t, "interrupts", ()) or ())
            ],
            "result": getattr(t, "result", None),
            "error": getattr(t, "error", None),
            "state": getattr(t, "state", None),
        })
    return {
        "values": getattr(state, "values", {}) or {},
        "next": list(getattr(state, "next", ()) or ()),
        "tasks": tasks,
        "checkpoint": _thin_checkpoint(getattr(state, "config", {}).get("configurable") if getattr(state, "config", None) else None),
        "metadata": getattr(state, "metadata", {}) or {},
        "created_at": getattr(state, "created_at", None),
        "parent_checkpoint": _thin_checkpoint(getattr(state, "parent_config", {}).get("configurable") if getattr(state, "parent_config", None) else None),
        "interrupts": [
            {"id": getattr(i, "id", None), "value": getattr(i, "value", None)}
            for task in (getattr(state, "tasks", ()) or ())
            for i in (getattr(task, "interrupts", ()) or ())
        ],
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/ok")
async def ok():
    return {"ok": True}


@app.get("/info")
async def info(request: Request):
    return {
        "version": "deepagents-oss/0.5.0",
        "flags": {"assistants": True, "crons": False, "langsmith": False},
        "db_kind": getattr(request.app.state, "db_kind", "unknown"),
    }


# ---------------------------------------------------------------------------
# Assistants
# ---------------------------------------------------------------------------

_RESEARCH_ASSISTANT = {
    "assistant_id": "research",
    "graph_id": "research",
    "name": "Deep Research",
    "config": {},
    "context": {},
    "metadata": {"created_by": "system"},
    "version": 1,
    "created_at": "2026-05-26T00:00:00Z",
    "updated_at": "2026-05-26T00:00:00Z",
}


@app.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str):
    if assistant_id != "research":
        raise HTTPException(404, f"assistant '{assistant_id}' not found")
    return _RESEARCH_ASSISTANT


@app.post("/assistants/search")
async def search_assistants(body: dict[str, Any] | None = None):
    body = body or {}
    if body.get("graph_id") and body["graph_id"] != "research":
        return []
    return [_RESEARCH_ASSISTANT]


# ---------------------------------------------------------------------------
# Threads:CRUD + state + history
# ---------------------------------------------------------------------------


@app.post("/threads")
async def create_thread(body: dict[str, Any] | None = None, request: Request = None):
    body = body or {}
    thread_id = body.get("thread_id") or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    # Thread metadata 本身不持久化到 checkpointer;由 saver 在第一次 put 时自然创建。
    # 这里只回最小信息。
    return {
        "thread_id": thread_id,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "metadata": body.get("metadata") or {},
        "status": "idle",
        "config": {},
        "values": {},
    }


@app.post("/threads/search")
async def search_threads(body: dict[str, Any] | None = None, request: Request = None):
    """列出 saver 中的 thread。

    `langgraph-checkpoint-{sqlite,postgres}` 没有官方"list threads" API;
    我们用 `alist(config=None)` 拿全部 checkpoints 然后按 thread_id 去重,取每个
    thread 的最新 checkpoint 作为代表。这是 demo 量级方案,如未来需要支持几百+
    thread 应改成 SQL 直查。
    """
    body = body or {}
    # F11 守护 + 修复 fix-bug:把 0 视为合法显式输入,只有 None 才回落默认 100。
    limit = _safe_int(body.get("limit"), default=100, field="limit")
    if limit <= 0:
        return _jsonify([])
    offset = _safe_int(body.get("offset"), default=0, field="offset")
    sort_by = body.get("sort_by") or "updated_at"
    if sort_by not in _ALLOWED_SORT_BY:
        # 不抛 422,优雅 fallback——客户端误传非白名单字段时回归默认排序,而不是 500。
        sort_by = "updated_at"
    sort_order = (body.get("sort_order") or "desc").lower()

    saver = request.app.state.saver
    # F4 mitigate:拉 (offset+limit)*10 倍 checkpoint 做按 thread_id 去重兜底,
    # 避免活跃 thread 把 fetch 配额全占了导致老 thread 漏出。但上 cap 5000 防 OOM。
    fetch = min(max((offset + limit) * 10, 100), 5000)
    seen: dict[str, dict[str, Any]] = {}
    async for ck in saver.alist(None, limit=fetch):
        tid = ck.config.get("configurable", {}).get("thread_id")
        if not tid or tid in seen:
            continue
        # F2 修复:created_at 用 checkpoint.ts(LangGraph checkpoint dict 标准字段);
        # ck.checkpoint 是 TypedDict 即 dict,truthy 判断即可。
        ts = ck.checkpoint.get("ts") if ck.checkpoint else None
        # F-E1 修复:前端 useThreads.ts 依赖 thread.values.messages 取首条消息当会话标题;
        # F16 之前的 fix 一刀切返 {} 让会话列表全退化成 "会话 <UUID>" fallback。还原
        # channel_values——_jsonify 的 _json_default 已能用 str(o) 兜住 Send / Command 等。
        ch = ck.checkpoint.get("channel_values", {}) if ck.checkpoint else {}
        seen[tid] = {
            "thread_id": tid,
            "created_at": ts,
            "updated_at": ts,
            "metadata": ck.metadata or {},
            "status": "idle",
            "config": ck.config,
            "values": ch or {},
        }
    # F5 修复:支持 sort_by + sort_order + offset(Python 层做,demo 量级 OK)
    threads = list(seen.values())
    # sort key 强转 str 防 dict<dict / datetime<NoneType 等比较 crash
    threads.sort(key=lambda t: str(t.get(sort_by) or ""), reverse=(sort_order == "desc"))
    return _jsonify(threads[offset:offset + limit])


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, request: Request):
    saver = request.app.state.saver
    if hasattr(saver, "adelete_thread"):
        await saver.adelete_thread(thread_id)
        return Response(status_code=204)
    # 兼容退路:saver 没暴露 delete API 时返回 501
    raise HTTPException(501, "saver does not support thread deletion")


@app.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str, request: Request):
    agent = request.app.state.agent
    cfg = _build_config(thread_id)
    state = await agent.aget_state(cfg)
    # F16 守护:state.values 含 langgraph.types.Send 等非 dataclass 对象时,FastAPI
    # 默认 jsonable_encoder 抛 'Send object is not iterable'/'vars() needs __dict__';
    # 走 _jsonify(_json_default fallback 到 str)绕开。
    return _jsonify(_serialize_state(state))


@app.post("/threads/{thread_id}/state")
async def update_thread_state(thread_id: str, body: dict[str, Any] | None = None, request: Request = None):
    # F12 守护:body 默认 None,与 search_threads / thread_history 风格一致(空 body 当作 no-op,而非 422)。
    body = body or {}
    agent = request.app.state.agent
    cfg = _build_config(thread_id)
    if checkpoint := body.get("checkpoint"):
        cfg["configurable"].update(checkpoint)
        # F6 守护:body.checkpoint.thread_id 不能跨 thread 写入(URL 路径胜出)
        cfg["configurable"]["thread_id"] = thread_id
    elif checkpoint_id := body.get("checkpoint_id"):
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    new_cfg = await agent.aupdate_state(cfg, body.get("values") or {}, as_node=body.get("as_node"))
    # LangGraph SDK client.threads.updateState 期待 Pick<Config, "configurable">;
    # 顶层必须含 "configurable" key(否则 SDK 拿不到新的 checkpoint_id 续传)。
    # 同时只返回 _thin_checkpoint 的 4 个 key,不把 graph_id 等内部字段回流前端。
    new_configurable = _thin_checkpoint(new_cfg.get("configurable") if new_cfg else None) or {}
    return _jsonify({"configurable": new_configurable, "checkpoint": new_configurable})


@app.post("/threads/{thread_id}/history")
async def thread_history(thread_id: str, body: dict[str, Any] | None = None, request: Request = None):
    body = body or {}
    agent = request.app.state.agent
    cfg = _build_config(thread_id)
    limit = _safe_int(body.get("limit"), default=10, field="limit")
    if limit <= 0:
        return _jsonify([])
    before = body.get("before")
    if isinstance(before, dict):
        before_cfg = {"configurable": before}
    else:
        before_cfg = None
    history = []
    async for snap in agent.aget_state_history(
        cfg, limit=limit, filter=body.get("metadata"), before=before_cfg
    ):
        history.append(_serialize_state(snap))
    # F16 守护:同 get_thread_state
    return _jsonify(history)


# ---------------------------------------------------------------------------
# Runs:SSE streaming
# ---------------------------------------------------------------------------


async def _stream_run(
    request: Request,
    thread_id: str | None,
    body: dict[str, Any],
) -> AsyncIterator[bytes]:
    """共享的 run 实现:被 POST /runs/stream 和 POST /threads/{id}/runs/stream 复用。"""
    agent = request.app.state.agent
    stream_modes = _validate_stream_mode(body.get("stream_mode"))  # [(client, lg), ...]
    client_names = [c for c, _ in stream_modes]
    lg_names = [l for _, l in stream_modes]
    # F1 守护:langgraph_name → client_name 反查(langgraph 用 "messages",前端期待 "messages-tuple")
    lg_to_client = {l: c for c, l in stream_modes}

    # 校验 assistant_id
    assistant_id = body.get("assistant_id") or "research"
    if assistant_id != "research":
        raise HTTPException(422, f"unknown assistant_id: {assistant_id}")

    # input vs command
    raw_input = body.get("input")
    command = _map_command(body.get("command"))
    actual_input: Any
    if command is not None:
        actual_input = command
    elif raw_input is not None:
        actual_input = raw_input
    else:
        actual_input = None

    # F13 守护:stateless /runs/stream 没有 thread_id 时为本次 run 生成一个,
    # 但**只用于 SSE metadata event**,**不**传进 _build_config —— 避免每次 stateless
    # run 都污染 saver(verified 2026-05: 不分流时 /threads/search 列表会被无主匿名
    # thread 灌满)。
    advertised_thread_id = thread_id or body.get("thread_id") or str(uuid.uuid4())

    # config:stateless 路径传 None 让 graph 跑 stateless(不持久化);persistent 路径
    # (URL path 含 thread_id)正常用 thread_id。
    user_cfg = body.get("config") or {}
    cfg = _build_config(thread_id, extra=user_cfg)
    if checkpoint := body.get("checkpoint"):
        cfg["configurable"].update(checkpoint)
        # F6 守护:URL 路径里的 thread_id 永远胜过 body.checkpoint.thread_id
        if thread_id:
            cfg["configurable"]["thread_id"] = thread_id

    # 发 metadata event
    run_id = str(uuid.uuid4())
    yield _sse_event("metadata", {"run_id": run_id, "thread_id": advertised_thread_id, "attempt": 1})

    # astream + 多 stream_mode(传 langgraph 内部名)
    try:
        async for chunk in agent.astream(
            actual_input,
            config=cfg,
            stream_mode=lg_names if len(lg_names) > 1 else lg_names[0],
            interrupt_before=body.get("interrupt_before"),
            interrupt_after=body.get("interrupt_after"),
        ):
            # 多 stream_mode 时 chunk 是 (mode, data) tuple
            if len(lg_names) > 1 and isinstance(chunk, tuple) and len(chunk) == 2:
                lg_mode, data = chunk
                yield _sse_event(lg_to_client.get(lg_mode, lg_mode), data)
            else:
                yield _sse_event(client_names[0], chunk)
    except Exception as e:
        # F7 守护:server 端 logger.exception 留完整 traceback 给运维;SSE error event
        # **只回类型 + 消息**,不带 traceback——避免向客户端(可能是公网访客)泄漏
        # 绝对路径 / 内部模块结构 / locals 中可能的敏感数据。
        # 仅当 DEEPAGENTS_DEBUG=1 时把 traceback 也发给客户端(本地调试用)。
        logger.exception(
            "[stream_run] failed; thread_id=%s run_id=%s", advertised_thread_id, run_id,
        )
        err_payload: dict[str, Any] = {"error": type(e).__name__, "message": str(e)}
        if os.environ.get("DEEPAGENTS_DEBUG") == "1":
            err_payload["traceback"] = traceback.format_exc()
        yield _sse_event("error", err_payload)
        return

    yield _sse_event("end", {"run_id": run_id})


@app.post("/runs/stream")
async def runs_stream(request: Request):
    body = await request.json()
    # 提前校验 stream_mode(在 StreamingResponse 提交头部前),否则 422 会被吞
    _validate_stream_mode(body.get("stream_mode"))
    return StreamingResponse(
        _stream_run(request, thread_id=None, body=body),
        media_type="text/event-stream",
    )


@app.post("/threads/{thread_id}/runs/stream")
async def thread_runs_stream(thread_id: str, request: Request):
    body = await request.json()
    _validate_stream_mode(body.get("stream_mode"))  # 同上,提前校验
    return StreamingResponse(
        _stream_run(request, thread_id=thread_id, body=body),
        media_type="text/event-stream",
    )


@app.get("/threads/{thread_id}/runs/{run_id}/stream")
async def join_run_stream(thread_id: str, run_id: str, request: Request):
    """useStream reconnectOnMount 用。

    本期不实现"按 run_id 续传旧流"——直接返回一个 end 事件让客户端认为旧 run 已结束,
    UI 会回到 idle 状态。后续若需要真正的断点续传,加 stream_resumable 持久化。
    """

    async def _close_stream():
        yield _sse_event("metadata", {"run_id": run_id, "thread_id": thread_id, "attempt": 1})
        yield _sse_event("end", {"run_id": run_id, "note": "reconnect; resumable stream not implemented"})

    return StreamingResponse(_close_stream(), media_type="text/event-stream")


@app.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(thread_id: str, run_id: str):
    """stream.stop() 用。本期实现为 no-op(返回 204),因为 graph.astream 在客户端
    断开连接时已通过 ASGI cancel 信号自然停止。"""
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 2024))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
