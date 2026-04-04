from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/workflow/status")
async def workflow_status() -> None:
    raise HTTPException(status_code=501, detail="Workflow status is not implemented.")


@router.get("/workflow/stream")
async def workflow_stream() -> StreamingResponse:
    async def event_generator() -> AsyncGenerator[str, None]:
        yield "data: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
