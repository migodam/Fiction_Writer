from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/ingest")
async def ingest_metadata() -> None:
    raise HTTPException(status_code=501, detail="Metadata ingestion is not implemented.")
