import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from safar_api.models.schemas import FlightSearchOutput
from safar_api.models.state import TravelState
from safar_api.services.llm import flight_llm
from safar_api.services.serpapi_client import flight_search_api, hotel_search_api

logger = logging.getLogger(__name__)

_flight_llm = flight_llm().with_structured_output(FlightSearchOutput)

_IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")


def _is_valid_iata(code: str | None) -> bool:
    """A real IATA airport code is exactly 3 uppercase letters."""
    return bool(code and _IATA_CODE_RE.match(code.strip().upper()))


def _build_flight_alternatives(search_data: dict, dest: str) -> dict:
    """Build alternative travel suggestions when no direct flights are found."""
    other_airports = search_data.get("other_airports") or []
    railway_stations = search_data.get("nearest_railway_station") or []

    alternatives: dict = {"nearby_airports": [], "railway_stations": [], "suggestions": []}

    for ap in other_airports:
        alternatives["nearby_airports"].append({
            "name": ap.get("name", ""),
            "code": ap.get("code", ""),
            "location": ap.get("location", ""),
        })

    for rs in railway_stations:
        alternatives["railway_stations"].append({
            "name": rs.get("name", ""),
            "code": rs.get("code", ""),
            "location": rs.get("location", ""),
        })

    if other_airports:
        names = ", ".join(f"{a.get('name', '')} ({a.get('code', '')})" for a in other_airports[:3])
        alternatives["suggestions"].append(f"Fly to a nearby airport: {names}, then take local transport.")

    if railway_stations:
        names = ", ".join(f"{r.get('name', '')} ({r.get('code', '')})" for r in railway_stations[:3])
        alternatives["suggestions"].append(f"Take a train to: {names}.")

    alternatives["suggestions"].append(
        f"Consider a bus or self-drive road trip to {dest}."
    )

    return alternatives


def _flight_alternatives_message(dest: str, alternatives: dict, reason: str = "no_results") -> str:
    intros = {
        "no_results": f"No direct flights found to {dest} for your dates.",
        "no_airport": f"{dest} doesn't seem to have a direct airport.",
        "invalid_codes": f"I couldn't identify a valid airport for {dest}.",
        "api_error": f"Flight search is temporarily unavailable for {dest}.",
    }
    lines = [intros.get(reason, intros["no_results"]) + " Here are some alternatives:\n"]
    for suggestion in alternatives.get("suggestions", []):
        lines.append(f"• {suggestion}")
    if alternatives.get("nearby_airports") or alternatives.get("railway_stations"):
        lines.append(
            "\nIf you'd like, I can search flights to one of the nearby airports — just tell me which one."
        )
    else:
        lines.append(
            "\nYou can try modifying the trip to a nearby city that has an airport, "
            "or switch the mode of transport to train, bus, or car."
        )
    return "\n".join(lines)


def _empty_flights_payload(search_data: dict, alternatives: dict) -> dict:
    return {
        "best_flights": [],
        "other_flights": [],
        "airports": [],
        "airport_meta": search_data,
        "alternatives": alternatives,
    }


