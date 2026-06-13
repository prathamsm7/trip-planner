from safar_api.models.state import TravelState
from safar_api.services.serpapi_client import serpapi_ai_mode
from safar_api.services.text import build_search_plan, clean_text


def web_queries(state: TravelState) -> dict:
    if state.search_plan:
        return {}
    return {"search_plan": build_search_plan(state.structured)}


def transport_search_node(state: TravelState) -> dict:
    plan = state.search_plan or build_search_plan(state.structured)
    query = (plan.get("queries") or {}).get("transport", "")
    if not query:
        return {"transport_results": None}

    results = serpapi_ai_mode(query)
    md = clean_text(results.get("reconstructed_markdown", ""))
    return {
        "transport_results": {
            "query": query,
            "reconstructed_markdown": md,
        }
    }


def activities_search_node(state: TravelState) -> dict:
    plan = state.search_plan or build_search_plan(state.structured)
    query = (plan.get("queries") or {}).get("activities", "")
    if not query:
        return {"activities_results": None}

    results = serpapi_ai_mode(query)
    md = clean_text(results.get("reconstructed_markdown", ""))
    return {
        "activities_results": {
            "query": query,
            "reconstructed_markdown": md,
        }
    }
