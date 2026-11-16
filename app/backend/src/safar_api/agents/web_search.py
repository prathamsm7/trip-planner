"""Open-ended web search agent for visas, events, opening hours, etc."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from safar_api.agents.base import AgentResult
from safar_api.logging_config import log_exception
from safar_api.services.llm import planning_llm
from safar_api.services.serpapi_client import search_ai_overview
from safar_api.services.text import clean_text
from safar_api.trip.state import AgentState

logger = logging.getLogger(__name__)


class _WebAnswer(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


def run_web_search(call: dict[str, Any], state: AgentState) -> AgentResult:
    args = call.get("args") or {}
    question = (args.get("question") or "").strip()
    if not question:
        # Fall back to the latest user message.
        if state.messages:
            question = str(getattr(state.messages[-1], "content", "") or "")
    if not question:
        return AgentResult(status="failed", summary="No question to search.", error="missing_fields")

    snippets: list[str] = []
    queries = [question]
    # Optionally add a second focused query.
    if state.brief.destination and state.brief.destination.lower() not in question.lower():
        queries.append(f"{question} {state.brief.destination}")

    for query in queries[:3]:
        try:
            raw = search_ai_overview(query)
            text = clean_text(str(raw.get("reconstructed_markdown") or ""))
            if text:
                snippets.append(f"Query: {query}\n{text[:6000]}")
        except Exception as exc:
            log_exception(
                logger,
                "web_search query failed",
                exc,
                context={"query": query[:160]},
            )

    if not snippets:
        return AgentResult(
            status="failed",
            summary="Web search returned no results.",
            detail="Searching the web",
            error="provider_error",
        )

    try:
        result = planning_llm().with_structured_output(_WebAnswer).invoke(
            [
                SystemMessage(
                    content=(
                        "Answer the user's travel question using only the search evidence. "
                        "Be concise and factual. If unsure, say so."
                    )
                ),
                HumanMessage(
                    content=f"Question: {question}\n\nEvidence:\n" + "\n\n".join(snippets)[:16000]
                ),
            ]
        )
        summary = result.answer
        if result.sources:
            summary += "\nSources: " + "; ".join(result.sources[:5])
        return AgentResult(
            status="ok",
            summary=summary,
            detail="Searching the web",
        )
    except Exception as exc:
        log_exception(
            logger,
            "web_search distill failed",
            exc,
            context={"question": question[:160]},
        )
        return AgentResult(
            status="partial",
            summary=snippets[0][:1500],
            detail="Searching the web",
            error=type(exc).__name__,
        )
