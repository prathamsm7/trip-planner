"""Trip facts passed into specialist tools, plus the UI snapshot mapping."""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from safar_api.trip.brief import TripBrief
from safar_api.trip.results import Artifact

logger = logging.getLogger(__name__)

_SUMMARY_PREFIX = "here is a summary of the conversation to date:"
_CONTEXT_PREFIX = "current trip (checkpoint context):"


def keep_latest(left: Any, right: Any) -> Any:
    """Graph reducer: the newest write wins."""
    return right if right is not None else left


def merge_selections(left: dict, right: dict) -> dict:
    """Graph reducer: overlay new flight/hotel picks onto the previous ones."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def merge_step_detail(left: str, right: str) -> str:
    """Graph reducer: newest non-empty progress label wins."""
    return right or left or ""


class AgentState(BaseModel):
    """Trip facts and saved results a specialist tool reads."""

    messages: Sequence[BaseMessage] = Field(default_factory=list)
    brief: TripBrief = Field(default_factory=TripBrief)
    research: Optional[Artifact] = None
    weather: Optional[Artifact] = None
    flights: Optional[Artifact] = None
    trains: Optional[Artifact] = None
    stays: Optional[Artifact] = None
    itinerary: Optional[Artifact] = None
    selections: dict = Field(default_factory=dict)


def visible_reply(text: str, tool_texts: set[str]) -> str:
    """Drop blank lines and lines that are raw tool status, not a reply."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped in tool_texts:
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def is_hidden_transcript_message(msg: BaseMessage) -> bool:
    """Session summaries and injected trip context are not chat turns."""
    kwargs = getattr(msg, "additional_kwargs", None) or {}
    if kwargs.get("lc_source") == "summarization":
        return True
    from safar_api.nodes.guardrail import message_text

    content = message_text(getattr(msg, "content", "") or "").strip().lower()
    return content.startswith(_SUMMARY_PREFIX) or content.startswith(_CONTEXT_PREFIX)


def _message_to_dict(msg: BaseMessage, tool_texts: set[str]) -> dict[str, Any] | None:
    from safar_api.nodes.guardrail import message_text, sanitize_output

    if isinstance(msg, ToolMessage) or is_hidden_transcript_message(msg):
        return None
    content = message_text(msg.content).strip()
    if isinstance(msg, HumanMessage):
        if not content:
            return None
        return {"role": "user", "content": content, "id": getattr(msg, "id", None)}
    if not isinstance(msg, AIMessage) or getattr(msg, "tool_calls", None):
        return None
    content = visible_reply(sanitize_output(content), tool_texts)
    if not content:
        return None
    return {"role": "assistant", "content": content, "id": getattr(msg, "id", None)}


def transcript_from_message_lists(
    message_lists: Sequence[Sequence[BaseMessage]],
) -> list[dict[str, str]]:
    """User and assistant turns in order, skipping summaries and tool traffic.

    Later checkpoints repeat earlier messages. The same id is kept once, from
    the oldest checkpoint, so a later summary cannot erase the conversation.
    """
    from safar_api.nodes.guardrail import message_text

    seen: set[str] = set()
    transcript: list[dict[str, str]] = []
    for messages in message_lists:
        tool_texts = {
            message_text(message.content).strip()
            for message in messages
            if isinstance(message, ToolMessage)
        }
        for message in messages:
            item = _message_to_dict(message, tool_texts)
            if not item:
                continue
            key = item.get("id") or f"{item['role']}\0{item['content']}"
            if key in seen:
                continue
            seen.add(key)
            transcript.append({"role": item["role"], "content": item["content"]})
    return transcript


def normalize_chat(items: Any) -> list[dict[str, str]]:
    """Keep stored user and assistant turns. Drop a saved session summary."""
    if not isinstance(items, list):
        return []
    transcript: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        lowered = content.lower()
        if lowered.startswith(_SUMMARY_PREFIX) or lowered.startswith(_CONTEXT_PREFIX):
            continue
        transcript.append({"role": role, "content": content})
    return transcript


