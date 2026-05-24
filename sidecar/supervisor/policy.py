"""W1 Supervisor policy loop.

Entry points:
  run_supervisor_streaming(project_path, config)  — async generator, same interface as run_streaming()
  run_supervisor_policy(state, tools)              — pure policy loop, returns final state
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sidecar.models.state import PROFILE_CONFIGS, ImportSupervisorState
from sidecar.supervisor.tool_registry import build_tool_registry
from sidecar.workflows.w1_import import (
    _chunk_progress,
    node_split_chunks,
    node_validate_file,
)


# ── Gate thresholds ─────────────────────────────────────────────────────────────

_CHAR_DENSITY_THRESHOLD = 0.5
_EVENT_DENSITY_THRESHOLD = 0.5
_FAILED_PROMPTS_THRESHOLD = 3


# ── Progress milestones ─────────────────────────────────────────────────────────

_PROGRESS_SEGMENT_MANIFEST = 0.05
_PROGRESS_EXTRACT_START = 0.10
_PROGRESS_EXTRACT_END = 0.65
_PROGRESS_REDUCE_REPAIR = 0.70
_PROGRESS_ARCHITECT = 0.80
_PROGRESS_QA_REVIEW = 0.88
_PROGRESS_PROPOSAL = 0.95
_PROGRESS_DONE = 1.0


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _record_decision(
    state: ImportSupervisorState,
    stage: str,
    tool_called: str,
    reason: str,
    metrics_before: dict,
    metrics_after: dict,
    action: str,
    rerun_targets: list[str] | None = None,
) -> ImportSupervisorState:
    decisions = list(state.get("supervisor_decisions", []))
    decisions.append({
        "iteration": state.get("supervisor_iteration", 0),
        "stage": stage,
        "tool_called": tool_called,
        "reason": reason,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "action": action,
        "rerun_targets": rerun_targets or [],
        "timestamp": _now_iso(),
    })
    return {**state, "supervisor_decisions": decisions}


def _evaluate_window_gate(metrics: dict, profile_config: dict) -> tuple[bool, list[str]]:
    """Return (gate_passed, list_of_failure_reasons) for a window's metrics."""
    chapters = max(metrics.get("chapter_count", 1), 1)
    char_density = metrics.get("char_count_extracted", 0) / chapters
    event_density = metrics.get("event_count_extracted", 0) / chapters
    failed = len(metrics.get("failed_prompts", []))
    reasons: list[str] = []
    if char_density < _CHAR_DENSITY_THRESHOLD:
        reasons.append(f"char_density={char_density:.2f}<{_CHAR_DENSITY_THRESHOLD}")
    if event_density < _EVENT_DENSITY_THRESHOLD:
        reasons.append(f"event_density={event_density:.2f}<{_EVENT_DENSITY_THRESHOLD}")
    if failed >= _FAILED_PROMPTS_THRESHOLD:
        reasons.append(f"failed_prompts={failed}>={_FAILED_PROMPTS_THRESHOLD}")
    return not reasons, reasons


async def _process_window(
    state: ImportSupervisorState,
    tools: dict,
    window_id: str,
    profile_config: dict,
) -> ImportSupervisorState:
    """Extract + optionally cross-validate + gate-check one window. Mutates nothing — returns new state."""
    validation = profile_config.get("validation_strictness", "per_window")
    max_reruns = profile_config.get("max_rerun_iterations", 2)

    # Extract
    update = await tools["extract_window"](state, window_id)
    state = {**state, **update}
    state = _record_decision(
        state, "extract_window", "extract_window", f"primary extraction for {window_id}",
        {}, {}, "proceed",
    )

    # Cross-validate
    if validation != "off":
        cv_update = await tools["cross_validate_window"](state, window_id)
        state = {**state, **cv_update}
        state = _record_decision(
            state, "cross_validate_window", "cross_validate_window",
            f"cross-validate {window_id}", {}, {}, "proceed",
        )

    # Gate evaluation + reruns
    metrics_dict = dict(state.get("window_metrics", {}))
    metrics = metrics_dict.get(window_id, {})
    rerun_count = 0

    while rerun_count < max_reruns:
        gate_passed, reasons = _evaluate_window_gate(metrics, profile_config)
        if gate_passed:
            break

        chapters = max(metrics.get("chapter_count", 1), 1)
        char_density = metrics.get("char_count_extracted", 0) / chapters
        missing_names = metrics.get("missing_majors", [])

        # Choose strategy: split if char_density is very low and window has multiple chapters,
        # otherwise augment with missing_char_names hint
        window = next((w for w in state.get("prompt_windows", []) if w.get("id") == window_id), {})
        can_split = len(window.get("chunk_ids", [])) > 1 and char_density < _CHAR_DENSITY_THRESHOLD
        strategy = "split" if can_split else "augment"

        rerun_update = await tools["rerun_window"](state, window_id, strategy, missing_names or None)
        state = {**state, **rerun_update}
        state = _record_decision(
            state, "rerun_window", "rerun_window",
            f"gate failures: {reasons}; strategy={strategy}",
            {"reasons": reasons}, {}, "rerun", [window_id],
        )

        metrics_dict = dict(state.get("window_metrics", {}))
        metrics = metrics_dict.get(window_id, {})
        rerun_count += 1

    return state


