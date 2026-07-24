"""W1 Supervisor pipeline tool contracts — Orchestrator-callable tools.

Tools accept ImportSupervisorState and return partial state dicts.
No raw prompt text is accepted. All review calls are deterministic (zero-cost).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from sidecar.models.state import ImportSupervisorState
from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer
from sidecar.supervisor.reviewers.fact_reviewer import FactReviewer
from sidecar.supervisor.reviewers.consistency_reviewer import ConsistencyReviewer
from sidecar.supervisor.tools import rerun_window
from sidecar.workflows.w1_import import node_write_to_project
from sidecar.supervisor.organizer import _container_key_for_category


async def run_quality_review(state: ImportSupervisorState) -> dict:
    """Run QualityReviewer over state proposals. Stores ReviewReport as reviewer_reports['quality']."""
    reviewer = QualityReviewer()
    report = reviewer.review(state)
    reviewer_reports = dict(state.get("reviewer_reports") or {})
    reviewer_reports["quality"] = report
    log = list(state.get("supervisor_log", []))
    log.append(f"run_quality_review: verdict={report.get('verdict')}, findings={len(report.get('findings', []))}")
    return {
        "reviewer_reports": reviewer_reports,
        "supervisor_log": log,
    }


async def run_fact_review(state: ImportSupervisorState) -> dict:
    """Run FactReviewer over state proposals/evidence_cards. Does not read state['chunks']."""
    reviewer = FactReviewer()
    report = reviewer.review(state)
    reviewer_reports = dict(state.get("reviewer_reports") or {})
    reviewer_reports["fact"] = report
    log = list(state.get("supervisor_log", []))
    log.append(f"run_fact_review: verdict={report.get('verdict')}, findings={len(report.get('findings', []))}")
    return {
        "reviewer_reports": reviewer_reports,
        "supervisor_log": log,
    }


async def run_consistency_review(state: ImportSupervisorState) -> dict:
    """Run ConsistencyReviewer — cross-import continuity checks. Zero-cost."""
    reviewer = ConsistencyReviewer()
    report = reviewer.review(state)
    reviewer_reports = dict(state.get("reviewer_reports") or {})
    reviewer_reports["consistency"] = report
    log = list(state.get("supervisor_log", []))
    log.append(f"run_consistency_review: verdict={report.get('verdict')}, findings={len(report.get('findings', []))}")
    return {
        "reviewer_reports": reviewer_reports,
        "supervisor_log": log,
    }


async def rerun_targeted_window(
    state: ImportSupervisorState,
    affected_window_ids: list[str],
    reason: str,
    parameter_overrides: dict | None = None,
) -> dict:
    """Targeted rerun for specific windows identified by a reviewer.

    Raises ValueError if affected_window_ids is empty (safety guard).
    """
    if not affected_window_ids:
        raise ValueError("rerun_targeted_window: affected_window_ids must be non-empty")

    partial: dict[str, Any] = {}
    log = list(state.get("supervisor_log", []))
    log.append(f"rerun_targeted_window: {len(affected_window_ids)} windows, reason={reason!r}")

    for window_id in affected_window_ids:
        current_state = {**state, **partial}
        update = await rerun_window(
            current_state,
            window_id,
            strategy="augment",
            parameter_overrides=parameter_overrides or {},
        )
        for k, v in update.items():
            if isinstance(v, list) and isinstance(partial.get(k), list):
                partial[k] = partial[k] + v
            elif isinstance(v, dict) and isinstance(partial.get(k), dict):
                merged = dict(partial[k])
                merged.update(v)
                partial[k] = merged
            else:
                partial[k] = v

    partial["supervisor_log"] = log
    return partial


async def repair_import_artifacts(
    state: ImportSupervisorState,
    repair_actions: list[dict],
) -> dict:
    """Apply deterministic local repair actions from ReviewReport.local_repair_actions.

    Supported action_types:
    - merge_duplicate: mark all but the first target_entity_id with skip_create=True
    - reclassify: update entity category field (world entities only)
    - relocate: apply an approved/deterministic World -> Character plan.  The
      plan is an in-memory proposal repair, never a direct canonical write.
    """
    if not repair_actions:
        return {"entity_registry": deepcopy(state.get("entity_registry", {}))}

    registry = {
        k: deepcopy(v) if isinstance(v, dict) else v
        for k, v in state.get("entity_registry", {}).items()
    }
    chars: dict[str, dict] = {k: dict(v) for k, v in registry.get("characters", {}).items()}
    world_detailed: dict[str, dict] = {k: dict(v) for k, v in registry.get("world_detailed", {}).items()}
    repair_log: list[str] = list(state.get("minor_repair_log", []))
    quarantine: list[dict] = list(state.get("quarantine_candidates", []))
    applied_plan_ids: list[str] = list(state.get("applied_relocation_plan_ids", []))

    for action in repair_actions:
        action_type = str(action.get("action_type", ""))
        target_ids = list(action.get("target_entity_ids", []))

        if action_type == "merge_duplicate" and len(target_ids) >= 2:
            for dup_id in target_ids[1:]:
                if dup_id in chars:
                    chars[dup_id]["skip_create"] = True
                    repair_log.append(f"merge_duplicate: marked {dup_id!r} skip_create=True")

        elif action_type == "reclassify":
            proposed = action.get("proposed_operations") or []
            if proposed:
                op = proposed[0]
                new_category = op.get("new_category", "")
                new_container_key = op.get("new_container_key", "")
                new_category_path = op.get("new_category_path", [])
            else:
                new_category = str(action.get("description", "")).split("to category=")[-1].strip()
                new_container_key = _container_key_for_category(new_category)
                new_category_path = []
            for entity_id in target_ids:
                if entity_id in world_detailed:
                    world_detailed[entity_id]["category"] = new_category
                    if new_container_key:
                        world_detailed[entity_id]["container_key"] = new_container_key
                    if new_category_path:
                        world_detailed[entity_id]["categoryPath"] = new_category_path
                    repair_log.append(
                        f"reclassify: {entity_id!r} → category={new_category!r} container={new_container_key!r}"
                    )

        elif action_type in {"relocate", "relocation"}:
            plans = [
                operation.get("relocation_plan")
                for operation in (action.get("proposed_operations") or [])
                if isinstance(operation, dict) and isinstance(operation.get("relocation_plan"), dict)
            ]
            if not plans and isinstance(action.get("relocation_plan"), dict):
                plans = [action["relocation_plan"]]
            for plan in plans:
                _apply_relocation_plan(
                    plan=plan,
                    chars=chars,
                    world_detailed=world_detailed,
                    world_registry=registry.get("world"),
                    quarantine=quarantine,
                    applied_plan_ids=applied_plan_ids,
                    repair_log=repair_log,
                )

    registry["characters"] = chars
    registry["world_detailed"] = world_detailed
    log = list(state.get("supervisor_log", []))
    log.append(f"repair_import_artifacts: {len(repair_actions)} actions applied")

    return {
        "entity_registry": registry,
        "minor_repair_log": repair_log,
        "supervisor_log": log,
        "quarantine_candidates": quarantine,
        "applied_relocation_plan_ids": applied_plan_ids,
    }


def _find_world_key(world_detailed: dict[str, dict], candidate_id: str) -> str | None:
    if candidate_id in world_detailed:
        return candidate_id
    for key, entry in world_detailed.items():
        if str(entry.get("entity_id") or entry.get("id") or "") == candidate_id:
            return key
    return None


def _append_unique(existing: Any, additions: Any) -> list:
    values = list(existing) if isinstance(existing, list) else []
    for item in additions if isinstance(additions, list) else []:
        if item and item not in values:
            values.append(item)
    return values


def _apply_relocation_plan(
    *, plan: dict, chars: dict[str, dict], world_detailed: dict[str, dict],
    world_registry: Any, quarantine: list[dict], applied_plan_ids: list[str], repair_log: list[str],
) -> None:
    """Apply one validated proposal relocation exactly once, or quarantine it."""
    plan_id = str(plan.get("plan_id") or "")
    if not plan_id:
        quarantine.append({"candidate_id": str(plan.get("source_candidate_id") or ""), "reason": "missing_relocation_plan_id", "plan": plan})
        return
    if plan_id in applied_plan_ids:
        return
    allowed = plan.get("status") == "approved" or bool(plan.get("deterministic"))
    target_id = str(plan.get("target_entity_id") or "")
    source_id = str(plan.get("source_candidate_id") or "")
    world_key = _find_world_key(world_detailed, source_id)
    if not allowed or plan.get("target_kind") != "character" or target_id not in chars or not world_key:
        quarantine.append({
            "candidate_id": source_id, "reason": "unsafe_relocation",
            "plan_id": plan_id, "plan": deepcopy(plan),
        })
        repair_log.append(f"relocate: quarantined plan={plan_id!r}")
        return

    source = world_detailed[world_key]
    target = chars[target_id]
    merge = plan.get("field_merge_plan") if isinstance(plan.get("field_merge_plan"), dict) else {}
    target["aliases"] = _append_unique(target.get("aliases"), merge.get("aliases"))
    role = str(merge.get("role") or "").strip()
    if role and not target.get("role"):
        target["role"] = role
    target["evidence_refs"] = _append_unique(
        _append_unique(target.get("evidence_refs"), source.get("evidence_refs") or source.get("evidenceRefs")),
        merge.get("evidence_refs"),
    )
    del world_detailed[world_key]
    if isinstance(world_registry, dict):
        for key, value in list(world_registry.items()):
            if key == world_key or key == source.get("name") or str(value) == source_id:
                world_registry.pop(key, None)
    applied_plan_ids.append(plan_id)
    repair_log.append(f"relocate: applied plan={plan_id!r} source={source_id!r} target={target_id!r}")


async def write_proposal_package(
    state: ImportSupervisorState,
    package: dict,
) -> dict:
    """Stage a ProposalPackage for the Workbench inbox.

    Does NOT write to canonical project storage directly.
    Package is added to state['pending_proposal_packages'] for later batch acceptance.
    """
    pending = list(state.get("pending_proposal_packages") or [])
    pending.append(package)
    log = list(state.get("supervisor_log", []))
    log.append(f"write_proposal_package: staged package_id={package.get('package_id')!r}")
    return {
        "pending_proposal_packages": pending,
        "supervisor_log": log,
    }
