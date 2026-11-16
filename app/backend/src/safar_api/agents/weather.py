"""Weather agent — Tavily search, then extract a structured outlook."""

from __future__ import annotations

import logging
from typing import Any

from safar_api.agents.base import AgentResult
from safar_api.services.weather_client import get_weather_outlook
from safar_api.trip.results import WeatherOutlook, make_artifact
from safar_api.trip.state import AgentState

logger = logging.getLogger(__name__)



def run_weather(call: dict[str, Any], state: AgentState) -> AgentResult:
    brief = state.brief
    if not brief.destination:
        return AgentResult(status="failed", summary="Missing destination.", error="missing_fields")
    if not brief.has_exact_dates() and not brief.month:
        return AgentResult(
            status="failed",
            summary="Need dates or a month for weather.",
            error="missing_fields",
        )

    args = call.get("args") or {}
    refresh = bool(args.get("refresh"))
    if state.weather and state.weather.matches(brief) and not refresh:
        return AgentResult(
            status="skipped",
            summary="Weather outlook already available.",
            detail="Weather ready",
        )

    raw = get_weather_outlook(
        brief.destination,
        start_date=brief.start_date,
        end_date=brief.end_date,
        month=brief.month,
    )
    logger.info(
        "weather outlook | requested=%r resolved=%r source=%s days=%s",
        brief.destination,
        raw.get("destination"),
        raw.get("source"),
        len(raw.get("days") or []),
    )

    outlook = WeatherOutlook.model_validate(raw)
    if not outlook.days and outlook.source == "unknown":
        return AgentResult(
            status="failed",
            summary=outlook.summary or "Weather lookup failed.",
            detail=f"Weather for {brief.destination}",
            error="provider_error",
        )

    artifact = make_artifact("weather", brief, outlook)
    return AgentResult(
        status="ok",
        summary=outlook.summary,
        detail=f"Weather for {brief.destination}",
        updates={"weather": artifact},
    )
