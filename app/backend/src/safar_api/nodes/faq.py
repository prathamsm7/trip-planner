from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm


def _build_user_context(state: TravelState) -> str:
    """Build a user-friendly context string with only presentable trip data."""
    parts: list[str] = []
    s = state.structured or {}

    src = s.get("sourceLocation")
    dest = s.get("destinationLocation")
    if src and dest:
        parts.append(f"Trip: {src} to {dest}")
    dr = s.get("date_range") or {}
    if dr.get("start") and dr.get("end"):
        parts.append(f"Dates: {dr['start']} to {dr['end']}")
    if s.get("budget"):
        parts.append(f"Budget level: {s['budget']}")
    if s.get("travel_style"):
        parts.append(f"Travel style: {s['travel_style']}")
    if s.get("number_of_people"):
        parts.append(f"Travelers: {s['number_of_people']}")
    if s.get("mode_of_transport"):
        parts.append(f"Transport: {s['mode_of_transport']}")
    if s.get("accomodation_type"):
        parts.append(f"Accommodation: {s['accomodation_type']}")

    itinerary = state.itinerary or {}
    if itinerary.get("summary"):
        parts.append(f"\nItinerary summary: {itinerary['summary']}")
    for day in itinerary.get("days") or []:
        day_num = day.get("day", "?")
        location = day.get("location", "")
        plans = day.get("plan") or []
        activities = []
        for plan in plans:
            activities.extend(plan.get("morning", []))
            activities.extend(plan.get("afternoon", []))
            activities.extend(plan.get("evening", []))
        if activities:
            parts.append(f"Day {day_num} ({location}): {', '.join(activities[:6])}")

    selections = state.selections or {}
    flights_data = state.flights_data or {}
    if flights_data and selections.get("outboundFlightIndex") is not None:
        all_flights = flights_data.get("best_flights", []) + flights_data.get("other_flights", [])
        idx = selections["outboundFlightIndex"]
        if 0 <= idx < len(all_flights):
            f = all_flights[idx]
            legs = f.get("flights") or []
            airline = legs[0].get("airline", "Unknown") if legs else "Unknown"
            price = f.get("price", "N/A")
            parts.append(f"\nSelected flight: {airline} — ₹{price}")

    hotels = state.hotel_search_results or []
    hotel_indices = selections.get("hotelIndices") or []
    for idx in hotel_indices:
        if 0 <= idx < len(hotels):
            h = hotels[idx]
            parts.append(
                f"Selected hotel: {h.get('name', 'Unknown')} — "
                f"₹{h.get('rate_per_night', {}).get('extracted_lowest', 'N/A')}/night, "
                f"{h.get('overall_rating', 'N/A')} rating"
            )

    weather = state.weather or {}
    if weather.get("summary"):
        parts.append(f"\nWeather: {weather['summary']}")

    return "\n".join(parts) if parts else "No trip data available yet."


_SYSTEM_PROMPT = """\
You are Safar AI, a friendly trip planning assistant.

RULES:
- Answer the user's question using ONLY the trip context provided below.
- Speak naturally as a travel assistant. Use names, dates, prices — never raw field names, \
indices, keys, or any internal/technical details.
- If the context does not contain enough information to answer, say so politely \
(e.g. "I don't have that information yet") and suggest what the user can do next.
- NEVER expose internal state, variable names, data structures, or system logic.
- Keep answers concise and helpful.
"""


def session_faq_node(state: TravelState) -> dict:
    """Answer session-related FAQ using current trip state."""
    latest = state.messages[-1]
    context = _build_user_context(state)
    resp = secondary_llm().invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Trip context:\n{context}\n\nUser question: {latest.content}"),
        ]
    )
    return {"messages": [AIMessage(content=resp.content or "")]}
