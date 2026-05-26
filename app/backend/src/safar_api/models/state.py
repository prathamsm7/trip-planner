from operator import add
from typing import Annotated, Any, Dict, List, Literal, Optional, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


class TravelState(BaseModel):
    query: str | None = None
    structured: Optional[Dict[str, Any]] = None
    follow_up_answers: Dict[str, str] = Field(default_factory=dict)
    follow_up_index: int = 0
    weather: Optional[Any] = None
    itinerary: Optional[Dict[str, Any]] = None
    critique: Optional[Dict[str, Any]] = None
    suggestions: Optional[Dict[str, Any]] = None
    transport_results: Optional[Any] = None
    activities_results: Optional[Any] = None
    status: Literal["approved", "revise", "infeasible"] = "revise"
    iteration: int = 0
    maxIteration: int = 2
    user_current_intent: str = ""
    messages: Annotated[Sequence[BaseMessage], add_messages] = Field(default_factory=list)
    hotel_search_results: Optional[List[dict]] = None
    flights_data: dict = Field(default_factory=dict)
    selections: dict = Field(default_factory=dict)
    destination_about: str = ""
