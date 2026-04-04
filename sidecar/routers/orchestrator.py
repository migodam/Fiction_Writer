from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/start")
async def start_orchestrator() -> None:
    raise HTTPException(status_code=501, detail="Orchestrator start is not implemented.")


@router.get("/status")
async def orchestrator_status() -> None:
    raise HTTPException(status_code=501, detail="Orchestrator status is not implemented.")


@router.post("/permission/{step_id}/grant")
async def grant_permission(step_id: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=f"Granting permission for step '{step_id}' is not implemented.",
    )


@router.post("/permission/{step_id}/deny")
async def deny_permission(step_id: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=f"Denying permission for step '{step_id}' is not implemented.",
    )
