import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import StructuredTravelExtract
from safar_api.models.state import TravelState
from safar_api.nodes.follow_up_fields import apply_follow_up_to_structured
from safar_api.services.llm import secondary_llm

_parser_llm = secondary_llm().with_structured_output(
    StructuredTravelExtract,
    method="function_calling",
)


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
                """

    parser_result = _parser_llm.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=latest_message.content),
        ]
    )

    structured = apply_follow_up_to_structured(parser_result.model_dump())
    out: dict = {"structured": structured}
    if structured.get("is_follow_up"):
        out["follow_up_index"] = 0
        out["follow_up_answers"] = {}
    return out


def followup_route(state: TravelState) -> str:
    structured = state.structured or {}
    if structured.get("is_follow_up"):
        return "follow_up_questions"
    return "web_queries"
