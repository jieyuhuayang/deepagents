"""AC-1 — SkillWhitelistMiddleware 的 per-run 白名单过滤。

覆盖 docs/features/v0.6.0/001-skill-loading-whitelist/spec.md AC-1:
- active_skills=["deep-research"] → 只注入该 skill
- active_skills=None            → 全注入(不过滤,安全默认)
- active_skills=[]              → 零注入(显式全关)
- active_skills=["nonexistent"] → 交集为空,静默忽略未知名

只测 modify_request 的过滤+渲染逻辑(纯函数面),不触磁盘加载(那是 before_agent,
交给路由/E2E)。用 FakeRequest 替身,避免构造真 ModelRequest 的重依赖。
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

import middlewares
from middlewares import SkillWhitelistMiddleware


# ── 测试替身 ──────────────────────────────────────────────────────────────

@dataclass
class FakeRequest:
    """最小 ModelRequest 替身:modify_request 只用到 state / system_message / override。"""

    state: dict[str, Any]
    system_message: Any = None

    def override(self, **overrides: Any) -> "FakeRequest":
        return replace(self, **overrides)


def _skill(name: str) -> dict[str, Any]:
    """构造一条 SkillMetadata(_format_skills_list 需要的键全给齐)。"""
    return {
        "name": name,
        "description": f"{name} description",
        "path": f"/built-in/{name}/SKILL.md",
        "metadata": {},
        "license": None,
        "compatibility": None,
        "allowed_tools": [],
    }


def _make_mw() -> SkillWhitelistMiddleware:
    from deepagents.backends.filesystem import FilesystemBackend

    root = os.path.join(os.path.dirname(__file__), "..", "data", "skills")
    return SkillWhitelistMiddleware(
        backend=FilesystemBackend(root_dir=root, virtual_mode=True),
        sources=["/built-in/"],
    )


_BASE_PROMPT = "BASE-PROMPT"


def _render(mw: SkillWhitelistMiddleware, metadata: list[dict], active, monkeypatch) -> str:
    """跑一遍 modify_request,返回注入后的 system message 文本。

    给一个非空 base system message,这样"整段不注入"时文本恰好等于 base,
    可区分"注入了空 skills 段"与"完全没注入"。
    """
    from langchain_core.messages import SystemMessage

    monkeypatch.setattr(
        middlewares,
        "get_config",
        lambda: {"configurable": {"active_skills": active}} if active is not _SENTINEL
        else {"configurable": {}},
    )
    req = FakeRequest(
        state={"skills_metadata": metadata},
        system_message=SystemMessage(content=_BASE_PROMPT),
    )
    out = mw.modify_request(req)
    return str(out.system_message.content)


_SENTINEL = object()  # 表示 configurable 里压根没有 active_skills 键


# ── 测试 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def two_skills():
    return [_skill("deep-research"), _skill("brand-guidelines")]


def test_whitelist_keeps_only_listed(two_skills, monkeypatch):
    text = _render(_make_mw(), two_skills, ["deep-research"], monkeypatch)
    assert "deep-research" in text
    assert "brand-guidelines" not in text


def test_none_injects_all(two_skills, monkeypatch):
    text = _render(_make_mw(), two_skills, None, monkeypatch)
    assert "deep-research" in text
    assert "brand-guidelines" in text


def test_missing_key_injects_all(two_skills, monkeypatch):
    # configurable 无 active_skills 键(旧客户端)→ 等价 None → 全注入
    text = _render(_make_mw(), two_skills, _SENTINEL, monkeypatch)
    assert "deep-research" in text
    assert "brand-guidelines" in text


def test_empty_list_injects_no_section(two_skills, monkeypatch):
    # 全关 [] → 整段不注入:system message 保持 base 原样,不留空壳(PRD §5.2)
    text = _render(_make_mw(), two_skills, [], monkeypatch)
    assert text == _BASE_PROMPT
    assert "Available Skills" not in text
    assert "No skills available" not in text


def test_unknown_name_injects_no_section(two_skills, monkeypatch):
    # 白名单全是未知名 → 过滤后无命中 → 同样整段不注入
    text = _render(_make_mw(), two_skills, ["nonexistent"], monkeypatch)
    assert text == _BASE_PROMPT
    assert "deep-research" not in text
    assert "brand-guidelines" not in text


def test_get_config_raises_falls_back_to_all(two_skills, monkeypatch):
    # run 之外 get_config() 抛错 → try/except → None → 不过滤
    def _boom():
        raise RuntimeError("called outside a runnable")

    monkeypatch.setattr(middlewares, "get_config", _boom)
    req = FakeRequest(state={"skills_metadata": two_skills})
    out = _make_mw().modify_request(req)
    text = str(out.system_message.content)
    assert "deep-research" in text
    assert "brand-guidelines" in text
