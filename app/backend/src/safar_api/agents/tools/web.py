"""Look up a fact that is not already saved on the trip."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from safar_api.agents.progress import emit_progress
from safar_api.agents.state_bridge import agent_state_from_runtime
from safar_api.agents.tools.support import TOOL_LABELS, emit_tool_start, runtime_thread_id
from safar_api.agents.web_search import run_web_search
from safar_api.nodes.guardrail import scan_tool_text


@tool
def web_search(question: str, runtime: ToolRuntime = None) -> str:  # type: ignore[assignment]
    """Look up a specific fact that is not in Current trip (visa, events, opening hours).

    Call ONLY when the user asks something the brief, research, weather, flights, and stays do not answer.
    Do NOT call for flights, hotels, weather, or itinerary — those have their own tools.
    Do NOT call for questions about the saved trip — use answer_trip_question.
    """
    emit_tool_start(runtime, "web_search")
    state = runtime.state if runtime else {}
    result = run_web_search(
        {"args": {"question": question}},
        agent_state_from_runtime(state),
    )
    summary = scan_tool_text(
        result.summary or result.error or "No results.",
        tool="web_search",
        thread_id=runtime_thread_id(runtime),
    )
    emit_progress(
        runtime,
        tool="web_search",
        status="complete",
        detail=summary[:200],
        label=TOOL_LABELS["web_search"],
    )
    return summary
