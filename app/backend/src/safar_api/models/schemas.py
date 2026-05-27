from typing import List, Literal

from pydantic import BaseModel, Field


class Duration(BaseModel):
    min_days: int = 0
    max_days: int = 0


class DateRange(BaseModel):
    start: str = ""
    end: str = ""


class StructuredTravelExtract(BaseModel):
    """Parser output — None / empty means still missing (no fake defaults)."""

    sourceLocation: str = ""
    destinationLocation: str = ""
    duration: Duration | None = None
    date_range: DateRange | None = None
    budget: Literal["low", "medium", "high"] | None = None
    travel_style: Literal["solo", "couple", "family", "friends", "business"] | None = None
    number_of_people: int = 1
    mode_of_transport: Literal["flight", "train", "bus", "car"] | None = None
    preferences: List[str] = []
    other_details: str = ""
    return_journey: bool = True
    accomodation_type: Literal["hotel", "guesthouse", "airbnb", "homestay"] = "hotel"
    month: str = ""
    season: str = ""


class StructuredTravel(BaseModel):
    sourceLocation: str
    destinationLocation: str
    duration: Duration
    date_range: DateRange
    budget: Literal["low", "medium", "high"] = "medium"
    travel_style: Literal["solo", "couple", "family", "friends", "business"] = "solo"
    number_of_people: int = 1
    mode_of_transport: Literal["flight", "train", "bus", "car"] = "flight"
    preferences: List[str] = []
    other_details: str = ""
    is_follow_up: bool = False
    follow_up_questions: List[str] = []
    return_journey: bool = True
    accomodation_type: Literal["hotel", "guesthouse", "airbnb", "homestay"] = "hotel"
    month: str = ""
    season: str = ""


class UpdateStructuredTravel(BaseModel):
    sourceLocation: str = ""
    destinationLocation: str = ""
    duration: Duration | None = None
    date_range: DateRange | None = None
    budget: Literal["low", "medium", "high"] = "medium"
    travel_style: Literal["solo", "couple", "family", "friends", "business"] = "solo"
    number_of_people: int = 1
    mode_of_transport: Literal["flight", "train", "bus", "car"] = "flight"
    preferences: List[str] = []
    other_details: str = ""
    return_journey: bool = True
    accomodation_type: Literal["hotel", "guesthouse", "airbnb", "homestay"] = "hotel"
    month: str = ""
    season: str = ""


class IntentOutput(BaseModel):
    intent: Literal[
        "plan_trip",
        "modify_itinerary",
        "book_hotel",
        "get_info",
        "flight_search",
    ] = "get_info"


class LocationDetails(BaseModel):
    name: str
    code: str
    location: str


class FlightSearchOutput(BaseModel):
    departure_airport_code: str
    arrival_airport_code: str
    departure_airport_name: str
    arrival_airport_name: str
    other_airports: list[LocationDetails] = Field(default_factory=list)
    nearest_railway_station: list[LocationDetails] = Field(default_factory=list)


class Plan(BaseModel):
    morning: List[str]
    afternoon: List[str]
    evening: List[str]


class DayPlan(BaseModel):
    day: int
    location: str
    plan: List[Plan]


class ItineraryOutput(BaseModel):
    summary: str
    days: List[DayPlan]


class WeatherDay(BaseModel):
    day_label: str = Field(description="e.g. '1 Mon' or 'Day 1'")
    date: str = ""
    temp_range: str = Field(description="e.g. '24°C-30°C'")
    humidity: str = ""
    wind: str = ""
    condition: str = Field(description="Rainy, Sunny, Showers, etc.")


class WeatherOutlook(BaseModel):
    destination: str
    summary: str
    days: List[WeatherDay]


class FollowUpResume(BaseModel):
    answers: dict[str, str] = Field(
        description="Map each follow-up question string to the user's answer"
    )
