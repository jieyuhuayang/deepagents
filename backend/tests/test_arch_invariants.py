"""强约束不变量 —— scripts/arch-guard.sh 的 pytest 镜像。

L0 arch-guard hook 在编辑时即时提醒;本测试是同一组红线的 pre-PR / CI 全量执行点。
两处口径必须一致(改一处记得改另一处 + CLAUDE.md §强约束 + spec 模板 §4)。

覆盖 CLAUDE.md §强约束 中【可机检的 5 条 + prompts 语序】。
"""

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_AGENT = _REPO / "backend" / "agent.py"
_PROMPTS = _REPO / "backend" / "prompts.py"
_USECHAT = _REPO / "frontend" / "src" / "app" / "hooks" / "useChat.ts"


def _read(p: Path) -> str:
    assert p.exists(), f"期望文件存在: {p}"
    return p.read_text(encoding="utf-8")


# ── agent.py 四条 ────────────────────────────────────────────────────────

def test_generative_ui_middleware_present():
    assert "GenerativeUIMiddleware" in _read(_AGENT), \
        "agent.py 必须保留 GenerativeUIMiddleware,否则 push_ui_message 被默默丢弃(§2.2)"


def test_llm_locked_to_chatopenai_dashscope():
    src = _read(_AGENT)
    assert "ChatOpenAI" in src, "LLM 必须是 ChatOpenAI(§2.1)"
    assert "dashscope" in src.lower(), "base_url 必须指向 DashScope(§2.1)"
    assert "init_chat_model(" not in src, "不得用 init_chat_model(provider registry 指不到 DashScope)"


def test_streaming_not_disabled():
    import re
    assert not re.search(r"streaming\s*=\s*False", _read(_AGENT)), \
        "streaming 不得改回 False —— 现代模型支持 tools+stream(§2.1)"


def test_no_memorysaver_in_agent():
    assert "MemorySaver" not in _read(_AGENT), \
        "checkpointer 由 server.py lifespan 注入,agent.py 不应硬塞 MemorySaver(§强约束 #3)"


# ── prompts.py:强制语序 ──────────────────────────────────────────────────

def test_prompts_keep_emit_research_card_ordering():
    assert "emit_research_card" in _read(_PROMPTS), \
        "prompts.py 必须保留 emit_research_card 强制语序,否则模型跳过卡片直接写文件(troubleshooting §2)"


# ── frontend useChat.ts:fetch monkey-patch ──────────────────────────────

def test_usechat_fetch_monkeypatch_present():
    if not _USECHAT.exists():
        pytest.skip("frontend 不在当前 checkout(如纯后端 worktree)")
    src = _read(_USECHAT)
    assert "window.fetch" in src and "stream_mode" in src, \
        "useChat.ts 的 fetch monkey-patch(过滤 stream_mode 'tools')不得删除(§3.3)"


# ── Skills(v0.6.0/001):GenerativeUI 仍在栈 + SkillWhitelist 排其前 ──────

def test_skill_whitelist_before_generative_ui():
    """AC-6:agent.py middleware 列表里 SkillWhitelistMiddleware 必须排在
    GenerativeUIMiddleware 之前(保证白名单过滤先于 UI 字段注入,且 GenerativeUI
    始终保留)。引入 Skills 后守护 §强约束 #1 不被新中间件挤掉。"""
    src = _read(_AGENT)
    assert "GenerativeUIMiddleware()" in src, "GenerativeUIMiddleware 必须仍在装配栈(§2.2)"
    assert "SkillWhitelistMiddleware(" in src, "SkillWhitelistMiddleware 应已接入 build_agent"
    swm = src.index("SkillWhitelistMiddleware(")
    gui = src.index("GenerativeUIMiddleware()")
    assert swm < gui, "SkillWhitelistMiddleware 必须排在 GenerativeUIMiddleware 之前(spec AC-6)"
