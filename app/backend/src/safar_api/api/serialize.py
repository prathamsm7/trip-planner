from typing import Any


def _artifact_patch(kind: str, update: dict[str, Any]) -> dict[str, Any]:
    """Map a saved artifact onto the field name the results panel reads."""
    artifact = update.get(kind)
    if artifact is None:
        return {}
    data = artifact.data if hasattr(artifact, "data") else (artifact or {}).get("data")
    if not isinstance(data, dict):
        return {}
    if kind == "flights":
        return {"flights_data": data}
    if kind == "stays":
        return {"hotel_search_results": data.get("properties") or []}
    if kind == "itinerary":
        return {"itinerary": data}
    if kind == "weather":
        return {"weather": data}
    if kind == "research":
        return {"destination_about": data.get("overview") or ""}
    return {}


def patch_for_node(node: str, update: dict[str, Any] | None) -> dict[str, Any]:
    """Extract UI-relevant payload from a supervisor or tool update."""
    del node
    if not update:
        return {}

    patch: dict[str, Any] = {}
    if update.get("messages"):
        patch["messages"] = update["messages"]
    brief = update.get("brief")
    if brief is not None:
        if hasattr(brief, "to_ui_trip"):
            patch["structured"] = brief.to_ui_trip()
        elif isinstance(brief, dict):
            from safar_api.trip.brief import TripBrief

            payload = dict(brief)
            if isinstance(payload.get("stated"), list):
                payload["stated"] = set(payload["stated"])
            patch["structured"] = TripBrief.model_validate(payload).to_ui_trip()
    for kind in ("research", "weather", "flights", "stays", "itinerary"):
        if kind in update:
            patch.update(_artifact_patch(kind, update))
    if update.get("last_step_detail"):
        patch["description"] = update["last_step_detail"]
    return patch
