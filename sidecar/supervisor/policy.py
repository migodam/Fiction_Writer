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

from sidecar.models.state import (
    PROFILE_CONFIGS,
    ImportSupervisorState,
    ThematicRerunRequest,
    ToolOperatingSpec,
    plan_converge_target,
    plan_import_pipeline,
    plan_orchestrator_targets,
    plan_tool_operating_spec,
    select_granularity_profile,
)
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


def _merge_registries(base: dict, update: dict) -> dict:
    """Union entity_registry sub-dicts. Base keys win — earlier windows are not clobbered."""
    return {
        "characters":     {**update.get("characters", {}),     **base.get("characters", {})},
        "events":         {**update.get("events", {}),         **base.get("events", {})},
        "world":          {**update.get("world", {}),          **base.get("world", {})},
        "world_detailed": {**update.get("world_detailed", {}), **base.get("world_detailed", {})},
    }


def _merge_window_result(state: ImportSupervisorState, result: dict) -> ImportSupervisorState:
    """Merge a single window result into accumulated state without replacing earlier data."""
    base_decisions = state.get("supervisor_decisions", [])
    result_decisions = result.get("supervisor_decisions", [])
    new_decisions = base_decisions + [d for d in result_decisions if d not in base_decisions]

    base_log = state.get("supervisor_log", [])
    result_log = result.get("supervisor_log", [])
    new_log = base_log + [l for l in result_log if l not in base_log]

    base_errors = state.get("errors", [])
    result_errors = result.get("errors", [])
    new_errors = base_errors + [e for e in result_errors if e not in base_errors]

    return {
        **state,
        "entity_registry": _merge_registries(
            state.get("entity_registry", {}), result.get("entity_registry", {})
        ),
        "raw_relationships": list(state.get("raw_relationships", [])) + list(result.get("raw_relationships", [])),
        "window_metrics": {**state.get("window_metrics", {}), **result.get("window_metrics", {})},
        "supervisor_decisions": new_decisions,
        "supervisor_log": new_log,
        "errors": new_errors,
    }


def _chapter_count_from_state(state: ImportSupervisorState) -> int:
    chunks = state.get("chunks", [])
    if chunks:
        return max(len(chunks), 1)
    windows = state.get("prompt_windows", [])
    return max(sum(len(w.get("chunk_ids", [])) or 1 for w in windows), 1)


def _ensure_orchestrator_plan(state: ImportSupervisorState) -> ImportSupervisorState:
    if state.get("tool_operating_spec") and state.get("converge_target"):
        return state
    context = state.get("context", {})
    chapter_count = _chapter_count_from_state(state)
    prompt_profile = state.get("prompt_profile", "balanced")
    source_language = state.get("source_language", "en")

    spec = plan_tool_operating_spec(
        prompt_profile=prompt_profile,
        source_language=source_language,
        chapter_count=chapter_count,
        overrides=context.get("tool_operating_spec_overrides", {}),
        use_supervisor=state.get("use_supervisor"),
        use_orchestrator=context.get("use_orchestrator"),
    )
    granularity_profile = select_granularity_profile(
        chapter_count=chapter_count,
        source_language=source_language,
        prompt_profile=prompt_profile,
        import_mode=state.get("import_mode", "import_all"),
    )
    target = plan_converge_target(spec, source_language, chapter_count, granularity_profile=granularity_profile)
    import_plan = plan_import_pipeline(
        granularity_profile,
        spec,
        source_language=source_language,
        prompt_profile=prompt_profile,
        chapter_count=chapter_count,
    )

    profile_config = dict(state.get("profile_config") or PROFILE_CONFIGS.get(
        prompt_profile, PROFILE_CONFIGS["balanced"]
    ))
    if spec.get("chapters_per_window_max"):
        profile_config["chapters_per_window"] = int(spec["chapters_per_window_max"])
    if spec.get("rerun_budget") is not None:
        profile_config["max_rerun_iterations"] = int(spec["rerun_budget"])
    return {
        **state,
        "tool_operating_spec": spec,
        "converge_target": target,
        "import_granularity_profile": granularity_profile,
        "import_plan": import_plan,
        "profile_config": profile_config,
        "use_supervisor": bool(state.get("use_supervisor") or spec.get("supervisor_enabled")),
        "orchestrator_phase": "planning",
        "converge_status": "planning",
    }


