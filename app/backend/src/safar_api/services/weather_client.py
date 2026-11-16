"""Weather via Tavily search + a short structured extract."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.config import settings
from safar_api.logging_config import log_exception
from safar_api.services.llm import utility_llm
from safar_api.trip.results import WeatherOutlook

logger = logging.getLogger(__name__)

_TAVILY_SEARCH = "https://api.tavily.com/search"

_EXTRACT_SYSTEM = """
Extract a weather outlook from the search answer.
Use only facts in the answer. Do not invent temperatures or conditions.
Set destination to the requested place.
Fill days when the answer has day-by-day detail; otherwise leave days empty and put the outlook in summary.
source is "forecast" for a date-specific forecast, "climatology" for typical/seasonal weather, "unknown" if the answer has no usable weather.
""".strip()


def _weather_query(destination: str, start_date: str, end_date: str, month: str) -> str:
    place = (destination or "").strip()
    if start_date and end_date:
        return f"weather forecast for {place} from {start_date} to {end_date}"
    if month:
        return f"typical weather in {place} during {month}"
    return f"weather forecast for {place}"


def tavily_search(query: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Call Tavily search and return the JSON body (includes `answer`)."""
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            _TAVILY_SEARCH,
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": 5,
            },
        )
        response.raise_for_status()
        return response.json()


def _evidence(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    answer = (payload.get("answer") or "").strip()
    if answer:
        parts.append(f"Answer:\n{answer}")
    for item in (payload.get("results") or [])[:5]:
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        if title or content:
            parts.append(f"{title}\n{content}".strip())
    return "\n\n".join(parts)


def get_weather_outlook(
    destination: str,
    start_date: str = "",
    end_date: str = "",
    month: str = "",
) -> dict[str, Any]:
    """Search Tavily for the place/dates and extract a WeatherOutlook."""
    query = _weather_query(destination, start_date, end_date, month)
    try:
        payload = tavily_search(query)
    except Exception as exc:
        log_exception(logger, "tavily weather search failed", exc, context={"query": query})
        return {
            "destination": destination,
            "summary": f"Weather lookup failed for {destination}.",
            "days": [],
            "source": "unknown",
        }

    evidence = _evidence(payload)
    if not evidence.strip():
        return {
            "destination": destination,
            "summary": f"No weather results for {destination}.",
            "days": [],
            "source": "unknown",
        }

    try:
        outlook = utility_llm().with_structured_output(WeatherOutlook).invoke(
            [
                SystemMessage(content=_EXTRACT_SYSTEM),
                HumanMessage(
                    content=(
                        f"Place: {destination}\n"
                        f"Dates: {start_date or '?'} to {end_date or '?'}\n"
                        f"Month: {month or 'n/a'}\n"
                        f"Query: {query}\n\n"
                        f"{evidence[:8000]}"
                    )
                ),
            ]
        )
    except Exception as exc:
        log_exception(logger, "weather extract failed", exc, context={"query": query})
        answer = (payload.get("answer") or "").strip()
        return {
            "destination": destination,
            "summary": answer or f"Could not extract weather for {destination}.",
            "days": [],
            "source": "unknown",
        }

    data = outlook.model_dump()
    if not data.get("destination"):
        data["destination"] = destination
    return data