def append_chat_turn(
    chat: Sequence[dict[str, str]],
    user_text: str,
    replies: Sequence[str],
) -> list[dict[str, str]]:
    """Add this turn when the saved transcript does not already end with it."""
    result = [dict(item) for item in chat]
    user_text = (user_text or "").strip()
    clean_replies = [reply.strip() for reply in replies if reply and reply.strip()]
    if not user_text and not clean_replies:
        return result
    tail: list[dict[str, str]] = []
    if user_text:
        tail.append({"role": "user", "content": user_text})
    tail.extend({"role": "assistant", "content": reply} for reply in clean_replies)
    if tail and len(result) >= len(tail) and result[-len(tail) :] == tail:
        return result
    if user_text and result and result[-1] == {"role": "user", "content": user_text}:
        result.extend({"role": "assistant", "content": reply} for reply in clean_replies)
        return result
    result.extend(tail)
    return result


def _oldest_first(snapshots: Sequence[Any]) -> list[Any]:
    if not snapshots:
        return []
    stamped = [snap.created_at for snap in snapshots if getattr(snap, "created_at", None)]
    if len(stamped) == len(snapshots):
        return sorted(snapshots, key=lambda snap: snap.created_at or "")
    return list(reversed(snapshots))


def sync_chat_transcript(
    graph: Any,
    config: dict[str, Any],
    *,
    user_text: str = "",
    replies: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    """Return the full user/assistant transcript and store it on the thread.

    The agent summary replaces older checkpoint messages. The first read walks
    checkpoint history once and saves the rebuilt transcript on `chat`. Later
    reads use that copy. Each new turn is appended.
    """
    values = (graph.get_state(config).values) or {}
    stored = normalize_chat(values.get("chat"))
    user_text = (user_text or "").strip()
    if stored:
        chat = append_chat_turn(stored, user_text, replies or [])
    else:
        try:
            history = _oldest_first(list(graph.get_state_history(config)))
            message_lists = []
            for snap in history:
                snap_values = snap.values if isinstance(getattr(snap, "values", None), dict) else {}
                message_lists.append(list(snap_values.get("messages") or []))
            if not any(message_lists):
                message_lists = [list(values.get("messages") or [])]
            chat = transcript_from_message_lists(message_lists)
        except Exception:
            logger.exception("Rebuilding chat transcript from history failed")
            chat = transcript_from_message_lists([list(values.get("messages") or [])])
        # History already contains this turn. Append only when it does not.
        latest_user = next((item["content"] for item in reversed(chat) if item["role"] == "user"), "")
        if user_text and latest_user != user_text:
            chat = append_chat_turn(chat, user_text, replies or [])
    if chat and chat != stored:
        try:
            graph.update_state(config, {"chat": chat})
        except Exception:
            logger.exception("Saving chat transcript failed")
    return chat


def snapshot_from_agent_state(values: dict[str, Any]) -> dict[str, Any]:
    """Map supervisor state to the fields the chat UI reads."""
    brief = values.get("brief")
    if isinstance(brief, TripBrief):
        structured = brief.to_ui_trip()
    elif isinstance(brief, dict):
        payload = dict(brief)
        if isinstance(payload.get("stated"), list):
            payload["stated"] = set(payload["stated"])
        structured = TripBrief.model_validate(payload).to_ui_trip()
    else:
        structured = None

    def _artifact_data(artifact: Any) -> dict | None:
        if artifact is None:
            return None
        if isinstance(artifact, Artifact):
            return artifact.data
        if isinstance(artifact, dict):
            if "data" in artifact:
                return artifact.get("data") or {}
            return artifact
        return None

    research_data = _artifact_data(values.get("research")) or {}
    weather_data = _artifact_data(values.get("weather"))
    flights_data = _artifact_data(values.get("flights")) or {}
    trains_data = _artifact_data(values.get("trains")) or {}
    stays_data = _artifact_data(values.get("stays")) or {}
    itinerary_data = _artifact_data(values.get("itinerary"))

    stored_chat = normalize_chat(values.get("chat"))
    if stored_chat:
        visible_messages = stored_chat
    else:
        visible_messages = transcript_from_message_lists([values.get("messages") or []])
    return {
        "structured": structured,
        "weather": weather_data,
        "destination_about": research_data.get("overview", "") if research_data else "",
        "itinerary": itinerary_data,
        "hotel_search_results": stays_data.get("properties") if stays_data else None,
        "flights_data": flights_data if flights_data else {},
        "trains": trains_data if trains_data else None,
        "selections": values.get("selections") or {},
        "messages": visible_messages,
    }
