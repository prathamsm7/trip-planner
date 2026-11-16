import logging
import time

import httpx

from safar_api.config import settings
from safar_api.logging_config import log_exception

logger = logging.getLogger(__name__)


def search(params: dict) -> dict:
    """SerpAPI GET with one retry on timeout or a server error."""
    if not settings.serpapi_api_key:
        raise ValueError(
            "SERPAPI_API_KEY is not set. Add it to .env at the repo root or app/.env."
        )
    engine = params.get("engine", "unknown")
    query = {**params, "api_key": settings.serpapi_api_key}
    timeout_s = settings.serpapi_timeout_s
    attempts = 2
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.get("https://serpapi.com/search", params=query)
                if response.status_code >= 500 and attempt < attempts - 1:
                    logger.warning(
                        "serpapi %s HTTP %s on attempt %s/%s — retrying",
                        engine,
                        response.status_code,
                        attempt + 1,
                        attempts,
                    )
                    time.sleep(0.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json()
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            log_exception(
                logger,
                "serpapi request failed",
                exc,
                context={
                    "engine": engine,
                    "attempt": attempt + 1,
                    "attempts": attempts,
                    "timeout_s": timeout_s,
                    "q": str(params.get("q") or params.get("departure_id") or "")[:80],
                },
            )
            if attempt < attempts - 1 and not isinstance(exc, httpx.HTTPStatusError):
                time.sleep(0.5 * (attempt + 1))
                continue
            if (
                attempt < attempts - 1
                and isinstance(exc, httpx.HTTPStatusError)
                and exc.response is not None
                and exc.response.status_code >= 500
            ):
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("serpapi search failed")


def search_ai_overview(query: str) -> dict:
    """Google AI Mode answer for destination research and open travel questions."""
    return search(
        {
            "engine": "google_ai_mode",
            "q": query,
            "hl": "en",
            "gl": "in",
        }
    )


def search_one_way_flights(
    outbound_date: str,
    departure_airport: str,
    arrival_airport: str,
    travellers: int,
) -> dict:
    """Google Flights one-way search (type=2)."""
    results = search(
        {
            "engine": "google_flights",
            "hl": "en",
            "gl": "in",
            "type": 2,
            "departure_id": departure_airport,
            "arrival_id": arrival_airport,
            "outbound_date": outbound_date,
            "currency": "INR",
            "adults": travellers,
            "children": 0,
            "deep_search": "true",
        }
    )
    return {
        "best_flights": results.get("best_flights", []),
        "other_flights": results.get("other_flights", []),
        "airports": results.get("airports", []),
    }


def search_round_trip_flights(
    outbound_date: str,
    return_date: str,
    departure_airport: str,
    arrival_airport: str,
    travellers: int,
) -> dict:
    """Two one-way searches so outbound and return can be chosen separately."""
    outbound = search_one_way_flights(
        outbound_date, departure_airport, arrival_airport, travellers
    )
    return_leg = search_one_way_flights(
        return_date, arrival_airport, departure_airport, travellers
    )
    outbound_best = outbound.get("best_flights") or []
    outbound_other = outbound.get("other_flights") or []
    return_best = return_leg.get("best_flights") or []
    return_other = return_leg.get("other_flights") or []
    airports = list(outbound.get("airports") or []) + list(return_leg.get("airports") or [])
    return {
        "outbound": {
            "best_flights": outbound_best,
            "other_flights": outbound_other,
        },
        "return": {
            "best_flights": return_best,
            "other_flights": return_other,
        },
        "airports": airports,
    }


def search_hotels(
    query: str,
    check_in: str,
    check_out: str,
    budget: str,
    travellers: int,
    stay_type: str,
    travel_style: str,
) -> list[dict]:
    """Google Hotels properties for the stay window."""
    hotel_query = f"{query} {stay_type} {budget} budget for {travel_style}"
    results = search(
        {
            "engine": "google_hotels",
            "q": hotel_query,
            "hl": "en",
            "gl": "in",
            "check_in_date": check_in,
            "check_out_date": check_out,
            "currency": "INR",
            "no_cache": "true",
            "adults": travellers,
            "children": 0,
        }
    )
    return results.get("properties", [])
