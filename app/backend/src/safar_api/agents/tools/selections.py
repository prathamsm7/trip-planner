"""Choose a flight, train, or hotel that is already in the results."""

from __future__ import annotations

from typing import Any

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.progress import emit_progress
from safar_api.agents.selections import apply_selection_preferences
from safar_api.agents.tools.support import TOOL_LABELS, emit_tool_start, tool_result_command


@tool
def select_options(
    outbound_pref: str | None = None,
    return_pref: str | None = None,
    hotel_pref: str | None = None,
    outbound_train_pref: str | None = None,
    return_train_pref: str | None = None,
    outbound_index: int | None = None,
    return_index: int | None = None,
    hotel_index: int | None = None,
    outbound_train_index: int | None = None,
    return_train_index: int | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Choose a flight, train, or hotel from results already in Current trip.

    Call ONLY when the user asks to pick, select, or prefer an option (time of day, cheapest, airline, train number, hotel name).
    Do NOT call search_flights, search_trains, or search_stays for that request.
    Do NOT call if nothing is available yet — say so, or search first only if lists are missing.
    Prefer outbound_pref / return_pref / hotel_pref for flights and hotels.
    Prefer outbound_train_pref / return_train_pref for trains. Use an index only if the user names a number.
    Outbound = leaving the origin. Return = leaving the destination.
    """
    emit_tool_start(runtime, "select_options")
    state = runtime.state if runtime else {}
    selections, summary = apply_selection_preferences(
        state,
        outbound_pref=outbound_pref,
        return_pref=return_pref,
        hotel_pref=hotel_pref,
        outbound_train_pref=outbound_train_pref,
        return_train_pref=return_train_pref,
        outbound_index=outbound_index,
        return_index=return_index,
        hotel_index=hotel_index,
        outbound_train_index=outbound_train_index,
        return_train_index=return_train_index,
    )
    emit_progress(
        runtime,
        tool="select_options",
        status="complete",
        detail=summary,
        label=TOOL_LABELS["select_options"],
    )
    update_payload: dict[str, Any] = {
        "selections": selections,
        "last_step_detail": summary,
    }
    itinerary_raw = state.get("itinerary")
    if itinerary_raw:
        if isinstance(itinerary_raw, dict):
            update_payload["itinerary"] = {**itinerary_raw, "flagged": True}
        elif hasattr(itinerary_raw, "model_copy"):
            update_payload["itinerary"] = itinerary_raw.model_copy(update={"flagged": True})

    return tool_result_command(
        runtime,
        update_payload,
        summary,
    )
