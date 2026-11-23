"""Result artifacts for the agentic pipeline, each tied to a brief fingerprint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from safar_api.trip.brief import TripBrief

Capability = Literal["research", "weather", "flights", "trains", "stays", "itinerary"]

# Fields that must be present before a capability can run.
REQUIREMENTS: dict[Capability, tuple[str, ...]] = {
    "research": ("destination",),
    "weather": ("destination",),  # plus dates OR month — checked in missing_fields
    "flights": ("origin", "destination", "start_date", "end_date"),
    "trains": ("origin", "destination", "start_date"),
    "stays": ("destination", "start_date", "end_date"),
    "itinerary": ("destination",),  # plus trip length — checked in missing_fields
}

# Brief fields stored on each result for cache / invalidation checks.
FINGERPRINT_FIELDS: dict[Capability, tuple[str, ...]] = {
    "research": ("destination", "origin", "transport_mode", "month", "style"),
    "weather": ("destination", "start_date", "end_date", "month"),
    "flights": ("origin", "destination", "start_date", "end_date", "travellers"),
    "trains": ("origin", "destination", "start_date", "end_date"),
    "stays": ("destination", "start_date", "end_date", "travellers", "stay_type", "budget"),
    "itinerary": (
        "destination",
        "start_date",
        "end_date",
        "duration_days",
        "budget",
        "style",
        "travellers",
        "preferences",
    ),
}

# Changing these fields CLEARS the result entirely.
CLEAR_ON: dict[Capability, frozenset[str]] = {
    "research": frozenset({"destination", "origin", "transport_mode"}),
    "weather": frozenset({"destination", "start_date", "end_date", "month"}),
    "flights": frozenset({"origin", "destination", "travellers"}),
    "trains": frozenset({"origin", "destination"}),
    "stays": frozenset(
        {"destination", "start_date", "end_date", "travellers", "stay_type"}
    ),
    "itinerary": frozenset({"destination", "start_date", "end_date", "duration_days"}),
}

# Changing these fields keeps the result but marks it for revision.
FLAG_ON: dict[Capability, frozenset[str]] = {
    "research": frozenset({"month", "style"}),
    "weather": frozenset(),
    "flights": frozenset(),
    "trains": frozenset(),
    "stays": frozenset({"budget"}),
    "itinerary": frozenset({"budget", "style", "travellers", "preferences"}),
}


class Attraction(BaseModel):
    name: str
    area: str = ""
    typical_duration_hours: float | None = None
    notes: str = ""


class AirportInfo(BaseModel):
    name: str = ""
    code: str = ""
    location: str = ""
    kind: Literal["primary", "nearby"] = "primary"


class DestinationResearch(BaseModel):
    overview: str = ""
    areas: list[str] = Field(default_factory=list)
    attractions: list[Attraction] = Field(default_factory=list)
    local_transport: str = ""
    airports: list[AirportInfo] = Field(default_factory=list)
    stations: list[AirportInfo] = Field(default_factory=list)
    food: str = ""
    tips: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    queries_used: list[str] = Field(default_factory=list)


class WeatherDay(BaseModel):
    day_label: str = ""
    date: str = ""
    temp_range: str = ""
    humidity: str = ""
    wind: str = ""
    condition: str = ""


class WeatherOutlook(BaseModel):
    destination: str = ""
    summary: str = ""
    days: list[WeatherDay] = Field(default_factory=list)
    source: Literal["forecast", "climatology", "unknown"] = "unknown"


class FlightShortlistItem(BaseModel):
    label: str
    price: float | None = None
    reason: str = ""
    index: int = 0


class FlightLegBundle(BaseModel):
    """One direction of a trip (outbound or return)."""

    best_flights: list[dict[str, Any]] = Field(default_factory=list)
    other_flights: list[dict[str, Any]] = Field(default_factory=list)
    shortlist: list[FlightShortlistItem] = Field(default_factory=list)


class FlightsResult(BaseModel):
    outbound: FlightLegBundle = Field(default_factory=FlightLegBundle)
    return_flights: FlightLegBundle = Field(default_factory=FlightLegBundle)
    airports: list[Any] = Field(default_factory=list)
    airport_meta: dict[str, Any] = Field(default_factory=dict)
    alternatives: dict[str, Any] = Field(default_factory=dict)


class StayShortlistItem(BaseModel):
    label: str
    name: str = ""
    price: float | None = None
    rating: float | None = None
    reason: str = ""
    index: int = 0


class StaysResult(BaseModel):
    properties: list[dict[str, Any]] = Field(default_factory=list)
    shortlist: list[StayShortlistItem] = Field(default_factory=list)


class ItineraryPlan(BaseModel):
    morning: list[str] = Field(default_factory=list)
    afternoon: list[str] = Field(default_factory=list)
    evening: list[str] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    day: int
    location: str = ""
    plan: list[ItineraryPlan] = Field(default_factory=list)


class Itinerary(BaseModel):
    summary: str = ""
    days: list[ItineraryDay] = Field(default_factory=list)


class Artifact(BaseModel):
    """A capability result plus the brief slice it was built from."""

    kind: Capability
    fingerprint: dict[str, Any] = Field(default_factory=dict)
    flagged: bool = False
    data: dict[str, Any] = Field(default_factory=dict)

    def matches(self, brief: TripBrief) -> bool:
        expected = brief.fingerprint(FINGERPRINT_FIELDS[self.kind])
        return self.fingerprint == expected and not self.flagged


def missing_fields(capability: Capability, brief: TripBrief) -> list[str]:
    """Return required brief fields that are still empty for this capability."""
    missing: list[str] = []
    for field in REQUIREMENTS[capability]:
        value = getattr(brief, field, None)
        if value is None or value == "" or value == []:
            missing.append(field)

    if capability == "weather":
        if not brief.has_exact_dates() and not brief.month:
            if "start_date" not in missing:
                missing.append("start_date")
            if "end_date" not in missing and "month" not in missing:
                missing.append("month")

    if capability == "itinerary":
        if not brief.has_trip_length():
            missing.append("duration_days")

    return missing


# A date change drops only that direction. The other direction stays.
_LEG_ON_DATE: dict[str, dict[str, str]] = {
    "flights": {"start_date": "outbound", "end_date": "return_flights"},
    "trains": {"start_date": "outbound", "end_date": "return"},
}


def _empty_leg(kind: str) -> dict | list:
    if kind == "flights":
        return {"best_flights": [], "other_flights": [], "shortlist": []}
    return []


def apply_brief_change(
    changed: set[str],
    artifacts: dict[str, Artifact | None],
) -> dict[str, Artifact | None]:
    """Clear or flag artifacts after brief fields change."""
    if not changed:
        return artifacts

    out = dict(artifacts)
    for kind, artifact in list(out.items()):
        if artifact is None:
            continue
        cap = kind  # type: ignore[assignment]
        if not isinstance(cap, str) or cap not in CLEAR_ON:
            continue
        if changed & CLEAR_ON[cap]:  # type: ignore[index]
            out[kind] = None
            continue
        leg_fields = _LEG_ON_DATE.get(cap, {})
        if changed & set(leg_fields):
            data = dict(artifact.data)
            for field, leg_key in leg_fields.items():
                if field not in changed:
                    continue
                data[leg_key] = _empty_leg(cap)
                if cap == "trains":
                    data["outbound_date" if leg_key == "outbound" else "return_date"] = ""
            out[kind] = artifact.model_copy(update={"data": data})
        elif changed & FLAG_ON[cap]:  # type: ignore[index]
            out[kind] = artifact.model_copy(update={"flagged": True})
    return out


def make_artifact(kind: Capability, brief: TripBrief, data: BaseModel | dict) -> Artifact:
    payload = data.model_dump() if isinstance(data, BaseModel) else dict(data)
    return Artifact(
        kind=kind,
        fingerprint=brief.fingerprint(FINGERPRINT_FIELDS[kind]),
        flagged=False,
        data=payload,
    )