def flight_search_node(state: TravelState) -> dict:
    structured = state.structured or {}
    if not structured:
        raise ValueError(
            "Please share your trip details (destination and dates) first, then I will search for flights."
        )

    outbound_date = structured.get("date_range", {}).get("start", "")
    return_date = structured.get("date_range", {}).get("end", "")
    number_of_people = structured.get("number_of_people", 1)
    dest = structured.get("destinationLocation", "your destination")

    if not outbound_date or not return_date:
        raise ValueError(
            "I need your trip start and end dates before searching flights. "
            "Please include dates in your trip plan, then ask again."
        )

    if not state.transport_results:
        alternatives = {
            "nearby_airports": [],
            "railway_stations": [],
            "suggestions": [
                f"Plan the trip first so I can look up airports near {dest}.",
                "Or try a train, bus, or self-drive road trip.",
            ],
        }
        return {
            "flights_data": _empty_flights_payload({}, alternatives),
            "messages": [
                AIMessage(content=_flight_alternatives_message(dest, alternatives, "invalid_codes"))
            ],
        }

    try:
        result = _flight_llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Extract airport information from the web search result. "
                        "Return ONLY valid 3-letter IATA airport codes (e.g. BOM, GOI, DEL). "
                        "If a city has no airport, leave its code empty and list nearby airports "
                        "in other_airports and railway stations in nearest_railway_station. "
                        "Return JSON only."
                    )
                ),
                HumanMessage(content=f"web search result:\n{state.transport_results}"),
            ]
        )
        search_data = result.model_dump()
    except Exception as exc:
        logger.warning("flight LLM extraction failed: %s", exc)
        search_data = {
            "departure_airport_code": "",
            "arrival_airport_code": "",
            "other_airports": [],
            "nearest_railway_station": [],
        }

    dep_code = (search_data.get("departure_airport_code") or "").strip().upper()
    arr_code = (search_data.get("arrival_airport_code") or "").strip().upper()

    if not _is_valid_iata(dep_code) or not _is_valid_iata(arr_code):
        alternatives = _build_flight_alternatives(search_data, dest)
        reason = "no_airport" if not _is_valid_iata(arr_code) else "invalid_codes"
        return {
            "flights_data": _empty_flights_payload(search_data, alternatives),
            "messages": [AIMessage(content=_flight_alternatives_message(dest, alternatives, reason))],
        }

    try:
        api_data = flight_search_api(
            outbound_date,
            return_date,
            dep_code,
            arr_code,
            number_of_people,
        )
    except Exception as exc:
        logger.warning("flight_search_api failed for %s->%s: %s", dep_code, arr_code, exc)
        alternatives = _build_flight_alternatives(search_data, dest)
        return {
            "flights_data": _empty_flights_payload(search_data, alternatives),
            "messages": [
                AIMessage(content=_flight_alternatives_message(dest, alternatives, "api_error"))
            ],
        }

    best = api_data.get("best_flights") or []
    other = api_data.get("other_flights") or []

    out: dict = {
        "flights_data": {
            "best_flights": best,
            "other_flights": other,
            "airports": api_data.get("airports") or [],
            "airport_meta": search_data,
        }
    }

    if not best and not other:
        alternatives = _build_flight_alternatives(search_data, dest)
        out["flights_data"]["alternatives"] = alternatives
        out["messages"] = [
            AIMessage(content=_flight_alternatives_message(dest, alternatives, "no_results"))
        ]

    return out


def _hotel_alternatives_message(dest: str, accom_type: str) -> str:
    return (
        f"No {accom_type}s found in {dest} for your selected dates. "
        f"Here are some suggestions:\n\n"
        f"• Try broadening your search — ask me to search for a different accommodation type "
        f"(hotel, guesthouse, airbnb, or homestay).\n"
        f"• Adjust your travel dates — availability may vary by season.\n"
        f"• Search for stays in a nearby town and commute to {dest}.\n\n"
        f"Would you like me to try a different search?"
    )


def hotel_search_node(state: TravelState) -> dict:
    s = state.structured or {}
    if not s.get("destinationLocation"):
        raise ValueError("Please plan your trip with a destination first, then search for hotels.")

    start = s.get("date_range", {}).get("start", "")
    end = s.get("date_range", {}).get("end", "")
    if not start or not end:
        raise ValueError("I need check-in and check-out dates before searching hotels.")

    dest = s.get("destinationLocation", "your destination")
    accom_type = s.get("accomodation_type", "hotel")

    result = hotel_search_api(
        dest,
        start,
        end,
        s.get("budget", "medium"),
        s.get("number_of_people", 1),
        accom_type,
        s.get("travel_style", "family"),
    )

    out: dict = {"hotel_search_results": result}
    if not result:
        out["messages"] = [AIMessage(content=_hotel_alternatives_message(dest, accom_type))]

    return out
