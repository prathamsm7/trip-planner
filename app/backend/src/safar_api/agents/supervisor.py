"""Trip planner agent — prompt, current-trip context, and the compiled supervisor."""

from __future__ import annotations

from datetime import date

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
    wrap_model_call,
)
from langchain_core.messages import HumanMessage

from safar_api.agents.selections import selections_prompt_block
from safar_api.agents.state_bridge import brief_from_state
from safar_api.agents.tools import SUPERVISOR_TOOLS, TOOL_LABELS
from safar_api.agents.trip_agent_state import TripAgentState
from safar_api.config import settings
from safar_api.nodes.guardrail import guardrail_middleware
from safar_api.services.llm import supervisor_llm, utility_llm
from safar_api.trip.brief import TripBrief
from safar_api.trip.persistence import get_checkpointer


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


def current_trip_text(state: dict) -> str:
    """Lean checkpoint — brief, statuses, and short selections only (no catalogs)."""
    brief = brief_from_state(state)
    lines = [f"Brief: {brief_summary(brief)}"]
    for name in ("research", "weather", "flights", "trains", "stays", "itinerary"):
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
        elif name == "trains" and data:
            origin_code = (data.get("origin_station") or {}).get("code") or "?"
            destination_code = (data.get("destination_station") or {}).get("code") or "?"
            lines.append(
                f"- trains: {status} stations={origin_code}→{destination_code} "
                f"searched={bool(data.get('searched'))} "
                f"outbound={len(data.get('outbound') or [])} "
                f"return={len(data.get('return') or [])}"
            )
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
- A stale itinerary means selections changed. Ask before rewriting it. Do not refresh it in the same turn.

Never assume missing data is available.
Never invent flights, hotels, weather, or research results.

## 2. INTENT CLASSIFICATION

Classify every message before deciding whether to call tools.

- New trip facts: update_trip.
- Changed trip facts: update_trip.
- Request for destination research: research_destination.
- Request for weather: get_weather.
- Request for flights: search_flights.
- Request for trains: search_railway_stations, then search_trains.
- Request for a bus or a car: bus and car search are not available. Say so. Do not invent those results.
- Request for accommodation: search_stays.
- Request to choose an existing flight, train, or hotel: select_options. Do not rewrite the itinerary in that turn.
- Request to create an itinerary when none exists: build_itinerary.
- Request to finalize the plan, or to update the plan after a selection: ask for confirmation. Do not call build_itinerary yet.
- Request to add, remove, or move a specific activity: build_itinerary.
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
- Call every search the user asked for in that message. A flight and a train in the same message are both required.
- Call search_flights and search_railway_stations in the same step when both were asked and their arguments are known. Call search_trains in the next step, after station codes are saved.
- Call a search only when its arguments are available. If origin, destination, or a required date is missing, ask for that and do not call the tool.
- Do not use transport_mode to skip a search the user asked for, and do not search a mode the user did not mention.
- Independent tools may run in parallel.
- Do not reply to the user between these steps.

## 4. TOOL RULES

research_destination: Call when destination research is missing or stale and destination is known.

get_weather: Call weather tool only when destination and dates are confirmed or month are known.

search_flights: Call when the user asked for a flight and origin, destination, and dates are known. Do not skip it because the trip also asks for a train.
Search the outbound flight by passing start_date. Pass end_date only when the user asked for a return or a round trip. Omit end_date otherwise. A saved end date is not a return request. For a return-only request, pass end_date and omit start_date.
If saved flights are already listed, do not search again unless explicitly requested.
If the tool says no flights were found and lists other airports, ask the user which one to use. Do not call search_flights again until they choose.
Even after searching with multiple airports, if the tool says no flights were found, ask the user which airport to use. Do not call search_flights again until they choose.

search_railway_stations: Call when the user asked for a train and the city names are known. Pass those cities. It finds the nearest railway stations and their station codes from the web, at most 3 per city. Run it in the same step as search_flights when the user asked for both.
Call it at most 3 times. If it says no station codes were found, or that it already ran 3 times, tell the user and stop. Do not call search_trains.
search_trains: Call only after station codes are saved. RailCore from and to must be those station codes, never the city name.
Search the outbound trains by passing start_date. Pass end_date only when the user asked for a return or a round trip. Omit end_date otherwise. A saved end date is not a return request. For a return-only request, pass end_date and omit start_date.
Call it at most 3 times. It searches trains for the primary station pair only.
If it says no trains were found, tell the user and ask them to choose another saved station. Do not search again until they choose.
When they choose, call search_trains with that station in origin_station or destination_station.
If it says the search already ran 3 times, tell the user and stop.

search_stays:
Call when stays are required or stale and destination and dates are known.
Do not call when the user only wants to choose among existing hotels.

select_options:
Call only when the user asks to select a flight, train, or hotel from previously fetched options.
Use the existing options. Never invent alternatives.
For a train, pass outbound_train_pref or return_train_pref. Do not pass the city name.

build_itinerary:
Call when the user asks to create an itinerary and none exists.
Call when the user asks to add, remove, move, or replace a specific activity.
Questions about the saved plan are not changes. Use answer_trip_question for them.
If a plan already exists and the user selects a flight, train, or hotel, or asks to finalize or update the plan, do not call this tool.
Ask exactly: "Update the day plan around your selected flights, trains, and hotels?"
Call this tool only after they agree in a later message.
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

Specialist tools save their results into trip state. The panels show those results.
Never paste a tool's raw status into the chat. That includes lines such as
"Updated fields: ..." and "Found 20 stays in Goa. Shortlist: ...".

The final response should be concise and direct.
For search or build results that already appear in a panel, use one or two sentences.

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
            *guardrail_middleware(),
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
        checkpointer=get_checkpointer(),
        name="safar",
    )
