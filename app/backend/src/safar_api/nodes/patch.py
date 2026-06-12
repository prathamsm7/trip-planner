import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from safar_api.models.state import TravelState
from safar_api.services.llm import secondary_llm


def patch_itinerary(state: TravelState) -> dict:
    """Apply day-level or wording tweaks without re-running searches."""
    itinerary = state.itinerary
    if not itinerary:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I don't have an itinerary to update yet. "
                        "Tell me where you'd like to go and I'll build a plan."
                    )
                )
            ]
        }

    query = state.messages[-1].content
    system_prompt = """
You are a travel itinerary editor.
Update ONLY what the user asked to change in the existing itinerary.
Preserve day count, locations, and structure unless the user explicitly asks to change them.
Return the full updated itinerary as valid JSON with the same schema:
{ "summary": "...", "days": [ { "day": 1, "location": "...", "plan": [ { "morning": [], "afternoon": [], "evening": [] } ] } ] }
"""

    response = secondary_llm().invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    f"User request:\n{query}\n\n"
                    f"Current itinerary:\n{json.dumps(itinerary, default=str)}"
                )
            ),
        ]
    )

    content = response.content or ""
    try:
        updated = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            updated = json.loads(content[start : end + 1])
        else:
            return {
                "messages": [
                    AIMessage(
                        content="I couldn't apply that change cleanly. Could you rephrase what you'd like updated?"
                    )
                ]
            }

    return {
        "itinerary": updated,
        "messages": [AIMessage(content="I've updated your itinerary with those changes.")],
    }
