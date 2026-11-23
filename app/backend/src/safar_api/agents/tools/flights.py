"""Flight search tool."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.booking import find_flights
from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import command_from_tool_result, emit_tool_start


@tool
def search_flights(
    departure_airport: str | None = None,
    arrival_airport: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    refresh: bool = False,
    runtime: ToolRuntime = None,
) -> Command:
    """Search flights when the user asked for a flight and origin, destination, and dates are known.

    Search the outbound journey. Pass end_date only when the user asked for a return or a round trip. Omit end_date otherwise. For a return-only request, pass end_date and omit start_date.
    Call when flights are missing or stale, the user asks to search or refresh, or they change airports or dates.
    Do NOT call to choose among flights already listed — use select_options.
    Pass IATA codes only when the user names airports. refresh=True only for a new search.
    If this tool reports no flights, ask the user which listed airport to use. Do not search another airport until they choose.
    """
    emit_tool_start(runtime, "search_flights")
    result = find_flights(
        {
            "args": {
                "departure_airport": departure_airport,
                "arrival_airport": arrival_airport,
                "start_date": start_date,
                "end_date": end_date,
                "refresh": refresh,
            }
        },
        agent_state_from_runtime(runtime.state if runtime else {}),
    )
    return command_from_tool_result(
        result, tool="search_flights", detail="Searching flights", runtime=runtime
    )
