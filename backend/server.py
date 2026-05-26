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
    # 空 list 视同未传(否则后续 lg_names[0] 在空 list 上 IndexError,会经
    # StreamingResponse 变成 SSE error event 而非 422,client 困惑)。
    if not raw:
        return [("values", "values")]
    # 元素类型守护:非 str 元素(dict/list 等非 hashable)在 dict.fromkeys 会 TypeError → 500;
    # 此处直接 422 with 友好 detail。
    if not all(isinstance(m, str) for m in raw):
        raise HTTPException(
            status_code=422,
            detail={"msg": "stream_mode entries must be strings", "got": raw},
        )
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
    """从 RunnableConfig.configurable 抽出 SDK Checkpoint 期望的 4 个字段。

    若 configurable 是空/不含 _CHECKPOINT_KEYS 任一(例如只有 graph_id),返回 None
    而非 {} —— 让前端 `if (state.checkpoint)` 守护真正生效。

    同时剔除 None 值字段:Pregel 兜底 snapshot 的 config 可能含 {thread_id: None},
    返回 {thread_id: None} 会让前端守护通过但解引用 .thread_id 是 null,SDK 构造
    `/threads/null/...` URL 或写脏数据。只保留有意义的 key。
    """
    if not configurable:
        return None
    result = {
        k: configurable[k]
        for k in _CHECKPOINT_KEYS
        if k in configurable and configurable[k] is not None
    }
    return result or None


# Sort-by 白名单:防 sort_by="metadata"(dict)在 dict<dict 比较时触发 TypeError 500。
_ALLOWED_SORT_BY = {"thread_id", "created_at", "updated_at"}


def _safe_int(raw: Any, *, default: int, field: str) -> int:
    """body 里的整数字段:None → default;不可转 int 则 422。

    - `0` 视为合法显式输入(避免 limit=0 走 falsy 转默认的语义反转)
    - bool 显式拒绝:`isinstance(True, int) is True`,`int(True)=1` 会让 limit=true
      被静默当 1。bool 是 JSON 协议错误,422。
    - float / Decimal 容忍 int(...) 默认行为(silent truncate),demo 量级可接受。
    """
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise HTTPException(
            status_code=422,
            detail={"msg": f"{field} must be int, not bool", "got": raw},
        )
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail={"msg": f"{field} must be int", "got": raw},
        ) from e


# DEEPAGENTS_DEBUG=1/true/yes/on 都视作开启;严格比较 "1" 会让常见 truthy 写法静默失败。
DEEPAGENTS_DEBUG = os.environ.get("DEEPAGENTS_DEBUG", "").strip().lower() in (
    "1", "true", "yes", "on",
)


def _serialize_state(state: Any) -> dict[str, Any]:
    """StateSnapshot → JSON-serializable dict (LangGraph SDK ThreadState 形状)。

    "空 snapshot"(thread 还没存过任何 checkpoint)的判定:Pregel.aget_state
    在 saver 找不到时返回 StateSnapshot(values={}, config=入参 cfg, metadata=None);
    此时不该把入参 cfg.configurable 当真 checkpoint 回去——返回 checkpoint: None。
    """
    if state is None:
        return {"values": {}, "next": [], "tasks": [], "checkpoint": None, "metadata": {}}
    # 区分 "saver 命中的 snapshot" 与 "Pregel 兜底的空 snapshot":前者 metadata 不为
    # None,后者 metadata = None。
    is_empty = (
        getattr(state, "metadata", None) is None
        and not getattr(state, "values", None)
    )
    if is_empty:
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
    limit = _safe_int(body.get("limit"), default=100, field="limit")
    if limit <= 0:
        return _jsonify([])
    offset = _safe_int(body.get("offset"), default=0, field="offset")
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"msg": "offset must be >= 0", "got": offset},
        )
    sort_by = body.get("sort_by") or "updated_at"
    if sort_by not in _ALLOWED_SORT_BY:
        sort_by = "updated_at"
    sort_order = (body.get("sort_order") or "desc").lower()

    saver = request.app.state.saver
    agent = request.app.state.agent
    # F4 mitigate + 5000 cap 防 OOM;真正根治要 SQL DISTINCT。
    fetch = min(max((offset + limit) * 10, 100), 5000)
    # Step 1:dedupe 出所有 thread_id。**不在这里过滤 checkpoint_ns** —— deepagents 的
    # sub-agent (`task` 工具)在同一 thread_id 下用 ns="tools:..." 写大量 checkpoint;
    # 如果先过滤 ns="" 再用 fetch limit,sub-agent ckpt 会占满 fetch 配额导致主 graph
    # ckpt 被截断(实测 lab host: 100 fetch 全是 sub-agent ns="tools:...",ns="" 主 graph
    # 11 个 ckpt 在 100+ 位置被截掉)。
    seen: dict[str, dict[str, Any]] = {}
    async for ck in saver.alist(None, limit=fetch):
        tid = ck.config.get("configurable", {}).get("thread_id")
        if not tid or tid in seen:
            continue
        ts = ck.checkpoint.get("ts") if ck.checkpoint else None
        seen[tid] = {
            "thread_id": tid,
            "created_at": ts,
            "updated_at": ts,
            "metadata": ck.metadata or {},
            "status": "idle",
            # config 走 _thin_checkpoint(配 ns="",由 _build_config 在 Step 2 填) —
            # 不泄漏 graph_id / __pregel_* 等内部字段。
            "config": {"configurable": _thin_checkpoint(ck.config.get("configurable")) or {}},
            # values 在 Step 2 用 agent.aget_state 填充
            "values": {},
        }
    # Step 2:对每个 thread 调 agent.aget_state(_build_config(tid)) 拿主 graph 的
    # reducer-resolved state —— _build_config 默认 ns="" 即主 graph。这步关键作用:
    # (a) 不管 Step 1 alist 拿到的是 sub-agent 还是主 graph ckpt,都重新指向主 graph;
    # (b) DeltaChannel(snapshot_frequency=50) 在非-snapshot step 上根本不在
    #     channel_values 含 messages key,要 walk DeltaSnapshot 祖先 + replay reducer
    #     才能拿到完整 list。aget_state 内部就做这个。
    # 只回前端实际用的 4 个业务 channel,避免泄漏 langgraph 内部 channel。
    for tid, item in seen.items():
        try:
            state = await agent.aget_state(_build_config(tid))
            full_values = (getattr(state, "values", None) or {}) if state is not None else {}
        except Exception:
            full_values = {}
        item["values"] = {
            k: full_values[k]
            for k in ("messages", "todos", "files", "ui")
            if k in full_values
        }
    # F5 + 排序:无 ts 的 thread(新建未跑过)在 desc(最常用)模式下排队首
    # (当作最新);asc 模式下排队尾(列表底)。简化:None 永远给 primary=1,
    # has-val 给 primary=0,靠 reverse 切换头尾位置——
    #   desc(reverse=True):(1,"") 排首,(0, ts) 在后 → None first
    #   asc (reverse=False):(0, ts) 排首,(1,"") 在后 → None last
    threads = list(seen.values())

    def _sort_key(t: dict[str, Any]) -> tuple[int, str]:
        v = t.get(sort_by)
        return (1 if v is None else 0, str(v or ""))

    threads.sort(key=_sort_key, reverse=(sort_order == "desc"))
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
    # 注意:configurable 与 checkpoint 两个 key 是**SDK 协议双别名**(SDK 版本不一致
    # 时分别读不同 key),内容必须保持一致——用 dict() copy 隔离,防止后人误改一个。
    new_configurable = _thin_checkpoint(new_cfg.get("configurable") if new_cfg else None) or {}
    return _jsonify({"configurable": new_configurable, "checkpoint": dict(new_configurable)})


