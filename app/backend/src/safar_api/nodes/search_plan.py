"""Build search plans from LLM parser output, with rule-based fallback."""

from __future__ import annotations

import re
from typing import Any

from safar_api.services.text import ACTIVITIES_BUNDLE, TRANSPORT_BUNDLE

SEARCH_PLAN_KEYS = (
    "run_transport",
    "run_activities",
    "run_weather",
    "transport_query",
    "activities_query",
)

_ACTIVITY_HINTS = (
    "sightseeing",
    "activities",
    "things to do",
    "museum",
    "beach",
    "hiking",
    "food",
    "culture",
    "adventure",
    "nature",
    "shopping",
    "nightlife",
)


def _normalize_location(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.lower().strip())


def _same_location(source: str | None, destination: str | None) -> bool:
    src = _normalize_location(source)
    dest = _normalize_location(destination)
    return bool(src and dest and src == dest)


def _has_activity_interest(structured: dict[str, Any]) -> bool:
    prefs = " ".join(structured.get("preferences") or []).lower()
    other = str(structured.get("other_details") or "").lower()
    blob = f"{prefs} {other}"
    return any(hint in blob for hint in _ACTIVITY_HINTS)


def strip_search_plan_fields(extract: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in extract.items() if k not in SEARCH_PLAN_KEYS}


def search_plan_from_extract(
    extract: dict[str, Any],
    structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a search_plan dict from LLM parser/merge output."""
    s = structured or extract
    source = s.get("sourceLocation", "")
    destination = s.get("destinationLocation", "")
    style = s.get("travel_style", "family")
    month = s.get("month", "")
    season = s.get("season", "")
    preferences = ", ".join(s.get("preferences") or [])

    run_transport = bool(extract.get("run_transport", True))
    run_activities = bool(extract.get("run_activities", True))
    run_weather = bool(extract.get("run_weather", run_activities))

    same_place = _same_location(source, destination)
    skip_reasons: dict[str, str | None] = {
        "transport": None,
        "activities": None,
        "weather": None,
    }

    if same_place and run_transport:
        run_transport = False
        skip_reasons["transport"] = "same_location"

    if not destination:
        run_transport = False
        run_activities = False
        run_weather = False

    queries: dict[str, str] = {}
    if run_transport:
        queries["transport"] = (extract.get("transport_query") or "").strip() or TRANSPORT_BUNDLE.format(
            source=source or "departure city",
            destination=destination,
        ).strip()
    else:
        skip_reasons["transport"] = skip_reasons["transport"] or "llm_skipped"

    if run_activities:
        queries["activities"] = (extract.get("activities_query") or "").strip() or ACTIVITIES_BUNDLE.format(
            source=source or "departure city",
            destination=destination,
            style=style,
            month=month,
            season=season,
        ).strip()
        if preferences and preferences not in queries["activities"]:
            queries["activities"] = f"{queries['activities']}\n{preferences} experiences in {destination}"
    else:
        skip_reasons["activities"] = "llm_skipped"
        run_weather = False

    if not run_weather:
        skip_reasons["weather"] = "no_activities_search" if not run_activities else "llm_skipped"

    return {
        "run_transport": run_transport,
        "run_activities": run_activities,
        "run_weather": run_weather,
        "queries": queries,
        "skip_reasons": skip_reasons,
        "source": "llm",
    }


def compute_search_plan(structured: dict[str, Any] | None) -> dict[str, Any]:
    """Rule-based fallback when no LLM search plan is available (e.g. modify re_search)."""
    s = structured or {}
    source = s.get("sourceLocation", "")
    destination = s.get("destinationLocation", "")
    style = s.get("travel_style", "family")
    month = s.get("month", "")
    season = s.get("season", "")
    preferences = ", ".join(s.get("preferences") or [])

    same_place = _same_location(source, destination)
    run_transport = bool(destination) and not same_place
    run_activities = bool(destination) and (
        style != "business" or _has_activity_interest(s)
    )
    run_weather = run_activities

    queries: dict[str, str] = {}
    if run_transport:
        queries["transport"] = TRANSPORT_BUNDLE.format(
            source=source or "departure city",
            destination=destination,
        ).strip()
    if run_activities:
        base = ACTIVITIES_BUNDLE.format(
            source=source or "departure city",
            destination=destination,
            style=style,
            month=month,
            season=season,
        ).strip()
        if preferences:
            base = f"{base}\n{preferences} experiences in {destination}"
        queries["activities"] = base

    return {
        "run_transport": run_transport,
        "run_activities": run_activities,
        "run_weather": run_weather,
        "queries": queries,
        "skip_reasons": {
            "transport": "same_location" if same_place else None,
            "activities": "business_trip" if not run_activities and destination else None,
            "weather": "no_activities_search" if not run_weather else None,
        },
        "source": "rules",
    }
