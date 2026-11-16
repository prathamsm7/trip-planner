import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from safar_api.api.stream import stream_graph
from safar_api.graph.build import get_graph
from safar_api.trip.state import snapshot_from_agent_state
from safar_api.logging_config import log_exception

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
    return {
        "thread_id": thread_id,
        "snapshot": snapshot_from_agent_state(snapshot.values or {}),
    }


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
        # Write only selections so the rest of the trip state stays intact.
        graph.update_state(config, {"selections": body.selections})
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
