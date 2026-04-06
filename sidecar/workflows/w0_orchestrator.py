"""W0 — Orchestrator Workflow.

Decomposes a natural-language goal into workflow steps (W1–W7) and executes them
serially, with a permission gate before destructive or first-time steps.

Graph (looping):
  acquire_lock → parse_goal → validate_plan
      → [LOOP] check_permission → [if needed] request_permission → INTERRUPT
                                → execute_step → evaluate_result → advance_step
      → done → release_lock → END

Permission gate fires for:
  - plan[current_step].requires_permission == True
  - W1 (always)
  - config contains overwrite: true
  - First occurrence of each workflow type in this session
  - Step creates more than 10 entities (parsed from config)

Resuming after permission: /orchestrator/permission/{step_id}/grant resumes via
graph.ainvoke(Command(resume=True), config).
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from sidecar.models.state import OrchestratorState, OrchestratorStep, PermissionRequest
from sidecar.shared import s4_proposal_queue
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w0_prompts import W0_PARSE_GOAL, W0_EVALUATE_RESULT


# ── Dispatch table: workflow string → sidecar endpoint path ───────────────────

_WORKFLOW_ENDPOINTS: dict[str, str] = {
    "W1": "/workflow/w1/start",
    "W2": "/workflow/w2/start",
    "W3": "/workflow/w3/start",
    "W4": "/workflow/w4/start",
    "W5": "/workflow/w5/start",
    "W6": "/workflow/w6/start",
    "W7": "/metadata/ingest",
}

_WORKFLOW_STATUS_PATHS: dict[str, str] = {
    "W1": "/workflow/w1/status",
    "W2": "/workflow/w2/status",
    "W3": "/workflow/w3/status",
    "W4": "/workflow/w4/status",
    "W5": "/workflow/w5/status",
    "W6": "/workflow/w6/status",
    "W7": "/metadata/status",
}

_AVAILABLE_WORKFLOWS = {
    "W1": {"description": "Import a novel file", "config_keys": ["source_file_path"]},
    "W2": {"description": "Manuscript sync", "config_keys": ["mode", "target_chapter_id"]},
    "W3": {"description": "Writing assistant (generate prose)", "config_keys": ["scene_id", "task", "hitl_mode"]},
    "W4": {"description": "Consistency check", "config_keys": ["scope", "target_id"]},
    "W5": {"description": "Simulation engine", "config_keys": ["scenario_variable", "affected_chapter_ids", "engines_selected"]},
    "W6": {"description": "Beta reader", "config_keys": ["persona_id", "target_chapter_ids"]},
    "W7": {"description": "Metadata ingestion", "config_keys": ["source_file_path", "file_type"]},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_model(state: dict) -> ChatOpenAI:
    ctx = state.get("context", {})
    import os
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    return ChatOpenAI(
        model=ctx.get("model", "deepseek-chat"),
        api_key=api_key,
        base_url=ctx.get("endpoint", "https://api.deepseek.com/v1"),
        max_tokens=4096,
    )


def _parse_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return {}


def _sidecar_base(state: dict) -> str:
    port = state.get("context", {}).get("sidecar_port", 8765)
    return f"http://127.0.0.1:{port}"


def _needs_permission(step: dict, step_results: list[dict]) -> bool:
    """Return True if this step requires user permission."""
    workflow = step.get("workflow", "")
    config = step.get("config", {})

    if step.get("requires_permission"):
        return True
    if workflow == "W1":
        return True
    if config.get("overwrite"):
        return True
    # >10 new entities check
    entity_count = config.get("entity_count", 0)
    if isinstance(entity_count, int) and entity_count > 10:
        return True
    # First occurrence of this workflow type in the session
    completed_workflows = {r.get("workflow") for r in step_results if isinstance(r, dict)}
    if workflow not in completed_workflows:
        return True
    return False


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def node_acquire_lock(state: dict) -> dict:
    # W0 does not acquire the project lock — child workflows manage their own locks.
    # Acquiring here would block all child workflow POSTs since they also acquire the lock.
    return {}


async def node_parse_goal(state: dict) -> dict:
    model = _get_model(state)
    # Build project summary (lightweight)
    project_path = Path(state["project_path"])
    project_json_path = project_path / "project.json"
    project_summary = "(blank project)"
    if project_json_path.exists():
        try:
            pj = json.loads(project_json_path.read_text(encoding="utf-8"))
            title = pj.get("title", "Untitled")
            char_count = len(pj.get("characters", []))
            chapter_count = len(pj.get("chapters", []))
            project_summary = f"Title: {title}. Characters: {char_count}. Chapters: {chapter_count}."
        except Exception:
            pass

    prompt = W0_PARSE_GOAL.format(
        goal=state.get("goal", ""),
        available_workflows_json=json.dumps(_AVAILABLE_WORKFLOWS, indent=2),
        project_summary=project_summary,
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        data = _parse_json(resp.content)
        steps_raw = data.get("steps", [])
    except Exception as e:
        return {"status": "error", "errors": [f"parse_goal failed: {e}"]}

    plan: list[OrchestratorStep] = []
    for s in steps_raw:
        plan.append(OrchestratorStep(
            step_id=s.get("step_id", f"step_{uuid.uuid4().hex[:6]}"),
            workflow=s.get("workflow", ""),
            config=s.get("config", {}),
            rationale=s.get("rationale", ""),
            requires_permission=s.get("requires_permission", False),
            status="pending",
        ))

    total = max(len(plan), 1)
    return {"plan": plan, "current_step": 0, "status": "executing",
            "progress": 1.0 / (total + 1)}


async def node_validate_plan(state: dict) -> dict:
    plan = state.get("plan", [])
    errors: list[str] = []
    for step in plan:
        w = step.get("workflow", "")
        if w not in _AVAILABLE_WORKFLOWS:
            errors.append(f"Unknown workflow '{w}' in step {step.get('step_id')}")
    if errors:
        return {"status": "error", "errors": errors}
    return {}


async def node_check_permission(state: dict) -> dict:
    """Check if current step needs permission. If so, interrupt the graph."""
    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    step_results = state.get("step_results", [])

    if current >= len(plan):
        return {"status": "done"}

    step = plan[current]
    if not _needs_permission(step, step_results):
        return {}  # No permission needed — proceed to execute_step

    # Auto-approve bypass for testing / headless operation
    ctx = state.get("context", {})
    if ctx.get("auto_approve_all"):
        return {}  # Skip permission gate

    # Build permission request
    perm = PermissionRequest(
        step_id=step["step_id"],
        description=f"Run {step['workflow']}: {step.get('rationale', '')}",
        risk_level="high" if step["workflow"] == "W1" else "medium",
        affected_entities=list(step.get("config", {}).keys()),
    )

    # Mark step as waiting
    updated_plan = list(plan)
    updated_plan[current] = {**step, "status": "pending"}

    # Interrupt graph — waits for /orchestrator/permission/{step_id}/grant
    interrupt({"permission_request": perm, "step_id": step["step_id"]})

    return {"pending_permission": perm, "plan": updated_plan, "status": "waiting_permission"}


async def node_execute_step(state: dict) -> dict:
    """POST to child workflow endpoint and poll until done."""
    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    if current >= len(plan):
        return {}

    step = plan[current]
    workflow = step.get("workflow", "")
    config = step.get("config", {})
    endpoint = _workflow_endpoints_for(workflow)
    base = _sidecar_base(state)

    # Mark step as running
    updated_plan = list(plan)
    updated_plan[current] = {**step, "status": "running"}

    ctx = state.get("context", {})
    payload = {
        "project_path": state["project_path"],
        **config,
        "context": ctx,
        # Flatten LLM credentials for workflow start endpoints (top-level fields)
        "api_key": ctx.get("api_key", ""),
        "model": ctx.get("model", "deepseek-chat"),
        "endpoint": ctx.get("endpoint", "https://api.deepseek.com/v1"),
    }
    step_result: dict = {"workflow": workflow, "step_id": step["step_id"]}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{base}{endpoint}", json=payload)
            resp.raise_for_status()
            start_data = resp.json()
            session_id = start_data.get("session_id", "")

            # Poll for completion (max 5 min)
            status_path = _workflow_status_for(workflow)
            for _ in range(150):
                await asyncio.sleep(2)
                try:
                    s = await client.get(f"{base}{status_path}", params={"session_id": session_id})
                    s_data = s.json()
                    w_status = s_data.get("status", "")
                    if w_status in ("done", "completed", "error", "failed"):
                        step_result["status"] = "completed" if w_status in ("done", "completed") else "failed"
                        step_result["summary"] = json.dumps(s_data)[:400]
                        break
                except Exception:
                    continue
            else:
                step_result["status"] = "failed"
                step_result["summary"] = "Timed out"

        updated_plan[current] = {**step, "status": step_result.get("status", "done")}
    except Exception as e:
        step_result["status"] = "failed"
        step_result["summary"] = str(e)
        updated_plan[current] = {**step, "status": "failed"}

    return {"plan": updated_plan, "_last_step_result": step_result}


def _workflow_endpoints_for(workflow: str) -> str:
    return _WORKFLOW_ENDPOINTS.get(workflow, f"/workflow/{workflow.lower()}/start")


def _workflow_status_for(workflow: str) -> str:
    return _WORKFLOW_STATUS_PATHS.get(workflow, f"/workflow/{workflow.lower()}/status")


async def node_evaluate_result(state: dict) -> dict:
    """Ask Claude if the step succeeded and if the plan needs revision."""
    model = _get_model(state)
    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    last = state.get("_last_step_result", {})
    step_results = list(state.get("step_results", []))
    step_results.append(last)

    remaining = plan[current + 1:]
    prompt = W0_EVALUATE_RESULT.format(
        step_id=last.get("step_id", ""),
        workflow=last.get("workflow", ""),
        step_result_summary=last.get("summary", ""),
        remaining_steps_json=json.dumps(remaining, ensure_ascii=False),
        original_goal=state.get("goal", ""),
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        eval_data = _parse_json(resp.content)
    except Exception:
        eval_data = {"step_succeeded": True, "revise_plan": False, "continue_execution": True}

    updates: dict = {"step_results": step_results}

    if not eval_data.get("continue_execution", True):
        updates["status"] = "error"
        updates["errors"] = [f"Orchestrator aborted: {eval_data.get('failure_reason', 'unknown')}"]
        return updates

    if eval_data.get("revise_plan") and eval_data.get("revised_steps"):
        # Replace remaining plan steps with revised ones
        revised = [OrchestratorStep(
            step_id=s.get("step_id", f"step_{uuid.uuid4().hex[:6]}"),
            workflow=s.get("workflow", ""),
            config=s.get("config", {}),
            rationale=s.get("rationale", ""),
            requires_permission=s.get("requires_permission", False),
            status="pending",
        ) for s in eval_data["revised_steps"]]
        updates["plan"] = plan[:current + 1] + revised

    return updates


async def node_advance_step(state: dict) -> dict:
    current = state.get("current_step", 0)
    plan = state.get("plan", [])
    next_step = current + 1
    total = max(len(plan), 1)
    progress = min(0.1 + 0.85 * next_step / total, 0.95)
    return {"current_step": next_step, "progress": progress}


def should_continue(state: dict) -> str:
    """Route: continue loop or go to done."""
    if state.get("status") in ("error", "done", "waiting_permission"):
        return "done"
    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    if current >= len(plan):
        return "done"
    return "check_permission"


async def node_done(state: dict) -> dict:
    """Aggregate all proposals and mark orchestrator done."""
    proposals = list(state.get("proposals", []))
    return {"status": "done", "proposals": proposals, "progress": 1.0}


async def node_release_lock(state: dict) -> dict:
    # W0 does not hold the project lock
    return {}


# ── Graph construction ────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(OrchestratorState)

    builder.add_node("acquire_lock", node_acquire_lock)
    builder.add_node("parse_goal", node_parse_goal)
    builder.add_node("validate_plan", node_validate_plan)
    builder.add_node("check_permission", node_check_permission)
    builder.add_node("execute_step", node_execute_step)
    builder.add_node("evaluate_result", node_evaluate_result)
    builder.add_node("advance_step", node_advance_step)
    builder.add_node("done", node_done)
    builder.add_node("release_lock", node_release_lock)

    builder.set_entry_point("acquire_lock")
    builder.add_edge("acquire_lock", "parse_goal")
    builder.add_edge("parse_goal", "validate_plan")

    # After validate_plan, enter the execution loop
    builder.add_edge("validate_plan", "check_permission")

    # check_permission → execute_step (no interrupt needed) or interrupts internally
    builder.add_edge("check_permission", "execute_step")
    builder.add_edge("execute_step", "evaluate_result")
    builder.add_edge("evaluate_result", "advance_step")

    # After advance_step: loop back or exit
    builder.add_conditional_edges(
        "advance_step",
        should_continue,
        {
            "check_permission": "check_permission",
            "done": "done",
        },
    )

    builder.add_edge("done", "release_lock")
    builder.add_edge("release_lock", END)

    memory = MemorySaver()
    _graph = builder.compile(checkpointer=memory)
    return _graph


async def run(project_path: str, config: dict) -> dict:
    initial_state: dict = {
        "project_path": project_path,
        "workflow_id": "W0",
        "goal": config.get("goal", ""),
        "plan": [],
        "current_step": 0,
        "step_results": [],
        "pending_permission": None,
        "status": "planning",
        "progress": 0.0,
        "errors": [],
        "proposals": [],
        "context": config.get("context", {}),
    }
    thread_id = config.get("thread_id", f"w0-{uuid.uuid4().hex[:8]}")
    graph = get_graph()
    result = await graph.ainvoke(initial_state, {"configurable": {"thread_id": thread_id}})
    return dict(result)
