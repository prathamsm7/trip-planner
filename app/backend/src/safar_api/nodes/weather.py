from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import WeatherExtract
from safar_api.models.state import TravelState
from safar_api.services.llm import weather_llm

_weather_llm = weather_llm().with_structured_output(WeatherExtract)


def extract_weather_node(state: TravelState) -> dict:
    activities = state.activities_results or {}
    text = ""
    if isinstance(activities, dict):
        text = str(activities.get("reconstructed_markdown") or "")
    else:
        text = str(activities)

    dest = (state.structured or {}).get("destinationLocation", "destination")
    if not text.strip():
        return {"weather": None}

    result = _weather_llm.invoke(
        [
            SystemMessage(
                content=(
                    "From the travel search text, extract:\n"
                    "1. A weather outlook for the trip (infer daily conditions per trip day "
                    "when exact dates are unclear).\n"
                    f"2. A 2-3 paragraph 'About {dest}' destination overview for the UI.\n"
                    "Use only facts from the search text. Return structured JSON only."
                )
            ),
            HumanMessage(
                content=f"Destination: {dest}\nTrip structured: {state.structured}\n\nSearch text:\n{text[:12000]}"
            ),
        ]
    )
    data = result.model_dump()
    weather = {
        "destination": data["destination"],
        "summary": data["summary"],
        "days": data["days"],
    }
    return {"weather": weather, "destination_about": data.get("destination_about", "")}
