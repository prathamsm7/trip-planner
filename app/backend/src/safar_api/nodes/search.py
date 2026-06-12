from safar_api.models.state import TravelState
from safar_api.nodes.search_plan import compute_search_plan
from safar_api.services.serpapi_client import serpapi_ai_mode
from safar_api.services.text import ACTIVITIES_BUNDLE, TRANSPORT_BUNDLE, clean_text


def _plan(state: TravelState) -> dict:
    return state.search_plan or compute_search_plan(state.structured)


def web_queries(state: TravelState) -> dict:
    if not state.structured:
        return {}
    if state.search_plan:
        return {}
    return {"search_plan": compute_search_plan(state.structured)}


def transport_search_node(state: TravelState) -> dict:
    plan = _plan(state)
    if not plan.get("run_transport"):
        return {"transport_results": None}

    s = state.structured or {}
    source = s.get("sourceLocation", "")
    destination = s.get("destinationLocation", "")
    query = (plan.get("queries") or {}).get("transport") or TRANSPORT_BUNDLE.format(
        source=source,
        destination=destination,
    )
    results = serpapi_ai_mode(query)
    md = clean_text(results.get("reconstructed_markdown", ""))
    return {
        "transport_results": {
            "query": query,
            "reconstructed_markdown": md,
            "skipped": False,
        }
    }


def activities_search_node(state: TravelState) -> dict:
    plan = _plan(state)
    if not plan.get("run_activities"):
        return {"activities_results": None}

    s = state.structured or {}
    source = s.get("sourceLocation", "")
    destination = s.get("destinationLocation", "")
    style = s.get("travel_style", "family")
    month = s.get("month", "")
    season = s.get("season", "")
    query = (plan.get("queries") or {}).get("activities") or ACTIVITIES_BUNDLE.format(
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
            "skipped": False,
        }
    }
