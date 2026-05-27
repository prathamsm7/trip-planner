from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import IntentOutput
from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm

_intent_llm = secondary_llm().with_structured_output(IntentOutput)


def extract_user_intent(state: TravelState) -> dict:
    """Extract user intent from the query"""

    has_itinerary = bool(state.itinerary)
    has_structured = bool(state.structured)

    SYSTEM_PROMPT = f"""
You are a senior conversation classification agent.
Classify the user's message into exactly one intent.

SESSION STATE:
- Trip planned (itinerary exists): {has_itinerary}
- Trip details collected: {has_structured}

INTENT DEFINITIONS — pick the BEST match:
- plan_trip: User wants to plan a NEW trip from scratch (e.g. "plan a trip to Goa").
  Do NOT pick this if a trip already exists and the user is just asking about it.
- modify_itinerary: User wants to CHANGE an existing planned trip (e.g. "change destination to Kerala", "add one more day").
- flight_search: User explicitly asks to search/find flights.
- book_hotel: User explicitly asks to search/find hotels or accommodation.
- get_info: User asks a QUESTION about the current trip, its details, budget, weather,
  itinerary, or anything that can be answered from existing session data.
  If a trip is already planned and the user asks about budget, cost, dates, places, etc., use this.
- For greetings, off-topic prompts, or casual conversation, use get_info so the app stays
  focused on session and travel context.

IMPORTANT: If a trip is already planned and the user asks about it (budget, details, summary, etc.),
classify as "get_info", NOT "plan_trip".
"""

    latest_message = state.messages[-1]

    result = _intent_llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=latest_message.content),
        ]
    )

    intent = result.model_dump().get("intent")

    return {"user_current_intent": intent}


def intent_route(state: TravelState) -> str:
    return state.user_current_intent or "get_info"
