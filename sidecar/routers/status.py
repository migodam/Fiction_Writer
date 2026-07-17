from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/workflow/status")
async def workflow_status(request: Request) -> dict:
    store = getattr(request.app.state, "runtime_store", None)
    return {"status": "ok", "recoverable_runs": store.scan_recoverable_attempts() if store else []}


@router.get("/workflow/stream")
async def workflow_stream(request: Request, attempt_id: str = "", afterSequence: int = 0) -> StreamingResponse:
    if not attempt_id:
        async def legacy_event_generator() -> AsyncGenerator[str, None]:
            yield "data: {}\n\n"
        return StreamingResponse(legacy_event_generator(), media_type="text/event-stream")

    store = getattr(request.app.state, "runtime_store", None)
    if store is None or store.get_attempt(attempt_id) is None:
        raise HTTPException(status_code=404, detail="attempt_not_found")
    last_event_id = request.headers.get("Last-Event-ID", "")
    cursor = max(afterSequence, int(last_event_id) if last_event_id.isdigit() else 0)
    live_stream = "text/event-stream" in request.headers.get("Accept", "")

    async def event_generator() -> AsyncGenerator[str, None]:
        nonlocal cursor
        yield "retry: 1000\n\n"
        heartbeat_at = time.monotonic()
        while True:
            events = store.list_events(attempt_id, after_sequence=cursor)
            for event in events:
                cursor = max(cursor, int(event["sequence"]))
                yield f"id: {event['sequence']}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=True, separators=(',', ':'))}\n\n"
            if not live_stream or await request.is_disconnected():
                return
            now = time.monotonic()
            if now - heartbeat_at >= 10:
                heartbeat_at = now
                yield f": heartbeat {cursor}\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
