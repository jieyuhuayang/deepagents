"""Custom middlewares for the Deep Research agent."""

from typing import Annotated, Any, Sequence

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langgraph.graph.ui import AnyUIMessage, ui_message_reducer


class GenerativeUIState(AgentState):
    ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer]


class GenerativeUIMiddleware(AgentMiddleware[GenerativeUIState, Any, Any]):
    """Inject a `ui` state field so `push_ui_message()` can write to it.

    Without this, `_DeepAgentState` has no `ui` channel and ui messages get
    dropped on the floor — `state.values.ui` stays `None`.
    """

    state_schema = GenerativeUIState
