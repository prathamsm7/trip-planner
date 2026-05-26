"""Deterministic follow-up: at most one question per required trip field."""

from __future__ import annotations

import datetime
import re

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import DateRange
from safar_api.services.llm import secondary_llm

REQUIRED_FIELDS = (
    "sourceLocation",
    "destinationLocation",
    "date_range",
    "budget",
    "travel_style",
    "mode_of_transport",
)

FIELD_QUESTIONS: dict[str, str] = {
    "sourceLocation": "Where are you traveling from?",
    "destinationLocation": "Where would you like to go?",
    "date_range": "What are your travel dates (start and end)?",
    "budget": "What is your budget — low, medium, or high?",
    "travel_style": "Who is traveling — solo, couple, family, friends, or business?",
    "mode_of_transport": "How would you like to travel — flight, train, bus, or car?",
}

_BUDGET_VALUES = ("low", "medium", "high")
_TRAVEL_STYLES = ("solo", "couple", "family", "friends", "business")
_TRANSPORT_MODES = ("flight", "train", "bus", "car")

_date_llm = secondary_llm().with_structured_output(
    DateRange,
    method="function_calling",
)


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def field_is_missing(structured: dict, field_key: str) -> bool:
    if field_key == "sourceLocation":
        return _blank(structured.get("sourceLocation"))
    if field_key == "destinationLocation":
        return _blank(structured.get("destinationLocation"))
    if field_key == "date_range":
        dr = structured.get("date_range") or {}
        return _blank(dr.get("start")) or _blank(dr.get("end"))
    if field_key == "budget":
        return structured.get("budget") is None
    if field_key == "travel_style":
        return structured.get("travel_style") is None
    if field_key == "mode_of_transport":
        return structured.get("mode_of_transport") is None
    return False


def pending_fields(structured: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if field_is_missing(structured, f)]


def apply_follow_up_to_structured(structured: dict) -> dict:
    """Set follow-up flags from missing required fields only (ignore LLM question lists)."""
    structured = dict(structured)
    structured.pop("follow_up_questions", None)
    missing = pending_fields(structured)
    structured["is_follow_up"] = bool(missing)
    structured["follow_up_questions"] = [FIELD_QUESTIONS[f] for f in missing]
    return structured


_STYLE_MIN_PEOPLE: dict[str, int] = {
    "solo": 1,
    "couple": 2,
    "family": 3,
    "friends": 2,
    "business": 1,
}


def with_planning_defaults(structured: dict) -> dict:
    """Fill defaults for downstream nodes once follow-up is complete."""
    out = dict(structured)
    if out.get("budget") is None:
        out["budget"] = "medium"
    if out.get("travel_style") is None:
        out["travel_style"] = "solo"
    if out.get("mode_of_transport") is None:
        out["mode_of_transport"] = "flight"
    style = out.get("travel_style", "solo")
    min_people = _STYLE_MIN_PEOPLE.get(style, 1)
    if (out.get("number_of_people") or 1) < min_people:
        out["number_of_people"] = min_people
    dr = out.get("date_range") or {}
    out.setdefault("date_range", {"start": dr.get("start") or "", "end": dr.get("end") or ""})
    dur = out.get("duration")
    if not dur:
        out["duration"] = {"min_days": 0, "max_days": 0}
    out["is_follow_up"] = False
    out["follow_up_questions"] = []
    return out


def _match_enum(answer: str, allowed: tuple[str, ...]) -> str | None:
    lower = answer.lower()
    for value in allowed:
        if re.search(rf"\b{re.escape(value)}\b", lower):
            return value
    return None


def _apply_date_range(structured: dict, answer: str) -> dict:
    today = datetime.date.today().isoformat()
    result = _date_llm.invoke(
        [
            SystemMessage(
                content=(
                    f"Today's date is {today}. Parse travel start and end dates from the user's answer. "
                    "Return ISO dates YYYY-MM-DD. Infer year from context when omitted."
                )
            ),
            HumanMessage(content=answer),
        ]
    )
    out = dict(structured)
    out["date_range"] = result.model_dump()
    return out


def apply_field_answer(structured: dict, field_key: str, answer: str) -> dict:
    """Merge one follow-up reply into structured so we stop asking for that field."""
    text = answer.strip()
    out = dict(structured)

    if field_key == "sourceLocation":
        out["sourceLocation"] = text
    elif field_key == "destinationLocation":
        out["destinationLocation"] = text
    elif field_key == "budget":
        matched = _match_enum(text, _BUDGET_VALUES)
        if matched:
            out["budget"] = matched
    elif field_key == "travel_style":
        matched = _match_enum(text, _TRAVEL_STYLES)
        if matched:
            out["travel_style"] = matched
    elif field_key == "mode_of_transport":
        matched = _match_enum(text, _TRANSPORT_MODES)
        if matched:
            out["mode_of_transport"] = matched
    elif field_key == "date_range":
        out = _apply_date_range(out, text)

    return apply_follow_up_to_structured(out)
