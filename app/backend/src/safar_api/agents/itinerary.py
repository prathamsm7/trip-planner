"""Itinerary agent — build or revise a day-by-day plan."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.agents.base import AgentResult
from safar_api.agents.selections import resolve_selections
from safar_api.logging_config import log_exception
from safar_api.services.llm import planning_llm
from safar_api.trip.results import Itinerary, make_artifact
from safar_api.trip.state import AgentState

logger = logging.getLogger(__name__)


def _state_as_dict(state: AgentState) -> dict[str, Any]:
    return {
        "selections": state.selections or {},
        "flights": state.flights.model_dump() if state.flights else None,
        "trains": state.trains.model_dump() if state.trains else None,
        "stays": state.stays.model_dump() if state.stays else None,
    }


def _travel_context(state: AgentState) -> str:
    resolved = resolve_selections(_state_as_dict(state))
    out = resolved.get("outbound_flight")
    ret = resolved.get("return_flight")
    out_train = resolved.get("outbound_train")
    ret_train = resolved.get("return_train")
    hotels = resolved.get("hotels") or []
    lines = ["SELECTED TRAVEL (authoritative — schedule around these):"]
    if out:
        lines.append(
            f"- Outbound: {out.get('airline')} {out.get('flight_number')} "
            f"{out.get('departure_airport')} {out.get('departure_time')} → "
            f"{out.get('arrival_airport')} {out.get('arrival_time')} "
            f"(₹{out.get('price')}, {out.get('stops')} stops)"
        )
        lines.append(
            "  Day 1 must respect arrival time: late-night arrival → light/evening-only plan; "
            "morning arrival → full day is fine."
        )
    elif out_train:
        train = out_train
        lines.append(
            f"- Outbound train: {train.get('train_number')} {train.get('train_name')} "
            f"({train.get('train_type_label') or train.get('train_type')}) "
            f"{train.get('from_station_code')} {train.get('departure_time')} → "
            f"{train.get('to_station_code')} {train.get('arrival_time')}"
        )
        lines.append("  Day 1 must respect the train arrival time.")
    else:
        lines.append("- Outbound: not selected yet")
    if ret:
        lines.append(
            f"- Return: {ret.get('airline')} {ret.get('flight_number')} "
            f"{ret.get('departure_airport')} {ret.get('departure_time')} → "
            f"{ret.get('arrival_airport')} {ret.get('arrival_time')} "
            f"(₹{ret.get('price')}, {ret.get('stops')} stops)"
        )
        lines.append(
            "  Last day must leave enough time to reach the airport before departure."
        )
    elif ret_train:
        train = ret_train
        lines.append(
            f"- Return train: {train.get('train_number')} {train.get('train_name')} "
            f"{train.get('from_station_code')} {train.get('departure_time')} → "
            f"{train.get('to_station_code')} {train.get('arrival_time')}"
        )
        lines.append("  The last day must leave enough time to reach the station before departure.")
    else:
        lines.append("- Return: not selected yet")
    if hotels:
        for h in hotels[:3]:
            lines.append(
                f"- Hotel: {h.get('name')} "
                f"(₹{h.get('price_per_night')}/night, rating={h.get('rating')})"
            )
    else:
        lines.append("- Hotels: not selected yet")
    return "\n".join(lines)


def _validate(itinerary: Itinerary, expected_days: int | None) -> list[str]:
    problems: list[str] = []
    if expected_days and len(itinerary.days) != expected_days:
        problems.append(
            f"Expected {expected_days} days, got {len(itinerary.days)}."
        )
    seen: set[str] = set()
    for day in itinerary.days:
        if not day.plan:
            problems.append(f"Day {day.day} has no plan blocks.")
            continue
        block = day.plan[0]
        for slot_name, activities in (
            ("morning", block.morning),
            ("afternoon", block.afternoon),
            ("evening", block.evening),
        ):
            if not activities:
                problems.append(f"Day {day.day} missing {slot_name}.")
            for act in activities:
                key = act.strip().lower()
                if key in seen:
                    problems.append(f"Repeated activity: {act}")
                seen.add(key)
    return problems


def _build(state: AgentState, instructions: str) -> AgentResult:
    brief = state.brief
    duration = brief.resolved_duration_days()
    if not brief.destination or not duration:
        return AgentResult(
            status="failed",
            summary="Need destination and trip length to build an itinerary.",
            error="missing_fields",
        )

    research = state.research.data if state.research else {}
    weather = state.weather.data if state.weather else {}
    travel = _travel_context(state)
    system = """
