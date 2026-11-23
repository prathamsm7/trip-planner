"""Shared helpers for turning a specialist result into a tool response."""

from __future__ import annotations

import logging
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from safar_api.agents.progress import emit_progress
from safar_api.agents.state_bridge import updates_from_agent_result
from safar_api.config import settings
from safar_api.logging_config import log_exception
from safar_api.nodes.guardrail import scan_tool_text

logger = logging.getLogger(__name__)

TOOL_LABELS: dict[str, str] = {
    "update_trip": "Updating trip details",
    "research_destination": "Researching destination",
    "get_weather": "Checking weather",
    "search_flights": "Searching flights",
    "search_railway_stations": "Finding railway stations",
    "search_trains": "Searching trains",
    "search_stays": "Searching stays",
    "select_options": "Updating your selections",
    "answer_trip_question": "Answering from your trip",
    "web_search": "Searching the web",
    "build_itinerary": "Building itinerary",
}


def runtime_thread_id(runtime: ToolRuntime | None) -> str:
    config = getattr(runtime, "config", None)
    if not isinstance(config, dict):
        return ""
    configurable = config.get("configurable") or {}
    return str(configurable.get("thread_id") or "")


def tool_result_command(
    runtime: ToolRuntime | None,
    update: dict[str, Any],
    observation: str,
) -> Command:
    call_id = getattr(runtime, "tool_call_id", None) if runtime else None
    if not call_id:
        raise ValueError("ToolRuntime.tool_call_id is required for Command tools")
    content = (observation or "ok").strip() or "ok"
    max_chars = max(120, settings.agent_tool_observation_chars)
    return Command(
        update={
            **update,
            "messages": [ToolMessage(content=content[:max_chars], tool_call_id=call_id)],
        }
    )


def command_from_tool_result(
    result,
    *,
    tool: str,
    detail: str,
    runtime: ToolRuntime | None,
) -> Command:
    update = updates_from_agent_result(result.updates)
    update["last_step_detail"] = result.detail or detail
    if result.status == "failed":
        log_exception(
            logger,
            f"{detail} failed",
            context={
                "status": result.status,
                "error": result.error,
                "summary": (result.summary or "")[:200],
            },
        )
    emit_progress(
        runtime,
        tool=tool,
        status="complete",
        detail=result.summary or result.detail or detail,
        label=TOOL_LABELS.get(tool, tool),
    )
    observation = scan_tool_text(
        result.summary or "",
        tool=tool,
        thread_id=runtime_thread_id(runtime),
    )
    return tool_result_command(runtime, update, observation)


def emit_tool_start(runtime: ToolRuntime | None, tool: str, detail: str = "") -> None:
    emit_progress(
        runtime,
        tool=tool,
        status="start",
        detail=detail or TOOL_LABELS.get(tool, tool),
        label=TOOL_LABELS.get(tool, tool),
    )

