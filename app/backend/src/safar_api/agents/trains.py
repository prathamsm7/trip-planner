"""Station codes come from a web search. Trains come from RailCore /routes/trains."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from safar_api.agents.base import AgentResult
from safar_api.logging_config import log_exception
from safar_api.services.llm import utility_llm
from safar_api.services.railcore_client import trains_on_route
from safar_api.services.serpapi_client import search_ai_overview
from safar_api.trip.brief import TripUpdate, apply_trip_update
from safar_api.trip.results import make_artifact
from safar_api.trip.state import AgentState

logger = logging.getLogger(__name__)

_CODE = re.compile(r"^[A-Z0-9]{2,6}$")
_MAX = 3
_CLASS_LABELS = {
    "1A": "AC First",
    "2A": "AC 2 Tier",
    "3A": "AC 3 Tier",
    "3E": "AC 3 Economy",
    "SL": "Sleeper",
    "CC": "Chair Car",
    "EC": "Executive Chair",
    "2S": "Second Sitting",
    "FC": "First Class",
}
_TYPE_LABELS = {
    "SF": "Superfast",
    "EXP": "Express",
    "MAIL": "Mail",
    "PASS": "Passenger",
    "RAJ": "Rajdhani",
    "SHT": "Shatabdi",
    "VAN": "Vande Bharat",
    "DRNT": "Duronto",
    "GR": "Garib Rath",
}


class _Station(BaseModel):
    name: str = ""
    code: str = ""


class _StationList(BaseModel):
    origin_stations: list[_Station] = Field(default_factory=list)
    destination_stations: list[_Station] = Field(default_factory=list)


def _evidence(raw: dict) -> str:
    for key in ("reconstructed_markdown", "text", "answer", "markdown"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:12000]
    return ""


def stations_from_web(origin: str, destination: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Web-search the nearest railway stations and their codes for each city."""
    query = (
        f"Nearest Indian Railways stations to {origin} and their official station codes. "
        f"Nearest Indian Railways stations to {destination} and their official station codes. "
        "Include the main station and two other nearby stations for each city."
    )
    logger.info("station web search | origin=%r destination=%r", origin, destination)
    evidence = _evidence(search_ai_overview(query))
    if not evidence.strip():
        return [], []
    result = utility_llm().with_structured_output(_StationList).invoke(
        [
            SystemMessage(
                content=(
                    "List the nearest railway stations from the web result. "
                    "Put the nearest main station first, then up to two other nearby stations in that city. "
                    "code is the official station code printed on the page, such as CSTM or MAO. "
                    "Leave code empty when the page does not print one. "
                    "Never use the city name as a code. Goa is not GOA. Mumbai is not MUMBAI."
                    "DO not guess the code. If the page does not print one, leave it empty."
                    "Return only in json format. Do not return any other text."
                )
            ),
            HumanMessage(
                content=f"Origin city: {origin}\nDestination city: {destination}\n\n{evidence}"
            ),
        ]
    )
    data = result.model_dump()

    def printed(items: list) -> list[dict[str, str]]:
        kept = []
        for item in items or []:
            code = str((item or {}).get("code") or "").strip().upper()
            if code and not re.search(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])", evidence):
                item = {**(item or {}), "code": ""}
            kept.append(item)
        return kept

    return printed(data.get("origin_stations")), printed(data.get("destination_stations"))


_GENERIC_NAME = {"station", "stations", "railway", "railways", "rail", "the", "and", "of", "city"}


def _city_key(city: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (city or "").upper())


def _name_is_city(name: str, city: str) -> bool:
    words = [word for word in re.findall(r"[a-z0-9]+", name.lower()) if word not in _GENERIC_NAME]
    city_words = re.findall(r"[a-z0-9]+", (city or "").lower())
    return words == city_words or not words


def _coded(stations: list, city: str) -> list[dict[str, str]]:
    chosen: list[dict[str, str]] = []
    seen: set[str] = set()
    city_key = _city_key(city)
    for item in stations or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        name = str(item.get("name") or "").strip() or code
        if not _CODE.match(code) or code in seen:
            continue
        if code == city_key and _name_is_city(name, city):
            continue
        seen.add(code)
        chosen.append({"code": code, "name": name})
        if len(chosen) == _MAX:
            break
    return chosen


