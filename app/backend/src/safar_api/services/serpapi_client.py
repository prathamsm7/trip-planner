import httpx

from safar_api.config import settings


def _search(params: dict) -> dict:
    if not settings.serpapi_api_key:
        raise ValueError(
            "SERPAPI_API_KEY is not set. Add it to .env at the repo root or app/.env."
        )
    query = {**params, "api_key": settings.serpapi_api_key}
    with httpx.Client(timeout=120.0) as client:
        response = client.get("https://serpapi.com/search", params=query)
        response.raise_for_status()
        return response.json()


def serpapi_ai_mode(query: str) -> dict:
    return _search(
        {
            "engine": "google_ai_mode",
            "q": query,
            "hl": "en",
            "gl": "us",
        }
    )


def flight_search_api(
    outbound_date: str,
    return_date: str,
    dep_id: str,
    arr_id: str,
    number_of_people: int,
) -> dict:
    results = _search(
        {
            "engine": "google_flights",
            "hl": "en",
            "gl": "in",
            "departure_id": dep_id,
            "arrival_id": arr_id,
            "outbound_date": outbound_date,
            "return_date": return_date,
            "currency": "INR",
            "adults": number_of_people,
            "children": 0,
            "deep_search": "true",
        }
    )
    return {
        "best_flights": results.get("best_flights", []),
        "other_flights": results.get("other_flights", []),
        "airports": results.get("airports", []),
    }


def hotel_search_api(
    query: str,
    start_date: str,
    end_date: str,
    budget: str,
    number_of_people: int,
    accomodation_type: str,
    travel_style: str,
) -> list[dict]:
    q = f"{query} {accomodation_type} {budget} budget for {travel_style}"
    results = _search(
        {
            "engine": "google_hotels",
            "q": q,
            "hl": "en",
            "gl": "in",
            "check_in_date": start_date,
            "check_out_date": end_date,
            "currency": "INR",
            "no_cache": "true",
            "adults": number_of_people,
            "children": 0,
        }
    )
    return results.get("properties", [])
