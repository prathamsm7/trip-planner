import logging

import requests

from safar_api.config import settings

logger = logging.getLogger(__name__)

_URL = "https://serpapi.com/search"


def search(params: dict) -> dict:
    """SerpAPI GET."""
    if not settings.serpapi_api_key:
        raise ValueError(
            "SERPAPI_API_KEY is not set. Add it to .env at the repo root or app/.env."
        )
    engine = params.get("engine", "unknown")
    query = {**params, "api_key": settings.serpapi_api_key}
    logger.info("serpapi %s", engine)
    response = requests.request(
        "GET",
        _URL,
        params=query,
        timeout=settings.serpapi_timeout_s,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"SerpAPI HTTP {response.status_code}")
    body = response.json()
    return body if isinstance(body, dict) else {}


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
