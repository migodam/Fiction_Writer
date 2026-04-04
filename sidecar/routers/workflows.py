from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/workflow/{workflow_id}/start")
async def start_workflow(workflow_id: str) -> None:
    raise HTTPException(status_code=501, detail=f"Workflow '{workflow_id}' start is not implemented.")


@router.post("/workflow/cancel")
async def cancel_workflow() -> None:
    raise HTTPException(status_code=501, detail="Workflow cancel is not implemented.")
