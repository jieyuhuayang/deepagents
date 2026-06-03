"""Custom middlewares for the Deep Research agent."""

from typing import Annotated, Any, Sequence

from langchain.agents.middleware.types import AgentMiddleware, AgentState, ModelRequest
from langgraph.config import get_config
from langgraph.graph.ui import AnyUIMessage, ui_message_reducer

from deepagents.middleware.skills import SkillsMiddleware


class GenerativeUIState(AgentState):
    ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer]


class GenerativeUIMiddleware(AgentMiddleware[GenerativeUIState, Any, Any]):
    """Inject a `ui` state field so `push_ui_message()` can write to it.

    Without this, `_DeepAgentState` has no `ui` channel and ui messages get
    dropped on the floor — `state.values.ui` stays `None`.
    """

    state_schema = GenerativeUIState


class SkillWhitelistMiddleware(SkillsMiddleware):
    """SkillsMiddleware + per-run 白名单过滤。

    deepagents 自带的 SkillsMiddleware 会把"加载到的所有 skill"全部注入 system
    prompt。本子类在渲染前按本轮请求的 `config.configurable.active_skills` 过滤
    `skills_metadata`,做到"一次加载、按 run 取舍":

    - `active_skills = None`(或 configurable 无此键)→ **不过滤**,全注入(安全
      默认,兼容旧客户端 / `/info` smoke)。
    - `active_skills = []`                          → 注入零 skill(显式全关)。
    - `active_skills = [...]`                       → 按 name 取交集,未知名静默忽略。

    为什么过滤在 `modify_request` 渲染**之前**、而不是"注入后再 strip":基类把
    skills 段 append 到 system message,后注入的文本无法干净反注入(脆弱)。子类
    化只在渲染前裁剪 `skills_metadata`,一次渲染、一个事实源。详见
    docs/features/v0.6.0/001-skill-loading-whitelist/spec.md §6 + 风险 R1。

    注意:本类**自己构造**放进 `create_deep_agent(middleware=[...])`,**不要**再给
    `create_deep_agent(skills=...)`——那会自动多插一个全量 SkillsMiddleware,导致
    双重注入。
    """

    def modify_request(self, request: ModelRequest) -> ModelRequest:
        active = _active_skills()
        if active is not None:
            allow = set(active)
            metadata = request.state.get("skills_metadata", [])
            kept = [s for s in metadata if s["name"] in allow]
            request = request.override(state={**request.state, "skills_metadata": kept})
        return super().modify_request(request)


def _active_skills() -> list[str] | None:
    """从本轮 run 的 config 读白名单;run 之外 / 缺省 → None(不过滤)。"""
    try:
        cfg = get_config() or {}
    except Exception:
        return None
    return (cfg.get("configurable") or {}).get("active_skills")
