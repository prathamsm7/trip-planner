"""Trip planner agent — LangChain create_agent + tools that write TripAgentState."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
    wrap_model_call,
)
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from safar_api.agents.answer_trip import run_trip_qa
from safar_api.agents.booking import run_booking
from safar_api.agents.itinerary import run_itinerary
from safar_api.agents.progress import emit_progress
from safar_api.agents.research import run_research
from safar_api.agents.selections import apply_selection_preferences, selections_prompt_block
from safar_api.agents.state_bridge import (
    agent_state_from_runtime,
    brief_from_state,
    updates_from_agent_result,
)
from safar_api.agents.trip_agent_state import TripAgentState
from safar_api.agents.weather import run_weather
from safar_api.agents.web_search import run_web_search
from safar_api.config import settings
from safar_api.logging_config import log_exception
from safar_api.services.llm import supervisor_llm, utility_llm
from safar_api.trip.brief import TripBrief, TripUpdate, apply_trip_update
from safar_api.trip.results import Artifact, apply_brief_change

logger = logging.getLogger(__name__)

_checkpointer = InMemorySaver()

TOOL_LABELS: dict[str, str] = {
    "update_trip": "Updating trip details",
    "research_destination": "Researching destination",
    "get_weather": "Checking weather",
    "search_flights": "Searching flights",
    "search_stays": "Searching stays",
    "select_options": "Updating your selections",
    "answer_trip_question": "Answering from your trip",
    "web_search": "Searching the web",
    "build_itinerary": "Building itinerary",
}


def brief_to_dict(brief: TripBrief) -> dict[str, Any]:
    data = brief.model_dump()
    data["stated"] = sorted(brief.stated)
    return data


def brief_summary(brief: TripBrief) -> str:
    """Compact brief for the model — omit empty fields and stated-set noise."""
    parts: list[str] = []
    for key in (
        "origin",
        "destination",
        "start_date",
        "end_date",
        "month",
        "travellers",
        "budget",
        "style",
        "transport_mode",
    ):
        value = getattr(brief, key, None)
        if value not in (None, "", 0):
            parts.append(f"{key}={value}")
    if brief.preferences:
        parts.append("preferences=" + ",".join(brief.preferences))
    if brief.notes:
        parts.append(f"notes={(brief.notes or '')[:120]}")
    return ", ".join(parts) or "(empty)"


def artifacts_from_state(state: dict) -> dict[str, Artifact | None]:
    out: dict[str, Artifact | None] = {}
    for key in ("research", "weather", "flights", "stays", "itinerary"):
        raw = state.get(key)
        if isinstance(raw, Artifact):
            out[key] = raw
        elif isinstance(raw, dict) and "kind" in raw:
            out[key] = Artifact.model_validate(raw)
        else:
            out[key] = None
    return out


def current_trip_text(state: dict) -> str:
    """Lean checkpoint — brief, statuses, and short selections only (no catalogs)."""
    brief = brief_from_state(state)
    lines = [f"Brief: {brief_summary(brief)}"]
    for name in ("research", "weather", "flights", "stays", "itinerary"):
        raw = state.get(name)
        if not raw:
            lines.append(f"- {name}: missing")
            continue
        flagged = raw.get("flagged") if isinstance(raw, dict) else False
        status = "stale" if flagged else "ready"
        data = raw.get("data") if isinstance(raw, dict) else {}
        if name == "flights" and data:
            meta = data.get("airport_meta") or {}
            outbound = data.get("outbound") or {}
            return_flights = data.get("return_flights") or {}
            outbound_count = len(outbound.get("best_flights") or []) + len(
                outbound.get("other_flights") or []
            )
            return_count = len(return_flights.get("best_flights") or []) + len(
                return_flights.get("other_flights") or []
            )
            route = (
                f"{meta.get('departure_airport_code') or '?'}→"
                f"{meta.get('arrival_airport_code') or '?'}"
            )
            lines.append(
                f"- flights: {status} outbound={outbound_count} return={return_count} {route}"
            )
            alternatives = data.get("alternatives") or {}
            if alternatives.get("ask_user") or (outbound_count + return_count) == 0:
                lines.append("  NOTE: ask user for alternate airport/destination if needed")
        elif name == "stays" and data:
            lines.append(f"- stays: {status} options={len(data.get('properties') or [])}")
        else:
            lines.append(f"- {name}: {status}")
    lines.append(selections_prompt_block(state))
    lines.append(
        "For questions about saved trip details (day plans, selected flights/hotels, "
        "summaries), call answer_trip_question. Do not invent those details from status alone."
    )
    return "\n".join(lines)


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
    return tool_result_command(runtime, update, result.summary or result.status)


def emit_tool_start(runtime: ToolRuntime | None, tool: str, detail: str = "") -> None:
    emit_progress(
        runtime,
        tool=tool,
        status="start",
        detail=detail or TOOL_LABELS.get(tool, tool),
        label=TOOL_LABELS.get(tool, tool),
    )


# ── Tools ────────────────────────────────────────────────────────────


@tool
def update_trip(
    origin: str | None = None,
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    duration_days: int | None = None,
    month: str | None = None,
    travellers: int | None = None,
    budget: str | None = None,
    style: str | None = None,
    transport_mode: str | None = None,
    stay_type: str | None = None,
    preferences: list[str] | None = None,
    notes: str | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Save new or changed trip facts (origin, destination, dates, travellers, budget, style).

    Call ONLY when the user states a fact that is missing or different in Current trip.
    Do NOT call for questions, selections, or repeats of fields already saved.
    Pass only changed fields. Dates are YYYY-MM-DD.
    Call this alone first — other tools read the saved brief on the next step.
    """
    emit_tool_start(runtime, "update_trip")
    state = runtime.state if runtime else {}
    updated, changed = apply_trip_update(
        brief_from_state(state),
        TripUpdate(
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            duration_days=duration_days,
            month=month,
            travellers=travellers,
            budget=budget,  # type: ignore[arg-type]
            style=style,  # type: ignore[arg-type]
            transport_mode=transport_mode,  # type: ignore[arg-type]
            stay_type=stay_type,  # type: ignore[arg-type]
            preferences=preferences,
            notes=notes,
        ),
    )
    artifacts = apply_brief_change(changed, artifacts_from_state(state))
    update: dict[str, Any] = {
        "brief": brief_to_dict(updated),
        "last_step_detail": f"Updated trip: {sorted(changed) or 'no changes'}",
    }
    for key, artifact in artifacts.items():
        update[key] = artifact.model_dump() if artifact is not None else None
    summary = f"Updated fields: {sorted(changed) or 'none'}"
    emit_progress(
        runtime,
        tool="update_trip",
        status="complete",
        detail=summary,
        label=TOOL_LABELS["update_trip"],
    )
    return tool_result_command(runtime, update, summary)


