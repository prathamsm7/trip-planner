"""SSE streaming for the supervisor agent."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from safar_api.api.serialize import patch_for_node
from safar_api.trip.state import (
    is_hidden_transcript_message,
    snapshot_from_agent_state,
    sync_chat_transcript,
    visible_reply,
)
from safar_api.agents.trip_agent_state import empty_trip_fields
from safar_api.graph.build import get_graph
from safar_api.logging_config import log_exception
from safar_api.nodes.guardrail import (
    message_text,
    redact_pii,
    refusal_message,
    rule_check,
    sanitize_output,
)
from safar_api.tracing import langsmith_run_config
from safar_api.utils.errors import friendly_error

logger = logging.getLogger(__name__)

try:
    from safar_api.agents.supervisor import TOOL_LABELS
except Exception as exc:  # pragma: no cover
    log_exception(logger, "Failed to import TOOL_LABELS", exc)
    TOOL_LABELS = {}


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _base_node_name(node: str) -> str:
    if "|" in node:
        return node.split("|")[-1]
    if ":" in node:
        return node.split(":")[-1]
    return node


def _ui_hints(node: str, update: dict | None = None) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    base = _base_node_name(node)
    if update and (update.get("itinerary") or base == "build_itinerary"):
        hints["open_tab"] = "itinerary"
        hints["show_package_card"] = True
    if update and (update.get("flights_data") or update.get("flights") or base == "search_flights"):
        hints["open_tab"] = "flights"
        hints["show_package_card"] = True
    if update and (update.get("trains") or base == "search_trains"):
        hints["open_tab"] = "trains"
        hints["show_package_card"] = True
    if update and (
        update.get("hotel_search_results") or update.get("stays") or base == "search_stays"
    ):
        hints["open_tab"] = "hotels"
        hints["show_package_card"] = True
    return hints


def _assistant_text(msg: Any) -> str | None:
    if not isinstance(msg, AIMessage) or getattr(msg, "tool_calls", None):
        return None
    text = message_text(msg.content).strip()
    return text or None


def _split_stream_item(item: Any) -> tuple[str | None, Any]:
    """Normalize astream items for stream_mode list (mode, data) or plain dict."""
    if isinstance(item, tuple) and len(item) == 2:
        mode, data = item
        return str(mode), data
    if isinstance(item, dict) and "type" in item and "data" in item:
        return str(item.get("type")), item.get("data")
    return None, item


async def _stream_agent(
    graph: Any,
    graph_input: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    user_text: str,
) -> AsyncIterator[str]:
    """Stream the supervisor via updates + custom (runtime.stream_writer progress)."""
    message_sent = False
    replies: list[str] = []
    tool_texts: set[str] = set()
    step_i = 0
    # tool_call_id → step_id so start/complete pair correctly
    open_steps: dict[str, str] = {}

    async for item in graph.astream(
        graph_input,
        config,
        stream_mode=["updates", "custom"],
    ):
        mode, data = _split_stream_item(item)

        if mode == "custom" and isinstance(data, dict) and data.get("tool"):
            tool = str(data["tool"])
            status = str(data.get("status") or "progress")
            label = str(data.get("label") or TOOL_LABELS.get(tool) or tool)
            call_id = str(data.get("tool_call_id") or tool)
            if status == "start":
                step_i += 1
                step_id = f"{tool}-{step_i}"
                open_steps[call_id] = step_id
                yield _sse(
                    {
                        "type": "step_start",
                        "node": tool,
                        "step_id": step_id,
                        "label": label,
                        "description": label,
                        "thread_id": thread_id,
                    }
                )
            elif status == "progress":
                step_id = open_steps.get(call_id) or f"{tool}-{step_i}"
                yield _sse(
                    {
                        "type": "step_start",
                        "node": tool,
                        "step_id": step_id,
                        "label": label,
                        "description": label,
                        "thread_id": thread_id,
                    }
                )
            elif status == "complete":
                step_id = open_steps.pop(call_id, None) or f"{tool}-{step_i}"
                yield _sse(
                    {
                        "type": "step_complete",
                        "node": tool,
                        "step_id": step_id,
                        "label": label,
                        "description": label,
                        "thread_id": thread_id,
                    }
                )
            continue

        if mode not in (None, "updates"):
            continue
        chunk = data if mode == "updates" else item
        if not isinstance(chunk, dict):
            continue

        for node, update in chunk.items():
            if node in ("type", "data"):
                continue
            base = _base_node_name(str(node))
            if not isinstance(update, dict):
                continue

            if base == "model":
                for msg in update.get("messages") or []:
                    text = _assistant_text(msg)
                    reply = visible_reply(sanitize_output(text), tool_texts) if text else ""
                    if reply:
                        message_sent = True
                        replies.append(reply)
                        yield _sse(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": reply,
                                "thread_id": thread_id,
                            }
                        )
                continue

            if base == "tools":
                for msg in update.get("messages") or []:
                    if isinstance(msg, ToolMessage):
                        tool_text = message_text(msg.content).strip()
                        if tool_text:
                            tool_texts.add(tool_text)
                patch = patch_for_node(base, update)
                hints = _ui_hints(base, update)
                produced = []
                if update.get("flights") is not None:
                    produced.append("search_flights")
                if update.get("trains") is not None:
                    train_update = update.get("trains")
                    train_data = {}
                    if isinstance(train_update, dict):
                        nested = train_update.get("data")
                        train_data = nested if isinstance(nested, dict) else train_update
                    elif hasattr(train_update, "data") and isinstance(train_update.data, dict):
                        train_data = train_update.data
                    produced.append("search_trains" if train_data.get("searched") else "search_railway_stations")
                if update.get("stays") is not None:
                    produced.append("search_stays")
                if update.get("research") is not None:
                    produced.append("research_destination")
                if update.get("weather") is not None:
                    produced.append("get_weather")
                if update.get("itinerary") is not None:
                    produced.append("build_itinerary")
                if update.get("brief") is not None:
                    produced.append("update_trip")
                for key in produced:
                    tool_label = TOOL_LABELS.get(key, key)
                    yield _sse(
                        {
                            "type": "step_complete",
                            "node": key,
                            "step_id": f"{key}-payload",
                            "label": tool_label,
                            "description": tool_label,
                            "payload": patch,
                            "ui_hints": hints,
                            "thread_id": thread_id,
                        }
                    )
                    if hints.get("show_package_card"):
                        yield _sse({"type": "package_ready", "thread_id": thread_id})

    values = (graph.get_state(config).values) or {}
    try:
        from safar_api.trip.persistence import upsert_trip_metadata
        upsert_trip_metadata(thread_id, values.get("brief") or {})
    except Exception as e:
        logger.error("Failed to sync trip metadata: %s", e)

    if not message_sent:
        history = list(values.get("messages") or [])
        last_user = -1
        for index, msg in enumerate(history):
            if isinstance(msg, HumanMessage) and not is_hidden_transcript_message(msg):
                last_user = index
        for msg in reversed(history[last_user + 1 :]):
            text = _assistant_text(msg)
            reply = visible_reply(sanitize_output(text), tool_texts) if text else ""
            if reply:
                replies.append(reply)
                yield _sse(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": reply,
                        "thread_id": thread_id,
                    }
                )
                break
    try:
        chat = sync_chat_transcript(graph, config, user_text=user_text, replies=replies)
        if chat:
            values = {**values, "chat": chat}
    except Exception:
        logger.exception("Saving chat transcript failed")
    yield _sse(
        {
            "type": "done",
            "thread_id": thread_id,
            "snapshot": snapshot_from_agent_state(values),
        }
    )


def unanswered_tool_messages(messages: list[Any]) -> list[ToolMessage]:
    """Tool results for calls that were saved without a result.

    A crashed tool leaves the assistant's function call in the checkpoint.
    The next turn is rejected until each call has a matching tool message.
    """
    answered = {
        message.tool_call_id
        for message in messages
        if isinstance(message, ToolMessage) and message.tool_call_id
    }
    repairs: list[ToolMessage] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
            if not call_id or call_id in answered:
                continue
            answered.add(call_id)
            repairs.append(
                ToolMessage(
                    content="That step failed before it finished.",
                    tool_call_id=call_id,
                )
            )
    return repairs


def _existing_snapshot(thread_id: str) -> dict[str, Any]:
    """Read a saved trip without building the graph for a new thread."""
    from safar_api.graph import build as graph_build

    if graph_build._graph is None:
        return snapshot_from_agent_state({})
    config = langsmith_run_config(thread_id)
    values = (graph_build._graph.get_state(config).values) or {}
    return snapshot_from_agent_state(values)


async def stream_graph(thread_id: str, content: str | None = None) -> AsyncIterator[str]:
    """One user turn: check the message, then run the supervisor.

    A blocked message stops here. The graph is not built and no tool runs.
    """
    try:
        if not content or not content.strip():
            yield _sse({"type": "error", "message": "Please enter a message."})
            return

        content = redact_pii(content)
        blocked = rule_check(content, thread_id=thread_id)
        if blocked:
            action, _reason = blocked
            reply = refusal_message(action)
            if reply:
                yield _sse(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": reply,
                        "thread_id": thread_id,
                    }
                )
            yield _sse(
                {
                    "type": "done",
                    "thread_id": thread_id,
                    "snapshot": _existing_snapshot(thread_id),
                }
            )
            return

        graph = get_graph()
        config = langsmith_run_config(thread_id)
        existing = (graph.get_state(config).values) or {}
        repairs = unanswered_tool_messages(list(existing.get("messages") or []))
        if repairs:
            graph.update_state(config, {"messages": repairs})
        graph_input = {"messages": [HumanMessage(content=content)]}
        if not existing:
            graph_input = {**empty_trip_fields(), **graph_input}
        async for event in _stream_agent(graph, graph_input, config, thread_id, content):
            yield event

    except Exception as exc:
        log_exception(
            logger,
            "stream_graph failed",
            exc,
            context={
                "thread_id": thread_id,
                "content_preview": (content or "")[:120],
                "error_type": type(exc).__name__,
            },
        )
        yield _sse(
            {
                "type": "error",
                "message": friendly_error(exc),
                "thread_id": thread_id,
            }
        )