def _with_status(
    state: ImportSupervisorState,
    *,
    current_tool: str,
    orchestrator_phase: str,
    current_window: str = "",
    chapter_range: str = "",
    rerun_reason: str = "",
    converge_status: str | None = None,
) -> ImportSupervisorState:
    update: dict = {
        "current_tool": current_tool,
        "current_window": current_window,
        "chapter_range": chapter_range,
        "orchestrator_phase": orchestrator_phase,
        "rerun_reason": rerun_reason,
    }
    if converge_status:
        update["converge_status"] = converge_status
    if state.get("judge_artifact"):
        update["judge_score"] = state["judge_artifact"].get("score", 0.0)
    return {**state, **update}


def _window_chapter_range(state: ImportSupervisorState, window_id: str) -> str:
    window = next((w for w in state.get("prompt_windows", []) if w.get("id") == window_id), {})
    return str(window.get("chapter_range", ""))


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


def _evaluate_window_gate(metrics: dict, profile_config: dict, tool_operating_spec: ToolOperatingSpec | None = None) -> tuple[bool, list[str]]:
    """Return (gate_passed, list_of_failure_reasons) for a window's metrics."""
    spec = tool_operating_spec or {}
    chapters = max(metrics.get("chapter_count", 1), 1)
    char_density = metrics.get("char_count_extracted", 0) / chapters
    event_density = metrics.get("event_count_extracted", 0) / chapters
    failed = len(metrics.get("failed_prompts", []))
    char_threshold = float(spec.get("min_characters_per_chapter", _CHAR_DENSITY_THRESHOLD))
    event_threshold = float(spec.get("event_density_target", _EVENT_DENSITY_THRESHOLD))
    reasons: list[str] = []
    if char_density < char_threshold:
        reasons.append(f"char_density={char_density:.2f}<{char_threshold}")
    if event_density < event_threshold:
        reasons.append(f"event_density={event_density:.2f}<{event_threshold}")
    if failed >= _FAILED_PROMPTS_THRESHOLD:
        reasons.append(f"failed_prompts={failed}>={_FAILED_PROMPTS_THRESHOLD}")
    return not reasons, reasons


