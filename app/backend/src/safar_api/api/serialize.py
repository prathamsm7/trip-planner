from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def message_to_dict(msg: BaseMessage) -> dict[str, Any]:
    role = "assistant"
    if isinstance(msg, HumanMessage):
        role = "user"
    elif isinstance(msg, AIMessage):
        role = "assistant"
    return {
        "role": role,
        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
        "id": getattr(msg, "id", None),
    }


def state_to_snapshot(values: dict[str, Any]) -> dict[str, Any]:
    messages = values.get("messages") or []
    return {
        "structured": values.get("structured"),
        "follow_up_answers": values.get("follow_up_answers"),
        "weather": values.get("weather"),
        "destination_about": values.get("destination_about"),
        "itinerary": values.get("itinerary"),
        "transport_results": values.get("transport_results"),
        "activities_results": values.get("activities_results"),
        "user_current_intent": values.get("user_current_intent"),
        "hotel_search_results": values.get("hotel_search_results"),
        "flights_data": values.get("flights_data"),
        "selections": values.get("selections"),
        "messages": [message_to_dict(m) for m in messages],
    }


def patch_for_node(node: str, update: dict[str, Any] | None) -> dict[str, Any]:
    """Extract UI-relevant payload from a node update."""
    if not update:
        return {}
    keys = {
        "parser": ["structured"],
        "follow_up_questions": ["follow_up_answers", "follow_up_index"],
        "merge_follow_up_structured": ["structured", "follow_up_answers", "follow_up_index"],
        "web_queries": [],
        "transport_search": ["transport_results"],
        "activities_search": ["activities_results"],
        "extract_weather": ["weather", "destination_about"],
        "planner": ["itinerary"],
        "flight_search": ["flights_data"],
        "hotel_search": ["hotel_search_results"],
        "modify_itinerary": ["structured"],
        "extract_user_intent": ["user_current_intent"],
        "session_faq": ["messages"],
    }
    allowed = keys.get(node, list(update.keys()))
    return {k: update[k] for k in allowed if k in update}
