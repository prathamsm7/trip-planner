"""Convert supervisor checkpoint dicts into the state specialist tools read."""

from __future__ import annotations

from typing import Any

from safar_api.trip.brief import TripBrief
from safar_api.trip.results import Artifact
from safar_api.trip.state import AgentState


def brief_from_state(state: dict[str, Any] | AgentState) -> TripBrief:
    raw = state.get("brief") if isinstance(state, dict) else state.brief
    if isinstance(raw, TripBrief):
        return raw
    payload = dict(raw or {})
    if isinstance(payload.get("stated"), list):
        payload["stated"] = set(payload["stated"])
    return TripBrief.model_validate(payload)


def artifact_from_state(raw: Any) -> Artifact | None:
    if raw is None:
        return None
    if isinstance(raw, Artifact):
        return raw
    if isinstance(raw, dict):
        if "kind" in raw and "data" in raw:
            return Artifact.model_validate(raw)
        return None
    return None


def agent_state_from_runtime(state: dict[str, Any]) -> AgentState:
    """Rebuild the specialist-tool state from the supervisor checkpoint."""
    return AgentState(
        messages=state.get("messages") or [],
        brief=brief_from_state(state),
        research=artifact_from_state(state.get("research")),
        weather=artifact_from_state(state.get("weather")),
        flights=artifact_from_state(state.get("flights")),
        stays=artifact_from_state(state.get("stays")),
        itinerary=artifact_from_state(state.get("itinerary")),
        selections=state.get("selections") or {},
    )


def dump_artifact(artifact: Artifact | None) -> dict | None:
    if artifact is None:
        return None
    return artifact.model_dump()


def updates_from_agent_result(result_updates: dict[str, Any]) -> dict[str, Any]:
    """Map run_* updates (Artifact objects) onto TripAgentState dict fields."""
    out: dict[str, Any] = {}
    for key in ("research", "weather", "flights", "stays", "itinerary"):
        if key in result_updates:
            out[key] = dump_artifact(result_updates[key])
    if "brief" in result_updates:
        brief = result_updates["brief"]
        if isinstance(brief, TripBrief):
            data = brief.model_dump()
            data["stated"] = sorted(brief.stated)
            out["brief"] = data
        else:
            out["brief"] = brief
    if "selections" in result_updates:
        out["selections"] = result_updates["selections"]
    if "last_step_detail" in result_updates:
        out["last_step_detail"] = result_updates["last_step_detail"]
    return out
