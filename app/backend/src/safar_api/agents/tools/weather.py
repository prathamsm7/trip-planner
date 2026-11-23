"""Weather tool."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import command_from_tool_result, emit_tool_start
from safar_api.agents.weather import run_weather


@tool
def get_weather(
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Fetch the weather outlook for the saved destination and dates.

    Call ONLY when Current trip shows weather missing or stale, or the user asks to refresh weather.
    Do NOT call if weather is ready. Requires a destination plus dates or a month already saved.
    """
    emit_tool_start(runtime, "get_weather")
    state = runtime.state if runtime else {}
    result = run_weather({"args": {"refresh": refresh}}, agent_state_from_runtime(state))
    return command_from_tool_result(
        result, tool="get_weather", detail="Checking weather", runtime=runtime
    )
