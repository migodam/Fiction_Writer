"""W7 Metadata Ingestion FastAPI endpoints."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# In-memory session store: session_id → session dict
_sessions: dict[str, dict] = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class MetadataIngestPayload(BaseModel):
    project_path: str
    source_file_path: str
    file_type: str = "other"   # novel|script|news|essay|draft|other
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"


class MetadataIngestResult(BaseModel):
    file_id: str
    session_id: str
    status: str


class MetadataStatusResult(BaseModel):
    status: str
    progress: float = 0.0
    file_id: str = ""
    vector_store_updated: bool = False
    errors: list = []


# ── Background task ───────────────────────────────────────────────────────────

async def _run_w7(session_id: str, file_id: str, config: dict) -> None:
    from sidecar.workflows.w7_metadata_ingestion import run as w7_run
    try:
        result = await w7_run(config["project_path"], {**config, "file_id": file_id})
        _sessions[session_id] = {
            "status": result.get("status", "done"),
            "progress": result.get("progress", 1.0),
            "file_id": file_id,
            "vector_store_updated": result.get("vector_store_updated", False),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        _sessions[session_id] = {
            "status": "error", "progress": 0.0,
            "file_id": file_id, "vector_store_updated": False, "errors": [str(e)],
        }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=MetadataIngestResult)
async def ingest_metadata(body: MetadataIngestPayload) -> MetadataIngestResult:
    """Start a W7 Metadata Ingestion run."""
    file_id = f"meta_{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "status": "running", "progress": 0.0,
        "file_id": file_id, "vector_store_updated": False, "errors": [],
    }
    config = {
        "project_path": body.project_path,
        "source_file_path": body.source_file_path,
        "file_type": body.file_type,
        "context": {"api_key": body.api_key, "model": body.model, "endpoint": body.endpoint},
    }
    asyncio.create_task(_run_w7(session_id, file_id, config))
    return MetadataIngestResult(file_id=file_id, session_id=session_id, status="started")


@router.get("/status", response_model=MetadataStatusResult)
async def metadata_status(session_id: str = "") -> MetadataStatusResult:
    """Return current W7 Metadata Ingestion status."""
    session = _sessions.get(session_id, {})
    return MetadataStatusResult(
        status=session.get("status", "idle"),
        progress=session.get("progress", 0.0),
        file_id=session.get("file_id", ""),
        vector_store_updated=session.get("vector_store_updated", False),
        errors=session.get("errors", []),
    )
