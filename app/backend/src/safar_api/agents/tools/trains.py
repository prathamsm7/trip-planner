"""Train tools: find station codes, then search trains for those codes."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import command_from_tool_result, emit_tool_start
from safar_api.agents.trains import search_railway_stations as find_stations
from safar_api.agents.trains import search_trains as find_trains


@tool
def search_railway_stations(
    origin: str | None = None,
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Read up to 3 railway station codes per city from the web.

    Call when the user asked for a train and the city names are known, before search_trains. Pass those cities. Does not search trains.
    If no station codes are found, tell the user and stop.
    """
    emit_tool_start(runtime, "search_railway_stations")
    result = find_stations(
        {
            "args": {
                "origin": origin,
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
            }
        },
        agent_state_from_runtime(runtime.state if runtime else {}),
    )
    return command_from_tool_result(
        result, tool="search_railway_stations", detail="Finding railway stations", runtime=runtime
    )


@tool
def search_trains(
    origin: str | None = None,
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    origin_station: str | None = None,
    destination_station: str | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Search trains on RailCore /routes/trains using saved station codes.

    from and to are station codes such as CSTM and MAO, never city names.
    Call only after station codes are saved. Does not look up stations.
    Pass start_date (YYYY-MM-DD) for the outbound journey. Pass end_date only when the user asked for the return. Omit end_date otherwise. For a return-only request, pass end_date and omit start_date.
    Searches the primary station pair. When the user picks another saved station,
    pass its name or code as origin_station or destination_station.
    """
    emit_tool_start(runtime, "search_trains")
    result = find_trains(
        {
            "args": {
                "origin": origin,
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
                "origin_station": origin_station,
                "destination_station": destination_station,
            }
        },
        agent_state_from_runtime(runtime.state if runtime else {}),
    )
    return command_from_tool_result(
        result, tool="search_trains", detail="Searching trains", runtime=runtime
    )