@app.post("/threads/{thread_id}/history")
async def thread_history(thread_id: str, body: dict[str, Any] | None = None, request: Request = None):
    body = body or {}
    agent = request.app.state.agent
    cfg = _build_config(thread_id)
    limit = _safe_int(body.get("limit"), default=10, field="limit")
    if limit <= 0:
        return _jsonify([])
    # 注:`offset` 字段不支持。LangGraph aget_state_history API 用 `before` 游标分页,
    # 没有 offset 参数;langgraph-sdk getHistory 也不传 offset。客户端误传时显式 422
    # 让其切换到 `before` 游标,避免之前"校验通过但被静默忽略"的假翻页。
    if body.get("offset") is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "msg": "thread_history uses 'before' cursor, not offset",
                "got_offset": body.get("offset"),
            },
        )
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

    # stateless /runs/stream(URL path 无 thread_id):mint 新 UUID 并**持久化**,
    # 跟 LangGraph SDK 客户端期望一致(server 给前端 anchor)。撤销 round-2 的"mint
    # 不写盘"设计——那导致 (a) /threads/search 拿不到这次 run 创建的 thread → 前端
    # URL 锚定不存在的 thread,(b) body.config.configurable.thread_id 可注入到现有
    # thread(verified 2026-05-27 跨 thread 写入)。
    #
    # 安全:stateless 路径下,客户端**不能**通过 body 指定 checkpoint anchor 相关任何
    # 字段(thread_id / checkpoint_id / checkpoint_ns / checkpoint_map)。若想复用
    # 已有 thread 或从某个 checkpoint 续传,必须用 /threads/{id}/runs/stream
    # (persistent 路径)。这里**完整 strip _CHECKPOINT_KEYS**,关上跨 thread 注入 +
    # cross-checkpoint-fork 漏洞。同时避免 mutate FastAPI body 引用,用 dict 重建。
    user_cfg = body.get("config") or {}
    if thread_id is None:
        thread_id = str(uuid.uuid4())
        # 整个 user_cfg.configurable 重建一份(避免 mutate body 引用 + 完整 strip
        # _CHECKPOINT_KEYS)
        existing_configurable = user_cfg.get("configurable") if isinstance(user_cfg, dict) else None
        if isinstance(existing_configurable, dict):
            cleaned = {k: v for k, v in existing_configurable.items() if k not in _CHECKPOINT_KEYS}
            user_cfg = {**user_cfg, "configurable": cleaned}

    # config:thread_id 强制走 URL/mint 出来的;_build_config 末尾会 force.
    cfg = _build_config(thread_id, extra=user_cfg)
    if checkpoint := body.get("checkpoint"):
        cfg["configurable"].update(checkpoint)
        # URL/mint 的 thread_id 永远胜过 body.checkpoint.thread_id
        cfg["configurable"]["thread_id"] = thread_id

    # 发 metadata event
    run_id = str(uuid.uuid4())
    yield _sse_event("metadata", {"run_id": run_id, "thread_id": thread_id, "attempt": 1})

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
            "[stream_run] failed; thread_id=%s run_id=%s", thread_id, run_id,
        )
        err_payload: dict[str, Any] = {"error": type(e).__name__, "message": str(e)}
        if DEEPAGENTS_DEBUG:
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
