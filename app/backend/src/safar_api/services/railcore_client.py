"""RailCore trains between stations.

https://railcore.tech/docs/api/route-trains
GET /v1/routes/trains?from=&to=&date=&quota=GN&match=city
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from safar_api.config import settings

logger = logging.getLogger(__name__)

_URL = "https://ir.railcore.tech/v1/routes/trains"


def _key() -> str:
    key = (settings.railcore_api_key or "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("RAILCORE_API_KEY is not set")
    return key


def trains_on_route(origin_code: str, destination_code: str, journey_date: str) -> list[dict[str, Any]]:
    """Trains between two station codes."""
    params = {
        "from": (origin_code or "").strip().upper(),
        "to": (destination_code or "").strip().upper(),
        "date": (journey_date or "").strip(),
        "quota": "GN",
        "match": "city",
    }
    if not params["from"] or not params["to"] or not params["date"]:
        raise RuntimeError("Train search needs from, to, and date.")
    logger.info("railcore trains | from=%s to=%s date=%s", params["from"], params["to"], params["date"])

    response = requests.request(
        "GET",
        _URL,
        params=params,
        headers={"X-RailCore-Key": _key()},
        timeout=20,
    )
    if response.status_code == 404:
        return []
    if response.status_code >= 400:
        raise RuntimeError(f"RailCore HTTP {response.status_code}")
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else {}
    trains = data.get("trains") if isinstance(data, dict) else None
    return [row for row in trains if isinstance(row, dict)] if isinstance(trains, list) else []