async def _process_window(
    state: ImportSupervisorState,
    tools: dict,
    window_id: str,
    profile_config: dict,
    tool_operating_spec: ToolOperatingSpec | None = None,
) -> ImportSupervisorState:
    """Extract + optionally cross-validate + gate-check one window. Mutates nothing — returns new state."""
    validation = profile_config.get("validation_strictness", "per_window")
    spec = tool_operating_spec or state.get("tool_operating_spec", {})
    max_reruns = int(spec.get("rerun_budget", profile_config.get("max_rerun_iterations", 2)))
    state = _with_status(
        state,
        current_tool="extract_window",
        current_window=window_id,
        chapter_range=_window_chapter_range(state, window_id),
        orchestrator_phase="extracting",
        converge_status="extracting",
    )

    # Extract
    update = await tools["extract_window"](state, window_id)
    state = _merge_window_result(state, update)
    if update.get("budget_exhausted"):
        state = {**state, "budget_exhausted": True}
    if update.get("errors"):
        state = {**state, "errors": list(state.get("errors", [])) + [
            e for e in update["errors"] if e not in state.get("errors", [])
        ]}
    state = _record_decision(
        state, "extract_window", "extract_window", f"primary extraction for {window_id}",
        {}, {}, "proceed",
    )

    # Bail out immediately if budget exhausted — no cross-validate, no reruns
    if state.get("budget_exhausted"):
        return state

    # Cross-validate
    if validation != "off":
        cv_update = await tools["cross_validate_window"](state, window_id)
        state = _merge_window_result(state, cv_update)
        state = _record_decision(
            state, "cross_validate_window", "cross_validate_window",
            f"cross-validate {window_id}", {}, {}, "proceed",
        )

    # Gate evaluation + reruns
    metrics_dict = dict(state.get("window_metrics", {}))
    metrics = metrics_dict.get(window_id, {})
    rerun_count = 0

    while rerun_count < max_reruns:
        gate_passed, reasons = _evaluate_window_gate(metrics, profile_config, spec)
        if gate_passed:
            break

        chapters = max(metrics.get("chapter_count", 1), 1)
        char_density = metrics.get("char_count_extracted", 0) / chapters
        missing_names = metrics.get("missing_majors", [])

        window = next((w for w in state.get("prompt_windows", []) if w.get("id") == window_id), {})
        can_split = len(window.get("chunk_ids", [])) > 1 and char_density < float(spec.get("min_characters_per_chapter", _CHAR_DENSITY_THRESHOLD))
        strategy = "split" if can_split else "augment"

        prev_window_ids = {w["id"] for w in state.get("prompt_windows", [])}
        state = _with_status(
            state,
            current_tool="rerun_window",
            current_window=window_id,
            chapter_range=_window_chapter_range(state, window_id),
            orchestrator_phase="rerunning",
            rerun_reason="; ".join(reasons),
            converge_status="rerunning",
        )
        rerun_update = await tools["rerun_window"](state, window_id, strategy, missing_names or None)
        state = _merge_window_result(state, rerun_update)
        # carry through any new prompt_windows added by rerun
        if "prompt_windows" in rerun_update:
            state = {**state, "prompt_windows": rerun_update["prompt_windows"]}
        state = _record_decision(
            state, "rerun_window", "rerun_window",
            f"gate failures: {reasons}; strategy={strategy}",
            {"reasons": reasons}, {}, "rerun", [window_id],
        )

        if strategy == "split":
            # Child windows were extracted inside rerun_window; qa_review evaluates them.
            # Do not re-check parent metrics — they won't change after a split.
            break

        # For augment: read the new window's metrics (new window ID in rerun result)
        new_window_ids = {w["id"] for w in state.get("prompt_windows", [])} - prev_window_ids
        if new_window_ids:
            new_id = next(iter(new_window_ids))
            metrics_dict = dict(state.get("window_metrics", {}))
            metrics = metrics_dict.get(new_id, metrics_dict.get(window_id, {}))
        else:
            metrics_dict = dict(state.get("window_metrics", {}))
            metrics = metrics_dict.get(window_id, {})
        rerun_count += 1

    return state


def _strategy_for_thematic_request(state: ImportSupervisorState, request: ThematicRerunRequest, window_id: str) -> str:
    window = next((w for w in state.get("prompt_windows", []) if w.get("id") == window_id), {})
    if request.get("theme") in {"character_undercoverage", "timeline_undercoverage"} and len(window.get("chunk_ids", [])) > 1:
        return "split"
    return "augment"


async def _call_rerun_window(
    tools: dict,
    state: ImportSupervisorState,
    window_id: str,
    strategy: str,
    missing_names: list[str] | None,
    parameter_overrides: dict,
) -> dict:
    """Call rerun_window while remaining compatible with older test doubles."""
    try:
        return await tools["rerun_window"](
            state,
            window_id,
            strategy,
            missing_names,
            parameter_overrides=parameter_overrides,
        )
    except TypeError as exc:
        if "parameter_overrides" not in str(exc) and "unexpected keyword" not in str(exc):
            raise
        return await tools["rerun_window"](state, window_id, strategy, missing_names)


async def _run_judge_import(state: ImportSupervisorState, tools: dict) -> ImportSupervisorState:
    state = _with_status(
        state,
        current_tool="judge_import",
        orchestrator_phase="judging",
        converge_status="judging",
    )
    judge_update = await tools["judge_import"](state)
    state = {**state, **judge_update, "current_stage": "judge_import"}
    state = _record_decision(
        state,
        "judge_import",
        "judge_import",
        "deterministic convergence judgment",
        {},
        {
            "score": state.get("judge_artifact", {}).get("score", 0.0),
            "passed": state.get("judge_artifact", {}).get("passed", False),
            "failed_gates": state.get("judge_artifact", {}).get("failed_gates", []),
        },
        "proceed" if state.get("judge_artifact", {}).get("passed") else "rerun",
        [],
    )
    return _with_status(
        state,
        current_tool="judge_import",
        orchestrator_phase="judging",
        converge_status=state.get("converge_status", "failed"),
    )


