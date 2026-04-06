"""W0 Orchestrator FastAPI endpoints.

Sessions are stored in-memory keyed by session_id. Each session holds:
  - thread_id: LangGraph MemorySaver key
  - status, progress, plan, current_step, pending_permission
  - errors

After an interrupt (waiting_permission), POST /permission/{step_id}/grant resumes
the graph via Command(resume=True).
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# In-memory session store: session_id → session dict
_sessions: dict[str, dict] = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class OrchestratorStartPayload(BaseModel):
    project_path: str
    goal: str
    auto_apply_threshold: float = 0.85
    auto_approve_all: bool = False
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    endpoint: str = "https://api.anthropic.com"
    sidecar_port: int = 8765


class OrchestratorStartResult(BaseModel):
    session_id: str
    status: str
    plan: List[Any] = []


class OrchestratorStatusResult(BaseModel):
    status: str
    current_step: int = 0
    total_steps: int = 0
    progress: float = 0.0
    pending_permission: Optional[Any] = None
    plan: List[Any] = []
    errors: List[str] = []


class PermissionActionPayload(BaseModel):
    session_id: str


class PermissionDenyPayload(BaseModel):
    session_id: str
    reason: str


# ── Background task helpers ───────────────────────────────────────────────────

def _update_session_from_result(session_id: str, result: dict) -> None:
    """Write workflow result dict into the session store."""
    session = _sessions.get(session_id, {})
    session.update({
        "status": result.get("status", "done"),
        "progress": result.get("progress", 1.0),
        "plan": result.get("plan", []),
        "current_step": result.get("current_step", 0),
        "pending_permission": result.get("pending_permission"),
        "errors": result.get("errors", []),
    })
    _sessions[session_id] = session


async def _run_orchestrator(session_id: str, initial_state: dict, thread_id: str) -> None:
    """Run W0 graph until completion or interrupt."""
    from sidecar.workflows.w0_orchestrator import get_graph
    from langgraph.errors import GraphInterrupt
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    try:
        result = await graph.ainvoke(initial_state, config)
        _update_session_from_result(session_id, result)
    except GraphInterrupt as gi:
        # Graph paused waiting for permission — update session to waiting state
        session = _sessions.get(session_id, {})
        interrupts = gi.args[0] if gi.args else []
        perm_data = None
        if interrupts:
            iv = interrupts[0].value if hasattr(interrupts[0], 'value') else {}
            perm_data = iv.get("permission_request") if isinstance(iv, dict) else None
        session.update({
            "status": "waiting_permission",
            "pending_permission": perm_data,
        })
        _sessions[session_id] = session
    except Exception as e:
        session = _sessions.get(session_id, {})
        session.update({"status": "error", "errors": [str(e)], "progress": 0.0})
        _sessions[session_id] = session


async def _resume_orchestrator(session_id: str, thread_id: str) -> None:
    """Resume an interrupted W0 graph after permission grant."""
    from sidecar.workflows.w0_orchestrator import get_graph
    from langgraph.types import Command
    from langgraph.errors import GraphInterrupt
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    _sessions[session_id]["status"] = "executing"
    try:
        result = await graph.ainvoke(Command(resume=True), config)
        _update_session_from_result(session_id, result)
    except GraphInterrupt as gi:
        session = _sessions.get(session_id, {})
        interrupts = gi.args[0] if gi.args else []
        perm_data = None
        if interrupts:
            iv = interrupts[0].value if hasattr(interrupts[0], 'value') else {}
            perm_data = iv.get("permission_request") if isinstance(iv, dict) else None
        session.update({
            "status": "waiting_permission",
            "pending_permission": perm_data,
        })
        _sessions[session_id] = session
    except Exception as e:
        session = _sessions.get(session_id, {})
        session.update({"status": "error", "errors": [str(e)]})
        _sessions[session_id] = session


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", response_model=OrchestratorStartResult)
async def start_orchestrator(body: OrchestratorStartPayload) -> OrchestratorStartResult:
    """Start an Orchestrator run."""
    session_id = str(uuid.uuid4())
    thread_id = f"w0-{session_id}"
    _sessions[session_id] = {
        "status": "planning",
        "progress": 0.0,
        "plan": [],
        "current_step": 0,
        "pending_permission": None,
        "thread_id": thread_id,
        "errors": [],
    }
    initial_state: dict = {
        "project_path": body.project_path,
        "workflow_id": "W0",
        "goal": body.goal,
        "plan": [],
        "current_step": 0,
        "step_results": [],
        "pending_permission": None,
        "status": "planning",
        "progress": 0.0,
        "errors": [],
        "proposals": [],
        "context": {
            "api_key": body.api_key,
            "model": body.model,
            "endpoint": body.endpoint,
            "sidecar_port": body.sidecar_port,
            "auto_approve_all": body.auto_approve_all,
        },
    }
    asyncio.create_task(_run_orchestrator(session_id, initial_state, thread_id))
    return OrchestratorStartResult(session_id=session_id, status="started")


@router.get("/status", response_model=OrchestratorStatusResult)
async def orchestrator_status(session_id: str = "") -> OrchestratorStatusResult:
    """Return current Orchestrator status."""
    session = _sessions.get(session_id, {})
    plan = session.get("plan", [])
    return OrchestratorStatusResult(
        status=session.get("status", "idle"),
        current_step=session.get("current_step", 0),
        total_steps=len(plan),
        progress=session.get("progress", 0.0),
        pending_permission=session.get("pending_permission"),
        plan=plan,
        errors=session.get("errors", []),
    )


@router.post("/permission/{step_id}/grant")
async def grant_permission(step_id: str, body: PermissionActionPayload) -> dict:
    """Grant permission for a pending orchestrator step and resume execution."""
    session = _sessions.get(body.session_id)
    if not session:
        return {"status": "error", "detail": "session_not_found"}
    if session.get("status") != "waiting_permission":
        return {"status": "error", "detail": "not_waiting_permission"}
    thread_id = session.get("thread_id", "")
    asyncio.create_task(_resume_orchestrator(body.session_id, thread_id))
    return {"status": "granted", "step_id": step_id}


@router.post("/permission/{step_id}/deny")
async def deny_permission(step_id: str, body: PermissionDenyPayload) -> dict:
    """Deny permission for a pending orchestrator step and mark it failed."""
    session = _sessions.get(body.session_id)
    if not session:
        return {"status": "error", "detail": "session_not_found"}
    session.update({
        "status": "error",
        "errors": [f"Step {step_id} denied by user: {body.reason}"],
        "pending_permission": None,
    })
    _sessions[body.session_id] = session
    return {"status": "denied", "step_id": step_id}
