import re
from typing import Any

TRANSPORT_QUERY = """\
{source} to {destination} transport options flight train bus distance time,
nearest airport railway-station {destination},
nearest airport railway-station {source},
local transport in {destination} taxi rental availability"""

ACTIVITIES_QUERY = """\
things to do in {destination} {month} weather,
tourist attractions and places to visit in {destination},
nearby sightseeing and cultural places"""


def _month(structured: dict[str, Any]) -> str:
    month = (structured.get("month") or "").strip()
    if month:
        return month
    start = ((structured.get("date_range") or {}).get("start") or "").strip()
    if len(start) >= 7:
        return start[:7]  # YYYY-MM from ISO date
    return (structured.get("season") or "").strip()


def build_transport_query(structured: dict[str, Any]) -> str:
    source = (structured.get("sourceLocation") or "departure city").strip()
    destination = (structured.get("destinationLocation") or "").strip()
    return TRANSPORT_QUERY.format(source=source, destination=destination).strip()


def build_activities_query(structured: dict[str, Any]) -> str:
    destination = (structured.get("destinationLocation") or "").strip()
    return ACTIVITIES_QUERY.format(
        destination=destination,
        month=_month(structured),
    ).strip()


def build_search_plan(structured: dict[str, Any] | None) -> dict[str, Any]:
    s = structured or {}
    if not s.get("destinationLocation"):
        return {"queries": {}}
    return {
        "queries": {
            "transport": build_transport_query(s),
            "activities": build_activities_query(s),
        }
    }


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    text = re.sub(r"\(([^)]+)\)", r"\1", text)
    text = re.sub(r"[#>*`_~-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
