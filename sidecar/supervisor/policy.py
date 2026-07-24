"""W1 Supervisor policy loop.

Entry points:
  run_supervisor_streaming(project_path, config)  — async generator, same interface as run_streaming()
  run_supervisor_policy(state, tools)              — pure policy loop, returns final state
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Mapping

from sidecar.models.state import (
    PROFILE_CONFIGS,
    ImportSupervisorState,
    ThematicRerunRequest,
    ToolOperatingSpec,
    analyze_source_profile,
    plan_converge_target,
    plan_import_pipeline,
    plan_orchestrator_targets,
    plan_tool_operating_spec,
    select_granularity_profile,
    validate_import_plan,
    reconstruct_source_span,
    validate_source_span,
)
from sidecar.supervisor.planner import (
    planner_proposal_to_import_plan,
    resolve_planner_next_action,
    validate_planner_proposal,
)
from sidecar.supervisor.planner_llm import (
    PlannerLiveCallError,
    build_live_planner_failure_record,
    generate_live_planner_proposal,
    generate_planner_proposal_stub,
)
from sidecar.supervisor.prompt_policy import (
    apply_prompt_policy_patch_to_plan,
    choose_prompt_policy_patch,
    prompt_policy_decision,
)
from sidecar.supervisor.organizer import OrganizerInput, organize_project_content
from sidecar.supervisor.pipeline_tools import repair_import_artifacts
from sidecar.supervisor.timeline_density import enforce_timeline_density
from sidecar.supervisor.tool_registry import build_tool_registry
from sidecar.workflows.w1_import import (
    _build_supervisor_evidence_cards,
    _chunk_progress,
    _merge_cross_validation_artifacts,
    _write_import_artifact,
    configure_w1_budget,
    persist_w1_usage_ledger,
    node_split_chunks,
    node_validate_file,
)
from sidecar.workflows.w1_run_events import append_event, cancel_requested


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

_SNAPSHOT_RESUME_ORDER = {
    "segment_manifest": 0,
    "extract_window": 1,
    "reduce_repair": 2,
    "architect_timeline": 3,
    "qa_review": 4,
    "judge_import": 5,
    "proposal_write": 6,
}
_SNAPSHOT_BOUNDARY_NEXT_NODE = {
    "reduce_repair": "architect_timeline",
    "architect_timeline": "qa_review",
    "qa_review": "judge_import",
    "judge_import": "proposal_write",
    "proposal_write": None,
}
_SNAPSHOT_PRIVATE_KEY = "_w1_supervisor_snapshot"
_SNAPSHOT_UNSAFE_KEY = re.compile(
    r"(?:api[_-]?key|secret|password|authorization|access[_-]?token|refresh[_-]?token|private[_-]?key|"
    r"prompt|source_(?:body|text|content)|raw_(?:content|text)|chain_?of_?thought|hidden_?reasoning|"
    r"reasoning_trace|callback|client|runtime|(?:^|_)(?:content|text)(?:$|_))",
    re.I,
)


def _snapshot_value(value: Any) -> Any:
    """Return JSON-only derived state without source/prompt material or secrets."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        # File paths and source bodies are never recovery state.  Relative
        # artifact IDs remain useful; absolute paths are rejected by v1 too.
        return "" if value.startswith("/") or re.match(r"^[A-Za-z]:[\\\\/]", value) else value
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _snapshot_value(item)
            for key, item in value.items()
            if isinstance(key, str) and not _SNAPSHOT_UNSAFE_KEY.search(key)
        }
    # Unknown runtime objects make a snapshot preview-only rather than trying
    # to serialize them.  The codec remains the final fail-closed validator.
    raise TypeError("supervisor_snapshot_state_is_not_json")


def _snapshot_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Project the Supervisor's derived artifacts onto the v1 allowlist."""
    chunk_fields = {
        "id", "chunk_id", "segment_id", "chapter_id", "chapter_number", "chapterNumber",
        "source_span", "raw_source_hash", "substring_hash", "absolute_start", "absolute_end",
        "source_tokens", "source_chars", "token_count", "char_count", "title",
    }
    compact_chunks = [
        {key: value for key, value in chunk.items() if key in chunk_fields}
        for chunk in state.get("chunks", [])
        if isinstance(chunk, Mapping)
    ]
    if state.get("chunks") and (
        len(compact_chunks) != len(state.get("chunks", []))
        or any(not isinstance(chunk.get("source_span"), Mapping) for chunk in compact_chunks)
    ):
        raise ValueError("supervisor_snapshot_requires_source_spans")
    projected = {
        "chunks": compact_chunks,
        # Prompt windows intentionally do not cross a restart boundary: they
        # contain the source/prompt body. QA reruns are completed before a
        # checkpoint; a future per-window contract can store span-only input.
        "chunk_extractions": state.get("chunk_extractions", []),
        "entity_registry": state.get("entity_registry", {}),
        "relationships": state.get("relationships", []),
        "world": {
            "world_settings": state.get("world_settings", {}),
            "world_containers": state.get("world_containers", []),
        },
        "timeline": {
            "timeline_architecture": state.get("timeline_architecture", {}),
            "timeline_branches": state.get("timeline_branches", []),
        },
        "organizer": {"organizer": state.get("organizer", {})},
        "reducer": {"reducer_artifact": state.get("reducer_artifact", {})},
        "cross_validation": state.get("cross_validation", {}),
        "reviewer": {"import_review_report": state.get("import_review_report", {})},
        "judge": {
            "judge_artifact": state.get("judge_artifact", {}),
            "gate_failures": state.get("gate_failures", []),
            "supervisor_iteration": state.get("supervisor_iteration", 0),
        },
        "proposal": {"proposals": state.get("proposals", []), "evidence_cards": state.get("evidence_cards", [])},
        "operations": state.get("operations", {}),
        "import_manifest": state.get("import_run_manifest", {}),
        "project_structure_digest": state.get("project_structure_digest", {}),
    }
    return {key: _snapshot_value(value) for key, value in projected.items()}


def _rehydrate_snapshot_chunks(state: ImportSupervisorState, source_file_path: str) -> ImportSupervisorState:
    """Rebuild transient chunk bodies solely from verified SourceSpan records."""
    source_path = Path(source_file_path)
    raw_source = source_path.read_text(encoding="utf-8")
    restored_chunks: list[dict[str, Any]] = []
    for compact in state.get("chunks", []):
        if not isinstance(compact, Mapping):
            raise ValueError("snapshot_chunk_is_invalid")
        span = compact.get("source_span")
        if not isinstance(span, Mapping):
            raise ValueError("snapshot_chunk_source_span_missing")
        valid, _errors = validate_source_span(dict(span), raw_source)
        if not valid:
            raise ValueError("snapshot_chunk_source_span_mismatch")
        body = reconstruct_source_span(dict(span), raw_source)
        restored_chunks.append({
            **dict(compact),
            "content": body,
            "raw_content": body,
            "manuscript_content": body,
        })
    return {**state, "chunks": restored_chunks, "source_text": raw_source}  # type: ignore[return-value]


