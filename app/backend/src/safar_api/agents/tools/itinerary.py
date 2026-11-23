"""Day-plan tool."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.itinerary import run_itinerary
from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import command_from_tool_result, emit_tool_start


@tool
def build_itinerary(
    mode: str = "build",
    instructions: str = "",
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Build or revise the day-by-day itinerary.

    Call ONLY when the user asks to create a plan or to change an existing one.
    Do NOT call when they ask what is already planned, including a specific day.
    mode=build when none exists. mode=revise with instructions when one exists.
    If a plan already exists, do not call this to finalize it or to match new selections.
    Ask whether to update the day plan, and call this only after the user agrees.
    """
    emit_tool_start(runtime, "build_itinerary")
    state = runtime.state if runtime else {}
    result = run_itinerary(
        {"args": {"mode": mode, "instructions": instructions}},
        agent_state_from_runtime(state),
    )
    return command_from_tool_result(
        result, tool="build_itinerary", detail="Building itinerary", runtime=runtime
    )
