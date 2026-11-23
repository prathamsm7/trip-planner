import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from safar_api.api.stream import stream_graph
from safar_api.graph.build import get_graph
from safar_api.trip.state import snapshot_from_agent_state, sync_chat_transcript
from safar_api.logging_config import log_exception
from safar_api.trip.persistence import list_saved_trips, delete_saved_trip, upsert_trip_metadata

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class MessageBody(BaseModel):
    content: str


class SelectionsBody(BaseModel):
    selections: dict[str, Any]


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "safar-ai",
    }


@router.post("/threads")
def create_thread():
    thread_id = str(uuid.uuid4())
    try:
        upsert_trip_metadata(thread_id, {})
    except Exception as e:
        logger.error("Failed to upsert blank trip metadata: %s", e)
    return {"thread_id": thread_id}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.values:
        return {
            "thread_id": thread_id,
            "snapshot": None,
        }
    values = dict(snapshot.values)
    try:
        chat = sync_chat_transcript(graph, config)
    except Exception:
        logger.exception("Loading chat transcript failed")
        chat = []
    if chat:
        values["chat"] = chat
    return {
        "thread_id": thread_id,
        "snapshot": snapshot_from_agent_state(values),
    }


@router.get("/trips")
def get_all_trips():
    try:
        return {"trips": list_saved_trips()}
    except Exception as exc:
        log_exception(logger, "get_all_trips failed", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch saved trips")


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    try:
        deleted = delete_saved_trip(thread_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Trip not found in index")
        return {"thread_id": thread_id, "status": "deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        log_exception(logger, "delete_thread failed", exc, context={"thread_id": thread_id})
        raise HTTPException(status_code=500, detail="Failed to delete trip")


def _sse_response(gen):
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, body: MessageBody):
    return _sse_response(stream_graph(thread_id, body.content))


@router.patch("/threads/{thread_id}/selections")
def patch_selections(thread_id: str, body: SelectionsBody):
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        updates: dict[str, Any] = {"selections": body.selections}
        itinerary_raw = snapshot.values.get("itinerary")
        if itinerary_raw:
            if isinstance(itinerary_raw, dict):
                updates["itinerary"] = {**itinerary_raw, "flagged": True}
            elif hasattr(itinerary_raw, "model_copy"):
                updates["itinerary"] = itinerary_raw.model_copy(update={"flagged": True})

        graph.update_state(config, updates)
        
        # Update index updated_at timestamp
        try:
            upsert_trip_metadata(thread_id, snapshot.values.get("brief") or {})
        except Exception as e:
            logger.error("Failed to update index on patch selections: %s", e)

        return {"thread_id": thread_id, "selections": body.selections}
    except HTTPException:
        raise
    except Exception as exc:
        log_exception(
            logger,
            "patch_selections failed",
            exc,
            context={"thread_id": thread_id},
        )
        raise HTTPException(status_code=500, detail="Failed to update selections") from exc
