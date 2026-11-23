"""Answer a question from the trip that is already saved."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from safar_api.agents.answer_trip import run_trip_qa
from safar_api.agents.progress import emit_progress
from safar_api.agents.tools.support import TOOL_LABELS, emit_tool_start


@tool
def answer_trip_question(
    question: str,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """Answer a question from the saved trip. Pass the user's question as-is.

    Call for day plans, summaries, selected flights or hotels, and other questions
    about data already saved. Do not call to search, create, or change the trip.
    """
    emit_tool_start(runtime, "answer_trip_question")
    state = runtime.state if runtime else {}
    answer = run_trip_qa(question, state)
    emit_progress(
        runtime,
        tool="answer_trip_question",
        status="complete",
        detail=answer[:200],
        label=TOOL_LABELS["answer_trip_question"],
    )
    return answer
