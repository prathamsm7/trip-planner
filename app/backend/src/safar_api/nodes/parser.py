import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import StructuredTravelExtract
from safar_api.models.state import TravelState
from safar_api.nodes.follow_up_fields import apply_follow_up_to_structured
from safar_api.nodes.search_plan import search_plan_from_extract, strip_search_plan_fields
from safar_api.services.llm import secondary_llm

_parser_llm = secondary_llm().with_structured_output(
    StructuredTravelExtract,
    method="function_calling",
)

_SEARCH_PLAN_PROMPT = """
Also decide which web searches are needed before building the itinerary:
- run_transport: false if source and destination are the same place (day trip / already there).
- run_activities: false for pure business trips with no leisure interest; true if user wants sightseeing, food, culture, etc.
- run_weather: usually same as run_activities; false when activities search is skipped.
- transport_query: a detailed web search string for transport options (flights, trains, distance, airports) when run_transport is true.
- activities_query: a detailed web search string for things to do, attractions, and local experiences when run_activities is true.
Tailor query strings to the user's trip style, dates, preferences, and destination.
"""


def parser_node(state: TravelState) -> dict:
    today = datetime.date.today().isoformat()

    latest_message = state.messages[-1]
    prompt = f"""
                Today's date: {today}

                Extract structured travel information from the user query below.
                Be precise about dates: if only month names are given, infer the most likely year.
                Extract: sourceLocation, destinationLocation, date_range, budget, travel_style,
                mode_of_transport, duration (from trip length if mentioned), number_of_people,
                preferences, accomodation_type.

                For number_of_people: infer from context — "couple" means 2, "solo" means 1,
                "family" means at least 3 unless specified, "friends" means at least 2.
                If the user explicitly states a number, use that.

                Leave any field the user did NOT mention as null (budget, travel_style, mode_of_transport)
                or empty string (sourceLocation, destinationLocation). Do not guess defaults.
                For date_range leave null if dates were not given.

                {_SEARCH_PLAN_PROMPT}
                """

    parser_result = _parser_llm.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=latest_message.content),
        ]
    )

    raw = parser_result.model_dump()
    structured = apply_follow_up_to_structured(strip_search_plan_fields(raw))
    out: dict = {"structured": structured}
    if structured.get("is_follow_up"):
        out["follow_up_index"] = 0
        out["follow_up_answers"] = {}
    else:
        out["search_plan"] = search_plan_from_extract(raw, structured)

    return out


def followup_route(state: TravelState) -> str:
    structured = state.structured or {}
    if structured.get("is_follow_up"):
        return "follow_up_questions"
    return "web_queries"
