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
    search_round_trip_flights,
)
from safar_api.services.text import clean_text
from safar_api.trip.results import (
    FlightLegBundle,
    FlightShortlistItem,
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
    "Extract the airport list from the web search result. "
    "Use IATA codes only (for example BOM, GOI, DEL). "
    "departure_airport_code and departure_airport_name are the main airport for the origin city. "
    "arrival_airport_code and arrival_airport_name are the main airport for the destination city. "
    "Put every other airport from the search in other_airports, each with name, code, and location. "
    "Leave a code empty when the search result does not name one. Return JSON only."
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


def _airport_entry(item: dict) -> dict | None:
    code = (item.get("code") or "").strip().upper()
    if not _valid_iata(code):
        return None
    return {
        "name": item.get("name") or "",
        "code": code,
        "location": item.get("location") or "",
        "kind": "nearby",
    }


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

    dep = (data.get("departure_airport_code") or "").strip().upper()
    arr = (data.get("arrival_airport_code") or "").strip().upper()
    if not _valid_iata(dep):
        dep = ""
    if not _valid_iata(arr):
        arr = ""
    nearby: list[dict] = []
    seen = {code for code in (dep, arr) if code}
    for item in data.get("other_airports") or []:
        if not isinstance(item, dict):
            continue
        entry = _airport_entry(item)
        if entry and entry["code"] not in seen:
            seen.add(entry["code"])
            nearby.append(entry)
    logger.info(
        "airport list | dep=%r arr=%r nearby=%s",
        dep,
        arr,
        [entry["code"] for entry in nearby],
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


def _flight_shortlist(best: list[dict], other: list[dict]) -> list[FlightShortlistItem]:
    all_flights = list(best) + list(other)
    items: list[FlightShortlistItem] = []
    if not all_flights:
        return items
    # Cheapest
    priced = [(i, f) for i, f in enumerate(all_flights) if f.get("price") is not None]
    if priced:
        i, f = min(priced, key=lambda x: x[1].get("price") or 1e18)
        items.append(
            FlightShortlistItem(
                label="cheapest",
                price=float(f.get("price")),
                reason="Lowest price",
                index=i,
            )
        )
    # Fastest
    timed = [(i, f) for i, f in enumerate(all_flights) if f.get("total_duration") is not None]
    if timed:
        i, f = min(timed, key=lambda x: x[1].get("total_duration") or 1e18)
        items.append(
            FlightShortlistItem(
                label="fastest",
                price=float(f["price"]) if f.get("price") is not None else None,
                reason="Shortest duration",
                index=i,
            )
        )
    return items[:3]


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
            }
        )
    return out


def _build_flight_candidates(
    dep: str,
    arr: str,
    nearby: list[dict],
    *,
    user_locked: bool,
) -> list[tuple[str, str]]:
    """Ordered routes to try. User-specified pair is exclusive; otherwise try nearby alts."""
    candidates: list[tuple[str, str]] = []
    if _valid_iata(dep) and _valid_iata(arr):
        candidates.append((dep, arr))
    if user_locked:
        return candidates

    for ap in _nearby_airport_entries(nearby, exclude={dep, arr}):
        code = ap["code"]
        # Prefer alternate arrival airports near the destination.
        route = (dep, code)
        if _valid_iata(dep) and route not in candidates:
            candidates.append(route)
    return candidates[:5]


def _flight_ask_user_summary(
    *,
    origin: str,
    destination: str,
    reason: str,
    primary: tuple[str, str] | None,
    tried: list[tuple[str, str]],
    nearby: list[dict],
) -> str:
    nearby_entries = _nearby_airport_entries(
        nearby,
        exclude={primary[0], primary[1]} if primary else set(),
    )
    tried_txt = ", ".join(f"{a}→{b}" for a, b in tried) or "none"
    if reason == "no_airport":
        lines = [
            f"I could not identify airports for {origin} → {destination}.",
            "Please share a nearby city with an airport, or specific IATA codes "
            "(e.g. departure BOM, arrival GOI or GOX).",
        ]
    else:
        primary_txt = f"{primary[0]}→{primary[1]}" if primary else "the primary airports"
        lines = [
            f"No flights found for {origin} → {destination} "
            f"(tried {tried_txt}; primary {primary_txt}).",
        ]
        if nearby_entries:
            labels = ", ".join(
                f"{a['code']}" + (f" ({a['name']})" if a.get("name") else "")
                for a in nearby_entries[:5]
            )
            lines.append(
                f"Other airports nearby: {labels}. "
                "Tell me which airport to use and I will search again."
            )
        else:
            lines.append(
                "Please suggest an alternative destination city or specific airport "
                "IATA codes, and I will search flights for that option."
            )
    return " ".join(lines)


