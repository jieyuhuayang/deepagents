"""AC-2 / AC-3 — Skill 管理只读 HTTP 路由契约。

覆盖 docs/features/v0.6.0/001-skill-loading-whitelist/spec.md:
- AC-2: GET /api/skills 列表,含 deep-research,键 {id,name,description,source,path}
- AC-3: GET /api/skills/{id} 命中带 instructions;未命中 404

用 FastAPI TestClient 跑 lifespan(临时 SQLite,见 conftest),与 test_routes.py 同 pattern。
list_skills/get_skill 纯函数也直接单测(脱离 HTTP)。
"""

from fastapi.testclient import TestClient

from agent import get_skill, list_skills
from server import app


# ── 纯函数面(不经 HTTP)──────────────────────────────────────────────────

def test_list_skills_includes_deep_research():
    skills = list_skills()
    names = [s["name"] for s in skills]
    assert "deep-research" in names
    dr = next(s for s in skills if s["name"] == "deep-research")
    assert set(dr.keys()) >= {"id", "name", "description", "source", "path"}
    assert dr["id"] == "built-in/deep-research"
    assert dr["source"] == "built-in"
    assert dr["path"].startswith("/built-in/")
    assert dr["description"]  # 非空


def test_get_skill_hit_has_instructions():
    skill = get_skill("built-in/deep-research")
    assert skill is not None
    assert isinstance(skill["instructions"], str) and skill["instructions"].strip()
    # body(frontmatter 之后)应含正文标题,不应再含 frontmatter 分隔符开头
    assert "# Deep Research" in skill["instructions"]


def test_get_skill_miss_returns_none():
    assert get_skill("built-in/does-not-exist") is None


def test_scan_skips_skill_without_description(tmp_path, monkeypatch):
    """code-review 回归:无 description 的 skill 不该出现在列表——否则前端能选、
    但 SkillsMiddleware(要求 name+description)不收,勾了静默不注入。"""
    import agent as agent_mod

    root = tmp_path / "skills"
    (root / "built-in" / "no-desc").mkdir(parents=True)
    (root / "built-in" / "no-desc" / "SKILL.md").write_text(
        "---\nname: no-desc\n---\n\n# body\n", encoding="utf-8"
    )
    (root / "built-in" / "ok").mkdir(parents=True)
    (root / "built-in" / "ok" / "SKILL.md").write_text(
        "---\nname: ok\ndescription: has desc\n---\n\n# body\n", encoding="utf-8"
    )
    monkeypatch.setattr(agent_mod, "SKILLS_ROOT", str(root))

    names = [s["name"] for s in agent_mod.list_skills()]
    assert "ok" in names
    assert "no-desc" not in names


# ── HTTP 契约 ──────────────────────────────────────────────────────────────

def test_api_skills_list():
    with TestClient(app) as client:
        r = client.get("/api/skills")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        dr = next((s for s in data if s["name"] == "deep-research"), None)
        assert dr is not None
        assert dr["id"] == "built-in/deep-research"
        assert dr["source"] == "built-in"


def test_api_skill_detail_hit():
    with TestClient(app) as client:
        r = client.get("/api/skills/built-in/deep-research")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "deep-research"
        assert data["instructions"].strip()


def test_api_skill_detail_404():
    with TestClient(app) as client:
        r = client.get("/api/skills/built-in/nope")
        assert r.status_code == 404
