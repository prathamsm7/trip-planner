"""Hotel and stay search tool."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.booking import find_stays
from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import command_from_tool_result, emit_tool_start


@tool
def search_stays(
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    stay_type: str | None = None,
    budget: str | None = None,
    area: str | None = None,
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Search hotels or stays for the trip.

    Call ONLY when stays are missing or stale, or the user asks to search/refresh stays.
    Do NOT call to pick a hotel already listed — use select_options.
    Pass destination plus start_date and end_date (YYYY-MM-DD) when Current trip does not already have them.
    If the tool says fields are missing, call update_trip once. Do not call search_stays again in the same step.
    """
    emit_tool_start(runtime, "search_stays")
    result = find_stays(
        {
            "args": {
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
                "stay_type": stay_type,
                "budget": budget,
                "area": area,
                "refresh": refresh,
            }
        },
        agent_state_from_runtime(runtime.state if runtime else {}),
    )
    return command_from_tool_result(
        result, tool="search_stays", detail="Searching stays", runtime=runtime
    )
