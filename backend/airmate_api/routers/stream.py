"""Server-Sent Events: live risk, readings, check-ins and alerts for the web app."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ..deps import AppState, get_state

router = APIRouter(tags=["stream"])
HEARTBEAT_S = 15.0


@router.get("/stream")
async def stream(
    request: Request,
    user_id: list[str] = Query(default=[], description="Repeat for several people, e.g. a buddy view"),
    community: bool = False,
    state: AppState = Depends(get_state),
) -> StreamingResponse:
    """Each message is ``event: <type>`` + ``data: {"type", "topic", "ts", "data"}`` (see docs/API.md)."""
    topics = [f"user:{uid}" for uid in user_id] + (["community"] if community else [])
    queue = state.bus.subscribe(topics)

    async def events():
        try:
            yield f"event: hello\ndata: {json.dumps({'topics': topics})}\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {message['type']}\ndata: {json.dumps(message)}\n\n"
        finally:
            state.bus.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