def _restore_snapshot_state(state: ImportSupervisorState, snapshot_state: Mapping[str, Any]) -> ImportSupervisorState:
    """Restore only v1-derived state; source text and transient clients stay live."""
    restored = dict(state)
    for key in ("chunks", "chunk_extractions", "entity_registry", "relationships", "cross_validation", "operations", "project_structure_digest"):
        if key in snapshot_state:
            restored[key] = snapshot_state[key]
    world = snapshot_state.get("world")
    if isinstance(world, Mapping):
        restored["world_settings"] = world.get("world_settings", {})
        restored["world_containers"] = world.get("world_containers", [])
    timeline = snapshot_state.get("timeline")
    if isinstance(timeline, Mapping):
        restored["timeline_architecture"] = timeline.get("timeline_architecture", {})
        restored["timeline_branches"] = timeline.get("timeline_branches", [])
    reducer = snapshot_state.get("reducer")
    if isinstance(reducer, Mapping):
        restored["reducer_artifact"] = reducer.get("reducer_artifact", {})
    reviewer = snapshot_state.get("reviewer")
    if isinstance(reviewer, Mapping):
        restored["import_review_report"] = reviewer.get("import_review_report", {})
    judge = snapshot_state.get("judge")
    if isinstance(judge, Mapping):
        restored["judge_artifact"] = judge.get("judge_artifact", {})
        restored["gate_failures"] = judge.get("gate_failures", [])
        restored["supervisor_iteration"] = judge.get("supervisor_iteration", 0)
    proposal = snapshot_state.get("proposal")
    if isinstance(proposal, Mapping):
        restored["proposals"] = proposal.get("proposals", [])
        restored["evidence_cards"] = proposal.get("evidence_cards", [])
    if "import_manifest" in snapshot_state:
        restored["import_run_manifest"] = snapshot_state["import_manifest"]
    return restored  # type: ignore[return-value]


def _resume_budget_is_compatible(config: Mapping[str, Any], snapshot: Mapping[str, Any]) -> bool:
    budget = snapshot.get("budget_snapshot")
    if not isinstance(budget, Mapping):
        return True
    spent = float(budget.get("spent_usd", 0.0) or 0.0)
    policy = config.get("budget_policy") or config.get("budget_config") or {}
    if not isinstance(policy, Mapping):
        return False
    limit = policy.get("budget_limit_usd", policy.get("max_cost_usd"))
    return limit is None or float(limit) >= spent


