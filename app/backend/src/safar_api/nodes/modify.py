from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import UpdateStructuredTravel
from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm


def modify_itinerary(state: TravelState) -> dict:
    query = state.messages[-1].content

    SYSTEM_PROMPT = f"""
    You are a senior travel operations planner.
    Your job is to modify the structured data based on the user query and the data provided.
    Only update the structured data if the user ask to update it, otherwise return the same structured data.
    Dont update full structured data only update the data that is asked by the user.

    Strictly return the structured data in json format only.
    Exsisting Structured Data: \n
    {state.structured}
    """

    result = secondary_llm().with_structured_output(UpdateStructuredTravel).invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=query),
        ]
    )

    merged = {
        **(state.structured or {}),
        **result.model_dump(),
    }

    return {
        "structured": merged,
        "flights_data": {},
        "hotel_search_results": None,
        "selections": {},
    }
