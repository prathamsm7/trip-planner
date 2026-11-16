"""Result type returned by specialist trip tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    status: str = "ok"  # ok | partial | failed | skipped
    summary: str = ""
    detail: str = ""
    updates: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
