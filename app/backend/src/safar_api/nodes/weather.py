from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import WeatherOutlook
from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm, weather_llm

_weather_llm = weather_llm().with_structured_output(WeatherOutlook)
_about_llm = secondary_llm()


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

    outlook = _weather_llm.invoke(
        [
            SystemMessage(
                content=(
                    "Extract a weather outlook for the trip from the travel search text. "
                    "Infer daily conditions for each day of the trip if exact dates are unclear. "
                    "Return structured JSON only."
                )
            ),
            HumanMessage(
                content=f"Destination: {dest}\nTrip structured: {state.structured}\n\nSearch text:\n{text[:12000]}"
            ),
        ]
    )
    about = ""
    if text.strip():
        resp = _about_llm.invoke(
            [
                SystemMessage(
                    content=(
                        f"Write a 2-3 paragraph 'About {dest}' overview for a trip planner UI. "
                        "Use only facts from the provided search text. Be concise and helpful."
                    )
                ),
                HumanMessage(content=text[:8000]),
            ]
        )
        about = resp.content or ""

    return {"weather": outlook.model_dump(), "destination_about": about}