async def _apply_thematic_reruns(
    state: ImportSupervisorState,
    tools: dict,
    profile_config: dict,
    tool_operating_spec: ToolOperatingSpec,
) -> ImportSupervisorState:
    # Hard stop: never run thematic reruns when budget is exhausted
    if state.get("budget_exhausted"):
        log = list(state.get("supervisor_log", []))
        log.append("_apply_thematic_reruns: skipped — budget_exhausted (API 402)")
        return _with_status(
            {**state, "supervisor_log": log},
            current_tool="judge_import",
            orchestrator_phase="judging",
            converge_status=state.get("converge_status", "failed"),
        )

    budget = max(int(tool_operating_spec.get("rerun_budget", 0)), 0)
    wave_cap = max(int(tool_operating_spec.get("thematic_rerun_wave_cap", 1)), 0)
    applied = 0
    waves_applied = 0
    seen: set[tuple[str, str]] = set()

    while applied < budget and waves_applied < wave_cap:
        artifact = state.get("judge_artifact", {})
        if artifact.get("passed"):
            break
        requests = list(artifact.get("thematic_rerun_requests", []))
        if not requests:
            break

        progressed = False
        for request in requests:
            target_windows = [w for w in request.get("target_windows", []) if w]
            if not target_windows:
                target_windows = [w.get("id", "") for w in state.get("prompt_windows", []) if w.get("id")][:1]
            for window_id in target_windows:
                key = (str(request.get("theme", "")), window_id)
                if key in seen:
                    continue
                if applied >= budget:
                    break
                seen.add(key)
                strategy = _strategy_for_thematic_request(state, request, window_id)
                reason = str(request.get("reason", request.get("theme", "thematic_rerun")))
                state = _with_status(
                    state,
                    current_tool="rerun_window",
                    current_window=window_id,
                    chapter_range=_window_chapter_range(state, window_id),
                    orchestrator_phase="rerunning",
                    rerun_reason=reason,
                    converge_status="rerunning",
                )
                missing_names: list[str] | None = None
                if request.get("theme") == "character_undercoverage":
                    registry = state.get("entity_registry", {})
                    existing_chars = list(registry.get("characters", {}).keys())
                    current_count = len(existing_chars)
                    target_count = int(
                        tool_operating_spec.get("min_characters_per_chapter", 1.5)
                        * len(state.get("chunks", []))
                    )
                    already_found = ", ".join(existing_chars[:40]) if existing_chars else "none"
                    missing_names = [
                        f"[CHARACTER_RECOVERY_PASS: found {current_count} characters, "
                        f"target ≥{target_count}. Already registered (do NOT duplicate): "
                        f"{already_found}. "
                        "Search the entire text for ADDITIONAL named characters missed in prior passes — "
                        "especially: servants, guards, merchants, elders, family members, "
                        "characters with only 1–2 appearances, and role-only references "
                        "(e.g. 三叔, 村长, 掌柜). Include every distinct named person.]"
                    ]
                rerun_update = await _call_rerun_window(
                    tools,
                    state,
                    window_id,
                    strategy,
                    missing_names,
                    dict(request.get("parameter_overrides", {})),
                )
                state = _merge_window_result(state, rerun_update)
                if "prompt_windows" in rerun_update:
                    state = {**state, "prompt_windows": rerun_update["prompt_windows"]}
                state = _record_decision(
                    state,
                    "thematic_rerun",
                    "rerun_window",
                    f"{request.get('theme')}: {reason}; strategy={strategy}",
                    {"judge_score": artifact.get("score")},
                    {},
                    "rerun",
                    [window_id],
                )
                applied += 1
                progressed = True
            if applied >= budget:
                break

        if not progressed:
            break

        waves_applied += 1
        reduce_update = await tools["reduce_entities"](state)
        state = {**state, **reduce_update, "current_stage": "reduce_entities"}
        repair_update = await tools["minor_repair"](state)
        state = {**state, **repair_update, "current_stage": "minor_repair"}
        arch_update = await tools["architect_timeline"](state)
        state = {**state, **arch_update, "current_stage": "architect_timeline"}
        qa_update = await tools["qa_review"](state)
        state = {**state, **qa_update, "current_stage": "qa_review"}
        state = await _run_judge_import(state, tools)

    # If wave cap was hit and judge has not passed, record rerun_cap_reached
    cap_hit = waves_applied >= wave_cap and wave_cap > 0 and not state.get("judge_artifact", {}).get("passed")
    if cap_hit:
        artifact = dict(state.get("judge_artifact", {}))
        artifact["rerun_cap_reached"] = True
        failed = artifact.get("failed_gates", [])
        soft_only = bool(failed) and all(g == "character_undercoverage" for g in failed)
        if soft_only and artifact.get("result_status") not in ("passed", "acceptable_with_warnings"):
            artifact["result_status"] = "acceptable_with_warnings"
        log = list(state.get("supervisor_log", []))
        log.append(f"_apply_thematic_reruns: wave_cap={wave_cap} reached after {waves_applied} waves; rerun_cap_reached=True")
        state = {**state, "judge_artifact": artifact, "supervisor_log": log}

    if state.get("judge_artifact", {}).get("passed"):
        return _with_status(state, current_tool="judge_import", orchestrator_phase="judging", converge_status="passed")
    return _with_status(state, current_tool="judge_import", orchestrator_phase="judging", converge_status="failed")