def _flight_alternatives_payload(
    nearby: list[dict],
    *,
    tried: list[tuple[str, str]],
    primary: tuple[str, str] | None,
    reason: str,
    destination: str,
) -> dict[str, Any]:
    nearby_entries = _nearby_airport_entries(nearby)
    suggestions: list[str] = []
    if nearby_entries:
        labels = ", ".join(
            f"{a.get('name') or a['code']} ({a['code']})" for a in nearby_entries[:4]
        )
        suggestions.append(f"Try a nearby airport: {labels}.")
    suggestions.append(
        f"Pick a different destination city near {destination} that has flight service."
    )
    suggestions.append("Or share exact IATA codes for departure and arrival airports.")
    return {
        "nearby_airports": nearby_entries,
        "tried_routes": [{"dep": a, "arr": b} for a, b in tried],
        "primary_route": (
            {"dep": primary[0], "arr": primary[1]} if primary else None
        ),
        "reason": reason,
        "suggestions": suggestions,
        "ask_user": True,
    }


def _search_flights(call: dict[str, Any], state: AgentState) -> AgentResult:
    args = call.get("args") or {}
    brief, dates_saved = _merge_search_fields(
        state.brief,
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
    )
    start = brief.start_date
    end = brief.end_date
    if not (brief.origin and brief.destination and start and end):
        return AgentResult(
            status="failed",
            summary="Need origin, destination, and dates for flights.",
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
        return AgentResult(status="skipped", summary="Flight results already available.")

    dep, arr, nearby = _resolve_airports(state, args)
    # If the user locked one side, keep Serp/research fill for the other side only.
    if arg_dep:
        dep = arg_dep
    if arg_arr:
        arr = arg_arr
    user_locked = bool(arg_dep and arg_arr)

    candidates = _build_flight_candidates(dep, arr, nearby, user_locked=user_locked)
    primary = (dep, arr) if _valid_iata(dep) and _valid_iata(arr) else None
    logger.info(
        "flight candidates | user_locked=%s primary=%s routes=%s nearby=%s",
        user_locked,
        primary,
        candidates,
        [a.get("code") for a in nearby[:5] if isinstance(a, dict)],
    )

    if not candidates:
        summary = _flight_ask_user_summary(
            origin=brief.origin,
            destination=brief.destination,
            reason="no_airport",
            primary=None,
            tried=[],
            nearby=nearby,
        )
        return AgentResult(
            status="failed",
            summary=summary,
            detail="Searching flights",
            error="no_airport",
            updates={
                "flights": make_artifact(
                    "flights",
                    brief,
                    FlightsResult(
                        airport_meta={
                            "departure_airport_code": dep,
                            "arrival_airport_code": arr,
                        },
                        alternatives=_flight_alternatives_payload(
                            nearby,
                            tried=[],
                            primary=None,
                            reason="no_airport",
                            destination=brief.destination,
                        ),
                    ),
                )
            },
        )

    last_error = ""
    tried: list[tuple[str, str]] = []
    for dep_id, arr_id in candidates:
        tried.append((dep_id, arr_id))
        try:
            logger.info("flight search attempt | %s→%s (outbound+return)", dep_id, arr_id)
            flight_results = search_round_trip_flights(
                start, end, dep_id, arr_id, brief.travellers
            )
            outbound_bundle = flight_results.get("outbound") or {}
            return_bundle = flight_results.get("return") or {}
            outbound_best = outbound_bundle.get("best_flights") or []
            outbound_other = outbound_bundle.get("other_flights") or []
            return_best = return_bundle.get("best_flights") or []
            return_other = return_bundle.get("other_flights") or []
            outbound_shortlist = _flight_shortlist(outbound_best, outbound_other)
            return_shortlist = _flight_shortlist(return_best, return_other)
            outbound = FlightLegBundle(
                best_flights=outbound_best,
                other_flights=outbound_other,
                shortlist=outbound_shortlist,
            )
            return_flights = FlightLegBundle(
                best_flights=return_best,
                other_flights=return_other,
                shortlist=return_shortlist,
            )
            result = FlightsResult(
                outbound=outbound,
                return_flights=return_flights,
                airports=flight_results.get("airports") or [],
                airport_meta={
                    "departure_airport_code": dep_id,
                    "arrival_airport_code": arr_id,
                },
                alternatives={
                    "nearby_airports": _nearby_airport_entries(
                        nearby, exclude={dep_id, arr_id}
                    ),
                    "tried_routes": [{"dep": a, "arr": b} for a, b in tried],
                },
            )
            outbound_count = len(outbound_best) + len(outbound_other)
            return_count = len(return_best) + len(return_other)
            # Accept if either leg has options; UI still shows both sections.
            if outbound_count or return_count:
                used_alternate = primary is not None and (dep_id, arr_id) != primary
                artifact = make_artifact("flights", brief, result)
                note = (
                    f" Primary {primary[0]}→{primary[1]} had no flights; "
                    f"showing alternate {dep_id}→{arr_id}."
                    if used_alternate and primary
                    else ""
                )
                missing = []
                if not outbound_count:
                    missing.append("outbound")
                if not return_count:
                    missing.append("return")
                miss_note = (
                    f" No {(' or '.join(missing))} options found."
                    if missing
                    else ""
                )
                return AgentResult(
                    status="ok" if (outbound_count and return_count) else "partial",
                    summary=(
                        f"Found {outbound_count} outbound ({dep_id}→{arr_id}) and "
                        f"{return_count} return ({arr_id}→{dep_id}) flights."
                        f"{note}{miss_note} "
                        f"Outbound shortlist: "
                        f"{', '.join(s.label for s in outbound_shortlist) or 'n/a'}; "
                        f"return shortlist: "
                        f"{', '.join(s.label for s in return_shortlist) or 'n/a'}."
                    ).strip(),
                    detail=f"Searching flights {dep_id} to {arr_id}",
                    updates={"flights": artifact, **({"brief": brief} if dates_saved else {})},
                )
            last_error = "no_results"
            logger.info("flight search empty both ways | %s→%s", dep_id, arr_id)
        except Exception as exc:
            last_error = type(exc).__name__
            log_exception(
                logger,
                "flight search failed",
                exc,
                context={"dep": dep_id, "arr": arr_id, "start": start, "end": end},
            )

    summary = _flight_ask_user_summary(
        origin=brief.origin,
        destination=brief.destination,
        reason="no_results",
        primary=primary,
        tried=tried,
        nearby=nearby,
    )
    empty = FlightsResult(
        airport_meta={
            "departure_airport_code": dep,
            "arrival_airport_code": arr,
        },
        alternatives=_flight_alternatives_payload(
            nearby,
            tried=tried,
            primary=primary,
            reason=last_error or "no_results",
            destination=brief.destination,
        ),
    )
    return AgentResult(
        status="failed",
        summary=summary,
        detail="Searching flights",
        error=last_error or "no_results",
        updates={"flights": make_artifact("flights", brief, empty)},
    )


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


def _search_stays(call: dict[str, Any], state: AgentState) -> AgentResult:
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


def run_booking(call: dict[str, Any], state: AgentState) -> AgentResult:
    name = call.get("name") or ""
    if name == "search_flights":
        return _search_flights(call, state)
    if name == "search_stays":
        return _search_stays(call, state)
    return AgentResult(status="failed", summary=f"Unknown booking tool: {name}", error="unknown_tool")
