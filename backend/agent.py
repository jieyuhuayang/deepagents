"""Deep Research agent — 装配中心。

提供 `build_agent(checkpointer)` factory:由 `backend/server.py` lifespan
显式传入 `AsyncPostgresSaver` / `AsyncSqliteSaver` 实例(根据 `DATABASE_URL`
路由)。详见 `docs/features/v0.5.0/002-fastapi-postgres-checkpointer/spec.md`
+ CLAUDE.md §强约束 #3 "自研 server 模式必须显式传 checkpointer"。

`agent = build_agent(None)` module-level fallback 保留供 `langgraph dev`
quick smoke 用(此时 langgraph dev 框架自动 attach inmem checkpointer,
checkpointer=None 等价于不传)。
"""

import os
import re
from typing import Any

import yaml
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

from middlewares import GenerativeUIMiddleware, SkillWhitelistMiddleware
from prompts import ORCHESTRATOR_PROMPT, RESEARCH_SUBAGENT_PROMPT
from tools import (
    bisheng_retrieve,
    emit_research_card,
    export_docx,
    request_clarification,
    think_tool,
    web_search,
)

load_dotenv()

# Skills 根目录:built-in/ 与(未来)personal/ 各为一个 source。
# 详见 docs/features/v0.6.0/001-skill-loading-whitelist/spec.md §5-§6。
SKILLS_ROOT = os.environ.get(
    "DEEPAGENTS_SKILLS_ROOT",
    os.path.join(os.path.dirname(__file__), "data", "skills"),
)

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
    "tools": [web_search, bisheng_retrieve, think_tool],
}


def build_agent(checkpointer: Any | None = None):
    """构造 deep research agent。

    Args:
        checkpointer: `AsyncPostgresSaver` / `AsyncSqliteSaver` 实例,由 server
            lifespan 根据 `DATABASE_URL` env 选择并 `.setup()` 后传入。
            `None` 仅用于 `langgraph dev` quick smoke——框架会自动 attach
            inmem checkpointer。自研 server 模式下必须显式传。
    """
    # Skills:自己构造 SkillWhitelistMiddleware(加载 + per-run 白名单过滤),
    # 经 middleware=[...] 注入,排在 GenerativeUIMiddleware 之前。
    # - 不传 create_deep_agent(skills=...):那会自动多插一个全量 SkillsMiddleware,
    #   造成双重注入。
    # - 不传 create_deep_agent(backend=...):SkillsMiddleware 用自己的 backend 读
    #   skill 目录(见 _get_backend);agent 的 write_file/export_docx 继续用默认
    #   state backend(虚拟文件系统),不能被换成真磁盘。
    # - virtual_mode=True:让 sources 的 "/built-in/" 相对 root_dir 解析,并把路径
    #   约束在 root_dir 内(拒绝 '..' / 绝对路径逃逸)。
    # 详见 spec §6 + middlewares.SkillWhitelistMiddleware docstring + 风险 R3。
    skills_backend = FilesystemBackend(root_dir=SKILLS_ROOT, virtual_mode=True)
    skills_middleware = SkillWhitelistMiddleware(
        backend=skills_backend,
        sources=["/built-in/"],
    )
    return create_deep_agent(
        model=model,
        tools=[web_search, think_tool, emit_research_card, request_clarification, export_docx],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=[research_subagent],
        middleware=[skills_middleware, GenerativeUIMiddleware()],
        checkpointer=checkpointer,
    )


# ---------------------------------------------------------------------------
# Skill 目录扫描(供 server.py 的只读 /api/skills 路由复用)
#
# 与 SkillsMiddleware 的加载解耦:这里直接 os.walk + frontmatter 解析,纯函数、
# 可脱离 agent 状态单测。SkillsMiddleware 走自己的 backend 注入 prompt;本组函数
# 只服务前端"列出/查看 skill"。详见 spec §6 / 风险 R4(id 含斜杠)。
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_skill_md(text: str) -> tuple[dict, str] | None:
    """切出 (frontmatter dict, body)。无合法 frontmatter / 非映射 → None。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data, text[m.end():]


def _scan_skills() -> list[dict]:
    """扫 SKILLS_ROOT/<source>/<name>/SKILL.md,返回带 body 的原始记录。

    容错:无 SKILL.md / frontmatter 解析失败 / 缺 name 的目录静默跳过,
    不让整个列表因单个坏 skill 失败(spec §3.1)。
    """
    records: list[dict] = []
    if not os.path.isdir(SKILLS_ROOT):
        return records
    for source in sorted(os.listdir(SKILLS_ROOT)):
        source_dir = os.path.join(SKILLS_ROOT, source)
        if not os.path.isdir(source_dir):
            continue
        for name in sorted(os.listdir(source_dir)):
            skill_md = os.path.join(source_dir, name, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            try:
                with open(skill_md, encoding="utf-8") as f:
                    parsed = _parse_skill_md(f.read())
            except OSError:
                continue
            if parsed is None:
                continue
            fm, body = parsed
            fm_name = str(fm.get("name", "")).strip()
            fm_desc = str(fm.get("description", "")).strip()
            # name + description 都必填:与 SkillsMiddleware._parse_skill_metadata 的
            # 契约一致,否则会出现"列表里能选、但 skills_metadata 没有 → 勾了不注入"
            # 的静默失配(code-review 发现)。
            if not fm_name or not fm_desc:
                continue
            records.append({
                "id": f"{source}/{fm_name}",
                "name": fm_name,
                "description": fm_desc,
                "source": source,
                "path": f"/{source}/{name}/SKILL.md",
                "instructions": body,
            })
    return records


def list_skills() -> list[dict]:
    """所有 skill 的摘要(不含 body),按 id 排序。"""
    return [
        {k: r[k] for k in ("id", "name", "description", "source", "path")}
        for r in _scan_skills()
    ]


def get_skill(skill_id: str) -> dict | None:
    """单个 skill 详情(含 `instructions` body);未命中 → None。"""
    for r in _scan_skills():
        if r["id"] == skill_id:
            return r
    return None


# Module-level fallback:让 langgraph dev / langgraph.json 仍可加载 graph
# (quick smoke 用,无持久化,与 langgraph dev 内置 inmem 兼容)。
# 自研 server (backend/server.py) 启动时会显式调 build_agent(saver) 拿带
# 持久化能力的 agent,不使用这个 module-level fallback。
agent = build_agent(None)
