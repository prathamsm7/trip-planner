"""Typed trip facts the supervisor and specialist tools share."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Budget = Literal["low", "medium", "high"]
TravelStyle = Literal["solo", "couple", "family", "friends", "business"] 
TransportMode = Literal["flight", "train", "bus", "car", ""]

BRIEF_FIELDS = (
    "origin",
    "destination",
    "start_date",
    "end_date",
    "duration_days",
    "month",
    "travellers",
    "budget",
    "style",
    "transport_mode",
    "stay_type",
    "preferences",
    "notes",
)

DEFAULTS: dict = {
    "travellers": 1,
    "budget": "medium",
    "style": "solo",
    "transport_mode": "",
    "stay_type": "hotel",
}


class TripBrief(BaseModel):
    origin: str = ""
    destination: str = ""
    start_date: str = ""
    end_date: str = ""
    duration_days: int | None = None
    month: str = ""
    travellers: int = 1
    budget: Budget = "medium"
    style: TravelStyle = "solo"
    transport_mode: TransportMode = ""
    stay_type: str = ""
    preferences: list[str] = Field(default_factory=list)
    notes: str = ""
    # Fields the user explicitly provided (not filled from defaults).
    stated: set[str] = Field(default_factory=set)

    def has_exact_dates(self) -> bool:
        return bool(self.start_date and self.end_date)

    def has_trip_length(self) -> bool:
        return self.has_exact_dates() or bool(self.duration_days) or bool(self.month)

    def resolved_duration_days(self) -> int | None:
        if self.duration_days and self.duration_days > 0:
            return self.duration_days
        if self.has_exact_dates():
            try:
                from datetime import date

                start = date.fromisoformat(self.start_date)
                end = date.fromisoformat(self.end_date)
                return max(1, (end - start).days + 1)
            except ValueError:
                return None
        return None

    def fingerprint(self, fields: tuple[str, ...] | list[str]) -> dict:
        """Compact brief slice used to decide whether a result is still valid."""
        data = self.model_dump()
        out: dict = {}
        for key in fields:
            value = data.get(key)
            if isinstance(value, list):
                out[key] = list(value)
            else:
                out[key] = value
        return out

    def to_ui_trip(self) -> dict:
        """Map the brief onto the trip fields the results panel reads."""
        duration = self.resolved_duration_days() or 0
        return {
            "sourceLocation": self.origin,
            "destinationLocation": self.destination,
            "date_range": {"start": self.start_date, "end": self.end_date},
            "duration": {"min_days": duration, "max_days": duration},
            "budget": self.budget,
            "travel_style": self.style,
            "number_of_people": self.travellers,
            "mode_of_transport": self.transport_mode,
            "accomodation_type": self.stay_type,
            "preferences": list(self.preferences),
            "other_details": self.notes,
            "month": self.month,
        }


class TripUpdate(BaseModel):
    """Fields the update_trip tool may change."""

    origin: str | None = None
    destination: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int | None = None
    month: str | None = None
    travellers: int | None = None
    budget: Budget | None = None
    style: TravelStyle | None = None
    transport_mode: TransportMode | None = None
    stay_type: str | None = None
    preferences: list[str] | None = None
    notes: str | None = None


def apply_trip_update(brief: TripBrief, update: TripUpdate | dict) -> tuple[TripBrief, set[str]]:
    """Merge an update into the brief. Returns (new_brief, changed_field_names)."""
    if isinstance(update, dict):
        update = TripUpdate.model_validate(update)

    data = brief.model_dump()
    stated = set(brief.stated)
    changed: set[str] = set()

    for field in BRIEF_FIELDS:
        value = getattr(update, field)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip() and field not in ("notes",):
            # Empty string means "clear" for identity fields.
            if field in ("origin", "destination", "start_date", "end_date", "month"):
                if data.get(field):
                    data[field] = ""
                    changed.add(field)
                    stated.discard(field)
            continue
        if data.get(field) != value:
            data[field] = value
            changed.add(field)
        stated.add(field)

    # Infer duration from dates when both are present and duration was not stated.
    if {"start_date", "end_date"} & changed and "duration_days" not in stated:
        try:
            from datetime import date

            if data.get("start_date") and data.get("end_date"):
                start = date.fromisoformat(data["start_date"])
                end = date.fromisoformat(data["end_date"])
                data["duration_days"] = max(1, (end - start).days + 1)
                changed.add("duration_days")
        except ValueError:
            pass

    # Infer month from start_date when month not stated.
    if "start_date" in changed and "month" not in stated and data.get("start_date"):
        data["month"] = data["start_date"][:7]
        changed.add("month")

    data["stated"] = stated
    return TripBrief.model_validate(data), changed
