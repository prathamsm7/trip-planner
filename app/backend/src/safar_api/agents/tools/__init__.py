"""Agent tools, one file per feature. Trains share a file because station lookup and train search are one flow."""

from safar_api.agents.tools.flights import search_flights
from safar_api.agents.tools.itinerary import build_itinerary
from safar_api.agents.tools.questions import answer_trip_question
from safar_api.agents.tools.research import research_destination
from safar_api.agents.tools.selections import select_options
from safar_api.agents.tools.stays import search_stays
from safar_api.agents.tools.support import TOOL_LABELS
from safar_api.agents.tools.trains import search_railway_stations, search_trains
from safar_api.agents.tools.trip import update_trip
from safar_api.agents.tools.weather import get_weather
from safar_api.agents.tools.web import web_search

SUPERVISOR_TOOLS = [
    update_trip,
    research_destination,
    get_weather,
    search_flights,
    search_railway_stations,
    search_trains,
    search_stays,
    select_options,
    answer_trip_question,
    web_search,
    build_itinerary,
]

__all__ = ["SUPERVISOR_TOOLS", "TOOL_LABELS"]