def _data(state: AgentState) -> dict[str, Any]:
    raw = state.trains
    if raw is None:
        return {}
    data = getattr(raw, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(raw, dict):
        nested = raw.get("data")
        return nested if isinstance(nested, dict) else raw
    return {}


def _tries(data: dict[str, Any], key: str) -> int:
    try:
        return int(data.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _open_try(state: AgentState, key: str, label: str) -> tuple[AgentResult | None, dict[str, Any]]:
    data = dict(_data(state))
    if _tries(data, key) >= _MAX:
        return (
            AgentResult(
                status="failed",
                summary=f"{label} already ran 3 times. Tell the user and do not call this tool again.",
                error="retry_limit",
            ),
            data,
        )
    data[key] = _tries(data, key) + 1
    return None, data


def _save(brief, payload: dict[str, Any], counted: dict[str, Any]) -> dict[str, Any]:
    merged = dict(counted)
    merged.update(payload)
    merged["station_attempts"] = _tries(counted, "station_attempts")
    merged["train_attempts"] = _tries(counted, "train_attempts")
    return {"trains": make_artifact("trains", brief, merged)}


def _side(stations: list[dict[str, str]], side: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tagged = [{**station, "side": side, "kind": "fallback"} for station in stations]
    if not tagged:
        return {}, []
    primary = {**tagged[0], "kind": "primary"}
    return primary, tagged[1:]


def _saved(data: dict[str, Any], side: str) -> list[dict[str, Any]]:
    meta = data.get("station_meta") if isinstance(data.get("station_meta"), dict) else {}
    primary = meta.get(side) or data.get(f"{side}_station")
    fallbacks = meta.get(f"{side}_fallbacks") or []
    stations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for station in [primary, *fallbacks]:
        if not isinstance(station, dict):
            continue
        code = str(station.get("code") or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        stations.append(station)
    return stations


def _pick(stations: list[dict[str, Any]], preference: str) -> dict[str, Any]:
    pref = (preference or "").strip().lower()
    if not pref:
        return stations[0] if stations else {}
    for station in stations:
        code = str(station.get("code") or "")
        name = str(station.get("name") or "").lower()
        if code.lower() == pref or pref in name:
            return station
    return {}


def _payload(
    origin: dict[str, Any],
    origin_fallbacks: list[dict[str, Any]],
    destination: dict[str, Any],
    destination_fallbacks: list[dict[str, Any]],
    *,
    searched: bool | None = None,
    outbound: list | None = None,
    returning: list | None = None,
    start: str = "",
    end: str = "",
    ask_user: bool = False,
    write_outbound: bool = False,
    write_return: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "origin_station": origin,
        "destination_station": destination,
        "station_meta": {
            "origin": origin,
            "destination": destination,
            "origin_fallbacks": origin_fallbacks,
            "destination_fallbacks": destination_fallbacks,
        },
        "alternatives": {
            "primary_route": {
                "from": origin.get("code"),
                "from_name": origin.get("name"),
                "to": destination.get("code"),
                "to_name": destination.get("name"),
            },
            "fallback_stations": origin_fallbacks + destination_fallbacks,
            "ask_user": ask_user,
        },
    }
    if searched is not None:
        payload["searched"] = searched
    if write_outbound:
        payload["outbound"] = outbound or []
        payload["outbound_date"] = start
    if write_return:
        payload["return"] = returning or []
        payload["return_date"] = end
    return payload


def search_railway_stations(call: dict[str, Any], state: AgentState) -> AgentResult:
    """Find up to 3 station codes per city from the web. Does not search trains."""
    args = call.get("args") or {}
    brief = state.brief
    origin = (args.get("origin") or brief.origin or "").strip()
    destination = (args.get("destination") or brief.destination or "").strip()
    start = (args.get("start_date") or brief.start_date or "").strip()
    end = (args.get("end_date") or brief.end_date or "").strip()
    stopped, counted = _open_try(state, "station_attempts", "Station lookup")
    if stopped:
        return stopped
    if not origin or not destination:
        return AgentResult(
            status="failed",
            summary="Need an origin and a destination to look up railway stations.",
            error="missing_fields",
            updates=_save(brief, {}, counted),
        )
    brief, changed = apply_trip_update(
        brief,
        TripUpdate(
            origin=origin,
            destination=destination,
            start_date=start or None,
            end_date=end or None,
            transport_mode="train",
        ),
    )
    try:
        origin_codes, destination_codes = stations_from_web(origin, destination)
        origin_codes = _coded(origin_codes, origin)
        destination_codes = _coded(destination_codes, destination)
    except Exception as exc:
        log_exception(logger, "station web search failed", exc, context={"origin": origin})
        return AgentResult(
            status="failed",
            summary=f"Could not search the web for railway stations: {exc}",
            error="station_lookup",
            updates={**_save(brief, {}, counted), **({"brief": brief} if changed else {})},
        )
    if not origin_codes or not destination_codes:
        missing = [name for name, rows in ((origin, origin_codes), (destination, destination_codes)) if not rows]
        return AgentResult(
            status="failed",
            summary=f"No railway station codes found for {' or '.join(missing)}.",
            error="no_station",
            updates={**_save(brief, {}, counted), **({"brief": brief} if changed else {})},
        )
    origin_station, origin_fallbacks = _side(origin_codes, "origin")
    destination_station, destination_fallbacks = _side(destination_codes, "destination")
    others = origin_fallbacks + destination_fallbacks
    summary = (
        f"Found station codes. Primary {origin_station['name']} ({origin_station['code']}) → "
        f"{destination_station['name']} ({destination_station['code']})."
    )
    if others:
        summary += " Other stations: " + ", ".join(f"{item['name']} ({item['code']})" for item in others) + "."
    summary += " Search trains for the primary stations next."
    return AgentResult(
        status="complete",
        summary=summary,
        detail=f"Finding stations for {origin} and {destination}",
        updates={
            **_save(
                brief,
                _payload(
                    origin_station,
                    origin_fallbacks,
                    destination_station,
                    destination_fallbacks,
                    searched=True if _data(state).get("searched") else False,
                ),
                counted,
            ),
            **({"brief": brief} if changed else {}),
        },
    )


def _train(row: dict[str, Any]) -> dict[str, Any]:
    classes = [str(code) for code in (row.get("classes") or []) if code]
    train_type = str(row.get("train_type") or "")
    availability = []
    for item in row.get("availability_summary") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("class_code") or "")
        availability.append(
            {
                "class_code": code,
                "class_label": _CLASS_LABELS.get(code, code),
                "status": str(item.get("status") or ""),
                "text": str(item.get("text") or item.get("status") or ""),
                "fare": item.get("fare"),
            }
        )
    return {
        "train_number": str(row.get("train_number") or ""),
        "train_name": str(row.get("extended_train_name") or row.get("train_name") or ""),
        "train_type": train_type,
        "train_type_label": _TYPE_LABELS.get(train_type, train_type),
        "from_station_code": str(row.get("from_station_code") or ""),
        "from_station_name": str(row.get("from_station_name") or ""),
        "to_station_code": str(row.get("to_station_code") or ""),
        "to_station_name": str(row.get("to_station_name") or ""),
        "departure_time": str(row.get("departure_time") or ""),
        "arrival_time": str(row.get("arrival_time") or ""),
        "duration_minutes": row.get("duration_minutes"),
        "distance_km": row.get("distance_km"),
        "classes": [{"code": code, "label": _CLASS_LABELS.get(code, code)} for code in classes],
        "running_days": [str(day) for day in (row.get("running_days") or [])],
        "availability": availability,
    }


def _leg(origin: str, destination: str, journey_date: str) -> tuple[list[dict], str]:
    try:
        rows = trains_on_route(origin, destination, journey_date)
    except Exception as exc:
        log_exception(
            logger,
            "train route lookup failed",
            exc,
            context={"origin": origin, "destination": destination, "date": journey_date},
        )
        return [], str(exc)
    return [_train(row) for row in rows[:12]], ""


def search_trains(call: dict[str, Any], state: AgentState) -> AgentResult:
    """Search RailCore /routes/trains for stations already found on the web."""
    args = call.get("args") or {}
    brief = state.brief
    asked_start = (args.get("start_date") or "").strip()
    asked_end = (args.get("end_date") or "").strip()
    # The agent passes end_date only for a return. A saved trip end date does not.
    legs = {"return"} if asked_end else set()
    if asked_start or not asked_end:
        legs.add("outbound")
    start = asked_start or (brief.start_date or "").strip()
    end = asked_end
    stopped, counted = _open_try(state, "train_attempts", "Train search")
    if stopped:
        return stopped
    if "outbound" in legs and not start:
        return AgentResult(
            status="failed",
            summary="Need a departure date to search outbound trains.",
            error="missing_fields",
            updates=_save(brief, {}, counted),
        )
    if "return" in legs and not end:
        return AgentResult(
            status="failed",
            summary="Need a return date to search return trains.",
            error="missing_fields",
            updates=_save(brief, {}, counted),
        )
    saved = _data(state)
    origin_stations = _saved(saved, "origin")
    destination_stations = _saved(saved, "destination")
    if not origin_stations or not destination_stations:
        return AgentResult(
            status="failed",
            summary="No railway stations are saved. Find stations before searching trains.",
            error="no_station",
            updates=_save(brief, {}, counted),
        )
    origin = _pick(origin_stations, args.get("origin_station") or "")
    destination = _pick(destination_stations, args.get("destination_station") or "")
    if not origin or not destination:
        return AgentResult(
            status="failed",
            summary="That station is not in the saved list. Choose one of the stations already found.",
            error="no_station",
            updates=_save(brief, {}, counted),
        )
    outbound: list[dict] = []
    outbound_error = ""
    returning: list[dict] = []
    return_error = ""
    if "outbound" in legs:
        outbound, outbound_error = _leg(origin["code"], destination["code"], start)
    if "return" in legs:
        returning, return_error = _leg(destination["code"], origin["code"], end)
    origin_fallbacks = [station for station in origin_stations if station["code"] != origin["code"]]
    destination_fallbacks = [station for station in destination_stations if station["code"] != destination["code"]]
    fallbacks = origin_fallbacks + destination_fallbacks
    parts = []
    if "outbound" in legs:
        parts.append(
            f"{len(outbound)} trains {origin['name']} ({origin['code']}) → "
            f"{destination['name']} ({destination['code']}) on {start}."
        )
    if "return" in legs:
        parts.append(
            f"{len(returning)} return trains {destination['name']} ({destination['code']}) → "
            f"{origin['name']} ({origin['code']}) on {end}."
        )
    summary = " ".join(parts)
    if not outbound and not returning:
        if legs == {"return"}:
            route = f"{destination['name']} ({destination['code']}) → {origin['name']} ({origin['code']})"
            when = end
        else:
            route = f"{origin['name']} ({origin['code']}) → {destination['name']} ({destination['code']})"
            when = start
        summary = f"No trains for {route} on {when}."
        if fallbacks:
            labels = ", ".join(f"{station['name']} ({station['code']})" for station in fallbacks)
            summary += f" Ask the user to choose another station: {labels}."
    if outbound_error or return_error:
        summary += f" Lookup note: {outbound_error or return_error}"
    found = bool(outbound or returning)
    return AgentResult(
        status="complete" if found else "failed",
        summary=summary,
        detail=f"Searching trains {origin['code']} to {destination['code']}",
        error="" if found else (outbound_error or "no_trains"),
        updates=_save(
            brief,
            _payload(
                origin,
                origin_fallbacks,
                destination,
                destination_fallbacks,
                searched=True,
                outbound=outbound,
                returning=returning,
                start=start,
                end=end,
                ask_user=not found,
                write_outbound="outbound" in legs,
                write_return="return" in legs,
            ),
            counted,
        ),
    )
