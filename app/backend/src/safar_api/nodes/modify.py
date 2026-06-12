from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import UpdateStructuredTravel
from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm

_MODIFY_SCOPE_PROMPT = """
Also set modify_scope — how aggressively the system should update the trip:
- patch: user only wants itinerary wording/day-level tweaks (e.g. "make Day 2 more relaxed"); structured trip fields unchanged or irrelevant.
- replan: budget, travel style, people, preferences, duration, or accommodation changed — rebuild itinerary but existing web research may still apply.
- re_search: source, destination, dates, or transport mode changed — full research pipeline must run again.
If no itinerary exists yet, use re_search.
"""


def modify_itinerary(state: TravelState) -> dict:
    query = state.messages[-1].content
    old_structured = dict(state.structured or {})
    has_itinerary = bool(state.itinerary)

    system_prompt = f"""
    You are a senior travel operations planner.
    Your job is to modify the structured data based on the user query and the data provided.
    Only update the structured data if the user ask to update it, otherwise return the same structured data.
    Dont update full structured data only update the data that is asked by the user.

    Trip planned (itinerary exists): {has_itinerary}

    Strictly return the structured data in json format only.
    Exsisting Structured Data: \n
    {state.structured}

    {_MODIFY_SCOPE_PROMPT}
    """

    result = secondary_llm().with_structured_output(UpdateStructuredTravel).invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query),
        ]
    )

    raw = result.model_dump()
    scope = raw.pop("modify_scope", "patch")
    merged = {**old_structured, **raw}

    out: dict = {
        "structured": merged,
        "modify_scope": scope,
        "flights_data": {},
        "hotel_search_results": None,
        "selections": {},
    }

    if scope == "re_search":
        out.update(
            {
                "transport_results": None,
                "activities_results": None,
                "weather": None,
                "destination_about": "",
                "search_plan": None,
            }
        )

    return out


def modify_route(state: TravelState) -> str:
    return state.modify_scope or "patch"
