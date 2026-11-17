from pydantic import BaseModel, Field


class LocationDetails(BaseModel):
    name: str = ""
    code: str = ""
    location: str = ""


class FlightSearchOutput(BaseModel):
    """Airports from a SerpAPI search, split by the city they serve."""

    origin_airports: list[LocationDetails] = Field(
        default_factory=list,
        description=(
            "Airports that serve the origin city. "
            "The first item is the main airport. Later items are alternatives for that same city."
        ),
    )
    destination_airports: list[LocationDetails] = Field(
        default_factory=list,
        description=(
            "Airports that serve the destination city, closest first. "
            "The first item is the main airport. "
            "Do not include airports that only serve the origin city."
        ),
    )
