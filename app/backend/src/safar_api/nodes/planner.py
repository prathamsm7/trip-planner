import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import ItineraryOutput
from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm

_planner_llm = secondary_llm().with_structured_output(ItineraryOutput)


def planner_node(state: TravelState) -> dict:
    s = state.structured or {}
    source = s.get("sourceLocation", "")
    destination = s.get("destinationLocation", "")
    start = (s.get("date_range") or {}).get("start", "")
    end = (s.get("date_range") or {}).get("end", "")
    budget = s.get("budget", "medium")
    style = s.get("travel_style", "family")
    people = s.get("number_of_people", 1)
    transport_mode = s.get("mode_of_transport", "flight")
    preferences = ", ".join(s.get("preferences") or []) or "none"
    other_details = s.get("other_details", "")
    follow_up_answers = state.follow_up_answers or (s.get("follow_up_answers") or {})
    weather = state.weather

    duration = (s.get("duration") or {}).get("max_days")
    if not duration and start and end:
        try:
            start_dt = datetime.date.fromisoformat(start)
            end_dt = datetime.date.fromisoformat(end)
            duration = max(1, (end_dt - start_dt).days + 1)
        except Exception:
            duration = 5
    duration = duration or 5

    transport_data = state.transport_results or {}
    activities_data = state.activities_results or {}
    transport_text = (
        str(transport_data.get("reconstructed_markdown") or transport_data)
        if isinstance(transport_data, dict)
        else str(transport_data)
    )
    activities_text = (
        str(activities_data.get("reconstructed_markdown") or activities_data)
        if isinstance(activities_data, dict)
        else str(activities_data)
    )

    evidence_block = f"""
Transport:
{transport_text}

Activities:
{activities_text}
"""

    system_prompt = f"""
You are a senior travel operations planner.
Create a REALISTIC, EXECUTABLE, WEATHER-AWARE, GEOGRAPHICALLY EFFICIENT itinerary.

FROM: {source}
TO: {destination}
DATES: {start} to {end}
TOTAL DAYS: {duration}
TRAVELERS: {people}
STYLE: {style}
BUDGET: {budget}
TRANSPORT: {transport_mode}
PREFERENCES: {preferences}
OTHER: {other_details}
FOLLOW-UP ANSWERS: {follow_up_answers}
WEATHER: {weather}

WEB EVIDENCE:
{evidence_block}

Generate EXACTLY {duration} days with morning/afternoon/evening each.
Return structured JSON matching itinerary schema.
"""

    result = _planner_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content="Create the complete itinerary now."),
        ]
    )
    return {"itinerary": result.model_dump()}
