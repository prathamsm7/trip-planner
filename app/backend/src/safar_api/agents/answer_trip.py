"""Answer questions from saved trip state. The formatted checkpoint is the only context."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.agents.selections import flight_catalog_block, selections_prompt_block
from safar_api.logging_config import log_exception
from safar_api.services.llm import planning_llm

logger = logging.getLogger(__name__)

_QA_SYSTEM = """\
Answer the user's question using ONLY the trip context below.
The trip context is the saved trip. Do not invent flights, hotels, weather, or activities.
If something is missing, say it is not saved.
If they ask about a day, include that day's morning, afternoon, and evening when listed.
Speak naturally with names, dates, and prices. Do not mention internal field names.
Do not tell them to check another section instead of answering.
""".strip()


def _data(state: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    raw = state.get(name)
    if not isinstance(raw, dict):
        return {}, "missing"
    status = "stale" if raw.get("flagged") else "ready"
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    return data, status


def _section(title: str, body: str) -> str:
    return f"{title}\n{body.strip() or '(none)'}"


def _itinerary_text(data: dict[str, Any]) -> str:
    lines: list[str] = []
    if data.get("summary"):
        lines.append(str(data["summary"]).strip())
    for day in data.get("days") or []:
        if not isinstance(day, dict):
            continue
        loc = (day.get("location") or "").strip()
        header = f"Day {day.get('day', '?')}"
        if loc:
            header += f" ({loc})"
        lines.append(header)
        plans = day.get("plan") or []
        if isinstance(plans, dict):
            plans = [plans]
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            for slot in ("morning", "afternoon", "evening"):
                items = [str(x).strip() for x in (plan.get(slot) or []) if str(x).strip()]
                lines.append(f"  {slot}: {'; '.join(items) if items else '(open)'}")
    return "\n".join(lines)


def _stays_text(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for i, prop in enumerate(data.get("properties") or []):
        if not isinstance(prop, dict):
            continue
        rate = prop.get("rate_per_night") or {}
        price = rate.get("extracted_lowest") or rate.get("lowest") or "?"
        lines.append(
            f"#{i} {prop.get('name') or 'Unknown'} — ₹{price}/night, "
            f"rating {prop.get('overall_rating') or '?'}"
        )
    return "\n".join(lines)


def _weather_text(data: dict[str, Any]) -> str:
    lines: list[str] = []
    if data.get("destination"):
        lines.append(str(data["destination"]))
    if data.get("summary"):
        lines.append(str(data["summary"]))
    for day in data.get("days") or []:
        if isinstance(day, dict):
            lines.append(str(day))
    return "\n".join(lines)


def _research_text(data: dict[str, Any]) -> str:
    text = data.get("overview") or data.get("destination_about") or data.get("summary") or ""
    return str(text).strip()[:2500]


def trip_context(state: dict[str, Any]) -> str:
    """One readable view of the saved trip. Same contents every question."""
    brief = state.get("brief")
    if hasattr(brief, "model_dump"):
        brief = brief.model_dump(exclude={"stated"})
    itinerary, itinerary_status = _data(state, "itinerary")
    flights, flights_status = _data(state, "flights")
    stays, stays_status = _data(state, "stays")
    weather, weather_status = _data(state, "weather")
    research, research_status = _data(state, "research")

    sections = [
        _section("Brief", json.dumps(brief or {}, default=str)),
        _section("Selections", selections_prompt_block(state)),
        _section(f"Itinerary ({itinerary_status})", _itinerary_text(itinerary)),
        _section(
            f"Flights ({flights_status})",
            flight_catalog_block(state) if flights else "",
        ),
        _section(f"Stays ({stays_status})", _stays_text(stays)),
        _section(f"Weather ({weather_status})", _weather_text(weather)),
        _section(f"Research ({research_status})", _research_text(research)),
    ]
    return "\n\n".join(sections)


def run_trip_qa(question: str, state: dict[str, Any]) -> str:
    """Answer from trip_context(state). No topic filtering."""
    context = trip_context(state)
    try:
        resp = planning_llm().invoke(
            [
                SystemMessage(content=_QA_SYSTEM),
                HumanMessage(content=f"{context}\n\nQuestion: {question}"),
            ]
        )
        return resp.content or ""
    except Exception as exc:
        log_exception(
            logger,
            "answer_trip_question failed",
            exc,
            context={"question": (question or "")[:120]},
        )
        return f"I could not answer that from the saved trip right now ({type(exc).__name__})."
