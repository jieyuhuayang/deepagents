"""server 路由契约种子测试。

- `_validate_stream_mode`:守护 "stream_mode 含 'tools' → 422" 契约——这正是
  frontend useChat.ts fetch monkey-patch 存在的意义(CLAUDE.md §强约束 #7)。
- `GET /ok`:用 FastAPI TestClient 跑通 lifespan(临时 SQLite,见 conftest)。

覆盖 SDD 测试模型 ① 后端 Test-First — `server.py` 路由契约。
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import _validate_stream_mode, app


# ── stream_mode 契约(纯函数,无需启动 app)─────────────────────────────────

def test_stream_mode_tools_rejected():
    with pytest.raises(HTTPException) as ei:
        _validate_stream_mode(["values", "tools"])
    assert ei.value.status_code == 422


def test_stream_mode_valid_subset_ok():
    # 合法子集应规范化为 list[(client_name, langgraph_name)],不抛
    result = _validate_stream_mode(["values", "messages-tuple", "updates"])
    assert isinstance(result, list) and len(result) == 3


def test_stream_mode_unknown_rejected():
    with pytest.raises(HTTPException) as ei:
        _validate_stream_mode(["bogus-mode"])
    assert ei.value.status_code == 422


# ── /ok 健康检查(TestClient 跑 lifespan:临时 SQLite saver + build_agent)──

def test_ok_health_check():
    with TestClient(app) as client:
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
