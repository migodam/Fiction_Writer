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
    prompt_profile: str = "balanced"
    api_key: str = ""
    model: str = "deepseek-chat"
    endpoint: str = "https://api.deepseek.com/v1"
    use_supervisor: bool = False


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
    current_step: str = ""
    prompt_profile: str = "balanced"
    proposals_count: int = 0
    import_review_report: dict = {}


class W1ConsoleResponse(BaseModel):
    entries: List[Any] = []
    paused: bool = False
    breakpoint_chunk: Optional[int] = None


class W1BreakpointRequest(BaseModel):
    session_id: str
    chunk_id: Optional[int] = None   # None = clear breakpoint


class W1ResumeRequest(BaseModel):
    session_id: str


class W1RewindRequest(BaseModel):
    session_id: str
    to_chunk_id: int


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
    from sidecar.workflows.w1_import import run_streaming, _chunk_progress, _chunk_log
    project_path = config["project_path"]

    # Poll _chunk_progress and _chunk_log every second so that mid-node chunk
    # updates (written by node_process_chunks after each individual chunk) are
    # reflected in the status and console endpoints without waiting for the node.
    ctrl: dict = {"active": True}

    async def _poll_chunk_progress() -> None:
        while ctrl["active"]:
            await asyncio.sleep(1)
            progress_data = _chunk_progress.get(project_path)
            log_entries = _chunk_log.get(project_path, [])
            current = _w1_sessions.get(session_id, {})
            if current.get("status") not in ("running", "paused"):
                continue
            updates: dict = {}
            if progress_data:
                c = progress_data.get("completed", 0)
                t = progress_data.get("total", 0)
                updates = {
                    "completed_chunks": c,
                    "total_chunks": t,
                    "progress": 0.1 + 0.7 * (c / max(t, 1)),
                    "current_step": "process_chunks",
                }
            if log_entries:
                updates["chunk_log"] = log_entries[:]
            if updates:
                _w1_sessions[session_id] = {**current, **updates}

    poll_task = asyncio.create_task(_poll_chunk_progress())

    try:
        async for state_update in run_streaming(project_path, config):
            current = _w1_sessions.get(session_id, {})
            _w1_sessions[session_id] = {
                **current,
                "status": "running",
                "progress": state_update.get("progress", 0.0),
                "errors": state_update.get("errors", []),
                "completed_chunks": state_update.get("completed_chunks", 0),
                "total_chunks": state_update.get("total_chunks", 0),
                "current_step": state_update.get("current_node", ""),
                "prompt_profile": current.get("prompt_profile", config.get("prompt_profile", "balanced")),
                "proposals_count": state_update.get("proposals_count", current.get("proposals_count", 0)),
                "import_review_report": state_update.get("import_review_report") or current.get("import_review_report", {}),
            }
        # Final state from the last update
        final = _w1_sessions.get(session_id, {})
        final["status"] = "done"
        final["progress"] = 1.0
        _w1_sessions[session_id] = final
    except Exception as e:
        _w1_sessions[session_id] = {
            "status": "error", "progress": 0.0, "errors": [str(e)],
            "completed_chunks": 0, "total_chunks": 0,
            "chunk_log": _chunk_log.get(project_path, []),
            "paused": False, "breakpoint_chunk": None,
        }
    finally:
        ctrl["active"] = False
        poll_task.cancel()
        _chunk_progress.pop(project_path, None)
        _chunk_log.pop(project_path, None)


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
    config = {
        "project_path": body.project_path,
        "source_file_path": body.source_file_path,
        "import_mode": body.import_mode,
        "prompt_profile": body.prompt_profile,
        "use_supervisor": body.use_supervisor,
        "context": {
            "api_key": body.api_key,
            "model": body.model,
            "endpoint": body.endpoint,
            "prompt_profile": body.prompt_profile,
            "use_supervisor": body.use_supervisor,
        },
        "session_id": session_id,
    }
    _w1_sessions[session_id] = {
        "status": "running", "progress": 0.0, "errors": [],
        "completed_chunks": 0, "total_chunks": 0,
        "prompt_profile": body.prompt_profile,
        "use_supervisor": body.use_supervisor,
        "supervisor_decisions": [],
        "gate_failures": [],
        "window_metrics": {},
        "supervisor_iteration": 0,
        "chunk_log": [],
        "paused": False,
        "breakpoint_chunk": None,
        "project_path": body.project_path,
        "config": config,
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


@router.get("/workflow/w1/supervisor_status")
async def w1_supervisor_status(session_id: str = "") -> dict:
    """Return supervisor orchestration state for a running or completed session."""
    session = _w1_sessions.get(session_id, {})
    return {
        "supervisor_decisions": session.get("supervisor_decisions", []),
        "gate_failures": session.get("gate_failures", []),
        "window_metrics": session.get("window_metrics", {}),
        "supervisor_iteration": session.get("supervisor_iteration", 0),
    }


@router.get("/workflow/w1/console", response_model=W1ConsoleResponse)
async def w1_console(session_id: str = "", after: int = 0) -> W1ConsoleResponse:
    """Return new chunk log entries since index `after`."""
    session = _w1_sessions.get(session_id, {})
    all_entries = session.get("chunk_log", [])
    return W1ConsoleResponse(
        entries=all_entries[after:],
        paused=session.get("paused", False),
        breakpoint_chunk=session.get("breakpoint_chunk"),
    )


@router.post("/workflow/w1/set_breakpoint")
async def w1_set_breakpoint(body: W1BreakpointRequest) -> dict:
    """Set or clear a breakpoint at a given chunk index."""
    from sidecar.workflows.w1_import import _breakpoint_chunks
    session = _w1_sessions.get(body.session_id, {})
    if session:
        session["breakpoint_chunk"] = body.chunk_id
        _w1_sessions[body.session_id] = session
        project_path = session.get("project_path", "")
        if project_path:
            _breakpoint_chunks[project_path] = body.chunk_id
    return {"ok": True, "breakpoint_chunk": body.chunk_id}


@router.post("/workflow/w1/resume")
async def w1_resume(body: W1ResumeRequest) -> dict:
    """Resume a paused W1 import session."""
    from sidecar.workflows.w1_import import _pause_events
    session = _w1_sessions.get(body.session_id, {})
    if session:
        session["paused"] = False
        session["breakpoint_chunk"] = None
        _w1_sessions[body.session_id] = session
        project_path = session.get("project_path", "")
        if project_path and project_path in _pause_events:
            _pause_events[project_path].set()
    return {"ok": True}


@router.post("/workflow/w1/rewind")
async def w1_rewind(body: W1RewindRequest) -> dict:
    """Rewind import to a prior checkpoint state and restart from that point."""
    import json
    from pathlib import Path
    from sidecar.workflows.w1_import import _cancel_events, _pause_events, _breakpoint_chunks

    session = _w1_sessions.get(body.session_id, {})
    if not session:
        return {"ok": False, "error": "session_not_found"}

    project_path = session.get("project_path", "")
    if not project_path:
        return {"ok": False, "error": "project_path_missing"}

    # Signal cancel of the current run
    if project_path in _cancel_events:
        _cancel_events[project_path].set()
    # Unblock any pause
    if project_path in _pause_events:
        _pause_events[project_path].set()

    # Wait briefly for session to terminate
    for _ in range(20):
        await asyncio.sleep(0.2)
        if _w1_sessions.get(body.session_id, {}).get("status") in ("cancelled", "error", "done"):
            break

    # Load and truncate checkpoint
    checkpoint_path = Path(project_path) / "system" / "imports" / "import_progress.json"
    if not checkpoint_path.exists():
        checkpoint_path = Path(project_path) / "import_progress.json"

    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                cp = json.load(f)
            cp["completed_chunk_ids"] = [cid for cid in cp.get("completed_chunk_ids", []) if cid < body.to_chunk_id]
            cp["chunk_extractions"] = [e for e in cp.get("chunk_extractions", []) if e.get("chunk_id", 0) < body.to_chunk_id]
            # Rebuild registry from truncated extractions (approximate — full rebuild happens in node)
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(cp, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            return {"ok": False, "error": f"checkpoint rewind failed: {exc}"}

    # Re-launch with same config
    old_config = session.get("config", {})
    if not old_config:
        return {"ok": False, "error": "original config missing from session"}

    new_session_id = str(uuid.uuid4())
    _w1_sessions[new_session_id] = {
        "status": "running", "progress": 0.0, "errors": [],
        "completed_chunks": body.to_chunk_id, "total_chunks": session.get("total_chunks", 0),
        "chunk_log": session.get("chunk_log", [])[:body.to_chunk_id],
        "paused": False, "breakpoint_chunk": None,
        "project_path": project_path,
        "config": old_config,
    }
    _breakpoint_chunks.pop(project_path, None)
    asyncio.create_task(_run_w1(new_session_id, old_config))
    return {"ok": True, "new_session_id": new_session_id}


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
        current_step=session.get("current_step", ""),
        prompt_profile=session.get("prompt_profile", "balanced"),
        proposals_count=session.get("proposals_count", 0),
        import_review_report=session.get("import_review_report", {}),
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
