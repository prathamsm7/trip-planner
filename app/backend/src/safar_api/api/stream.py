import json
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from safar_api.api.serialize import patch_for_node, state_to_snapshot
from safar_api.graph.build import NODE_LABELS, get_graph
from safar_api.nodes.follow_up import conversational_follow_up_message
from safar_api.utils.errors import friendly_error


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _ui_hints(node: str, intent: str | None) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    if node == "planner":
        hints["open_tab"] = "itinerary"
        hints["show_package_card"] = True
    elif node == "modify_itinerary":
        hints["open_tab"] = "itinerary"
    elif node == "flight_search":
        hints["open_tab"] = "flights"
        hints["show_package_card"] = True
    elif node == "hotel_search":
        hints["open_tab"] = "hotels"
        hints["show_package_card"] = True
    elif intent == "plan_trip" and node == "parser":
        hints["open_tab"] = None
    return hints


def _interrupt_sse(thread_id: str, value: dict[str, Any]) -> dict[str, Any]:
    question = value.get("question")
    index = value.get("index", 0)
    total = value.get("total", 1)
    if question:
        message = value.get("message") or conversational_follow_up_message(
            question, index, total
        )
        return {
            "type": "interrupt",
            "interrupt_type": value.get("type", "follow_up"),
            "question": question,
            "index": index,
            "total": total,
            "thread_id": thread_id,
            "message": message,
        }
    questions = value.get("questions", [])
    return {
        "type": "interrupt",
        "interrupt_type": value.get("type"),
        "questions": questions,
        "thread_id": thread_id,
        "message": "I need a few more details:\n"
        + "\n".join(f"- {q}" for q in questions),
    }


async def stream_graph(
    thread_id: str,
    content: str | None = None,
    *,
    resume: bool = False,
) -> AsyncIterator[str]:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    if resume:
        snapshot = graph.get_state(config)
        interrupt = snapshot.interrupts[0] if snapshot.interrupts else None
        if not interrupt or not content:
            yield _sse({"type": "error", "message": friendly_error(ValueError("No interrupt to resume"))})
            return
        graph_input = Command(resume=content.strip())
    else:
        if not content:
            yield _sse({"type": "error", "message": "Please enter a message."})
            return
        graph_input = {"messages": [HumanMessage(content=content)]}

    intent_seen: str | None = None
    interrupt_sent = False

    try:
        async for mode, chunk in graph.astream(
            graph_input,
            config,
            stream_mode=["updates"],
        ):
            if mode != "updates" or not isinstance(chunk, dict):
                continue
            for node, update in chunk.items():
                if isinstance(update, tuple):
                    update = None
                if update is not None and not isinstance(update, dict):
                    continue

                label = NODE_LABELS.get(node, node)
                yield _sse(
                    {
                        "type": "step_start",
                        "node": node,
                        "label": label,
                        "thread_id": thread_id,
                    }
                )
                patch = patch_for_node(node, update)
                if node == "extract_user_intent" and "user_current_intent" in patch:
                    intent_seen = patch["user_current_intent"]
                hints = _ui_hints(node, intent_seen)
                yield _sse(
                    {
                        "type": "step_complete",
                        "node": node,
                        "label": label,
                        "payload": patch,
                        "ui_hints": hints,
                        "thread_id": thread_id,
                    }
                )

                if hints.get("show_package_card"):
                    yield _sse({"type": "package_ready", "thread_id": thread_id})

                _msg_nodes = (
                    "session_faq",
                    "flight_search",
                    "hotel_search",
                    "guardrail",
                    "modify_itinerary",
                    "patch_itinerary_day",
                )
                if update and node in _msg_nodes and update.get("messages"):
                    last = update["messages"][-1]
                    if isinstance(last, AIMessage):
                        yield _sse(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": last.content,
                                "thread_id": thread_id,
                            }
                        )

        snapshot = graph.get_state(config)
        if snapshot.interrupts and not interrupt_sent:
            intr = snapshot.interrupts[0]
            value = intr.value or {}
            interrupt_sent = True
            yield _sse(_interrupt_sse(thread_id, value))
        else:
            values = snapshot.values or {}
            yield _sse(
                {
                    "type": "done",
                    "thread_id": thread_id,
                    "snapshot": state_to_snapshot(values),
                }
            )
    except Exception as exc:
        yield _sse(
            {
                "type": "error",
                "message": friendly_error(exc),
                "thread_id": thread_id,
            }
        )
