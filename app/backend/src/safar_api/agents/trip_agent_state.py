"""Shared state for the create_agent trip planner."""

from __future__ import annotations

from typing import Annotated, Any, NotRequired

from langchain.agents import AgentState

from safar_api.trip.state import keep_latest, merge_selections, merge_step_detail


def replace_dict(left: dict | None, right: dict | None) -> dict | None:
    """Graph reducer: replace the artifact. None clears it."""
    if right is None:
        return None
    return right


class TripAgentState(AgentState):
    """Conversation + trip artifacts. Optional on first turn; tools fill them in."""

    brief: NotRequired[Annotated[dict, keep_latest]]
    research: NotRequired[Annotated[dict | None, replace_dict]]
    weather: NotRequired[Annotated[dict | None, replace_dict]]
    flights: NotRequired[Annotated[dict | None, replace_dict]]
    trains: NotRequired[Annotated[dict | None, replace_dict]]
    stays: NotRequired[Annotated[dict | None, replace_dict]]
    itinerary: NotRequired[Annotated[dict | None, replace_dict]]
    selections: NotRequired[Annotated[dict, merge_selections]]
    chat: NotRequired[Annotated[list, keep_latest]]
    last_step_detail: NotRequired[Annotated[str, merge_step_detail]]
    remaining_steps: NotRequired[Annotated[int, keep_latest]]


def empty_trip_fields() -> dict[str, Any]:
    """Defaults for a brand-new thread."""
    return {
        "brief": {},
        "research": None,
        "weather": None,
        "flights": None,
        "trains": None,
        "stays": None,
        "itinerary": None,
        "selections": {},
        "last_step_detail": "",
    }
