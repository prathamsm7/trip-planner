from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from safar_api.models.state import TravelState
from safar_api.nodes import (
    activities_search_node,
    extract_user_intent,
    extract_weather_node,
    flight_search_node,
    follow_up_questions,
    follow_up_router,
    followup_route,
    guardrail_node,
    guardrail_respond,
    guardrail_route,
    hotel_search_node,
    intent_route,
    merge_follow_up_structured,
    modify_itinerary,
    parser_node,
    planner_node,
    session_faq_node,
    transport_search_node,
    web_queries,
)

_memory = InMemorySaver()
_graph = None

NODE_LABELS: dict[str, str] = {
    "guardrail": "Checking message",
    "guardrail_respond": "Responding",
    "extract_user_intent": "Understanding your request",
    "parser": "Extracting trip details",
    "follow_up_questions": "Need a few more details",
    "merge_follow_up_structured": "Updating trip details",
    "web_queries": "Preparing searches",
    "transport_search": "Finding transport options",
    "activities_search": "Finding activities & weather",
    "extract_weather": "Preparing weather outlook",
    "planner": "Building your itinerary",
    "flight_search": "Searching flights",
    "hotel_search": "Searching hotels",
    "modify_itinerary": "Updating your plan",
    "session_faq": "Answering your question",
}


def compile_graph():
    workflow = StateGraph(TravelState)

    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("guardrail_respond", guardrail_respond)
    workflow.add_node("extract_user_intent", extract_user_intent)
    workflow.add_node("parser", parser_node)
    workflow.add_node("follow_up_questions", follow_up_questions)
    workflow.add_node("merge_follow_up_structured", merge_follow_up_structured)
    workflow.add_node("transport_search", transport_search_node)
    workflow.add_node("activities_search", activities_search_node)
    workflow.add_node("extract_weather", extract_weather_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("web_queries", web_queries)
    workflow.add_node("hotel_search", hotel_search_node)
    workflow.add_node("flight_search", flight_search_node)
    workflow.add_node("modify_itinerary", modify_itinerary)
    workflow.add_node("session_faq", session_faq_node)

    workflow.add_edge(START, "guardrail")
    workflow.add_conditional_edges(
        "guardrail",
        guardrail_route,
        {
            "extract_user_intent": "extract_user_intent",
            "guardrail_respond": "guardrail_respond",
        },
    )
    workflow.add_edge("guardrail_respond", END)
    workflow.add_conditional_edges(
        "extract_user_intent",
        intent_route,
        {
            "plan_trip": "parser",
            "modify_itinerary": "modify_itinerary",
            "flight_search": "flight_search",
            "book_hotel": "hotel_search",
            "get_info": "session_faq",
        },
    )
    workflow.add_edge("modify_itinerary", "web_queries")
    workflow.add_edge("hotel_search", END)
    workflow.add_edge("flight_search", END)
    workflow.add_edge("session_faq", END)

    workflow.add_conditional_edges(
        "parser",
        followup_route,
        {
            "follow_up_questions": "follow_up_questions",
            "web_queries": "web_queries",
        },
    )
    workflow.add_conditional_edges(
        "follow_up_questions",
        follow_up_router,
        {
            "follow_up_questions": "follow_up_questions",
            "merge_follow_up_structured": "merge_follow_up_structured",
        },
    )
    workflow.add_edge("merge_follow_up_structured", "web_queries")
    workflow.add_edge("web_queries", "transport_search")
    workflow.add_edge("web_queries", "activities_search")
    workflow.add_edge("transport_search", "planner")
    workflow.add_edge("activities_search", "extract_weather")
    workflow.add_edge("extract_weather", "planner")
    workflow.add_edge("planner", END)

    return workflow.compile(checkpointer=_memory)


def get_graph():
    global _graph
    if _graph is None:
        _graph = compile_graph()
    return _graph
