"""Resolve UI selections (indices) into concrete flight, train, and hotel details."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_HOTEL_CAP = 3


def _hotel_indices(raw: Any) -> list[int]:
    chosen: list[int] = []
    for index in raw or []:
        if isinstance(index, int) and index not in chosen:
            chosen.append(index)
        if len(chosen) == _HOTEL_CAP:
            break
    return chosen


def _flight_list(bundle: dict | None) -> list[dict]:
    if not isinstance(bundle, dict):
        return []
    return list(bundle.get("best_flights") or []) + list(bundle.get("other_flights") or [])


def _summarize_flight(flight: dict | None) -> dict[str, Any] | None:
    if not isinstance(flight, dict):
        return None
    legs = flight.get("flights") or []
    first = legs[0] if legs else {}
    last = legs[-1] if legs else first
    dep = first.get("departure_airport") or {}
    arr = last.get("arrival_airport") or {}
    return {
        "airline": first.get("airline") or "",
        "flight_number": first.get("flight_number") or "",
        "departure_airport": dep.get("id") or "",
        "departure_time": dep.get("time") or "",
        "arrival_airport": arr.get("id") or "",
        "arrival_time": arr.get("time") or "",
        "duration_min": flight.get("total_duration"),
        "price": flight.get("price"),
        "stops": max(0, len(legs) - 1),
    }


def _summarize_hotel(prop: dict | None) -> dict[str, Any] | None:
    if not isinstance(prop, dict):
        return None
    rate = prop.get("rate_per_night") or {}
    return {
        "name": prop.get("name") or "",
        "rating": prop.get("overall_rating"),
        "price_per_night": rate.get("extracted_lowest") or rate.get("lowest"),
        "type": prop.get("type") or "",
        "link": prop.get("link") or "",
    }


def _option_lists(state: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    flights_art = state.get("flights")
    flights_data: dict = {}
    if isinstance(flights_art, dict):
        flights_data = flights_art.get("data") or flights_art

    outbound = _flight_list(
        flights_data.get("outbound") if isinstance(flights_data.get("outbound"), dict) else None
    )
    return_list = _flight_list(
        flights_data.get("return_flights")
        if isinstance(flights_data.get("return_flights"), dict)
        else None
    )

    stays_art = state.get("stays")
    stays_data: dict = {}
    if isinstance(stays_art, dict):
        stays_data = stays_art.get("data") or stays_art
    properties = list(stays_data.get("properties") or [])
    return outbound, return_list, properties


def _train_lists(state: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    art = state.get("trains")
    data: dict = {}
    if isinstance(art, dict):
        data = art.get("data") or art
    if not isinstance(data, dict):
        return [], []
    outbound = data.get("outbound") if isinstance(data.get("outbound"), list) else []
    returning = data.get("return") if isinstance(data.get("return"), list) else []
    return [row for row in outbound if isinstance(row, dict)], [row for row in returning if isinstance(row, dict)]


def _train_fare(train: dict) -> tuple[float | None, str]:
    best: tuple[float, str] | None = None
    for row in train.get("availability") or []:
        if not isinstance(row, dict):
            continue
        fare = row.get("fare")
        if not isinstance(fare, (int, float)):
            continue
        label = str(row.get("class_label") or row.get("class_code") or "")
        if best is None or float(fare) < best[0]:
            best = (float(fare), label)
    return (best[0], best[1]) if best else (None, "")


def _summarize_train(train: dict | None) -> dict[str, Any] | None:
    if not isinstance(train, dict):
        return None
    fare, fare_class = _train_fare(train)
    return {
        "train_number": train.get("train_number") or "",
        "train_name": train.get("train_name") or "",
        "from_station_code": train.get("from_station_code") or "",
        "from_station_name": train.get("from_station_name") or "",
        "to_station_code": train.get("to_station_code") or "",
        "to_station_name": train.get("to_station_name") or "",
        "departure_time": train.get("departure_time") or "",
        "arrival_time": train.get("arrival_time") or "",
        "fare": fare,
        "fare_class": fare_class,
    }


def resolve_selections(state: dict[str, Any]) -> dict[str, Any]:
    """Turn selection indices + artifacts into concrete options the LLM can use."""
    selections = state.get("selections") or {}
    if not isinstance(selections, dict):
        selections = {}

    outbound, return_list, properties = _option_lists(state)
    outbound_trains, return_trains = _train_lists(state)

    out_idx = selections.get("outboundFlightIndex")
    ret_idx = selections.get("returnFlightIndex")
    out_train_idx = selections.get("outboundTrainIndex")
    ret_train_idx = selections.get("returnTrainIndex")
    hotel_indices = _hotel_indices(selections.get("hotelIndices"))

    selected_outbound = None
    selected_return = None
    if isinstance(out_idx, int) and 0 <= out_idx < len(outbound):
        selected_outbound = _summarize_flight(outbound[out_idx])
    if isinstance(ret_idx, int) and 0 <= ret_idx < len(return_list):
        selected_return = _summarize_flight(return_list[ret_idx])

    selected_outbound_train = None
    selected_return_train = None
    if isinstance(out_train_idx, int) and 0 <= out_train_idx < len(outbound_trains):
        selected_outbound_train = _summarize_train(outbound_trains[out_train_idx])
    if isinstance(ret_train_idx, int) and 0 <= ret_train_idx < len(return_trains):
        selected_return_train = _summarize_train(return_trains[ret_train_idx])

    selected_hotels = []
    for idx in hotel_indices:
        if isinstance(idx, int) and 0 <= idx < len(properties):
            summary = _summarize_hotel(properties[idx])
            if summary:
                selected_hotels.append(summary)

    return {
        "indices": {
            "outboundFlightIndex": out_idx,
            "returnFlightIndex": ret_idx,
            "outboundTrainIndex": out_train_idx,
            "returnTrainIndex": ret_train_idx,
            "hotelIndices": hotel_indices,
        },
        "outbound_flight": selected_outbound,
        "return_flight": selected_return,
        "outbound_train": selected_outbound_train,
        "return_train": selected_return_train,
        "hotels": selected_hotels,
        "available": {
            "outbound_options": len(outbound),
            "return_options": len(return_list),
            "outbound_trains": len(outbound_trains),
            "return_trains": len(return_trains),
            "hotel_options": len(properties),
        },
    }


def _parse_hour(time_str: str | None) -> int | None:
    if not time_str:
        return None
    text = str(time_str).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(text, fmt).hour
        except ValueError:
            continue
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            return hour
    return None


def _time_bucket(hour: int | None) -> str:
    if hour is None:
        return "unknown"
    if 4 <= hour < 9:
        return "early_morning"
    if 9 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "late_night"


def _pref_buckets(pref: str) -> set[str]:
    p = (pref or "").lower()
    buckets: set[str] = set()
    if any(k in p for k in ("early morning", "early-morning", "dawn", "red-eye outbound")):
        buckets.add("early_morning")
    if "late night" in p or "late-night" in p or "midnight" in p or "night flight" in p:
        buckets.add("late_night")
    if "evening" in p:
        buckets.add("evening")
    if "afternoon" in p:
        buckets.add("afternoon")
    if re.search(r"\bmorning\b", p) and "early" not in p:
        buckets.add("morning")
        buckets.add("early_morning")
    if "night" in p and "late" not in p and "midnight" not in p:
        buckets.add("late_night")
        buckets.add("evening")
    return buckets


def _price_value(raw: Any) -> float:
    if raw is None:
        return float("inf")
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"[\d.]+", str(raw).replace(",", ""))
    return float(m.group(0)) if m else float("inf")


def _flight_score(flight: dict, pref: str) -> float:
    summary = _summarize_flight(flight) or {}
    p = (pref or "").lower().strip()
    if not p:
        return 0.0
    score = 0.0
    hour = _parse_hour(summary.get("departure_time"))
    bucket = _time_bucket(hour)
    wanted = _pref_buckets(p)
    if wanted:
        if bucket in wanted:
            score += 100
        else:
            score -= 40
        # Prefer earlier within early_morning, later within late_night
        if hour is not None and "early_morning" in wanted and bucket == "early_morning":
            score += max(0, 9 - hour) * 2
        if hour is not None and "late_night" in wanted and bucket == "late_night":
            score += (hour if hour >= 21 else hour + 24) - 21

    if "nonstop" in p or "non-stop" in p or "direct" in p:
        score += 30 if (summary.get("stops") or 0) == 0 else -20
    if "cheap" in p or "lowest" in p or "budget" in p:
        score += max(0, 50 - min(50, _price_value(summary.get("price")) / 500))
    if "fast" in p or "shortest" in p:
        dur = summary.get("duration_min") or 9999
        score += max(0, 40 - min(40, float(dur) / 15))

    airline = (summary.get("airline") or "").lower()
    flight_no = (summary.get("flight_number") or "").lower()
    if airline and airline in p:
        score += 50
    if flight_no and flight_no.replace(" ", "") in p.replace(" ", ""):
        score += 80

    # Mild preference for cheaper when scores tie
    score -= min(10, _price_value(summary.get("price")) / 5000)
    return score


def _pick_flight_index(flights: list[dict], pref: str | None) -> int | None:
    if not flights or not (pref or "").strip():
        return None
    scored = [(_flight_score(f, pref or ""), i) for i, f in enumerate(flights)]
    scored.sort(key=lambda x: (-x[0], x[1]))
    best_score, best_i = scored[0]
    if best_score < 20:
        return None
    return best_i


def _hotel_score(prop: dict, pref: str) -> float:
    summary = _summarize_hotel(prop) or {}
    p = (pref or "").lower().strip()
    if not p:
        return 0.0
    score = 0.0
    name = (summary.get("name") or "").lower()
    if name and any(tok and tok in name for tok in re.split(r"\W+", p) if len(tok) > 3):
        score += 60
    rating = summary.get("rating")
    try:
        rating_f = float(rating) if rating is not None else 0.0
    except (TypeError, ValueError):
        rating_f = 0.0
    if "best" in p or "top rated" in p or "highest rated" in p:
        score += rating_f * 15
    if "cheap" in p or "budget" in p or "lowest" in p:
        score += max(0, 40 - min(40, _price_value(summary.get("price_per_night")) / 400))
    if "luxury" in p or "premium" in p:
        score += rating_f * 10
        score += min(20, _price_value(summary.get("price_per_night")) / 1000)
    score += rating_f * 2
    score -= min(8, _price_value(summary.get("price_per_night")) / 8000)
    return score


def _train_score(train: dict, pref: str) -> float:
    summary = _summarize_train(train) or {}
    p = (pref or "").lower().strip()
    if not p:
        return 0.0
    score = 0.0
    number = str(summary.get("train_number") or "").lower()
    name = str(summary.get("train_name") or "").lower()
    if number and number in p.replace(" ", ""):
        score += 80
    if name and any(tok and tok in name for tok in re.split(r"\W+", p) if len(tok) > 3):
        score += 50
    hour = _parse_hour(summary.get("departure_time"))
    bucket = _time_bucket(hour)
    wanted = _pref_buckets(p)
    if wanted:
        score += 100 if bucket in wanted else -40
    if "cheap" in p or "lowest" in p or "budget" in p:
        fare = summary.get("fare")
        score += max(0, 40 - min(40, _price_value(fare) / 200))
    score -= min(8, _price_value(summary.get("fare")) / 5000)
    return score


def _pick_train_index(trains: list[dict], pref: str | None) -> int | None:
    if not trains or not (pref or "").strip():
        return None
    scored = [(_train_score(train, pref or ""), i) for i, train in enumerate(trains)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_i = scored[0]
    if best_score < 20:
        return None
    return best_i


def _pick_hotel_index(properties: list[dict], pref: str | None) -> int | None:
    if not properties or not (pref or "").strip():
        return None
    scored = [(_hotel_score(p, pref or ""), i) for i, p in enumerate(properties)]
    scored.sort(key=lambda x: (-x[0], x[1]))
    best_score, best_i = scored[0]
    if best_score < 10:
        return None
    return best_i


def apply_selection_preferences(
    state: dict[str, Any],
    *,
    outbound_pref: str | None = None,
    return_pref: str | None = None,
    hotel_pref: str | None = None,
    outbound_train_pref: str | None = None,
    return_train_pref: str | None = None,
    outbound_index: int | None = None,
    return_index: int | None = None,
    hotel_index: int | None = None,
    outbound_train_index: int | None = None,
    return_train_index: int | None = None,
) -> tuple[dict[str, Any], str]:
    """
    Update selections from explicit indices and/or natural-language prefs.

    Returns (merged_selections, observation_text).
    """
    outbound, return_list, properties = _option_lists(state)
    outbound_trains, return_trains = _train_lists(state)
    current = dict(state.get("selections") or {})
    notes: list[str] = []

    if outbound_index is not None:
        if 0 <= outbound_index < len(outbound):
            current["outboundFlightIndex"] = outbound_index
            notes.append(f"outbound index={outbound_index}")
        else:
            notes.append(f"outbound index {outbound_index} out of range (0-{len(outbound) - 1})")
    elif outbound_pref:
        if not outbound:
            notes.append("no outbound flights available — search_flights first")
        else:
            idx = _pick_flight_index(outbound, outbound_pref)
            if idx is None:
                notes.append(f"no outbound match for {outbound_pref!r}")
            else:
                current["outboundFlightIndex"] = idx
                s = _summarize_flight(outbound[idx]) or {}
                notes.append(
                    f"outbound→ {s.get('airline')} {s.get('flight_number')} "
                    f"{s.get('departure_time')} (#{idx})"
                )

    if return_index is not None:
        if 0 <= return_index < len(return_list):
            current["returnFlightIndex"] = return_index
            notes.append(f"return index={return_index}")
        else:
            notes.append(f"return index {return_index} out of range (0-{len(return_list) - 1})")
    elif return_pref:
        if not return_list:
            notes.append("no return flights available — search_flights first")
        else:
            idx = _pick_flight_index(return_list, return_pref)
            if idx is None:
                notes.append(f"no return match for {return_pref!r}")
            else:
                current["returnFlightIndex"] = idx
                s = _summarize_flight(return_list[idx]) or {}
                notes.append(
                    f"return→ {s.get('airline')} {s.get('flight_number')} "
                    f"{s.get('departure_time')} (#{idx})"
                )

    if outbound_train_index is not None:
        if 0 <= outbound_train_index < len(outbound_trains):
            current["outboundTrainIndex"] = outbound_train_index
            notes.append(f"outbound train index={outbound_train_index}")
        else:
            notes.append(
                f"outbound train index {outbound_train_index} out of range (0-{len(outbound_trains) - 1})"
            )
    elif outbound_train_pref:
        if not outbound_trains:
            notes.append("no outbound trains available — search_trains first")
        else:
            idx = _pick_train_index(outbound_trains, outbound_train_pref)
            if idx is None:
                notes.append(f"no outbound train match for {outbound_train_pref!r}")
            else:
                current["outboundTrainIndex"] = idx
                s = _summarize_train(outbound_trains[idx]) or {}
                notes.append(f"outbound train→ {s.get('train_number')} {s.get('train_name')} (#{idx})")

    if return_train_index is not None:
        if 0 <= return_train_index < len(return_trains):
            current["returnTrainIndex"] = return_train_index
            notes.append(f"return train index={return_train_index}")
        else:
            notes.append(
                f"return train index {return_train_index} out of range (0-{len(return_trains) - 1})"
            )
    elif return_train_pref:
        if not return_trains:
            notes.append("no return trains available — search_trains first")
        else:
            idx = _pick_train_index(return_trains, return_train_pref)
            if idx is None:
                notes.append(f"no return train match for {return_train_pref!r}")
            else:
                current["returnTrainIndex"] = idx
                s = _summarize_train(return_trains[idx]) or {}
                notes.append(f"return train→ {s.get('train_number')} {s.get('train_name')} (#{idx})")

    if hotel_index is not None:
        if 0 <= hotel_index < len(properties):
            current["hotelIndices"] = [hotel_index]
            notes.append(f"hotel index={hotel_index}")
        else:
            notes.append(f"hotel index {hotel_index} out of range (0-{len(properties) - 1})")
    elif hotel_pref:
        if not properties:
            notes.append("no hotels available — search_stays first")
        else:
            idx = _pick_hotel_index(properties, hotel_pref)
            if idx is None:
                notes.append(f"no hotel match for {hotel_pref!r}")
            else:
                current["hotelIndices"] = [idx]
                s = _summarize_hotel(properties[idx]) or {}
                notes.append(f"hotel→ {s.get('name')} (#{idx})")

    obs = "; ".join(notes) if notes else "no selection changes"
    return current, obs


def _catalog_flight_lines(flights: list[dict], label: str, limit: int = 20) -> list[str]:
    if not flights:
        return [f"{label}: none"]
    lines = [f"{label} ({len(flights)}):"]
    for i, flight in enumerate(flights[:limit]):
        s = _summarize_flight(flight) or {}
        lines.append(
            f"  #{i} {s.get('airline')} {s.get('flight_number')} "
            f"{s.get('departure_airport')} {s.get('departure_time')} → "
            f"{s.get('arrival_airport')} {s.get('arrival_time')} "
            f"₹{s.get('price')} stops={s.get('stops')}"
        )
    extra = len(flights) - limit
    if extra > 0:
        lines.append(f"  … {extra} more")
    return lines


def flight_catalog_block(state: dict[str, Any]) -> str:
    """One line per saved flight so the assistant can answer from state."""
    outbound, return_list, _properties = _option_lists(state)
    if not outbound and not return_list:
        return ""
    lines = ["Saved flights (use these; do not re-search):"]
    lines.extend(_catalog_flight_lines(outbound, "Outbound"))
    lines.extend(_catalog_flight_lines(return_list, "Return"))
    return "\n".join(lines)


def selections_prompt_block(state: dict[str, Any]) -> str:
    """Human-readable block for the supervisor system prompt."""
    resolved = resolve_selections(state)
    lines = ["Selections:"]
    avail = resolved["available"]
    lines.append(
        f"  available: outbound={avail['outbound_options']} "
        f"return={avail['return_options']} "
        f"outbound_trains={avail['outbound_trains']} return_trains={avail['return_trains']} "
        f"hotels={avail['hotel_options']}"
    )
    out = resolved.get("outbound_flight")
    if out:
        lines.append(
            "  SELECTED outbound: "
            f"{out.get('airline')} {out.get('flight_number')} "
            f"{out.get('departure_airport')} {out.get('departure_time')} → "
            f"{out.get('arrival_airport')} {out.get('arrival_time')} "
            f"(₹{out.get('price')}, {out.get('stops')} stops)"
        )
    else:
        lines.append("  SELECTED outbound: none")
    ret = resolved.get("return_flight")
    if ret:
        lines.append(
            "  SELECTED return: "
            f"{ret.get('airline')} {ret.get('flight_number')} "
            f"{ret.get('departure_airport')} {ret.get('departure_time')} → "
            f"{ret.get('arrival_airport')} {ret.get('arrival_time')} "
            f"(₹{ret.get('price')}, {ret.get('stops')} stops)"
        )
    else:
        lines.append("  SELECTED return: none")
    out_train = resolved.get("outbound_train")
    if out_train:
        lines.append(
            "  SELECTED outbound train: "
            f"{out_train.get('train_number')} {out_train.get('train_name')} "
            f"{out_train.get('from_station_code')} {out_train.get('departure_time')} → "
            f"{out_train.get('to_station_code')} {out_train.get('arrival_time')} "
            f"(₹{out_train.get('fare')} {out_train.get('fare_class')})"
        )
    else:
        lines.append("  SELECTED outbound train: none")
    ret_train = resolved.get("return_train")
    if ret_train:
        lines.append(
            "  SELECTED return train: "
            f"{ret_train.get('train_number')} {ret_train.get('train_name')} "
            f"{ret_train.get('from_station_code')} {ret_train.get('departure_time')} → "
            f"{ret_train.get('to_station_code')} {ret_train.get('arrival_time')} "
            f"(₹{ret_train.get('fare')} {ret_train.get('fare_class')})"
        )
    else:
        lines.append("  SELECTED return train: none")
    hotels = resolved.get("hotels") or []
    if hotels:
        for h in hotels[:3]:
            lines.append(
                f"  SELECTED hotel: {h.get('name')} "
                f"(₹{h.get('price_per_night')}/night, rating={h.get('rating')})"
            )
    else:
        lines.append("  SELECTED hotels: none")
    return "\n".join(lines)
