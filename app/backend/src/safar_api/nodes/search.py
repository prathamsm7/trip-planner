from safar_api.models.state import TravelState
from safar_api.services.serpapi_client import serpapi_ai_mode
from safar_api.services.text import ACTIVITIES_BUNDLE, TRANSPORT_BUNDLE, clean_text


def web_queries(state: TravelState) -> dict:
    if not state.structured:
        return {}
    return {}


def transport_search_node(state: TravelState) -> dict:
    source = state.structured.get("sourceLocation", "")
    destination = state.structured.get("destinationLocation", "")
    query = TRANSPORT_BUNDLE.format(source=source, destination=destination)
    results = serpapi_ai_mode(query)
    md = clean_text(results.get("reconstructed_markdown", ""))
    return {
        "transport_results": {
            "query": query,
            "reconstructed_markdown": md,
        }
    }


def activities_search_node(state: TravelState) -> dict:
    s = state.structured or {}
    source = s.get("sourceLocation", "")
    destination = s.get("destinationLocation", "")
    style = s.get("travel_style", "family")
    month = s.get("month", "")
    season = s.get("season", "")
    query = ACTIVITIES_BUNDLE.format(
        source=source,
        destination=destination,
        style=style,
        month=month,
        season=season,
    )
    results = serpapi_ai_mode(query)
    md = clean_text(results.get("reconstructed_markdown", ""))
    return {
        "activities_results": {
            "query": query,
            "reconstructed_markdown": md,
        }
    }