def _snapshot_budget(config: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, float]:
    policy = config.get("budget_policy") or config.get("budget_config") or {}
    policy = policy if isinstance(policy, Mapping) else {}
    ledger = state.get("usage_ledger") if isinstance(state.get("usage_ledger"), Mapping) else {}
    limit = policy.get("budget_limit_usd", policy.get("max_cost_usd", 0.0))
    spent = ledger.get("spent_usd", ledger.get("cost_usd", 0.0)) if isinstance(ledger, Mapping) else 0.0
    return {
        "budget_limit_usd": max(0.0, float(limit or 0.0)),
        "spent_usd": max(0.0, float(spent or 0.0)),
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _session_id(state: ImportSupervisorState) -> str:
    return str(state.get("session_id") or state.get("context", {}).get("session_id") or "")


def _emit_activity(state: ImportSupervisorState, **event: object) -> None:
    session_id = _session_id(state)
    if session_id:
        append_event(session_id, dict(event))


def _cancel_requested(state: ImportSupervisorState) -> bool:
    session_id = _session_id(state)
    return bool(session_id and cancel_requested(session_id))


def _merge_registries(base: dict, update: dict) -> dict:
    """Union entity_registry sub-dicts. Base keys win — earlier windows are not clobbered."""
    def _merge_entity_maps(base_items: dict, update_items: dict) -> dict:
        merged = {**update_items, **base_items}
        for entity_id in set(base_items) & set(update_items):
            earlier = base_items[entity_id]
            later = update_items[entity_id]
            if not isinstance(earlier, dict) or not isinstance(later, dict):
                continue
            item = {**later, **earlier}
            for key in ("evidence_refs", "source_prompt_window_ids", "source_chunk_ids", "source_segment_ids"):
                item[key] = list(dict.fromkeys([
                    *earlier.get(key, []),
                    *later.get(key, []),
                ]))
            merged[entity_id] = item
        return merged

    return {
        "characters": _merge_entity_maps(base.get("characters", {}), update.get("characters", {})),
        "events": _merge_entity_maps(base.get("events", {}), update.get("events", {})),
        "world": _merge_entity_maps(base.get("world", {}), update.get("world", {})),
        "world_detailed": _merge_entity_maps(base.get("world_detailed", {}), update.get("world_detailed", {})),
    }


def _with_window_provenance(
    state: ImportSupervisorState,
    result: dict,
    window_id: str,
) -> dict:
    """Annotate candidates created by one prompt window without changing extraction tools."""
    window = next((item for item in state.get("prompt_windows", []) if item.get("id") == window_id), {})
    if not window:
        return result

    base_registry = state.get("entity_registry", {})
    result_registry = result.get("entity_registry")
    if not isinstance(result_registry, dict):
        return result

    annotated_registry = {key: dict(value) if isinstance(value, dict) else value for key, value in result_registry.items()}
    for domain in ("characters", "events", "world", "world_detailed"):
        base_items = base_registry.get(domain, {}) or {}
        updated_items = annotated_registry.get(domain, {}) or {}
        if not isinstance(updated_items, dict):
            continue
        for entity_id, value in list(updated_items.items()):
            if not isinstance(value, dict) or base_items.get(entity_id) == value:
                continue
            item = dict(value)
            item["source_prompt_window_ids"] = list(dict.fromkeys([
                *item.get("source_prompt_window_ids", []), window_id,
            ]))
            item["source_chunk_ids"] = list(dict.fromkeys([
                *item.get("source_chunk_ids", []), *window.get("chunk_ids", []),
            ]))
            updated_items[entity_id] = item

    existing_relationship_count = len(state.get("raw_relationships", []))
    raw_relationships = list(result.get("raw_relationships", []))
    for relationship in raw_relationships[existing_relationship_count:]:
        if not isinstance(relationship, dict):
            continue
        relationship["source_prompt_window_ids"] = list(dict.fromkeys([
            *relationship.get("source_prompt_window_ids", []), window_id,
        ]))
        relationship["source_chunk_ids"] = list(dict.fromkeys([
            *relationship.get("source_chunk_ids", []), *window.get("chunk_ids", []),
        ]))

    return {**result, "entity_registry": annotated_registry, "raw_relationships": raw_relationships}


def _persist_supervisor_evidence_cards(state: ImportSupervisorState) -> ImportSupervisorState:
    """Materialize non-canonical reviewer evidence before the supervisor QA pass."""
    evidence_update = _build_supervisor_evidence_cards(state)
    updated_state = {**state, **evidence_update}
    project_path = updated_state.get("project_path")
    import_run_id = updated_state.get("import_run_id")
    if project_path and import_run_id:
        _write_import_artifact(project_path, import_run_id, "evidence_cards.json", updated_state["evidence_cards"])
    return updated_state


async def _organize_staged_world_candidates(state: ImportSupervisorState) -> ImportSupervisorState:
    """Run Organizer and safe World-to-Character repairs for either supervisor path.

    This is proposal staging only.  It never writes canonical project data and
    therefore preserves the Workbench package acceptance gate.  In particular,
    a title/person expression must be relocated while its source still exists
    in the registry; rebuilding World from Organizer survivors first would
    discard the evidence needed to enrich the target character.
    """
    registry = dict(state.get("entity_registry", {}))
    world_detailed = registry.get("world_detailed", {}) or {}
    organizer_candidates: dict[str, dict] = {}
    if isinstance(world_detailed, dict):
        for storage_key, detail in world_detailed.items():
            if not isinstance(detail, dict):
                continue
            display_name = str(detail.get("name") or storage_key).strip() or str(storage_key)
            organizer_candidates.setdefault(display_name, detail)

    organizer_output = organize_project_content(OrganizerInput(
        characters=registry.get("characters", {}),
        events=list(registry.get("events", {}).values()),
        relationships=state.get("relationships", []),
        world_candidates=organizer_candidates,
        manuscript_notes=[],
        timeline_architecture=state.get("timeline_architecture", {}),
        project_digest=state.get("project_structure_digest", {}),
        source_language=state.get("source_language", "zh"),
    ))

    repair_actions = [
        {
            "action_type": "relocate",
            "target_entity_ids": [
                plan.get("source_candidate_id"),
                plan.get("target_entity_id"),
            ],
            "description": "Apply deterministic staged World-to-Character relocation.",
            "deterministic": bool(plan.get("deterministic")),
            "proposed_operations": [{
                "op": "relocate_world_item",
                "relocation_plan": plan,
            }],
        }
        for plan in organizer_output.get("relocation_plans", [])
        if isinstance(plan, dict)
    ]
    repair_result = await repair_import_artifacts({
        **state,
        "entity_registry": registry,
        "quarantine_candidates": list(organizer_output.get("quarantine_items", [])),
        "applied_relocation_plan_ids": list(state.get("applied_relocation_plan_ids", [])),
    }, repair_actions)

    # Organizer survivors are the only World proposals.  Character changes
    # from relocation come from the repaired registry before this rebuild.
    repaired_registry = repair_result["entity_registry"]
    organized_world_items = organizer_output["world_items"]
    organized_registry = {
        **repaired_registry,
        "world": {item["name"]: item["category"] for item in organized_world_items},
        "world_detailed": {item["name"]: item for item in organized_world_items},
    }
    project_path = state.get("project_path", "")
    import_run_id = state.get("import_run_id", "")
    if project_path and import_run_id:
        _write_import_artifact(project_path, import_run_id, "organizer_output.json", dict(organizer_output))

    return {
        **state,
        "entity_registry": organized_registry,
        "world_containers": organizer_output["world_containers"],
        "organizer_output": organizer_output,
        "candidate_ledger": organizer_output.get("candidate_ledger", []),
        "quarantine_candidates": repair_result.get("quarantine_candidates", []),
        "relocation_plans": organizer_output.get("relocation_plans", []),
        "applied_relocation_plan_ids": repair_result.get("applied_relocation_plan_ids", []),
        "minor_repair_log": repair_result.get("minor_repair_log", []),
        "supervisor_log": repair_result.get("supervisor_log", []),
    }


def _prepare_reviewer_staging_state(state: ImportSupervisorState) -> ImportSupervisorState:
    """Expose deterministic manuscript staging inputs to pre-proposal reviewers."""
    projection = state.get("staged_manuscript_projection") or state.get("stagedManuscriptProjection") or {}
    chapters = projection.get("chapters", []) if isinstance(projection, dict) else []
    nodes = projection.get("nodes", []) if isinstance(projection, dict) else []
    source = "staged_projection" if chapters else "manuscript_chapters"
    if not chapters:
        chapters = state.get("manuscript_chapters") or []
    if not chapters:
        chapters = [chunk for chunk in (state.get("chunks") or []) if isinstance(chunk, dict) and (chunk.get("content") or chunk.get("text"))]
        source = "chunk_projection_inputs"
    return {**state, "reviewer_staged_projection_metrics": {"phase": "preproposal", "source": source, "inputs_present": bool(chapters), "chapter_count": len(chapters), "node_count": len(nodes) if nodes else len(chapters) * 2}}


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
        "cross_validation": _merge_cross_validation_artifacts(
            state.get("cross_validation"), result.get("cross_validation"), str(state.get("import_run_id", ""))
        ),
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


def _run_live_planner(
    state: ImportSupervisorState,
    *,
    source_profile: dict | None = None,
    tool_operating_spec: dict | None = None,
    granularity_profile: dict | None = None,
) -> tuple[dict | None, dict, str | None]:
    """Invoke the opt-in planner once through its explicit approval boundary."""
    context = state.get("context", {})
    callback = context.get("planner_model_callback") if isinstance(context, dict) else None
    planner_state = {
        **state,
        **({"source_profile": source_profile} if source_profile is not None else {}),
        **({"tool_operating_spec": tool_operating_spec} if tool_operating_spec is not None else {}),
        **({"import_granularity_profile": granularity_profile} if granularity_profile is not None else {}),
    }
    try:
        proposal, decision_record = generate_live_planner_proposal(
            planner_state,
            model_callback=callback if callable(callback) else None,
        )
        return proposal, decision_record, None
    except PlannerLiveCallError as exc:
        return None, build_live_planner_failure_record(
            planner_state,
            exc,
            retry_authorization=exc.retry_authorization,
        ), exc.safe_message


def _ensure_orchestrator_plan(state: ImportSupervisorState) -> ImportSupervisorState:
    if state.get("tool_operating_spec") and state.get("converge_target"):
        context = state.get("context", {})
        proposal = state.get("planner_proposal") or context.get("planner_proposal")
        if proposal is None and context.get("llm_planner_mode") == "live":
            proposal, decision_record, error = _run_live_planner(state)
            if error is not None:
                return {
                    **state,
                    "planner_decision_record": decision_record,
                    "import_plan_validation": {"ok": False, "errors": [error]},
                    "orchestrator_phase": "planning_failed",
                    "converge_status": "hard_fail",
                    "errors": list(state.get("errors", [])) + [error],
                }
            state = {
                **state,
                "planner_proposal": proposal,
                "planner_decision_record": decision_record,
            }
        if proposal is not None and not state.get("planner_proposal_validation"):
            proposal_ok, proposal_errors = validate_planner_proposal(proposal)
            if not proposal_ok:
                return {
                    **state,
                    "planner_proposal": proposal,
                    "planner_proposal_validation": {"ok": False, "errors": proposal_errors},
                    "import_plan_validation": {"ok": False, "errors": proposal_errors},
                    "orchestrator_phase": "planning_failed",
                    "converge_status": "hard_fail",
                    "errors": list(state.get("errors", [])) + [
                        f"planner_proposal_validation: {err}" for err in proposal_errors
                    ],
                }
        # A live planner may resume from a previously blocked state that has a
        # spec/target but no valid ImportPlan. Rebuild only the deterministic
        # plan projection here; this does not execute any W1 tool or write
        # canonical/proposal data.
        prior_plan_validation = state.get("import_plan_validation") or {}
        if proposal is not None and (
            not state.get("import_plan") or not prior_plan_validation.get("ok")
        ):
            chapter_count = _chapter_count_from_state(state)
            source_language = str(state.get("source_language", "en") or "en")
            prompt_profile = str(state.get("prompt_profile", "balanced") or "balanced")
            try:
                import_plan = planner_proposal_to_import_plan(
                    proposal,
                    state["tool_operating_spec"],
                    source_language=source_language,
                    prompt_profile=prompt_profile,
                    chapter_count=chapter_count,
                )
                plan_ok, plan_errors = validate_import_plan(import_plan)
            except ValueError as exc:
                import_plan = {}  # type: ignore[assignment]
                plan_ok, plan_errors = False, [str(exc)]
            return {
                **state,
                "planner_proposal": proposal,
                "planner_proposal_validation": {"ok": plan_ok, "errors": plan_errors},
                "import_plan": import_plan,
                "import_plan_validation": {"ok": plan_ok, "errors": plan_errors},
                "orchestrator_phase": "planning" if plan_ok else "planning_failed",
                "converge_status": "planning" if plan_ok else "hard_fail",
                "errors": list(state.get("errors", [])) + [
                    f"import_plan_validation: {err}" for err in plan_errors
                ],
            }
        if state.get("import_plan") and not state.get("import_plan_validation"):
            is_valid, errors = validate_import_plan(state["import_plan"])
            return {
                **state,
                "import_plan_validation": {"ok": is_valid, "errors": errors},
                "errors": list(state.get("errors", [])) + [
                    f"import_plan_validation: {err}" for err in errors
                ],
                **(
                    {"orchestrator_phase": "planning_failed", "converge_status": "hard_fail"}
                    if not is_valid
                    else {}
                ),
            }
        return state
    context = state.get("context", {})
    chapter_count = _chapter_count_from_state(state)
    prompt_profile = state.get("prompt_profile", "balanced")
    source_language = state.get("source_language", "en")
    source_profile = analyze_source_profile(
        state.get("chunks", []),
        source_language=source_language,
        prompt_profile=prompt_profile,
    )

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
    policy_patch = choose_prompt_policy_patch(source_profile, state.get("quality_hints", {}))
    if policy_patch.get("event_density_strategy"):
        granularity_profile = {
            **granularity_profile,
            "event_density": policy_patch["event_density_strategy"],
        }
        if policy_patch["event_density_strategy"] == "sparse_turning_points":
            granularity_profile["min_events_per_chapter"] = 0.4 if chapter_count >= 8 else 0.75
            granularity_profile["acceptable_floor_fraction"] = 0.70
    target = plan_converge_target(spec, source_language, chapter_count, granularity_profile=granularity_profile)
    profile_config = dict(state.get("profile_config") or PROFILE_CONFIGS.get(
        prompt_profile, PROFILE_CONFIGS["balanced"]
    ))
    if spec.get("chapters_per_window_max"):
        profile_config["chapters_per_window"] = int(spec["chapters_per_window_max"])
    if spec.get("rerun_budget") is not None:
        profile_config["max_rerun_iterations"] = int(spec["rerun_budget"])

    proposal = state.get("planner_proposal") or context.get("planner_proposal")
    planner_mode = context.get("llm_planner_mode")
    effective_policy_patch = policy_patch
    planner_decision_record = state.get("planner_decision_record")
    if proposal is None and planner_mode == "stub":
        proposal = generate_planner_proposal_stub({
            **state,
            "source_profile": source_profile,
            "tool_operating_spec": spec,
            "import_granularity_profile": granularity_profile,
            "source_language": source_language,
            "prompt_profile": prompt_profile,
        })
    elif proposal is None and planner_mode == "live":
        proposal, planner_decision_record, error = _run_live_planner(
            state,
            source_profile=source_profile,
            tool_operating_spec=spec,
            granularity_profile=granularity_profile,
        )
        if error is not None:
            return {
                **state,
                "tool_operating_spec": spec,
                "converge_target": target,
                "import_granularity_profile": granularity_profile,
                "planner_decision_record": planner_decision_record,
                "import_plan_validation": {"ok": False, "errors": [error]},
                "source_profile": source_profile,
                "profile_config": profile_config,
                "use_supervisor": bool(state.get("use_supervisor") or spec.get("supervisor_enabled")),
                "orchestrator_phase": "planning_failed",
                "converge_status": "hard_fail",
                "errors": list(state.get("errors", [])) + [error],
            }
    planner_proposal_validation = None

    if proposal is not None:
        proposal_ok, proposal_errors = validate_planner_proposal(proposal)
        planner_proposal_validation = {"ok": proposal_ok, "errors": proposal_errors}
        if not proposal_ok:
            return {
                **state,
                "tool_operating_spec": spec,
                "converge_target": target,
                "import_granularity_profile": granularity_profile,
                "import_plan_validation": {"ok": False, "errors": proposal_errors},
                "planner_proposal": proposal,
                "planner_proposal_validation": planner_proposal_validation,
                "source_profile": source_profile,
                "profile_config": profile_config,
                "use_supervisor": bool(state.get("use_supervisor") or spec.get("supervisor_enabled")),
                "orchestrator_phase": "planning_failed",
                "converge_status": "hard_fail",
                "errors": list(state.get("errors", [])) + [
                    f"planner_proposal_validation: {err}" for err in proposal_errors
                ],
            }
        try:
            import_plan = planner_proposal_to_import_plan(
                proposal, spec,
                source_language=source_language,
                prompt_profile=prompt_profile,
                chapter_count=chapter_count,
            )
            proposal_patch = proposal.get("prompt_policy_patch") if isinstance(proposal, dict) else None
            if proposal_patch:
                import_plan = apply_prompt_policy_patch_to_plan(import_plan, proposal_patch)  # type: ignore[assignment]
                effective_policy_patch = proposal_patch
            else:
                effective_policy_patch = {}
            plan_is_valid, plan_errors = True, []
        except ValueError as exc:
            import_plan = {}  # type: ignore[assignment]
            plan_is_valid, plan_errors = False, [str(exc)]
            planner_proposal_validation = {"ok": False, "errors": plan_errors}
    else:
        import_plan = plan_import_pipeline(
            granularity_profile,
            spec,
            source_language=source_language,
            prompt_profile=prompt_profile,
            chapter_count=chapter_count,
        )
        import_plan = apply_prompt_policy_patch_to_plan(import_plan, policy_patch)  # type: ignore[assignment]
        plan_is_valid, plan_errors = validate_import_plan(import_plan)

    if plan_is_valid:
        granularity_profile = dict(import_plan.get("granularity_profile") or granularity_profile)
        applied_patch = (import_plan.get("prompt_policy") or {}).get("prompt_policy_patch") or effective_policy_patch
        if isinstance(applied_patch, dict) and applied_patch.get("event_density_strategy") == "sparse_turning_points":
            granularity_profile["event_density"] = "sparse_turning_points"
            granularity_profile["min_events_per_chapter"] = 0.4 if chapter_count >= 8 else 0.75
            granularity_profile["acceptable_floor_fraction"] = 0.70
        target = plan_converge_target(
            spec,
            source_language,
            chapter_count,
            granularity_profile=granularity_profile,
        )
        window_strategy = import_plan.get("window_strategy") or {}
        if window_strategy.get("chapters_per_window_max") is not None:
            profile_config["chapters_per_window"] = int(window_strategy["chapters_per_window_max"])

    import_plan_validation = {"ok": plan_is_valid, "errors": plan_errors}
    decision_patch = (
        ((import_plan.get("prompt_policy") or {}).get("prompt_policy_patch") or effective_policy_patch)
        if isinstance(import_plan, dict)
        else effective_policy_patch
    )

    result = {
        **state,
        "tool_operating_spec": spec,
        "converge_target": target,
        "import_granularity_profile": granularity_profile,
        "import_plan": import_plan,
        "import_plan_validation": import_plan_validation,
        "prompt_policy_decision": prompt_policy_decision(source_profile, decision_patch),
        "source_profile": source_profile,
        "profile_config": profile_config,
        "use_supervisor": bool(state.get("use_supervisor") or spec.get("supervisor_enabled")),
        "orchestrator_phase": "planning" if plan_is_valid else "planning_failed",
        "converge_status": "planning" if plan_is_valid else "hard_fail",
        "errors": list(state.get("errors", [])) + [
            f"import_plan_validation: {err}" for err in plan_errors
        ],
    }
    if proposal is not None:
        result["planner_proposal"] = proposal
        result["planner_proposal_validation"] = planner_proposal_validation
    if planner_decision_record is not None:
        result["planner_decision_record"] = planner_decision_record
    return result


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


def _effective_window_gate_policy(
    state: ImportSupervisorState,
    tool_operating_spec: ToolOperatingSpec | None = None,
) -> dict:
    """Derive per-window gate thresholds from the validated ImportPlan.

    ToolOperatingSpec is intentionally conservative. Once the planner has
    selected a granularity profile, window reruns should honor that profile so
    coarse webnovel imports do not burn budget chasing fine-grained targets.
    """
    spec = dict(tool_operating_spec or state.get("tool_operating_spec") or {})
    granularity = dict(state.get("import_granularity_profile") or {})
    if granularity.get("min_characters_per_chapter") is not None:
        spec["min_characters_per_chapter"] = float(granularity["min_characters_per_chapter"])
    if granularity.get("min_events_per_chapter") is not None:
        spec["event_density_target"] = float(granularity["min_events_per_chapter"])
    if granularity.get("rerun_on_character_gap") is not None:
        spec["rerun_on_character_gap"] = bool(granularity["rerun_on_character_gap"])
    return spec


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
    if bool(spec.get("rerun_on_character_gap", True)) and char_density < char_threshold:
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
    if _cancel_requested(state):
        _emit_activity(
            state,
            phase="cancelled",
            tool="extract_window",
            window_id=window_id,
            status="cancelled",
            level="warning",
            message=f"Skipping {window_id}; import was cancelled.",
        )
        return {**state, "status": "cancelled"}

    validation = profile_config.get("validation_strictness", "per_window")
    spec = _effective_window_gate_policy(state, tool_operating_spec)
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
    _emit_activity(
        state,
        phase="extracting",
        tool="extract_window",
        window_id=window_id,
        chapter_range=_window_chapter_range(state, window_id),
        status="start",
        message=f"Extracting window {window_id} ({_window_chapter_range(state, window_id) or 'unknown chapters'}).",
    )
    update = await tools["extract_window"](state, window_id)
    state = _merge_window_result(state, update)
    _emit_activity(
        state,
        phase="extracting",
        tool="extract_window",
        window_id=window_id,
        chapter_range=_window_chapter_range(state, window_id),
        status="fail" if update.get("budget_exhausted") or update.get("errors") else "success",
        level="error" if update.get("budget_exhausted") else "info",
        message=(
            f"Budget exhausted while extracting {window_id}."
            if update.get("budget_exhausted")
            else f"Finished extracting window {window_id}."
        ),
        error="; ".join(str(e) for e in update.get("errors", [])[:3]) if update.get("errors") else "",
    )
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
        if _cancel_requested(state):
            return {**state, "status": "cancelled"}
        _emit_activity(
            state,
            phase="validating",
            tool="cross_validate_window",
            window_id=window_id,
            chapter_range=_window_chapter_range(state, window_id),
            status="start",
            message=f"Cross-validating window {window_id}.",
        )
        cv_update = await tools["cross_validate_window"](state, window_id)
        state = _merge_window_result(state, cv_update)
        if cv_update.get("budget_exhausted"):
            return {**state, "budget_exhausted": True}
        _emit_activity(
            state,
            phase="validating",
            tool="cross_validate_window",
            window_id=window_id,
            chapter_range=_window_chapter_range(state, window_id),
            status="success",
            message=f"Finished cross-validation for {window_id}.",
        )
        state = _record_decision(
            state, "cross_validate_window", "cross_validate_window",
            f"cross-validate {window_id}", {}, {}, "proceed",
        )

    # Gate evaluation + reruns
    metrics_dict = dict(state.get("window_metrics", {}))
    metrics = metrics_dict.get(window_id, {})
    rerun_count = 0

    while rerun_count < max_reruns:
        if _cancel_requested(state):
            return {**state, "status": "cancelled"}
        gate_passed, reasons = _evaluate_window_gate(metrics, profile_config, spec)
        if gate_passed:
            break

        chapters = max(metrics.get("chapter_count", 1), 1)
        char_density = metrics.get("char_count_extracted", 0) / chapters
        missing_names = metrics.get("missing_majors", [])

        window = next((w for w in state.get("prompt_windows", []) if w.get("id") == window_id), {})
        can_split = (
            bool(spec.get("rerun_on_character_gap", True))
            and len(window.get("chunk_ids", [])) > 1
            and char_density < float(spec.get("min_characters_per_chapter", _CHAR_DENSITY_THRESHOLD))
        )
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
        _emit_activity(
            state,
            phase="rerunning",
            tool="rerun_window",
            window_id=window_id,
            chapter_range=_window_chapter_range(state, window_id),
            status="start",
            message=f"Rerunning {window_id}: {'; '.join(reasons)}.",
        )
        rerun_update = await tools["rerun_window"](state, window_id, strategy, missing_names or None)
        state = _merge_window_result(state, rerun_update)
        _emit_activity(
            state,
            phase="rerunning",
            tool="rerun_window",
            window_id=window_id,
            chapter_range=_window_chapter_range(state, window_id),
            status="success",
            message=f"Finished rerun for {window_id} using {strategy}.",
        )
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
                        state.get("converge_target", {}).get("expected_min_characters")
                        or (
                            _effective_window_gate_policy(state, tool_operating_spec).get("min_characters_per_chapter", 1.5)
                            * len(state.get("chunks", []))
                        )
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
        state = _prepare_reviewer_staging_state(enforce_timeline_density(state))
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


async def _apply_initial_planner_action(
    state: ImportSupervisorState,
    tools: dict,
    action: dict,
) -> ImportSupervisorState:
    """Execute only planner actions that are legal before the fixed W1 pipeline.

    The planner cannot jump ahead of segmentation/reduction/proposal gates. At
    this entry point, `segment_manifest` is the sole legal tool action; a rerun
    is legal only for an already materialized window and still uses the
    registered `rerun_window` tool.
    """
    if state.get("budget_exhausted"):
        return _with_status(state, current_tool="budget_stop", orchestrator_phase="stopped", converge_status="hard_fail")

    kind = action.get("kind")
    if kind == "tool" and action.get("tool") == "segment_manifest":
        update = await tools["segment_manifest"](state)
        return _record_decision(
            {**state, **update, "current_stage": "segment_manifest"},
            "segment_manifest", "segment_manifest", "planner-selected legal initial tool",
            {}, {"window_count": len(update.get("prompt_windows", []))}, "proceed",
        )

    if kind == "rerun":
        window_id = str(action.get("window_id") or "")
        valid_window_ids = {str(window.get("id") or "") for window in state.get("prompt_windows", [])}
        if window_id in valid_window_ids and "rerun_window" in tools:
            update = await tools["rerun_window"](state, window_id, strategy="augment")
            merged = _merge_window_result(state, update)
            return _record_decision(
                merged, "planner_action", "rerun_window", f"planner rerun for {window_id}",
                {}, {}, "rerun", [window_id],
            )
        reason = "unknown_window" if window_id not in valid_window_ids else "unregistered_rerun_tool"
    else:
        reason = "out_of_order_tool" if kind == "tool" else "unsupported_action"

    fallback = {"kind": "tool", "tool": "segment_manifest", "reason": f"{reason}_fallback"}
    log = list(state.get("supervisor_log", []))
    log.append(f"planner action rejected ({reason}); falling back to deterministic segment_manifest")
    return {**state, "planner_next_action": fallback, "supervisor_log": log}


async def run_supervisor_policy(
    state: ImportSupervisorState,
    tools: dict,
) -> ImportSupervisorState:
    """Execute the full supervisor policy loop. Returns final state."""
    state = _ensure_orchestrator_plan(state)
    planner_action = resolve_planner_next_action(
        state.get("planner_proposal") or state.get("context", {}).get("planner_proposal") or {},
        registered_tools=set(tools),
        default_tool="segment_manifest",
        iteration=int(state.get("supervisor_iteration", 0) or 0),
        max_iterations=int(state.get("max_supervisor_iterations", 0) or 0),
        budget_exhausted=bool(state.get("budget_exhausted")),
    )
    state = {**state, "planner_next_action": planner_action}
    if planner_action["kind"] == "stop":
        return _with_status(
            state,
            current_tool="planner_stop",
            orchestrator_phase="stopped",
            converge_status="hard_fail",
        )
    if state.get("budget_exhausted"):
        return _with_status(state, current_tool="budget_stop", orchestrator_phase="stopped", converge_status="hard_fail")
    state = await _apply_initial_planner_action(state, tools, planner_action)
    planner_consumed_segment_manifest = state.get("current_stage") == "segment_manifest"
    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(
        state.get("prompt_profile", "balanced"), PROFILE_CONFIGS["balanced"]
    )
    tool_operating_spec = state.get("tool_operating_spec", {})

    # ── 1. Segment manifest ──────────────────────────────────────────────────
    if not planner_consumed_segment_manifest:
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
        for window, result in zip(batch, results):
            if isinstance(result, Exception):
                errs = list(state.get("errors", [])) + [str(result)]
                state = {**state, "errors": errs}
            else:
                result = _with_window_provenance(state, result, str(window.get("id", "")))
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

    # ── 3c. Content organizer ────────────────────────────────────────────────
    state = await _organize_staged_world_candidates(state)

    # ── 4. Minor repair ──────────────────────────────────────────────────────
    state = _with_status(state, current_tool="minor_repair", orchestrator_phase="repairing")
    repair_update = await tools["minor_repair"](state)
    state = {**state, **repair_update, "current_stage": "minor_repair"}
    state = _record_decision(
        state, "minor_repair", "minor_repair", "deterministic repair pass",
        {}, {}, "repair",
    )
    state = _persist_supervisor_evidence_cards(state)

    # ── 5. Architect timeline ────────────────────────────────────────────────
    state = _with_status(state, current_tool="architect_timeline", orchestrator_phase="architecting")
    arch_update = await tools["architect_timeline"](state)
    state = {**state, **arch_update, "current_stage": "architect_timeline"}
    state = _prepare_reviewer_staging_state(enforce_timeline_density(state))
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

    _ja = state.get("judge_artifact") or {}
    return _with_status(
        state,
        current_tool="proposal_write",
        orchestrator_phase="done",
        converge_status="passed" if _ja.get("passed", True) else _ja.get("result_status", "failed"),
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
    session_id = str(config.get("session_id") or config.get("context", {}).get("session_id") or "")
    configure_w1_budget(config, str(session_id or ""))

    import_run_id = str(config.get("import_run_id") or f"sup_{uuid.uuid4().hex[:10]}")

    state: ImportSupervisorState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "import_mode": import_mode,
        "prompt_profile": profile,
        "profile_config": profile_config,
        "context": {**config.get("context", {}), "session_id": session_id, "budget_policy": config.get("budget_policy")},
        "session_id": session_id,
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

    resume_next_node = ""

    def _emit(progress: float, node: str, errors: list | None = None) -> dict:
        chunks_done = len(state.get("chunk_extractions", []))
        total = len(state.get("chunks", [])) or 1
        _chunk_progress[project_path] = {"completed": chunks_done, "total": total}
        update = {
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
        if node in _SNAPSHOT_BOUNDARY_NEXT_NODE:
            try:
                completed = [
                    boundary for boundary, order in _SNAPSHOT_RESUME_ORDER.items()
                    if order <= _SNAPSHOT_RESUME_ORDER[node]
                ]
                completed_windows = [
                    str(item.get("window_id") or item.get("id"))
                    for item in state.get("chunk_extractions", [])
                    if isinstance(item, Mapping) and isinstance(item.get("window_id") or item.get("id"), str)
                ]
                update[_SNAPSHOT_PRIVATE_KEY] = {
                    "state": _snapshot_state(state),
                    "completed_nodes": completed,
                    "completed_window_ids": list(dict.fromkeys(completed_windows)),
                    "repeatable_node_counts": {"qa_review": int(state.get("supervisor_iteration", 0) or 0) + 1},
                    "budget_snapshot": _snapshot_budget(config, state),
                    # The adapter cross-checks this against RuntimeStore before
                    # publishing a resumable checkpoint.
                    "unknown_tool_call_ids": [],
                }
            except (TypeError, ValueError):
                # A normal import may still finish, but its checkpoint remains
                # preview-only when derived state cannot satisfy v1.
                pass
        return update

    # Supervisor only runs for import_all
    if import_mode != "import_all":
        yield _emit(0.01, "supervisor_skip")
        from sidecar.workflows.w1_import import run_streaming as _legacy_stream
        async for update in _legacy_stream(project_path, config):
            yield update
        return

    resume_reference = config.get("w1_supervisor_resume_snapshot_ref")
    if isinstance(resume_reference, Mapping):
        from sidecar.runtime.w1_supervisor_snapshot import (
            SnapshotValidationError,
            load_w1_supervisor_snapshot,
        )
        from sidecar.workflows.w1_agentic_adapter import build_supervisor_snapshot_identities

        lineage_id = str(resume_reference.get("lineage_id") or "")
        source_attempt_id = str(resume_reference.get("attempt_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", lineage_id) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", source_attempt_id):
            raise SnapshotValidationError("snapshot_reference_identity_is_invalid")
        config.setdefault(
            "w1_supervisor_staged_source_relative_path",
            f"system/imports/{lineage_id}/attempts/{source_attempt_id}/raw_source.txt",
        )
        config.setdefault("snapshot_source_attempt_id", source_attempt_id)
        source_identity, config_identity = build_supervisor_snapshot_identities(config, project_path=project_path)
        loaded = load_w1_supervisor_snapshot(
            project_path,
            resume_reference,
            expected_source_identity=source_identity,
            expected_config_identity=config_identity,
        )
        snapshot = loaded["snapshot"]
        expected_attempt_id = str(config.get("snapshot_source_attempt_id") or config.get("attempt_id") or "")
        if snapshot.get("attempt_id") != expected_attempt_id:
            raise SnapshotValidationError("snapshot_attempt_provenance_mismatch")
        runtime_store = config.get("runtime_store")
        current_attempt_id = str(config.get("attempt_id") or "")
        actual_unknown = []
        if runtime_store is not None and current_attempt_id:
            actual_unknown = [str(item.get("tool_call_id")) for item in runtime_store.list_unknown_call_summaries(current_attempt_id)]
        if sorted(actual_unknown) != sorted(str(item) for item in snapshot.get("unknown_tool_call_ids", [])):
            raise SnapshotValidationError("snapshot_unknown_tool_calls_mismatch")
        if actual_unknown:
            raise SnapshotValidationError("snapshot_unknown_tool_calls_require_human_confirmation")
        if not _resume_budget_is_compatible(config, snapshot):
            raise SnapshotValidationError("snapshot_budget_is_not_compatible")
        state = _restore_snapshot_state(state, loaded["state"])
        source_for_rebuild = Path(str(config.get("source_file_path") or ""))
        if not source_for_rebuild.is_file():
            source_for_rebuild = Path(project_path) / str(config["w1_supervisor_staged_source_relative_path"])
        state = _rehydrate_snapshot_chunks(state, str(source_for_rebuild))
        resume_next_node = str(snapshot.get("next_node") or "proposal_gate")
        if resume_next_node not in {*_SNAPSHOT_RESUME_ORDER, "proposal_gate"}:
            raise SnapshotValidationError("snapshot_next_node_is_not_resumable")
        state = _with_status(
            state,
            current_tool=resume_next_node,
            orchestrator_phase="resuming",
            converge_status="resuming",
        )

    # ── Validate file + split chunks ─────────────────────────────────────────
    # A v1 snapshot starts *after* one of the complete Supervisor boundaries.
    # It never resumes inside a provider call or an extraction window.
    if not resume_next_node:
      try:
        _emit_activity(state, phase="validate", tool="validate_file", status="start", message="Validating source file and workflow lock.")
        validate_result = await node_validate_file(state)
        state = {**state, **validate_result}
        _emit_activity(state, phase="validate", tool="validate_file", status="success", message="Source file validated.")
        yield _emit(0.02, "validate_file", state.get("errors", []))

        _emit_activity(state, phase="windowing", tool="split_chunks", status="start", message="Splitting manuscript and building prompt windows.")
        split_result = await node_split_chunks(state)
        state = {**state, **split_result}
        persist_w1_usage_ledger(state)
        total_chunks = len(state.get("chunks", []))
        _chunk_progress[project_path] = {"completed": 0, "total": total_chunks}
        _emit_activity(
            state,
            phase="windowing",
            tool="split_chunks",
            status="success",
            message=f"Built {len(state.get('prompt_windows', []))} prompt windows from {total_chunks} chunks.",
            completed=0,
            total=len(state.get("prompt_windows", [])),
        )
        yield _emit(0.05, "split_chunks", state.get("errors", []))
      except Exception as exc:
        _emit_activity(state, phase="error", tool="split_chunks", status="fail", level="error", message="Failed before extraction.", error=str(exc))
        yield _emit(0.0, "error", [str(exc)])
        return

    tools = build_tool_registry()

    # ── Policy loop with progress reporting ──────────────────────────────────
    windows = state.get("prompt_windows", [])
    total_windows = max(len(windows), 1)

    async def _policy_with_progress():
        nonlocal state
        def _should_run(stage: str) -> bool:
            return (
                not resume_next_node
                or (
                    resume_next_node in _SNAPSHOT_RESUME_ORDER
                    and _SNAPSHOT_RESUME_ORDER[stage] >= _SNAPSHOT_RESUME_ORDER[resume_next_node]
                )
            )
        if not resume_next_node:
            _emit_activity(state, phase="planning", tool="planner", status="start", message="Preparing orchestrator import plan.")
            state = _ensure_orchestrator_plan(state)
        if not resume_next_node:
          _emit_activity(
            state,
            phase="planning",
            tool="planner",
            status="success" if state.get("import_plan_validation", {}).get("ok", True) else "fail",
            level="info" if state.get("import_plan_validation", {}).get("ok", True) else "error",
            message=f"Planner selected {state.get('import_granularity_profile', {}).get('profile_name', 'unknown')} granularity.",
          )
        planner_action = resolve_planner_next_action(
            state.get("planner_proposal") or state.get("context", {}).get("planner_proposal") or {},
            registered_tools=set(tools),
            default_tool="segment_manifest",
            iteration=int(state.get("supervisor_iteration", 0) or 0),
            max_iterations=int(state.get("max_supervisor_iterations", 0) or 0),
            budget_exhausted=bool(state.get("budget_exhausted")),
        )
        if not resume_next_node:
          state = {**state, "planner_next_action": planner_action}
        if not resume_next_node and planner_action["kind"] == "stop":
            state = _with_status(
                state,
                current_tool="planner_stop",
                orchestrator_phase="stopped",
                converge_status="hard_fail",
            )
            _emit_activity(state, phase="planning", tool="planner_stop", status="success", message="Planner requested a bounded stop.")
            _emit(1.0, "planner_stop", state.get("errors", []))
            return
        if not resume_next_node and state.get("budget_exhausted"):
            state = _with_status(state, current_tool="budget_stop", orchestrator_phase="stopped", converge_status="hard_fail")
            _emit(1.0, "budget_stop", state.get("errors", []))
            return
        if not resume_next_node:
            state = await _apply_initial_planner_action(state, tools, planner_action)
            persist_w1_usage_ledger(state)
        planner_consumed_segment_manifest = bool(resume_next_node) or state.get("current_stage") == "segment_manifest"
        profile_config_local = state.get("profile_config") or profile_config
        tool_operating_spec_local = state.get("tool_operating_spec", {})

        # segment_manifest
        if not planner_consumed_segment_manifest:
            state = _with_status(state, current_tool="segment_manifest", orchestrator_phase="planning", converge_status="planning")
            _emit_activity(state, phase="planning", tool="segment_manifest", status="start", message="Writing segment manifest.")
            seg_update = await tools["segment_manifest"](state)
            state = {**state, **seg_update, "current_stage": "segment_manifest"}
            _emit_activity(state, phase="planning", tool="segment_manifest", status="success", message="Segment manifest ready.")
            persist_w1_usage_ledger(state)
        if not resume_next_node:
            _emit(_PROGRESS_SEGMENT_MANIFEST, "segment_manifest")

        # Extract windows (batches of 3, progress linearly from 0.10 → 0.65)
        windows_local = list(state.get("prompt_windows", []))
        total_w = max(len(windows_local), 1)
        batch_size = 3
        window_idx = 0
        for batch_start in ([] if resume_next_node else range(0, len(windows_local), batch_size)):
            if state.get("budget_exhausted") or _cancel_requested(state):
                persist_w1_usage_ledger(state)
                break
            batch = windows_local[batch_start: batch_start + batch_size]
            _emit_activity(
                state,
                phase="extracting",
                tool="extract_batch",
                status="start",
                message=f"Starting extraction batch {batch_start // batch_size + 1}: {len(batch)} windows.",
                completed=window_idx,
                total=total_w,
            )
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
            _emit_activity(
                state,
                phase="extracting",
                tool="extract_batch",
                status="fail" if state.get("budget_exhausted") else "success",
                level="error" if state.get("budget_exhausted") else "info",
                message=(
                    "Extraction batch stopped because budget was exhausted."
                    if state.get("budget_exhausted")
                    else f"Finished extraction batch; {window_idx}/{total_w} windows processed."
                ),
                completed=window_idx,
                total=total_w,
            )
            if state.get("budget_exhausted") or _cancel_requested(state):
                persist_w1_usage_ledger(state)
                break
            progress = _PROGRESS_EXTRACT_START + (_PROGRESS_EXTRACT_END - _PROGRESS_EXTRACT_START) * (window_idx / total_w)
            _chunk_progress[project_path] = {"completed": window_idx, "total": total_w}
            yield progress, "extract_windows", state.get("errors", [])

        if not resume_next_node:
            state = {**state, "current_stage": "extract_windows"}
        if not resume_next_node and _cancel_requested(state):
            persist_w1_usage_ledger(state)
            _emit_activity(state, phase="cancelled", tool="workflow", status="cancelled", level="warning", message="Import cancelled after extraction loop.")
            return

        # Reduce entities
        if not resume_next_node:
          state = _with_status(state, current_tool="reduce_entities", orchestrator_phase="reducing")
          _emit_activity(state, phase="reducing", tool="reduce_entities", status="start", message="Reducing extracted entities.")
          reduce_update = await tools["reduce_entities"](state)
          state = {**state, **reduce_update, "current_stage": "reduce_entities"}
          _emit_activity(state, phase="reducing", tool="reduce_entities", status="success", message="Entity reduction complete.")

        # ── 3b. Reduce world entities (streaming path) ───────────────────────
        if not resume_next_node and "reduce_world_entities" in tools:
            state = _with_status(state, current_tool="reduce_world_entities", orchestrator_phase="reducing")
            _emit_activity(state, phase="reducing", tool="reduce_world_entities", status="start", message="Reducing world entities.")
            rwe_update = tools["reduce_world_entities"](state)
            state = {**state, **rwe_update, "current_stage": "reduce_world_entities"}
            _emit_activity(state, phase="reducing", tool="reduce_world_entities", status="success", message="World entity reduction complete.")

        # ── 3c. Content organizer (streaming path) ───────────────────────────
        if not resume_next_node:
          _emit_activity(state, phase="reducing", tool="organizer", status="start", message="Running content organizer to filter world candidates.")
          state = await _organize_staged_world_candidates(state)
          _emit_activity(state, phase="reducing", tool="organizer", status="success", message="Content organizer complete.")

        # ── 4. Minor repair (streaming path) ─────────────────────────────────
        if not resume_next_node:
          state = _with_status(state, current_tool="minor_repair", orchestrator_phase="repairing")
          _emit_activity(state, phase="repairing", tool="minor_repair", status="start", message="Running deterministic repair.")
          repair_update = await tools["minor_repair"](state)
          state = {**state, **repair_update, "current_stage": "minor_repair"}
          _emit_activity(state, phase="repairing", tool="minor_repair", status="success", message="Deterministic repair complete.")
          state = _persist_supervisor_evidence_cards(state)
          yield _PROGRESS_REDUCE_REPAIR, "reduce_repair", state.get("errors", [])

        # Architect
        if resume_next_node in {"", "architect_timeline"}:
          state = _with_status(state, current_tool="architect_timeline", orchestrator_phase="architecting")
          _emit_activity(state, phase="architecting", tool="architect_timeline", status="start", message="Architecting timeline topology.")
          arch_update = await tools["architect_timeline"](state)
          state = {**state, **arch_update, "current_stage": "architect_timeline"}
          state = _prepare_reviewer_staging_state(enforce_timeline_density(state))
          _emit_activity(state, phase="architecting", tool="architect_timeline", status="success", message="Timeline architecture complete.")
          yield _PROGRESS_ARCHITECT, "architect_timeline", state.get("errors", [])

        # QA + optional reruns.  A later snapshot resumes at the next complete
        # boundary, never inside these rerun/provider loops.
        if _should_run("qa_review"):
            max_sup_iters = state.get("max_supervisor_iterations", 3)
            for sup_iter in range(max_sup_iters):
                state = {**state, "supervisor_iteration": sup_iter}
                state = _with_status(state, current_tool="qa_review", orchestrator_phase="reviewing")
                _emit_activity(state, phase="reviewing", tool="qa_review", status="start", message=f"Running QA review iteration {sup_iter + 1}.")
                qa_update = await tools["qa_review"](state)
                state = {**state, **qa_update, "current_stage": "qa_review"}
                _emit_activity(state, phase="reviewing", tool="qa_review", status="success", message=f"QA review iteration {sup_iter + 1} complete.")
                gate_failures = list(state.get("gate_failures", []))
                if not gate_failures:
                    break
                failing_ids = list({f["window_id"] for f in gate_failures if "window_id" in f})
                for wid in failing_ids:
                    if _cancel_requested(state):
                        break
                    state = await _process_window(state, tools, wid, profile_config_local, tool_operating_spec_local)
                reduce_u = await tools["reduce_entities"](state)
                state = {**state, **reduce_u}
                repair_u = await tools["minor_repair"](state)
                state = {**state, **repair_u}
            yield _PROGRESS_QA_REVIEW, "qa_review", state.get("errors", [])

        if _should_run("judge_import") and "judge_import" in tools:
            _emit_activity(state, phase="judging", tool="judge_import", status="start", message="Judging import quality.")
            state = await _run_judge_import(state, tools)
            _active_tos_local = state.get("tool_operating_spec") or tool_operating_spec_local
            state = await _apply_thematic_reruns(state, tools, profile_config_local, _active_tos_local)
            _emit_activity(state, phase="judging", tool="judge_import", status="success", message="Import quality judgment complete.")
            yield _PROGRESS_QA_REVIEW, "judge_import", state.get("errors", [])

        # proposal_gate is terminal from a persisted proposal.  It deliberately
        # does not call proposal_write or accept canonical data again.
        if _should_run("proposal_write"):
            state = _with_status(state, current_tool="proposal_write", orchestrator_phase="writing", converge_status="writing")
            _emit_activity(state, phase="writing", tool="proposal_write", status="start", message="Writing import proposals and artifacts.")
            proposal_update = await tools["proposal_write"](state)
            state = {**state, **proposal_update, "current_stage": "proposal_write"}
            _emit_activity(state, phase="writing", tool="proposal_write", status="success", message="Import proposals written.")
            yield _PROGRESS_PROPOSAL, "proposal_write", state.get("errors", [])
        elif resume_next_node == "proposal_gate":
            state = _with_status(state, current_tool="proposal_gate", orchestrator_phase="proposal_gate", converge_status="awaiting_acceptance")
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

    _ja = state.get("judge_artifact") or {}
    persist_w1_usage_ledger(state)
    state = _with_status(
        state,
        current_tool="proposal_write",
        orchestrator_phase="done",
        converge_status="passed" if _ja.get("passed", True) else _ja.get("result_status", "failed"),
    )
    yield _emit(_PROGRESS_DONE, "done")