async def run_supervisor_policy(
    state: ImportSupervisorState,
    tools: dict,
) -> ImportSupervisorState:
    """Execute the full supervisor policy loop. Returns final state."""
    state = _ensure_orchestrator_plan(state)
    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(
        state.get("prompt_profile", "balanced"), PROFILE_CONFIGS["balanced"]
    )
    tool_operating_spec = state.get("tool_operating_spec", {})

    # ── 1. Segment manifest ──────────────────────────────────────────────────
    state = _with_status(state, current_tool="segment_manifest", orchestrator_phase="planning", converge_status="planning")
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
        if state.get("budget_exhausted"):
            break
        batch = windows[batch_start: batch_start + batch_size]
        tasks = [_process_window(state, tools, w["id"], profile_config, tool_operating_spec) for w in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                errs = list(state.get("errors", [])) + [str(result)]
                state = {**state, "errors": errs}
            else:
                state = _merge_window_result(state, result)
                if result.get("budget_exhausted"):
                    state = {**state, "budget_exhausted": True}
                # Carry through any new prompt_windows added by reruns inside _process_window
                if result.get("prompt_windows"):
                    merged_windows = {w["id"]: w for w in state.get("prompt_windows", [])}
                    for w in result["prompt_windows"]:
                        merged_windows.setdefault(w["id"], w)
                    state = {**state, "prompt_windows": list(merged_windows.values())}
        if state.get("budget_exhausted"):
            log = list(state.get("supervisor_log", []))
            log.append("run_supervisor_policy: stopping extraction — budget_exhausted (API 402)")
            state = {**state, "supervisor_log": log}
            break

    state = {**state, "current_stage": "extract_windows"}

    # ── 3. Reduce entities ───────────────────────────────────────────────────
    state = _with_status(state, current_tool="reduce_entities", orchestrator_phase="reducing")
    reduce_update = await tools["reduce_entities"](state)
    state = {**state, **reduce_update, "current_stage": "reduce_entities"}
    state = _record_decision(
        state, "reduce_entities", "reduce_entities", "deduplicate entity registry",
        {}, {}, "proceed",
    )

    # ── 3b. Reduce world entities ────────────────────────────────────────────
    if "reduce_world_entities" in tools:
        state = _with_status(state, current_tool="reduce_world_entities", orchestrator_phase="reducing")
        rwe_update = tools["reduce_world_entities"](state)
        state = {**state, **rwe_update, "current_stage": "reduce_world_entities"}
        state = _record_decision(
            state, "reduce_world_entities", "reduce_world_entities",
            "deduplicate world entity registry",
            {}, {"world_count": len(state.get("entity_registry", {}).get("world", {}))}, "proceed",
        )

    # ── 4. Minor repair ──────────────────────────────────────────────────────
    state = _with_status(state, current_tool="minor_repair", orchestrator_phase="repairing")
    repair_update = await tools["minor_repair"](state)
    state = {**state, **repair_update, "current_stage": "minor_repair"}
    state = _record_decision(
        state, "minor_repair", "minor_repair", "deterministic repair pass",
        {}, {}, "repair",
    )

    # ── 5. Architect timeline ────────────────────────────────────────────────
    state = _with_status(state, current_tool="architect_timeline", orchestrator_phase="architecting")
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

        state = _with_status(state, current_tool="qa_review", orchestrator_phase="reviewing")
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
            state = await _process_window(state, tools, wid, profile_config, tool_operating_spec)

        # Redo reduce + repair after reruns
        reduce_update = await tools["reduce_entities"](state)
        state = {**state, **reduce_update}
        if "reduce_world_entities" in tools:
            rwe_update = tools["reduce_world_entities"](state)
            state = {**state, **rwe_update}
        repair_update = await tools["minor_repair"](state)
        state = {**state, **repair_update}

    if "judge_import" in tools:
        state = await _run_judge_import(state, tools)
        # Re-read tool_operating_spec from state — judge_import may have updated it
        _active_tos = state.get("tool_operating_spec") or tool_operating_spec
        state = await _apply_thematic_reruns(state, tools, profile_config, _active_tos)

    # ── 7. Proposal write ────────────────────────────────────────────────────
    state = _with_status(state, current_tool="proposal_write", orchestrator_phase="writing", converge_status="writing")
    proposal_update = await tools["proposal_write"](state)
    state = {**state, **proposal_update, "current_stage": "proposal_write"}
    state = _record_decision(
        state, "proposal_write", "proposal_write", "write final import proposal",
        {}, {}, "proceed",
    )

    return _with_status(
        state,
        current_tool="proposal_write",
        orchestrator_phase="done",
        converge_status="passed" if state.get("judge_artifact", {}).get("passed", True) else "failed",
    )


async def run_supervisor_streaming(
    project_path: str,
    config: dict,
) -> AsyncGenerator[dict, None]:
    """Async generator — same interface as run_streaming(). Yields progress dicts."""
    import_mode = config.get("import_mode", "import_all")
    profile = config.get("prompt_profile") or config.get("context", {}).get("prompt_profile", "balanced")
    profile_config = dict(PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS["balanced"]))
    if isinstance(config.get("profile_config"), dict):
        profile_config.update(config["profile_config"])
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
        "thematic_rerun_requests": [],
        "current_tool": "init",
        "current_window": "",
        "chapter_range": "",
        "orchestrator_phase": "planning",
        "judge_score": 0.0,
        "rerun_reason": "",
        "converge_status": "not_started",
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
            "current_tool": state.get("current_tool", node),
            "current_window": state.get("current_window", ""),
            "chapter_range": state.get("chapter_range", ""),
            "orchestrator_phase": state.get("orchestrator_phase", ""),
            "judge_score": state.get("judge_score", 0.0),
            "rerun_reason": state.get("rerun_reason", ""),
            "converge_status": state.get("converge_status", ""),
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
        state = _ensure_orchestrator_plan(state)
        profile_config_local = state.get("profile_config") or profile_config
        tool_operating_spec_local = state.get("tool_operating_spec", {})

        # segment_manifest
        state = _with_status(state, current_tool="segment_manifest", orchestrator_phase="planning", converge_status="planning")
        seg_update = await tools["segment_manifest"](state)
        state = {**state, **seg_update, "current_stage": "segment_manifest"}
        _emit(_PROGRESS_SEGMENT_MANIFEST, "segment_manifest")

        # Extract windows (batches of 3, progress linearly from 0.10 → 0.65)
        windows_local = list(state.get("prompt_windows", []))
        total_w = max(len(windows_local), 1)
        batch_size = 3
        window_idx = 0
        for batch_start in range(0, len(windows_local), batch_size):
            if state.get("budget_exhausted"):
                break
            batch = windows_local[batch_start: batch_start + batch_size]
            tasks = [_process_window(state, tools, w["id"], profile_config_local, tool_operating_spec_local) for w in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    errs = list(state.get("errors", [])) + [str(result)]
                    state = {**state, "errors": errs}
                else:
                    state = _merge_window_result(state, result)
                    if result.get("budget_exhausted"):
                        state = {**state, "budget_exhausted": True}
                    if result.get("prompt_windows"):
                        merged_windows = {w["id"]: w for w in state.get("prompt_windows", [])}
                        for w in result["prompt_windows"]:
                            merged_windows.setdefault(w["id"], w)
                        state = {**state, "prompt_windows": list(merged_windows.values())}
            window_idx += len(batch)
            if state.get("budget_exhausted"):
                break
            progress = _PROGRESS_EXTRACT_START + (_PROGRESS_EXTRACT_END - _PROGRESS_EXTRACT_START) * (window_idx / total_w)
            _chunk_progress[project_path] = {"completed": window_idx, "total": total_w}
            yield progress, "extract_windows", state.get("errors", [])

        state = {**state, "current_stage": "extract_windows"}

        # Reduce + repair
        state = _with_status(state, current_tool="reduce_entities", orchestrator_phase="reducing")
        reduce_update = await tools["reduce_entities"](state)
        state = {**state, **reduce_update, "current_stage": "reduce_entities"}
        state = _with_status(state, current_tool="minor_repair", orchestrator_phase="repairing")
        repair_update = await tools["minor_repair"](state)
        state = {**state, **repair_update, "current_stage": "minor_repair"}
        yield _PROGRESS_REDUCE_REPAIR, "reduce_repair", state.get("errors", [])

        # Architect
        state = _with_status(state, current_tool="architect_timeline", orchestrator_phase="architecting")
        arch_update = await tools["architect_timeline"](state)
        state = {**state, **arch_update, "current_stage": "architect_timeline"}
        yield _PROGRESS_ARCHITECT, "architect_timeline", state.get("errors", [])

        # QA + optional reruns
        max_sup_iters = state.get("max_supervisor_iterations", 3)
        for sup_iter in range(max_sup_iters):
            state = {**state, "supervisor_iteration": sup_iter}
            state = _with_status(state, current_tool="qa_review", orchestrator_phase="reviewing")
            qa_update = await tools["qa_review"](state)
            state = {**state, **qa_update, "current_stage": "qa_review"}
            gate_failures = list(state.get("gate_failures", []))
            if not gate_failures:
                break
            failing_ids = list({f["window_id"] for f in gate_failures if "window_id" in f})
            for wid in failing_ids:
                state = await _process_window(state, tools, wid, profile_config_local, tool_operating_spec_local)
            reduce_u = await tools["reduce_entities"](state)
            state = {**state, **reduce_u}
            repair_u = await tools["minor_repair"](state)
            state = {**state, **repair_u}
        yield _PROGRESS_QA_REVIEW, "qa_review", state.get("errors", [])

        if "judge_import" in tools:
            state = await _run_judge_import(state, tools)
            _active_tos_local = state.get("tool_operating_spec") or tool_operating_spec_local
            state = await _apply_thematic_reruns(state, tools, profile_config_local, _active_tos_local)
        yield _PROGRESS_QA_REVIEW, "judge_import", state.get("errors", [])

        # Proposal write
        state = _with_status(state, current_tool="proposal_write", orchestrator_phase="writing", converge_status="writing")
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
                session["current_tool"] = state.get("current_tool", "")
                session["current_window"] = state.get("current_window", "")
                session["chapter_range"] = state.get("chapter_range", "")
                session["orchestrator_phase"] = state.get("orchestrator_phase", "")
                session["judge_score"] = state.get("judge_score", 0.0)
                session["rerun_reason"] = state.get("rerun_reason", "")
                session["converge_status"] = state.get("converge_status", "")
                session["judge_artifact"] = state.get("judge_artifact", {})
            except Exception:
                pass
        yield _emit(progress, node, errors)

    state = _with_status(
        state,
        current_tool="proposal_write",
        orchestrator_phase="done",
        converge_status="passed" if state.get("judge_artifact", {}).get("passed", True) else "failed",
    )
    yield _emit(_PROGRESS_DONE, "done")
