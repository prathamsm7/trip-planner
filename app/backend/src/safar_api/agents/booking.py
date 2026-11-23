"""Booking agent — flights and stays search with bounded retries."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.agents.base import AgentResult
from safar_api.logging_config import log_exception
from safar_api.models.schemas import FlightSearchOutput
from safar_api.services.llm import utility_llm
from safar_api.services.serpapi_client import (
    search_ai_overview,
    search_hotels,
    search_one_way_flights,
)
from safar_api.services.text import clean_text
from safar_api.trip.results import (
    FlightLegBundle,
    FlightsResult,
    StayShortlistItem,
    StaysResult,
    make_artifact,
)
from safar_api.trip.brief import TripUpdate, apply_trip_update
from safar_api.trip.state import AgentState

logger = logging.getLogger(__name__)


def _merge_search_fields(brief, **fields: str | None):
    """Copy destination/dates passed on a search tool into the brief."""
    payload = {
        key: value.strip()
        for key, value in fields.items()
        if isinstance(value, str) and value.strip()
    }
    if not payload:
        return brief, False
    updated, changed = apply_trip_update(brief, TripUpdate(**payload))
    return updated, bool(changed)
_IATA = re.compile(r"^[A-Z]{3}$")

_AIRPORT_EXTRACT_SYSTEM = (
    "Split the airports in the web search result by the city they serve. "
    "Use IATA codes only (for example BOM, SDW, GOX). "
    "origin_airports are airports for the origin city. Put the main one first, then alternatives "
    "that also serve that same city. "
    "destination_airports are airports for reaching the destination city. Put the closest main "
    "airport first, then alternatives used to reach that destination. "
    "An airport that serves the origin must not appear in destination_airports. "
    "Each item needs name, code, and location. Leave code empty when the result has no IATA code."
)


def _valid_iata(code: str | None) -> bool:
    if not code:
        return False
    return bool(_IATA.match(code.strip().upper()))


def _normalize_arg_code(value: str | None) -> str:
    """Keep a tool argument only when it is already an IATA code."""
    raw = (value or "").strip().upper()
    return raw if _valid_iata(raw) else ""


def _airport_search_query(origin: str, destination: str) -> str:
    src = (origin or "departure city").strip()
    dest = (destination or "destination city").strip()
    return (
        f"Airports with IATA codes serving {src} and {dest}. "
        f"Main airport and nearby alternative airports for {src}. "
        f"Main airport and nearby alternative airports for {dest}."
    )


def _serp_evidence(raw: dict) -> str:
    """Text the airport extractor reads from a SerpAPI response."""
    for key in ("reconstructed_markdown", "text", "answer", "markdown"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:12000]
    blocks = raw.get("text_blocks")
    if isinstance(blocks, list):
        parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict):
                snippet = block.get("snippet") or block.get("text") or block.get("answer")
                if snippet:
                    parts.append(str(snippet))
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "\n".join(parts)[:12000]
    return clean_text(str(raw))[:12000]


def _airport_entry(item: dict, *, side: str) -> dict | None:
    code = (item.get("code") or "").strip().upper()
    if not _valid_iata(code):
        return None
    return {
        "name": item.get("name") or "",
        "code": code,
        "location": item.get("location") or "",
        "kind": "primary" if side.endswith("primary") else "nearby",
        "side": "origin" if side.startswith("origin") else "destination",
    }


def _airport_choices(items: list, *, side: str) -> list[dict]:
    choices: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        entry = _airport_entry(item, side=f"{side}-primary" if index == 0 else side)
        if entry and entry["code"] not in seen:
            seen.add(entry["code"])
            choices.append(entry)
    return choices


def _extract_airports_from_serp(origin: str, destination: str) -> tuple[str, str, list[dict]]:
    """Search SerpAPI for airports, then utility_llm extracts the list."""
    query = _airport_search_query(origin, destination)
    logger.info("airport search | origin=%r destination=%r query=%r", origin, destination, query)
    try:
        evidence = _serp_evidence(search_ai_overview(query))
    except Exception as exc:
        log_exception(
            logger,
            "airport SerpAPI lookup failed",
            exc,
            context={"origin": origin, "destination": destination, "query": query[:160]},
        )
        return "", "", []
    if not evidence.strip():
        log_exception(
            logger,
            "airport SerpAPI returned empty evidence",
            context={"origin": origin, "destination": destination, "query": query[:160]},
        )
        return "", "", []

    try:
        result = utility_llm().with_structured_output(FlightSearchOutput).invoke(
            [
                SystemMessage(content=_AIRPORT_EXTRACT_SYSTEM),
                HumanMessage(
                    content=(
                        f"Origin city: {origin}\n"
                        f"Destination city: {destination}\n\n"
                        f"web search result:\n{evidence}"
                    )
                ),
            ]
        )
        data = result.model_dump()
    except Exception as exc:
        log_exception(
            logger,
            "airport extract LLM failed",
            exc,
            context={"origin": origin, "destination": destination},
        )
        return "", "", []

    origin = _airport_choices(data.get("origin_airports") or [], side="origin")
    destination = _airport_choices(data.get("destination_airports") or [], side="destination")
    # A code cannot be both the arrival airport and an origin-city airport.
    origin_codes = {entry["code"] for entry in origin}
    destination = [entry for entry in destination if entry["code"] not in origin_codes]
    dep = origin[0]["code"] if origin else ""
    arr = destination[0]["code"] if destination else ""
    nearby = origin[1:] + destination[1:]
    logger.info(
        "airport list | dep=%r arr=%r origin_alts=%s destination_alts=%s",
        dep,
        arr,
        [entry["code"] for entry in origin[1:]],
        [entry["code"] for entry in destination[1:]],
    )
    return dep, arr, nearby


def _resolve_airports(state: AgentState, args: dict) -> tuple[str, str, list[dict]]:
    """Use named IATA codes when the user gave both. Otherwise Serp plus the small model."""
    dep = _normalize_arg_code(args.get("departure_airport") or args.get("dep_id"))
    arr = _normalize_arg_code(args.get("arrival_airport") or args.get("arr_id"))
    if dep and arr:
        logger.info("resolve_airports using named codes | dep=%r arr=%r", dep, arr)
        return dep, arr, []

    found_dep, found_arr, nearby = _extract_airports_from_serp(
        state.brief.origin,
        state.brief.destination,
    )
    return dep or found_dep, arr or found_arr, nearby


def _nearby_airport_entries(nearby: list[dict], *, exclude: set[str] | None = None) -> list[dict]:
    exclude = exclude or set()
    out: list[dict] = []
    seen: set[str] = set()
    for ap in nearby:
        if not isinstance(ap, dict):
            continue
        code = (ap.get("code") or "").upper()
        if not _valid_iata(code) or code in exclude or code in seen:
            continue
        seen.add(code)
        out.append(
            {
                "name": ap.get("name") or "",
                "code": code,
                "location": ap.get("location") or "",
                "kind": ap.get("kind") or "nearby",
                "side": ap.get("side") or "destination",
            }
        )
    return out


def _airport_labels(entries: list[dict]) -> str:
    return ", ".join(
        f"{entry['code']}" + (f" ({entry['name']})" if entry.get("name") else "")
        for entry in entries[:5]
    )


def _ask_for_another_airport(origin: str, destination: str, dep: str, arr: str, nearby: list[dict]) -> tuple[str, dict]:
    """Tell the user this pair has no flights and list other airports they can choose."""
    others = _nearby_airport_entries(nearby, exclude={code for code in (dep, arr) if code})
    if _valid_iata(dep) and _valid_iata(arr):
        summary = f"No flights found for {dep} → {arr}."
    else:
        summary = f"I could not identify airports for {origin} → {destination}."
    if others:
        summary += f" Other airports: {_airport_labels(others)}. Tell me which one to search."
    else:
        summary += " Tell me another city or the IATA codes to search."
    return summary, {"nearby_airports": others, "suggestions": [summary], "ask_user": True}


def _flight_leg_has_results(bundle: Any) -> bool:
    if not isinstance(bundle, dict):
        return False
    return bool(bundle.get("best_flights") or bundle.get("other_flights"))


def _flights_not_found(
    state: AgentState,
    brief,
    dep: str,
    arr: str,
    legs: set[str],
    summary: str,
    alternatives: dict,
    error: str,
    dates_saved: bool = False,
) -> AgentResult:
    saved = _keep_unsearched_flight_legs(
        state,
        FlightsResult(
            airport_meta={"departure_airport_code": dep, "arrival_airport_code": arr},
            alternatives=alternatives,
        ),
        legs,
    )
    return AgentResult(
        status="failed",
        summary=summary,
        detail="Searching flights",
        error=error,
        updates={"flights": make_artifact("flights", brief, saved), **({"brief": brief} if dates_saved else {})},
    )


def _keep_unsearched_flight_legs(state: AgentState, result: FlightsResult, legs: set[str]) -> FlightsResult:
    """Write only the direction this call searched. Leave the other direction in place."""
    previous = state.flights.data if state.flights and isinstance(state.flights.data, dict) else {}
    if "outbound" not in legs and isinstance(previous.get("outbound"), dict):
        result.outbound = FlightLegBundle.model_validate(previous["outbound"])
    if "return" not in legs and isinstance(previous.get("return_flights"), dict):
        result.return_flights = FlightLegBundle.model_validate(previous["return_flights"])
    return result


def find_flights(call: dict[str, Any], state: AgentState) -> AgentResult:
    args = call.get("args") or {}
    asked_start = (args.get("start_date") or "").strip()
    asked_end = (args.get("end_date") or "").strip()
    # The agent passes end_date only for a return. A saved trip end date does not.
    legs = {"return"} if asked_end else set()
    if asked_start or not asked_end:
        legs.add("outbound")
    brief, dates_saved = _merge_search_fields(
        state.brief,
        start_date=asked_start or None,
        end_date=asked_end or None,
    )

    start = asked_start or (brief.start_date or "")
    end = asked_end
    if not brief.origin or not brief.destination:
        return AgentResult(
            status="failed",
            summary="Need an origin and a destination for flights.",
            error="missing_fields",
        )
    if "outbound" in legs and not start:
        return AgentResult(
            status="failed",
            summary="Need a departure date to search outbound flights.",
            error="missing_fields",
        )
    if "return" in legs and not end:
        return AgentResult(
            status="failed",
            summary="Need a return date to search return flights.",
            error="missing_fields",
        )

    arg_dep = _normalize_arg_code(args.get("departure_airport") or args.get("dep_id"))
    arg_arr = _normalize_arg_code(args.get("arrival_airport") or args.get("arr_id"))
    user_override = bool(arg_dep or arg_arr)
    # User-selected airports always re-search, even if a prior flights artifact matches.
    if (
        state.flights
        and state.flights.matches(brief)
        and not args.get("refresh")
        and not user_override
    ):
        saved = state.flights.data if isinstance(state.flights.data, dict) else {}
        outbound_ready = "outbound" not in legs or _flight_leg_has_results(saved.get("outbound"))
        return_ready = "return" not in legs or _flight_leg_has_results(saved.get("return_flights"))
        if outbound_ready and return_ready:
            return AgentResult(status="skipped", summary="Flight results already available.")

    dep, arr, nearby = _resolve_airports(state, args)
    if arg_dep:
        dep = arg_dep
    if arg_arr:
        arr = arg_arr
    summary, alternatives = _ask_for_another_airport(brief.origin, brief.destination, dep, arr, nearby)
    if not (_valid_iata(dep) and _valid_iata(arr)):
        return _flights_not_found(state, brief, dep, arr, legs, summary, alternatives, "no_airport", dates_saved)

    logger.info("flight search | %s→%s (%s)", dep, arr, "+".join(sorted(legs)))
    outbound_bundle: dict = {}
    return_bundle: dict = {}
    airports: list = []
    try:
        if "outbound" in legs:
            outbound_bundle = search_one_way_flights(start, dep, arr, brief.travellers)
            airports.extend(outbound_bundle.get("airports") or [])
        if "return" in legs:
            return_bundle = search_one_way_flights(end, arr, dep, brief.travellers)
            airports.extend(return_bundle.get("airports") or [])
    except Exception as exc:
        log_exception(
            logger,
            "flight search failed",
            exc,
            context={"dep": dep, "arr": arr, "start": start, "end": end},
        )
        return _flights_not_found(
            state,
            brief,
            dep,
            arr,
            legs,
            f"Flight search failed for {dep} → {arr}. Tell me another airport to try.",
            alternatives,
            type(exc).__name__,
            dates_saved,
        )

    def _count(bundle: dict) -> int:
        return len(bundle.get("best_flights") or []) + len(bundle.get("other_flights") or [])

    outbound_count = _count(outbound_bundle) if "outbound" in legs else 0
    return_count = _count(return_bundle) if "return" in legs else 0
    result = _keep_unsearched_flight_legs(
        state,
        FlightsResult(
            outbound=FlightLegBundle(
                best_flights=outbound_bundle.get("best_flights") or [],
                other_flights=outbound_bundle.get("other_flights") or [],
            ),
            return_flights=FlightLegBundle(
                best_flights=return_bundle.get("best_flights") or [],
                other_flights=return_bundle.get("other_flights") or [],
            ),
            airports=airports,
            airport_meta={"departure_airport_code": dep, "arrival_airport_code": arr},
        ),
        legs,
    )
    if outbound_count or return_count:
        parts = []
        if "outbound" in legs:
            parts.append(f"{outbound_count} outbound ({dep}→{arr})")
        if "return" in legs:
            parts.append(f"{return_count} return ({arr}→{dep})")
        return AgentResult(
            status="ok",
            summary=f"Found {' and '.join(parts)} flights.",
            detail=f"Searching flights {dep} to {arr}",
            updates={"flights": make_artifact("flights", brief, result), **({"brief": brief} if dates_saved else {})},
        )
    return _flights_not_found(state, brief, dep, arr, legs, summary, alternatives, "no_results", dates_saved)


def _stay_shortlist(properties: list[dict]) -> list[StayShortlistItem]:
    items: list[StayShortlistItem] = []
    if not properties:
        return items
    priced = []
    for i, p in enumerate(properties):
        rate = (p.get("rate_per_night") or {}).get("extracted_lowest")
        if rate is not None:
            priced.append((i, p, float(rate)))
    if priced:
        i, p, price = min(priced, key=lambda x: x[2])
        items.append(
            StayShortlistItem(
                label="cheapest",
                name=p.get("name") or "",
                price=price,
                rating=p.get("overall_rating"),
                reason="Lowest nightly rate",
                index=i,
            )
        )
    rated = [
        (i, p)
        for i, p in enumerate(properties)
        if p.get("overall_rating") is not None
    ]
    if rated:
        i, p = max(rated, key=lambda x: x[1].get("overall_rating") or 0)
        items.append(
            StayShortlistItem(
                label="top_rated",
                name=p.get("name") or "",
                price=(p.get("rate_per_night") or {}).get("extracted_lowest"),
                rating=p.get("overall_rating"),
                reason="Highest rating",
                index=i,
            )
        )
    return items[:3]


def find_stays(call: dict[str, Any], state: AgentState) -> AgentResult:
    args = call.get("args") or {}
    brief, brief_saved = _merge_search_fields(
        state.brief,
        destination=args.get("destination"),
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
    )
    start = brief.start_date
    end = brief.end_date
    dest = brief.destination
    if not (dest and start and end):
        missing = [
            name
            for name, value in (
                ("destination", dest),
                ("start_date", start),
                ("end_date", end),
            )
            if not value
        ]
        return AgentResult(
            status="failed",
            summary=(
                f"Missing {', '.join(missing)} for stays. "
                "Call update_trip with those fields, then search_stays once. Do not retry yet."
            ),
            error="missing_fields",
        )

    if state.stays and state.stays.matches(brief) and not args.get("refresh"):
        return AgentResult(status="skipped", summary="Stay results already available.")

    stay_type = args.get("stay_type") or brief.stay_type
    budget = args.get("budget") or brief.budget
    area = (args.get("area") or "").strip()
    query = f"{dest} {area}".strip()

    attempts = [
        (stay_type, budget),
        ("hotel", budget),
        (stay_type, "medium" if budget != "medium" else "high"),
    ]
    last_error = ""
    for stay_type_try, budget_try in attempts[:3]:
        try:
            props = search_hotels(
                query,
                start,
                end,
                budget_try,
                brief.travellers,
                stay_type_try,
                brief.style,
            )
            if props:
                result = StaysResult(properties=props, shortlist=_stay_shortlist(props))
                artifact = make_artifact("stays", brief, result)
                return AgentResult(
                    status="ok",
                    summary=(
                        f"Found {len(props)} stays in {dest}. "
                        f"Shortlist: {', '.join(s.label for s in result.shortlist) or 'n/a'}."
                    ),
                    detail=f"Searching stays in {dest}",
                    updates={"stays": artifact, **({"brief": brief} if brief_saved else {})},
                )
            last_error = "no_results"
        except Exception as exc:
            last_error = type(exc).__name__
            log_exception(
                logger,
                "hotel search failed",
                exc,
                context={
                    "dest": dest,
                    "stay_type": stay_type_try,
                    "budget": budget_try,
                    "start": start,
                    "end": end,
                },
            )

    empty = StaysResult(properties=[])
    return AgentResult(
        status="failed",
        summary=f"No stays found in {dest} for your dates.",
        detail=f"Searching stays in {dest}",
        error=last_error or "no_results",
        updates={
            "stays": make_artifact("stays", brief, empty),
            **({"brief": brief} if brief_saved else {}),
        },
    )