@tool
def research_destination(
    focus: str = "both",
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Fetch destination overview, areas, and tips.

    Call ONLY when Current trip shows research missing or stale, or the user asks to refresh research.
    Do NOT call if research is ready. Do NOT call to pick flights or hotels.
    refresh=True only when the user asks to refresh or the brief destination changed.
    """
    emit_tool_start(runtime, "research_destination")
    state = runtime.state if runtime else {}
    result = run_research(
        {"args": {"focus": focus, "refresh": refresh}},
        agent_state_from_runtime(state),
    )
    return command_from_tool_result(
        result, tool="research_destination", detail="Researching destination", runtime=runtime
    )


@tool
def get_weather(
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Fetch the weather outlook for the saved destination and dates.

    Call ONLY when Current trip shows weather missing or stale, or the user asks to refresh weather.
    Do NOT call if weather is ready. Requires a destination plus dates or a month already saved.
    """
    emit_tool_start(runtime, "get_weather")
    state = runtime.state if runtime else {}
    result = run_weather({"args": {"refresh": refresh}}, agent_state_from_runtime(state))
    return command_from_tool_result(
        result, tool="get_weather", detail="Checking weather", runtime=runtime
    )


@tool
def search_flights(
    departure_airport: str | None = None,
    arrival_airport: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Search outbound and return flights for the saved trip.

    Call ONLY when flights are missing or stale, the user asks to search/refresh, or they change airports or dates.
    Do NOT call to choose among flights already listed — use select_options.
    Pass IATA codes only when the user names airports. refresh=True only for a new search.
    If this tool reports no flights, ask the user which listed airport to use. Do not search another airport until they choose.

    """
    emit_tool_start(runtime, "search_flights")
    state = runtime.state if runtime else {}
    result = run_booking(
        {
            "name": "search_flights",
            "args": {
                "departure_airport": departure_airport,
                "arrival_airport": arrival_airport,
                "start_date": start_date,
                "end_date": end_date,
                "refresh": refresh,
            },
        },
        agent_state_from_runtime(state),
    )
    return command_from_tool_result(
        result, tool="search_flights", detail="Searching flights", runtime=runtime
    )


@tool
def search_stays(
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    stay_type: str | None = None,
    budget: str | None = None,
    area: str | None = None,
    refresh: bool = False,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Search hotels or stays for the trip.

    Call ONLY when stays are missing or stale, or the user asks to search/refresh stays.
    Do NOT call to pick a hotel already listed — use select_options.
    Pass destination plus start_date and end_date (YYYY-MM-DD) when Current trip does not already have them.
    If the tool says fields are missing, call update_trip once. Do not call search_stays again in the same step.
    """
    emit_tool_start(runtime, "search_stays")
    state = runtime.state if runtime else {}
    result = run_booking(
        {
            "name": "search_stays",
            "args": {
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
                "stay_type": stay_type,
                "budget": budget,
                "area": area,
                "refresh": refresh,
            },
        },
        agent_state_from_runtime(state),
    )
    return command_from_tool_result(
        result, tool="search_stays", detail="Searching stays", runtime=runtime
    )


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
    summary = result.summary or result.error or "No results."
    emit_progress(
        runtime,
        tool="web_search",
        status="complete",
        detail=summary[:200],
        label=TOOL_LABELS["web_search"],
    )
    return summary


@tool
def select_options(
    outbound_pref: str | None = None,
    return_pref: str | None = None,
    hotel_pref: str | None = None,
    outbound_index: int | None = None,
    return_index: int | None = None,
    hotel_index: int | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Choose flights or hotels from results already in Current trip.

    Call ONLY when the user asks to pick, select, or prefer an option (time of day, cheapest, airline, hotel name).
    Do NOT call search_flights or search_stays for that request.
    Do NOT call if nothing is available yet — say so, or search first only if lists are missing.
    Prefer outbound_pref / return_pref / hotel_pref. Use an index only if the user names a number.
    Outbound = leaving the origin. Return = leaving the destination.
    """
    emit_tool_start(runtime, "select_options")
    state = runtime.state if runtime else {}
    selections, summary = apply_selection_preferences(
        state,
        outbound_pref=outbound_pref,
        return_pref=return_pref,
        hotel_pref=hotel_pref,
        outbound_index=outbound_index,
        return_index=return_index,
        hotel_index=hotel_index,
    )
    emit_progress(
        runtime,
        tool="select_options",
        status="complete",
        detail=summary,
        label=TOOL_LABELS["select_options"],
    )
    return tool_result_command(
        runtime,
        {"selections": selections, "last_step_detail": summary},
        summary,
    )


@tool
def build_itinerary(
    mode: str = "build",
    instructions: str = "",
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> Command:
    """Build or revise the day-by-day itinerary.

    Call ONLY when the user asks to create a plan or to change an existing one.
    Do NOT call when they ask what is already planned, including a specific day.
    mode=build when none exists. mode=revise with instructions when one exists.
    """
    emit_tool_start(runtime, "build_itinerary")
    state = runtime.state if runtime else {}
    result = run_itinerary(
        {"args": {"mode": mode, "instructions": instructions}},
        agent_state_from_runtime(state),
    )
    return command_from_tool_result(
        result, tool="build_itinerary", detail="Building itinerary", runtime=runtime
    )


SUPERVISOR_TOOLS = [
    update_trip,
    research_destination,
    get_weather,
    search_flights,
    search_stays,
    select_options,
    answer_trip_question,
    web_search,
    build_itinerary,
]


SUPERVISOR_SYSTEM = """

You are Safar, an intelligent trip planning assistant.
Today's date: {today}

Your only responsibility is to assist the user with their trip planning needs.
Provide assistance only related to the trip planning, and do not provide any other information.
Say no to any questions that are not related to trip planning.
Only future trip planning is allowed.
If user provide the future date which has so much gap(more than 3 months) from the current date, ask the user to clarify the full date.


## 1. STATE MANAGEMENT

Always prioritize Current trip data.

Trip statuses:
- ready: Data exists and is current. Never fetch again unless explicitly refreshed.
- missing: Data does not exist. Fetch only when needed for the current request.
- stale: Data may be outdated. Refresh when the user needs it.

Never assume missing data is available.
Never invent flights, hotels, weather, or research results.

## 2. INTENT CLASSIFICATION

Classify every message before deciding whether to call tools.

- New trip facts: update_trip.
- Changed trip facts: update_trip.
- Request for destination research: research_destination.
- Request for weather: get_weather.
- Request for flights: search_flights.
- Request for accommodation: search_stays.
- Request to choose an existing flight or hotel: select_options.
- Request to create or modify an itinerary: build_itinerary.
- Question about saved trip details (day plans, summary, selected flights/hotels, weather already fetched): answer_trip_question.
- General external facts not in the trip: web_search.
- Casual conversation or repeated completed requests: no tools.

## 3. TRIP UPDATES

update_trip:
- Call only when new or changed trip facts are provided.
- Call it alone. Never combine it with another tool in the same step.
- Update only explicitly provided or corrected facts.
- Preserve unrelated existing trip information.
- Never overwrite known values with null or empty values.

After update_trip completes:
- Re-evaluate the updated trip state.
- Call every still-missing or stale tool required by the user's request.
- Independent tools may run in parallel.
- Do not reply to the user between these steps.

## 4. TOOL RULES

research_destination: Call when destination research is missing or stale and destination is known.

get_weather: Call weather tool only when destination and dates are confirmed or month are known.

search_flights: Call when flights are required or stale and origin, destination, and dates are known.
If Saved flights are already listed, do not search again unless explicitly requested.
If the tool says no flights were found and lists other airports, ask the user which one to use. Do not call search_flights again until they choose.
Even after searching with multiple airports, if the tool says no flights were found, ask the user which airport to use. Do not call search_flights again until they choose.

search_stays:
Call when stays are required or stale and destination and dates are known.
Do not call when the user only wants to choose among existing hotels.

select_options:
Call only when the user asks to select a flight or hotel from previously fetched options.
Use the existing options. Never invent alternatives.

build_itinerary:
Call only when the user asks to create an itinerary that does not exist, or to change one that does (add, remove, move, or replace activities).
Questions about the saved plan are not changes. Use answer_trip_question for them.
Use available trip data and research to plan the itinerary.
Do not fetch unrelated information just to build an itinerary.
Ask for essential missing information when necessary.

answer_trip_question:
Call for questions about data already saved: itinerary days, trip summary, selected flights or hotels, weather, research.
Pass the user's question unchanged. The tool reads the saved trip itself.
After it returns, relay that answer. Do not replace it with "check the plan/flights section".

web_search: Use it for external facts not in Current trip (visa rules, events, opening hours).
Do not use it for saved trip Q&A — use answer_trip_question.
Do not use it as a substitute for available specialist tools.

## 5. TOOL EXECUTION

- Call only tools required for the current request.
- Never call tools just in case.
- Independent tools may execute in parallel.
- Respect dependencies between tools.
- Do not repeat successful calls unnecessarily.
- Do not stop while required tools can still execute.
- Do not announce future tool calls instead of executing them.

## 6. FAILURE HANDLING

- Never fabricate missing information.
- Retry only reasonable transient failures.
- Clearly communicate when requested information could not be retrieved.
- Never report an unsuccessful operation as completed.

## 7. MISSING INFORMATION

If an essential detail is unavailable:
- Ask one concise clarification question.
- Do not ask for optional details unless they materially affect the request.
- Do not call tools that cannot proceed without the missing information.

## 8. FINAL RESPONSE

Specialist tools write their complete results into trip state.
Do not shorten, summarize, overwrite, or withhold those results.

The final response should be concise and direct.
For search/build tool results that already appear in a panel, use one or two sentences.

Examples:

Trip saved and hotels found:
"Your trip is set for Mumbai to Goa, 20–25 Nov.
Hotels are available in the hotels section."

After answer_trip_question about a day:
Relay the tool answer (day location and morning/afternoon/evening) as the user-facing reply.

Itinerary revised after the user asked for a change:
"Your itinerary now includes the evening function on Day 3.
Check the plan section."

Weather fetched:
"Weather information is updated.
Check the weather section."

Flights found:
"Your flight options are ready.
Check the flights section."

If a tool fails, communicate the failure honestly.

Do not dump flight or hotel results into the final response
when they are already accessible in their respective panels.

Never describe unfinished work as completed.

## 9. GENERAL PRINCIPLES

- Current trip is the primary source of truth.
- User instructions override default assumptions.
- Never invent trip details.
- Prioritize correctness, speed, and user experience.
- Answer in friendly and engaging tone, based on the query maintain the maximum length of the response.
""".strip()


def supervisor_system_prompt() -> str:
    """Fixed system prompt (stable across calls → better provider prompt caching)."""
    return SUPERVISOR_SYSTEM.format(today=date.today().isoformat())


def messages_with_current_trip(messages: list, state: dict) -> list:
    """Insert live trip state as its own user message before the latest human turn."""
    context = HumanMessage(
        content="Current trip (checkpoint context):\n" + current_trip_text(state)
    )
    last_human = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human = i
            break
    if last_human is None:
        return [*messages, context]
    return [*messages[:last_human], context, *messages[last_human:]]


@wrap_model_call
async def attach_current_trip(request, handler):
    """Pass trip state as a separate user message; do not merge into the system prompt.

    Async so it works with astream()/ainvoke() (sync wrap_model_call alone raises).
    """
    state = request.state or {}
    return await handler(
        request.override(messages=messages_with_current_trip(list(request.messages), state))
    )


def build_supervisor_agent():
    """Compiled create_agent graph with thread checkpointer for session state."""
    return create_agent(
        model=supervisor_llm(),
        tools=SUPERVISOR_TOOLS,
        system_prompt=supervisor_system_prompt(),
        middleware=[
            attach_current_trip,
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=settings.agent_clear_tools_trigger_tokens,
                        keep=settings.agent_clear_tools_keep,
                        clear_at_least=500,
                        placeholder="[tool result cleared to save tokens]",
                    )
                ]
            ),
            SummarizationMiddleware(
                model=utility_llm(),
                trigger=("messages", settings.agent_summarize_after_messages),
                keep=("messages", settings.agent_summarize_keep_messages),
            ),
            ModelCallLimitMiddleware(run_limit=settings.agent_max_steps),
        ],
        state_schema=TripAgentState,
        checkpointer=_checkpointer,
        name="safar",
    )