async def run_supervisor_policy(
    state: ImportSupervisorState,
    tools: dict,
) -> ImportSupervisorState:
    """Execute the full supervisor policy loop. Returns final state."""
    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(
        state.get("prompt_profile", "balanced"), PROFILE_CONFIGS["balanced"]
    )

    # ── 1. Segment manifest ──────────────────────────────────────────────────
    seg_update = await tools["segment_manifest"](state)
    state = {**state, **seg_update, "current_stage": "segment_manifest"}
    state = _record_decision(
        state, "segment_manifest", "segment_manifest", "build prompt windows",
        {}, {"window_count": len(state.get("prompt_windows", []))}, "proceed",
    )

    # ── 2. Extract + validate each window (batches of 3) ────────────────────
    windows = list(state.get("prompt_windows", []))
    batch_size = 3
    for batch_start in range(0, len(windows), batch_size):
        batch = windows[batch_start: batch_start + batch_size]
        tasks = [_process_window(state, tools, w["id"], profile_config) for w in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                errs = list(state.get("errors", [])) + [str(result)]
                state = {**state, "errors": errs}
            else:
                # Merge window metrics and entity_registry updates back
                state = {
                    **state,
                    "entity_registry": result.get("entity_registry", state.get("entity_registry", {})),
                    "window_metrics": {**state.get("window_metrics", {}), **result.get("window_metrics", {})},
                    "supervisor_decisions": result.get("supervisor_decisions", state.get("supervisor_decisions", [])),
                    "supervisor_log": result.get("supervisor_log", state.get("supervisor_log", [])),
                    "errors": result.get("errors", state.get("errors", [])),
                }

    state = {**state, "current_stage": "extract_windows"}

    # ── 3. Reduce entities ───────────────────────────────────────────────────
    reduce_update = await tools["reduce_entities"](state)
    state = {**state, **reduce_update, "current_stage": "reduce_entities"}
    state = _record_decision(
        state, "reduce_entities", "reduce_entities", "deduplicate entity registry",
        {}, {}, "proceed",
    )

    # ── 4. Minor repair ──────────────────────────────────────────────────────
    repair_update = await tools["minor_repair"](state)
    state = {**state, **repair_update, "current_stage": "minor_repair"}
    state = _record_decision(
        state, "minor_repair", "minor_repair", "deterministic repair pass",
        {}, {}, "repair",
    )

    # ── 5. Architect timeline ────────────────────────────────────────────────
    arch_update = await tools["architect_timeline"](state)
    state = {**state, **arch_update, "current_stage": "architect_timeline"}
    state = _record_decision(
        state, "architect_timeline", "architect_timeline", "build timeline structure",
        {}, {}, "proceed",
    )

    # ── 6. QA review + optional full rerun loop ──────────────────────────────
    max_supervisor_iterations = state.get("max_supervisor_iterations", 3)
    for sup_iter in range(max_supervisor_iterations):
        state = {**state, "supervisor_iteration": sup_iter}

        qa_update = await tools["qa_review"](state)
        state = {**state, **qa_update, "current_stage": "qa_review"}
        gate_failures = list(state.get("gate_failures", []))
        state = _record_decision(
            state, "qa_review", "qa_review", "quality gate evaluation",
            {}, {"gate_failures": len(gate_failures)},
            "proceed" if not gate_failures else "rerun",
            [f["window_id"] for f in gate_failures if "window_id" in f],
        )

        if not gate_failures:
            break

        # Rerun only windows responsible for failing gates
        failing_window_ids = list({f["window_id"] for f in gate_failures if "window_id" in f})
        for wid in failing_window_ids:
            state = await _process_window(state, tools, wid, profile_config)

        # Redo reduce + repair after reruns
        reduce_update = await tools["reduce_entities"](state)
        state = {**state, **reduce_update}
        repair_update = await tools["minor_repair"](state)
        state = {**state, **repair_update}

    # ── 7. Proposal write ────────────────────────────────────────────────────
    proposal_update = await tools["proposal_write"](state)
    state = {**state, **proposal_update, "current_stage": "proposal_write"}
    state = _record_decision(
        state, "proposal_write", "proposal_write", "write final import proposal",
        {}, {}, "proceed",
    )

    return state


async def run_supervisor_streaming(
    project_path: str,
    config: dict,
) -> AsyncGenerator[dict, None]:
    """Async generator — same interface as run_streaming(). Yields progress dicts."""
    import_mode = config.get("import_mode", "import_all")
    profile = config.get("prompt_profile") or config.get("context", {}).get("prompt_profile", "balanced")
    profile_config = PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS["balanced"])
    session_id = config.get("session_id", "")

    import_run_id = f"sup_{uuid.uuid4().hex[:10]}"

    state: ImportSupervisorState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "import_mode": import_mode,
        "prompt_profile": profile,
        "profile_config": profile_config,
        "context": config.get("context", {}),
        "chunks": [],
        "import_run_id": import_run_id,
        "import_run_manifest": {},
        "evidence_cards": [],
        "reducer_artifact": {},
        "timeline_architecture": {},
        "import_review_report": {},
        "project_structure_digest": {},
        "prompt_windows": [],
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "chunk_extractions": [],
        "raw_relationships": [],
        "relationships": [],
        "character_tags": [],
        "world_settings": {},
        "timeline_branches": [],
        "world_containers": [],
        "manuscript_chapters": [],
        "proposals": [],
        "checkpoint_path": str(__import__("pathlib").Path(project_path) / "import_progress.json"),
        "progress": 0.0,
        "errors": [],
        "status": "running",
        # Supervisor fields
        "use_supervisor": True,
        "supervisor_decisions": [],
        "current_stage": "init",
        "window_metrics": {},
        "rerun_candidates": [],
        "gate_failures": [],
        "supervisor_iteration": 0,
        "max_supervisor_iterations": 3,
        "supervisor_log": [],
        "minor_repair_log": [],
    }

    def _emit(progress: float, node: str, errors: list | None = None) -> dict:
        chunks_done = len(state.get("chunk_extractions", []))
        total = len(state.get("chunks", [])) or 1
        _chunk_progress[project_path] = {"completed": chunks_done, "total": total}
        return {
            "progress": progress,
            "errors": errors or [],
            "completed_chunks": chunks_done,
            "total_chunks": total,
            "current_node": node,
            "import_review_report": state.get("import_review_report", {}),
            "proposals_count": len(state.get("proposals", [])),
        }

    # Supervisor only runs for import_all
    if import_mode != "import_all":
        yield _emit(0.01, "supervisor_skip")
        from sidecar.workflows.w1_import import run_streaming as _legacy_stream
        async for update in _legacy_stream(project_path, config):
            yield update
        return

    # ── Validate file + split chunks ─────────────────────────────────────────
    try:
        validate_result = await node_validate_file(state)
        state = {**state, **validate_result}
        yield _emit(0.02, "validate_file", state.get("errors", []))

        split_result = await node_split_chunks(state)
        state = {**state, **split_result}
        total_chunks = len(state.get("chunks", []))
        _chunk_progress[project_path] = {"completed": 0, "total": total_chunks}
        yield _emit(0.05, "split_chunks", state.get("errors", []))
    except Exception as exc:
        yield _emit(0.0, "error", [str(exc)])
        return

    tools = build_tool_registry()

    # ── Policy loop with progress reporting ──────────────────────────────────
    windows = state.get("prompt_windows", [])
    total_windows = max(len(windows), 1)

    async def _policy_with_progress():
        nonlocal state
        profile_config_local = state.get("profile_config") or profile_config

        # segment_manifest
        seg_update = await tools["segment_manifest"](state)
        state = {**state, **seg_update, "current_stage": "segment_manifest"}
        _emit(_PROGRESS_SEGMENT_MANIFEST, "segment_manifest")

        # Extract windows (batches of 3, progress linearly from 0.10 → 0.65)
        windows_local = list(state.get("prompt_windows", []))
        total_w = max(len(windows_local), 1)
        batch_size = 3
        window_idx = 0
        for batch_start in range(0, len(windows_local), batch_size):
            batch = windows_local[batch_start: batch_start + batch_size]
            tasks = [_process_window(state, tools, w["id"], profile_config_local) for w in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    errs = list(state.get("errors", [])) + [str(result)]
                    state = {**state, "errors": errs}
                else:
                    state = {
                        **state,
                        "entity_registry": result.get("entity_registry", state.get("entity_registry", {})),
                        "window_metrics": {**state.get("window_metrics", {}), **result.get("window_metrics", {})},
                        "supervisor_decisions": result.get("supervisor_decisions", state.get("supervisor_decisions", [])),
                        "supervisor_log": result.get("supervisor_log", state.get("supervisor_log", [])),
                        "errors": result.get("errors", state.get("errors", [])),
                    }
                window_idx += 1
            progress = _PROGRESS_EXTRACT_START + (_PROGRESS_EXTRACT_END - _PROGRESS_EXTRACT_START) * (window_idx / total_w)
            _chunk_progress[project_path] = {"completed": window_idx, "total": total_w}
            yield progress, "extract_windows", state.get("errors", [])

        state = {**state, "current_stage": "extract_windows"}

        # Reduce + repair
        reduce_update = await tools["reduce_entities"](state)
        state = {**state, **reduce_update, "current_stage": "reduce_entities"}
        repair_update = await tools["minor_repair"](state)
        state = {**state, **repair_update, "current_stage": "minor_repair"}
        yield _PROGRESS_REDUCE_REPAIR, "reduce_repair", state.get("errors", [])

        # Architect
        arch_update = await tools["architect_timeline"](state)
        state = {**state, **arch_update, "current_stage": "architect_timeline"}
        yield _PROGRESS_ARCHITECT, "architect_timeline", state.get("errors", [])

        # QA + optional reruns
        max_sup_iters = state.get("max_supervisor_iterations", 3)
        for sup_iter in range(max_sup_iters):
            state = {**state, "supervisor_iteration": sup_iter}
            qa_update = await tools["qa_review"](state)
            state = {**state, **qa_update, "current_stage": "qa_review"}
            gate_failures = list(state.get("gate_failures", []))
            if not gate_failures:
                break
            failing_ids = list({f["window_id"] for f in gate_failures if "window_id" in f})
            for wid in failing_ids:
                state = await _process_window(state, tools, wid, profile_config_local)
            reduce_u = await tools["reduce_entities"](state)
            state = {**state, **reduce_u}
            repair_u = await tools["minor_repair"](state)
            state = {**state, **repair_u}
        yield _PROGRESS_QA_REVIEW, "qa_review", state.get("errors", [])

        # Proposal write
        proposal_update = await tools["proposal_write"](state)
        state = {**state, **proposal_update, "current_stage": "proposal_write"}
        yield _PROGRESS_PROPOSAL, "proposal_write", state.get("errors", [])

    async for progress, node, errors in _policy_with_progress():
        # Propagate supervisor decisions back to session if session_id provided
        if session_id:
            try:
                from sidecar.routers.workflows import _w1_sessions  # type: ignore
                session = _w1_sessions.get(session_id, {})
                session["supervisor_decisions"] = state.get("supervisor_decisions", [])
                session["gate_failures"] = state.get("gate_failures", [])
                session["window_metrics"] = state.get("window_metrics", {})
                session["supervisor_iteration"] = state.get("supervisor_iteration", 0)
            except Exception:
                pass
        yield _emit(progress, node, errors)

    yield _emit(_PROGRESS_DONE, "done")
