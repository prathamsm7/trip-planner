import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from safar_api.api.serialize import state_to_snapshot
from safar_api.api.stream import stream_graph
from safar_api.graph.build import get_graph

router = APIRouter(prefix="/api")


class MessageBody(BaseModel):
    content: str


class ResumeBody(BaseModel):
    content: str


class SelectionsBody(BaseModel):
    selections: dict[str, Any]


@router.get("/health")
def health():
    return {"status": "ok", "service": "safar-ai"}


@router.post("/threads")
def create_thread():
    thread_id = str(uuid.uuid4())
    return {"thread_id": thread_id}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.values and not snapshot.interrupts:
        return {
            "thread_id": thread_id,
            "snapshot": None,
            "interrupt": None,
        }
    interrupt = None
    if snapshot.interrupts:
        value = snapshot.interrupts[0].value or {}
        interrupt = {
            "type": value.get("type"),
            "question": value.get("question"),
            "index": value.get("index"),
            "total": value.get("total"),
            "message": value.get("message"),
            "questions": value.get("questions", []),
        }
    return {
        "thread_id": thread_id,
        "snapshot": state_to_snapshot(snapshot.values or {}),
        "interrupt": interrupt,
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
    return _sse_response(stream_graph(thread_id, body.content, resume=False))


@router.post("/threads/{thread_id}/resume")
async def post_resume(thread_id: str, body: ResumeBody):
    return _sse_response(stream_graph(thread_id, body.content, resume=True))


@router.patch("/threads/{thread_id}/selections")
def patch_selections(thread_id: str, body: SelectionsBody):
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found")
    values = dict(snapshot.values)
    values["selections"] = body.selections
    graph.update_state(config, values)
    return {"thread_id": thread_id, "selections": body.selections}
