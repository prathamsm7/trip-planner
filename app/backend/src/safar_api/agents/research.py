"""Destination research agent — LLM-planned queries + SerpAPI + structured distill."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from safar_api.agents.base import AgentResult
from safar_api.logging_config import log_exception
from safar_api.services.llm import planning_llm
from safar_api.services.serpapi_client import search_ai_overview
from safar_api.services.text import clean_text
from safar_api.trip.brief import TripBrief
from safar_api.trip.results import DestinationResearch, make_artifact
from safar_api.trip.state import AgentState

logger = logging.getLogger(__name__)


class _QueryPlan(BaseModel):
    queries: list[str] = Field(default_factory=list)


def _plan_queries(brief: TripBrief, focus: str) -> list[str]:
    prompt = f"""
You are a travel agent who plans web search queries for a trip planner.
Destination: {brief.destination}
Origin: {brief.origin or "unknown"}
Month: {brief.month or "unknown"}
Style: {brief.style}
Transport: {brief.transport_mode}
Preferences: {", ".join(brief.preferences) or "none"}
Focus: {focus}

Return 3 to 5 short search queries covering:
- attractions and areas
- local transport / airports / stations (if focus is transport or both)
- food and practical tips
"""
    try:
        plan = planning_llm().with_structured_output(_QueryPlan).invoke(
            [SystemMessage(content=prompt), HumanMessage(content="Plan the queries.")]
        )
        queries = [q.strip() for q in plan.queries if q and q.strip()]
        return queries[:5] or _fallback_queries(brief, focus)
    except Exception as exc:
        log_exception(
            logger,
            "query planning failed",
            exc,
            context={"destination": brief.destination, "focus": focus},
        )
        return _fallback_queries(brief, focus)


def _fallback_queries(brief: TripBrief, focus: str) -> list[str]:
    dest = brief.destination
    month = brief.month or ""
    queries = [
        f"things to do in {dest} {month}".strip(),
        f"tourist attractions and areas in {dest}",
    ]
    if focus in ("transport", "both"):
        origin = brief.origin or "departure city"
        queries.append(
            f"{origin} to {dest} transport flight train bus nearest airport railway"
        )
    queries.append(f"food and practical travel tips {dest}")
    return queries


def _run_query(query: str) -> tuple[str, str]:
    try:
        raw = search_ai_overview(query)
        md = clean_text(str(raw.get("reconstructed_markdown") or raw.get("text") or ""))
        return query, md[:8000]
    except Exception as exc:
        log_exception(
            logger,
            "research query failed",
            exc,
            context={"query": query[:160]},
        )
        return query, ""


def _distill(brief: TripBrief, snippets: list[tuple[str, str]]) -> DestinationResearch:
    evidence = "\n\n".join(
        f"Query: {q}\n{text}" for q, text in snippets if text
    )[:20000]
    if not evidence.strip():
        return DestinationResearch(
            overview=f"Limited research available for {brief.destination}.",
            queries_used=[q for q, _ in snippets],
        )

    system = f"""
Extract structured destination research for {brief.destination}.
Use only facts from the search text. Include IATA codes when clearly stated.
Return JSON matching the schema.
"""
    try:
        result = planning_llm().with_structured_output(DestinationResearch).invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=f"Brief: {brief.model_dump()}\n\nEvidence:\n{evidence}"),
            ]
        )
        result.queries_used = [q for q, _ in snippets]
        return result
    except Exception as exc:
        log_exception(
            logger,
            "research distill failed",
            exc,
            context={"destination": brief.destination},
        )
        overview = evidence[:1200]
        return DestinationResearch(
            overview=overview or f"Research for {brief.destination}",
            queries_used=[q for q, _ in snippets],
        )


def run_research(call: dict[str, Any], state: AgentState) -> AgentResult:
    brief = state.brief
    if not brief.destination:
        return AgentResult(status="failed", summary="Missing destination.", error="missing_fields")

    args = call.get("args") or {}
    focus = args.get("focus") or "both"
    refresh = bool(args.get("refresh"))

    if state.research and state.research.matches(brief) and not refresh:
        return AgentResult(
            status="skipped",
            summary="Destination research already available for this trip.",
            detail="Research ready",
        )

    queries = _plan_queries(brief, focus)
    snippets: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(4, len(queries) or 1)) as pool:
        futures = [pool.submit(_run_query, q) for q in queries]
        for fut in as_completed(futures):
            snippets.append(fut.result())

    ok = sum(1 for _, text in snippets if text)
    research = _distill(brief, snippets)
    artifact = make_artifact("research", brief, research)
    status = "ok" if ok else "failed"
    if ok and ok < len(snippets):
        status = "partial"

    return AgentResult(
        status=status,
        summary=(
            f"Researched {brief.destination}: {len(research.attractions)} attractions, "
            f"{len(research.airports)} airports."
            if ok
            else f"Research failed for {brief.destination}."
        ),
        detail=f"Researching {brief.destination}",
        updates={"research": artifact} if ok else {},
        error="" if ok else "provider_error",
    )
