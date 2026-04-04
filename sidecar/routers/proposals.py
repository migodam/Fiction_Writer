from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/{proposal_id}/accept")
async def accept_proposal(proposal_id: str) -> None:
    raise HTTPException(status_code=501, detail=f"Proposal '{proposal_id}' accept is not implemented.")


@router.post("/{proposal_id}/reject")
async def reject_proposal(proposal_id: str) -> None:
    raise HTTPException(status_code=501, detail=f"Proposal '{proposal_id}' reject is not implemented.")


@router.get("/list")
async def list_proposals() -> None:
    raise HTTPException(status_code=501, detail="Proposal listing is not implemented.")