You are a senior travel operations planner.
Create a REALISTIC, WEATHER-AWARE, GEOGRAPHICALLY EFFICIENT itinerary.
Generate EXACTLY the requested number of days with morning/afternoon/evening each.
Honor SELECTED TRAVEL times (late-night arrival → light Day 1; leave buffer before return departure).
Return structured JSON matching the itinerary schema.
""".strip()
    user = f"""
Create the complete itinerary now.

FROM: {brief.origin}
TO: {brief.destination}
DATES: {brief.start_date} to {brief.end_date}
TOTAL DAYS: {duration}
TRAVELERS: {brief.travellers}
STYLE: {brief.style}
BUDGET: {brief.budget}
TRANSPORT: {brief.transport_mode}
PREFERENCES: {", ".join(brief.preferences) or "none"}
NOTES: {brief.notes}
EXTRA INSTRUCTIONS: {instructions or "none"}

{travel}

RESEARCH:
{research}

WEATHER:
{weather}
""".strip()
    try:
        result = planning_llm().with_structured_output(Itinerary).invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=user),
            ]
        )
    except Exception as exc:
        log_exception(logger, "itinerary build failed", exc, context={"duration": duration})
        return AgentResult(
            status="failed",
            summary=f"Could not build itinerary: {exc}",
            detail="Building itinerary",
            error=type(exc).__name__,
        )

    problems = _validate(result, duration)
    if problems:
        try:
            result = planning_llm().with_structured_output(Itinerary).invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(
                        content=(
                            "Repair this itinerary. Fix ONLY these problems:\n"
                            + "\n".join(problems)
                            + f"\n\nTrip context:\n{user}\n\nCurrent itinerary:\n{result.model_dump()}"
                        )
                    ),
                ]
            )
        except Exception as exc:
            log_exception(
                logger,
                "itinerary repair failed",
                exc,
                context={"problems": problems[:5]},
            )

    artifact = make_artifact("itinerary", brief, result)
    return AgentResult(
        status="ok",
        summary=result.summary or f"{duration}-day itinerary for {brief.destination} is ready.",
        detail="Building itinerary",
        updates={"itinerary": artifact},
    )


def _revise(state: AgentState, instructions: str) -> AgentResult:
    if not state.itinerary:
        return _build(state, instructions)
    brief = state.brief
    current = state.itinerary.data
    duration = brief.resolved_duration_days()
    travel = _travel_context(state)
    system = """
You are a travel itinerary editor.
Update ONLY what the instructions ask for.
Preserve day count, locations, and structure unless asked to change them.
Honor SELECTED TRAVEL times when adjusting Day 1 or the last day.
Return the full updated itinerary as structured JSON.
""".strip()
    user = (
        f"Instructions:\n{instructions or 'Revise for updated preferences.'}\n\n"
        f"Brief: {brief.model_dump()}\n\n"
        f"{travel}\n\n"
        f"Current itinerary:\n{current}"
    )
    try:
        result = planning_llm().with_structured_output(Itinerary).invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=user),
            ]
        )
    except Exception as exc:
        log_exception(
            logger,
            "itinerary revise failed",
            exc,
            context={"instructions": (instructions or "")[:120]},
        )
        return AgentResult(
            status="failed",
            summary=f"Could not revise itinerary: {exc}",
            detail="Updating itinerary",
            error=type(exc).__name__,
        )

    problems = _validate(result, duration)
    if problems:
        logger.info("itinerary revise validation: %s", problems)

    artifact = make_artifact("itinerary", brief, result)
    return AgentResult(
        status="ok",
        summary=result.summary or "Itinerary updated.",
        detail="Updating itinerary",
        updates={"itinerary": artifact},
    )


def run_itinerary(call: dict[str, Any], state: AgentState) -> AgentResult:
    args = call.get("args") or {}
    mode = (args.get("mode") or "build").lower()
    instructions = args.get("instructions") or ""
    if mode == "revise" or (state.itinerary and state.itinerary.flagged and mode != "build"):
        return _revise(state, instructions)
    if state.itinerary and state.itinerary.matches(state.brief) and not args.get("refresh"):
        if not instructions:
            return AgentResult(status="skipped", summary="Itinerary already available.")
        return _revise(state, instructions)
    return _build(state, instructions)
