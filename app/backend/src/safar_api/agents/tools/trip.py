"""Save trip facts. Other tools read the saved brief on the next step."""

from __future__ import annotations

from typing import Any

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from safar_api.agents.progress import emit_progress
from safar_api.agents.state_bridge import brief_from_state
from safar_api.agents.tools.support import TOOL_LABELS, emit_tool_start, tool_result_command
from safar_api.trip.brief import TripBrief, TripUpdate, apply_trip_update
from safar_api.trip.results import Artifact, apply_brief_change


def brief_to_dict(brief: TripBrief) -> dict[str, Any]:
    data = brief.model_dump()
    data["stated"] = sorted(brief.stated)
    return data


def artifacts_from_state(state: dict) -> dict[str, Artifact | None]:
    out: dict[str, Artifact | None] = {}
    for key in ("research", "weather", "flights", "trains", "stays", "itinerary"):
        raw = state.get(key)
        if isinstance(raw, Artifact):
            out[key] = raw
        elif isinstance(raw, dict) and "kind" in raw:
            out[key] = Artifact.model_validate(raw)
        else:
            out[key] = None
    return out


@tool
def update_trip(
    origin: str | None = None,
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    duration_days: int | None = None,
    month: str | None = None,
    travellers: int | None = None,
    budget: str | None = None,
    style: str | None = None,
    transport_mode: str | None = None,
    stay_type: str | None = None,
    preferences: list[str] | None = None,
    notes: str | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Save new or changed trip facts (origin, destination, dates, travellers, budget, style).

    Call ONLY when the user states a fact that is missing or different in Current trip.
    Do NOT call for questions, selections, or repeats of fields already saved.
    Pass only changed fields. Dates are YYYY-MM-DD.
    Call this alone first — other tools read the saved brief on the next step.
    """
    emit_tool_start(runtime, "update_trip")
    state = runtime.state if runtime else {}
    updated, changed = apply_trip_update(
        brief_from_state(state),
        TripUpdate(
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            duration_days=duration_days,
            month=month,
            travellers=travellers,
            budget=budget,  # type: ignore[arg-type]
            style=style,  # type: ignore[arg-type]
            transport_mode=transport_mode,  # type: ignore[arg-type]
            stay_type=stay_type,  # type: ignore[arg-type]
            preferences=preferences,
            notes=notes,
        ),
    )
    artifacts = apply_brief_change(changed, artifacts_from_state(state))
    update: dict[str, Any] = {
        "brief": brief_to_dict(updated),
        "last_step_detail": f"Updated trip: {sorted(changed) or 'no changes'}",
    }
    for key, artifact in artifacts.items():
        update[key] = artifact.model_dump() if artifact is not None else None
    summary = f"Updated fields: {sorted(changed) or 'none'}"
    emit_progress(
        runtime,
        tool="update_trip",
        status="complete",
        detail=summary,
        label=TOOL_LABELS["update_trip"],
    )
    return tool_result_command(runtime, update, summary)
