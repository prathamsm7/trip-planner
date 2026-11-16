from pydantic import BaseModel, Field


class LocationDetails(BaseModel):
    name: str
    code: str
    location: str


class FlightSearchOutput(BaseModel):
    """Airports extracted by the small model from a SerpAPI airport search."""

    departure_airport_code: str
    arrival_airport_code: str
    departure_airport_name: str
    arrival_airport_name: str
    other_airports: list[LocationDetails] = Field(default_factory=list)
