"""W3 Writing Assistant FastAPI endpoints.

Sessions for three_options interrupts are stored in-memory in _sessions dict.
Each session maps a UUID to the graph config needed to resume execution.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError

router = APIRouter()

# In-memory session store: session_id → {"thread_id": str, "project_path": str}
_sessions: dict[str, dict] = {}

# Per-workflow session stores for W1/W2/W4/W5/W6
_w1_sessions: dict[str, dict] = {}
_w2_sessions: dict[str, dict] = {}
_w4_sessions: dict[str, dict] = {}
_w5_sessions: dict[str, dict] = {}
_w6_sessions: dict[str, dict] = {}


# ── Request / Response models ─────────────────────────────────────────────────

class W3StartRequest(BaseModel):
    project_path: str
    scene_id: str
    task: str = "continue"
    hitl_mode: str = "direct_output"
    metadata_file_id: Optional[str] = None
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    endpoint: str = "https://api.anthropic.com"


class W3SelectRequest(BaseModel):
    session_id: str
    selected_option: int


class W3StartResponse(BaseModel):
    status: str
    output: Optional[str] = None
    options: Optional[list[str]] = None
    session_id: Optional[str] = None
    error: Optional[str] = None


class W3SelectResponse(BaseModel):
    status: str
    output: Optional[str] = None
    error: Optional[str] = None


class W3StatusResponse(BaseModel):
    status: str
    progress: float = 0.0
    workflow_id: Optional[str] = None



# ── W3 endpoints ──────────────────────────────────────────────────────────────

@router.post("/workflow/w3/start", response_model=W3StartResponse)
async def w3_start(body: W3StartRequest) -> W3StartResponse:
    """Start a W3 Writing Assistant run.

    Returns immediately with {status:"waiting", options, session_id} if
    hitl_mode=="three_options" (graph interrupted before expand_selected).
    Returns {status:"done", output} if hitl_mode=="direct_output".
    """
    from sidecar.models.state import WritingState
    from sidecar.workflows.w3_writing_assistant import get_graph

    try:
        await acquire_lock(body.project_path, "W3")
    except WorkflowBusyError as e:
        return W3StartResponse(status="error", error=str(e))

    session_id = str(uuid.uuid4())
    thread_id = f"w3-{session_id}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: WritingState = {
        "project_path": body.project_path,
        "workflow_id": "W3",
        "scene_id": body.scene_id,
        "task": body.task,  # type: ignore[typeddict-item]
        "context": {
            "api_key": body.api_key,
            "model": body.model,
            "endpoint": body.endpoint,
        },
        "active_todos": [],
        "metadata_style": body.metadata_file_id,
        "metadata_chunks": [],
        "hitl_mode": body.hitl_mode,  # type: ignore[typeddict-item]
        "options": [],
        "selected_option": None,
        "output": "",
        "new_entities": [],
        "proposals": [],
        "progress": 0.0,
        "errors": [],
    }

    graph = get_graph()

    try:
        # ainvoke runs until completion or interrupt
        result_state = await graph.ainvoke(initial_state, config)

        # If we got here with options but no output → interrupted (three_options)
        if body.hitl_mode == "three_options" and result_state.get("options"):
            _sessions[session_id] = {
                "thread_id": thread_id,
                "project_path": body.project_path,
            }
            return W3StartResponse(
                status="waiting",
                options=result_state["options"],
                session_id=session_id,
            )

        # direct_output completed
        await release_lock(body.project_path)
        return W3StartResponse(status="done", output=result_state.get("output", ""))

    except Exception as e:
        await release_lock(body.project_path)
        return W3StartResponse(status="error", error=str(e))


@router.post("/workflow/w3/select", response_model=W3SelectResponse)
async def w3_select(body: W3SelectRequest) -> W3SelectResponse:
    """Resume a three_options graph after user selects an option.

    Resumes the interrupted graph thread with the selected option index,
    runs to completion, and returns the expanded prose output.
    """
    from langgraph.types import Command
    from sidecar.workflows.w3_writing_assistant import get_graph

    session = _sessions.get(body.session_id)
    if not session:
        return W3SelectResponse(status="error", error="session_not_found")

    thread_id = session["thread_id"]
    project_path = session["project_path"]
    config = {"configurable": {"thread_id": thread_id}}

    graph = get_graph()

    try:
        # Resume graph: update selected_option then continue
        result_state = await graph.ainvoke(
            Command(resume=body.selected_option, update={"selected_option": body.selected_option}),
            config,
        )
        _sessions.pop(body.session_id, None)
        await release_lock(project_path)
        return W3SelectResponse(status="done", output=result_state.get("output", ""))

    except Exception as e:
        _sessions.pop(body.session_id, None)
        await release_lock(project_path)
        return W3SelectResponse(status="error", error=str(e))


@router.get("/workflow/w3/status", response_model=W3StatusResponse)
async def w3_status() -> W3StatusResponse:
    """Return current W3 workflow status. SSE stream is used for live progress."""
    active_sessions = len(_sessions)
    if active_sessions > 0:
        return W3StatusResponse(status="waiting_selection", progress=0.6, workflow_id="W3")
    return W3StatusResponse(status="idle", progress=0.0, workflow_id=None)


# ── W1 Import models ──────────────────────────────────────────────────────────

class W1StartRequest(BaseModel):
    project_path: str
    source_file_path: str
    import_mode: str = "import_all"
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"


class W1StartResponse(BaseModel):
    session_id: str
    status: str


class W1CancelRequest(BaseModel):
    session_id: str


class W1CancelResponse(BaseModel):
    status: str


class W1StatusResponse(BaseModel):
    status: str
    progress: float = 0.0
    errors: List[str] = []
    completed_chunks: int = 0
    total_chunks: int = 0


# ── W2 Manuscript Sync models ────────────────────────────────────────────────

class W2StartRequest(BaseModel):
    project_path: str
    mode: str
    target_chapter_id: Optional[str] = None
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"


class W2StartResponse(BaseModel):
    session_id: str
    status: str


class W2StatusResult(BaseModel):
    status: str
    progress: float = 0.0
    errors: List[str] = []
    proposals_count: int = 0


# ── W1 background task ────────────────────────────────────────────────────────

async def _run_w1(session_id: str, config: dict) -> None:
    from sidecar.workflows.w1_import import run as w1_run
    try:
        result = await w1_run(config["project_path"], config)
        chunks = result.get("chunks", [])
        _w1_sessions[session_id] = {
            "status": result.get("status", "done"),
            "progress": result.get("progress", 1.0),
            "errors": result.get("errors", []),
            "completed_chunks": len(chunks),
            "total_chunks": len(chunks),
        }
    except Exception as e:
        _w1_sessions[session_id] = {
            "status": "error", "progress": 0.0, "errors": [str(e)],
            "completed_chunks": 0, "total_chunks": 0,
        }


# ── W2 background task ────────────────────────────────────────────────────────

async def _run_w2(session_id: str, config: dict) -> None:
    from sidecar.workflows.w2_manuscript_sync import run as w2_run
    try:
        result = await w2_run(config["project_path"], config)
        _w2_sessions[session_id] = {
            "status": result.get("status", "done"),
            "progress": result.get("progress", 1.0),
            "errors": result.get("errors", []),
            "proposals_count": len(result.get("proposals", [])),
        }
    except Exception as e:
        _w2_sessions[session_id] = {
            "status": "error", "progress": 0.0, "errors": [str(e)], "proposals_count": 0,
        }


# ── W1 Import endpoints ──────────────────────────────────────────────────────

@router.post("/workflow/w1/start", response_model=W1StartResponse)
async def w1_start(body: W1StartRequest) -> W1StartResponse:
    """Start a W1 Import workflow run."""
    session_id = str(uuid.uuid4())
    _w1_sessions[session_id] = {
        "status": "running", "progress": 0.0, "errors": [],
        "completed_chunks": 0, "total_chunks": 0,
    }
    config = {
        "project_path": body.project_path,
        "source_file_path": body.source_file_path,
        "import_mode": body.import_mode,
        "context": {"api_key": body.api_key, "model": body.model, "endpoint": body.endpoint},
    }
    asyncio.create_task(_run_w1(session_id, config))
    return W1StartResponse(session_id=session_id, status="started")


@router.post("/workflow/w1/cancel", response_model=W1CancelResponse)
async def w1_cancel(body: W1CancelRequest) -> W1CancelResponse:
    """Cancel a running W1 Import session (best-effort — marks session as cancelled)."""
    session = _w1_sessions.get(body.session_id, {})
    if session:
        _w1_sessions[body.session_id] = {**session, "status": "cancelled"}
    return W1CancelResponse(status="cancelled")


@router.get("/workflow/w1/status", response_model=W1StatusResponse)
async def w1_status(session_id: str = "") -> W1StatusResponse:
    """Return current W1 Import workflow status."""
    session = _w1_sessions.get(session_id, {})
    return W1StatusResponse(
        status=session.get("status", "idle"),
        progress=session.get("progress", 0.0),
        errors=session.get("errors", []),
        completed_chunks=session.get("completed_chunks", 0),
        total_chunks=session.get("total_chunks", 0),
    )


# ── W2 Manuscript Sync endpoints ─────────────────────────────────────────────

@router.post("/workflow/w2/start", response_model=W2StartResponse)
async def w2_start(body: W2StartRequest) -> W2StartResponse:
    """Start a W2 Manuscript Sync run."""
    session_id = str(uuid.uuid4())
    _w2_sessions[session_id] = {
        "status": "running", "progress": 0.0, "errors": [], "proposals_count": 0,
    }
    config = {
        "project_path": body.project_path,
        "mode": body.mode,
        "target_chapter_id": body.target_chapter_id,
        "context": {"api_key": body.api_key, "model": body.model, "endpoint": body.endpoint},
    }
    asyncio.create_task(_run_w2(session_id, config))
    return W2StartResponse(session_id=session_id, status="started")


@router.get("/workflow/w2/status", response_model=W2StatusResult)
async def w2_status(session_id: str = "") -> W2StatusResult:
    """Return current W2 Manuscript Sync status."""
    session = _w2_sessions.get(session_id, {})
    return W2StatusResult(
        status=session.get("status", "idle"),
        progress=session.get("progress", 0.0),
        errors=session.get("errors", []),
        proposals_count=session.get("proposals_count", 0),
    )


# ── W4 Consistency Check models ───────────────────────────────────────────────

class W4StartRequest(BaseModel):
    project_path: str
    scope: str  # "scene" | "chapter" | "full"
    target_id: str
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"


class W4StartResult(BaseModel):
    session_id: str
    status: str


class W4StatusResult(BaseModel):
    status: str
    progress: float = 0.0
    issues: List[Any] = []
    severity_counts: dict = {}
    errors: List[str] = []


# ── W5 Simulation Engine models ───────────────────────────────────────────────

class W5StartRequest(BaseModel):
    project_path: str
    scenario_variable: str
    affected_chapter_ids: List[str]
    engines_selected: List[str]
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"


class W5StartResult(BaseModel):
    session_id: str
    status: str


class W5StatusResult(BaseModel):
    status: str
    progress: float = 0.0
    report_markdown: str = ""
    engine_results: dict = {}
    errors: List[str] = []


# ── W6 Beta Reader models ─────────────────────────────────────────────────────

class W6StartRequest(BaseModel):
    project_path: str
    persona_id: str
    target_chapter_ids: List[str]
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"


class W6StartResult(BaseModel):
    session_id: str
    status: str


class W6StatusResult(BaseModel):
    status: str
    progress: float = 0.0
    report_markdown: str = ""
    feedback_items: List[Any] = []
    errors: List[str] = []


# ── W4 background task ────────────────────────────────────────────────────────

async def _run_w4(session_id: str, config: dict) -> None:
    from sidecar.workflows.w4_consistency_check import run as w4_run
    try:
        result = await w4_run(config["project_path"], config)
        _w4_sessions[session_id] = {
            "status": result.get("status", "done"),
            "progress": result.get("progress", 1.0),
            "issues": result.get("issues", []),
            "severity_counts": result.get("severity_counts", {}),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        _w4_sessions[session_id] = {"status": "error", "progress": 0.0,
                                     "issues": [], "severity_counts": {}, "errors": [str(e)]}


# ── W5 background task ────────────────────────────────────────────────────────

async def _run_w5(session_id: str, config: dict) -> None:
    from sidecar.workflows.w5_simulation import run as w5_run
    try:
        result = await w5_run(config["project_path"], config)
        _w5_sessions[session_id] = {
            "status": result.get("status", "done"),
            "progress": result.get("progress", 1.0),
            "report_markdown": result.get("report_markdown", ""),
            "engine_results": result.get("engine_results", {}),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        _w5_sessions[session_id] = {"status": "error", "progress": 0.0,
                                     "report_markdown": "", "engine_results": {}, "errors": [str(e)]}


# ── W6 background task ────────────────────────────────────────────────────────

async def _run_w6(session_id: str, config: dict) -> None:
    from sidecar.workflows.w6_beta_reader import run as w6_run
    try:
        result = await w6_run(config["project_path"], config)
        _w6_sessions[session_id] = {
            "status": result.get("status", "done"),
            "progress": result.get("progress", 1.0),
            "report_markdown": result.get("report_markdown", ""),
            "feedback_items": result.get("feedback_items", []),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        _w6_sessions[session_id] = {"status": "error", "progress": 0.0,
                                     "report_markdown": "", "feedback_items": [], "errors": [str(e)]}


# ── W4 Consistency Check endpoints ───────────────────────────────────────────

@router.post("/workflow/w4/start", response_model=W4StartResult)
async def w4_start(body: W4StartRequest) -> W4StartResult:
    """Start a W4 Consistency Check run."""
    session_id = str(uuid.uuid4())
    _w4_sessions[session_id] = {"status": "running", "progress": 0.0,
                                 "issues": [], "severity_counts": {}, "errors": []}
    config = {
        "project_path": body.project_path,
        "scope": body.scope,
        "target_id": body.target_id,
        "context": {"api_key": body.api_key, "model": body.model, "endpoint": body.endpoint},
    }
    asyncio.create_task(_run_w4(session_id, config))
    return W4StartResult(session_id=session_id, status="started")


@router.get("/workflow/w4/status", response_model=W4StatusResult)
async def w4_status(session_id: str = "") -> W4StatusResult:
    """Return current W4 Consistency Check status."""
    session = _w4_sessions.get(session_id, {})
    return W4StatusResult(
        status=session.get("status", "idle"),
        progress=session.get("progress", 0.0),
        issues=session.get("issues", []),
        severity_counts=session.get("severity_counts", {}),
        errors=session.get("errors", []),
    )


# ── W5 Simulation Engine endpoints ───────────────────────────────────────────

@router.post("/workflow/w5/start", response_model=W5StartResult)
async def w5_start(body: W5StartRequest) -> W5StartResult:
    """Start a W5 Simulation Engine run."""
    session_id = str(uuid.uuid4())
    _w5_sessions[session_id] = {"status": "running", "progress": 0.0,
                                 "report_markdown": "", "engine_results": {}, "errors": []}
    config = {
        "project_path": body.project_path,
        "scenario_variable": body.scenario_variable,
        "affected_chapter_ids": body.affected_chapter_ids,
        "engines_selected": body.engines_selected,
        "context": {"api_key": body.api_key, "model": body.model, "endpoint": body.endpoint},
    }
    asyncio.create_task(_run_w5(session_id, config))
    return W5StartResult(session_id=session_id, status="started")


@router.get("/workflow/w5/status", response_model=W5StatusResult)
async def w5_status(session_id: str = "") -> W5StatusResult:
    """Return current W5 Simulation Engine status."""
    session = _w5_sessions.get(session_id, {})
    return W5StatusResult(
        status=session.get("status", "idle"),
        progress=session.get("progress", 0.0),
        report_markdown=session.get("report_markdown", ""),
        engine_results=session.get("engine_results", {}),
        errors=session.get("errors", []),
    )


# ── W6 Beta Reader endpoints ──────────────────────────────────────────────────

@router.post("/workflow/w6/start", response_model=W6StartResult)
async def w6_start(body: W6StartRequest) -> W6StartResult:
    """Start a W6 Beta Reader run."""
    session_id = str(uuid.uuid4())
    _w6_sessions[session_id] = {"status": "running", "progress": 0.0,
                                 "report_markdown": "", "feedback_items": [], "errors": []}
    config = {
        "project_path": body.project_path,
        "persona_id": body.persona_id,
        "target_chapter_ids": body.target_chapter_ids,
        "context": {"api_key": body.api_key, "model": body.model, "endpoint": body.endpoint},
    }
    asyncio.create_task(_run_w6(session_id, config))
    return W6StartResult(session_id=session_id, status="started")


@router.get("/workflow/w6/status", response_model=W6StatusResult)
async def w6_status(session_id: str = "") -> W6StatusResult:
    """Return current W6 Beta Reader status."""
    session = _w6_sessions.get(session_id, {})
    return W6StatusResult(
        status=session.get("status", "idle"),
        progress=session.get("progress", 0.0),
        report_markdown=session.get("report_markdown", ""),
        feedback_items=session.get("feedback_items", []),
        errors=session.get("errors", []),
    )


# ── Legacy stub endpoints (catch-all, must be LAST to avoid shadowing specific routes) ──

@router.post("/workflow/{workflow_id}/start")
async def start_workflow(workflow_id: str) -> None:
    raise HTTPException(status_code=501, detail=f"Workflow '{workflow_id}' start is not implemented.")


@router.post("/workflow/cancel")
async def cancel_workflow() -> None:
    raise HTTPException(status_code=501, detail="Workflow cancel is not implemented.")
