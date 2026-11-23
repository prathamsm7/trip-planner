"""Destination research tool."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.research import run_research
from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import command_from_tool_result, emit_tool_start


@tool
def research_destination(
    focus: str = "both",
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Fetch destination overview, areas, and tips.

    Call ONLY when Current trip shows research missing or stale, or the user asks to refresh research.
    Do NOT call if research is ready. Do NOT call to pick flights or hotels.
    refresh=True only when the user asks to refresh or the brief destination changed.
    """
    emit_tool_start(runtime, "research_destination")
    state = runtime.state if runtime else {}
    result = run_research(
        {"args": {"focus": focus, "refresh": refresh}},
        agent_state_from_runtime(state),
    )
    return command_from_tool_result(
        result, tool="research_destination", detail="Researching destination", runtime=runtime
    )
