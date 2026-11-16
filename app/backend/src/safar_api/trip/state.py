"""Trip facts passed into specialist tools, plus the UI snapshot mapping."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field

from safar_api.trip.brief import TripBrief
from safar_api.trip.results import Artifact


def keep_latest(left: Any, right: Any) -> Any:
    """Graph reducer: the newest write wins."""
    return right if right is not None else left


def merge_selections(left: dict, right: dict) -> dict:
    """Graph reducer: overlay new flight/hotel picks onto the previous ones."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def merge_step_detail(left: str, right: str) -> str:
    """Graph reducer: newest non-empty progress label wins."""
    return right or left or ""


class AgentState(BaseModel):
    """Trip facts and saved results a specialist tool reads."""

    messages: Sequence[BaseMessage] = Field(default_factory=list)
    brief: TripBrief = Field(default_factory=TripBrief)
    research: Optional[Artifact] = None
    weather: Optional[Artifact] = None
    flights: Optional[Artifact] = None
    stays: Optional[Artifact] = None
    itinerary: Optional[Artifact] = None
    selections: dict = Field(default_factory=dict)


def _message_to_dict(msg: BaseMessage) -> dict[str, Any]:
    from safar_api.nodes.guardrail import message_text, sanitize_output

    role = "assistant"
    if isinstance(msg, HumanMessage):
        role = "user"
    elif isinstance(msg, AIMessage):
        role = "assistant"
    content = message_text(msg.content)
    if role == "assistant":
        content = sanitize_output(content)
    return {
        "role": role,
        "content": content,
        "id": getattr(msg, "id", None),
    }


def snapshot_from_agent_state(values: dict[str, Any]) -> dict[str, Any]:
    """Map supervisor state to the fields the chat UI reads."""
    brief = values.get("brief")
    if isinstance(brief, TripBrief):
        structured = brief.to_ui_trip()
    elif isinstance(brief, dict):
        payload = dict(brief)
        if isinstance(payload.get("stated"), list):
            payload["stated"] = set(payload["stated"])
        structured = TripBrief.model_validate(payload).to_ui_trip()
    else:
        structured = None

    def _artifact_data(artifact: Any) -> dict | None:
        if artifact is None:
            return None
        if isinstance(artifact, Artifact):
            return artifact.data
        if isinstance(artifact, dict):
            if "data" in artifact:
                return artifact.get("data") or {}
            return artifact
        return None

    research_data = _artifact_data(values.get("research")) or {}
    weather_data = _artifact_data(values.get("weather"))
    flights_data = _artifact_data(values.get("flights")) or {}
    stays_data = _artifact_data(values.get("stays")) or {}
    itinerary_data = _artifact_data(values.get("itinerary"))

    messages = values.get("messages") or []
    return {
        "structured": structured,
        "weather": weather_data,
        "destination_about": research_data.get("overview", "") if research_data else "",
        "itinerary": itinerary_data,
        "hotel_search_results": stays_data.get("properties") if stays_data else None,
        "flights_data": flights_data if flights_data else {},
        "selections": values.get("selections") or {},
        "messages": [_message_to_dict(m) for m in messages],
    }
