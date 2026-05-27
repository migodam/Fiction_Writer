"""W1 zero-cost import quality rubric.

Offline, deterministic QA layer for import artifacts. Does NOT replace judge_import.
No model calls are made. Accepts partial/synthetic state gracefully.

Safety principle: hard failures are reserved for contract/safety breaks only.
Novelist-quality signals (missing characters, events without branchId, etc.) are soft warnings.
"""
from __future__ import annotations

def evaluate_import_quality(state: dict) -> dict:
    """Evaluate import quality from state dict. Returns a structured QualityReport.

    Hard failures: contract/safety breaks (plan invalid, safety gates missing, proposal
    validation failed). All novelist quality signals are soft warnings.
    """
    hard_failures: list[str] = []
    warnings: list[str] = []
    quality_notes: list[str] = []
    suggested_next_actions: list[str] = []
    checks: dict[str, dict] = {}

    # ── 1. Import plan validation ─────────────────────────────────────────────
    plan_validation = state.get("import_plan_validation")
    if plan_validation is not None:
        if plan_validation.get("ok") is False:
            errors = plan_validation.get("errors", [])
            hard_failures.append(f"import_plan_validation failed: {errors}")
            checks["import_plan_validation"] = {"result": "fail", "detail": str(errors)}
        else:
            checks["import_plan_validation"] = {"result": "pass", "detail": "ok"}
    else:
        warnings.append("import_plan_validation absent from state")
        checks["import_plan_validation"] = {"result": "warn", "detail": "key absent"}

    # ── 2. Safety gates ───────────────────────────────────────────────────────
    import_plan = state.get("import_plan")
    if import_plan:
        safety = import_plan.get("safety")
        if safety is None:
            hard_failures.append("import_plan.safety missing — proposal gate and schema validation not enforced")
            checks["safety_gates"] = {"result": "fail", "detail": "safety key absent from import_plan"}
        else:
            gate_errors = []
            if safety.get("proposal_gate_required") is not True:
                gate_errors.append("proposal_gate_required is not True")
            if safety.get("schema_validated_plan") is not True:
                gate_errors.append("schema_validated_plan is not True")
            if gate_errors:
                hard_failures.append(f"safety gates not set: {gate_errors}")
                checks["safety_gates"] = {"result": "fail", "detail": str(gate_errors)}
            else:
                checks["safety_gates"] = {"result": "pass", "detail": "all gates set"}
    else:
        warnings.append("import_plan absent from state — safety gates cannot be evaluated")
        checks["safety_gates"] = {"result": "warn", "detail": "import_plan absent"}

    # ── 3. Planner proposal validation (if proposal submitted) ────────────────
    planner_proposal = state.get("planner_proposal")
    planner_proposal_validation = state.get("planner_proposal_validation")
    if planner_proposal_validation is not None:
        if planner_proposal_validation.get("ok") is False:
            errs = planner_proposal_validation.get("errors", [])
            hard_failures.append(f"planner_proposal_validation failed: {errs}")
            checks["planner_proposal_validation"] = {"result": "fail", "detail": str(errs)}
        else:
            checks["planner_proposal_validation"] = {"result": "pass", "detail": "ok"}
    elif planner_proposal is not None:
        # Proposal present but no validation recorded — treat as warn, not hard fail
        warnings.append("planner_proposal present but planner_proposal_validation absent")
        checks["planner_proposal_validation"] = {"result": "warn", "detail": "validation record absent"}
    else:
        checks["planner_proposal_validation"] = {"result": "pass", "detail": "no proposal submitted"}

    # ── 4. Proposal gate bypass check ────────────────────────────────────────
    if planner_proposal is not None and import_plan:
        if import_plan.get("planner_kind") == "deterministic_rules":
            hard_failures.append(
                "planner_proposal submitted but import_plan.planner_kind is deterministic_rules — "
                "proposal may not have been applied through the validated gate"
            )
            checks["proposal_gate_bypass"] = {"result": "fail", "detail": "planner_kind mismatch"}
        else:
            checks["proposal_gate_bypass"] = {"result": "pass", "detail": "planner_kind matches proposal"}
    else:
        checks["proposal_gate_bypass"] = {"result": "pass", "detail": "no proposal or no plan to cross-check"}

    # ── 5. Character coverage (soft warn) ────────────────────────────────────
    converge_target = state.get("converge_target") or {}
    expected_min_chars = converge_target.get("expected_min_characters", 0)
    proposals = state.get("inbox_proposals", []) or state.get("proposals", []) or []
    char_proposals = [
        op
        for p in proposals
        for op in (p.get("operations") or [])
        if _entity_type(op) == "character"
    ]
    if expected_min_chars > 0 and len(char_proposals) == 0:
        warnings.append(
            f"no character proposals found; converge_target expects {expected_min_chars} characters"
        )
        suggested_next_actions.append(
            "Run extraction or inspect window artifacts for character coverage"
        )
        checks["character_coverage"] = {"result": "warn", "detail": f"0 characters, expected ≥{expected_min_chars}"}
    else:
        checks["character_coverage"] = {
            "result": "pass",
            "detail": f"{len(char_proposals)} character proposals" if proposals else "no proposals yet",
        }

    # ── 6. Event topology (soft warn) ────────────────────────────────────────
    event_proposals = [
        op
        for p in proposals
        for op in (p.get("operations") or [])
        if _entity_type(op) == "timeline_event"
    ]
    if event_proposals:
        missing_branch = [
            op.get("entityId", "?")
            for op in event_proposals
            if not (op.get("fields") or {}).get("branchId")
        ]
        missing_order = [
            op.get("entityId", "?")
            for op in event_proposals
            if (op.get("fields") or {}).get("orderIndex") is None
        ]
        if missing_branch:
            warnings.append(
                f"{len(missing_branch)} event(s) missing branchId: useful for timeline topology"
            )
            suggested_next_actions.append("Ensure timeline events include branchId for topology mapping")
            checks["event_branch_id"] = {"result": "warn", "detail": f"{len(missing_branch)} events missing branchId"}
        else:
            checks["event_branch_id"] = {"result": "pass", "detail": "all events have branchId"}

        if missing_order:
            warnings.append(f"{len(missing_order)} event(s) missing orderIndex")
            checks["event_order_index"] = {"result": "warn", "detail": f"{len(missing_order)} events missing orderIndex"}
        else:
            checks["event_order_index"] = {"result": "pass", "detail": "all events have orderIndex"}
    else:
        quality_notes.append("No event proposals to evaluate for topology")
        checks["event_branch_id"] = {"result": "pass", "detail": "no events yet"}
        checks["event_order_index"] = {"result": "pass", "detail": "no events yet"}

    # ── 7. Relationship evidence (soft warn) ──────────────────────────────────
    rel_proposals = [
        op
        for p in proposals
        for op in (p.get("operations") or [])
        if _entity_type(op) == "relationship"
    ]
    if rel_proposals:
        missing_evidence = [
            op.get("entityId", "?")
            for op in rel_proposals
            if not (op.get("fields") or {}).get("evidence")
        ]
        if missing_evidence:
            warnings.append(
                f"{len(missing_evidence)} relationship(s) missing evidence field"
            )
            suggested_next_actions.append(
                "Add evidence field to relationships for provenance tracking"
            )
            checks["relationship_evidence"] = {
                "result": "warn",
                "detail": f"{len(missing_evidence)} relationships missing evidence",
            }
        else:
            checks["relationship_evidence"] = {"result": "pass", "detail": "all relationships have evidence"}
    else:
        checks["relationship_evidence"] = {"result": "pass", "detail": "no relationships yet"}

    # ── 8. World/person boundary (soft warn) ─────────────────────────────────
    world_proposals = [
        op
        for p in proposals
        for op in (p.get("operations") or [])
        if _entity_type(op) in {"world", "world_entity", "organization", "faction", "location"}
    ]
    character_names = {_operation_name(op) for op in char_proposals if _operation_name(op)}
    world_names = {_operation_name(op) for op in world_proposals if _operation_name(op)}
    collisions = sorted(character_names & world_names)
    if collisions:
        warnings.append(
            "world/person boundary collision: "
            f"{', '.join(collisions[:5])} appear as both character and world entities"
        )
        suggested_next_actions.append(
            "Inspect minor_repair/world boundary handling before writing canonical entities"
        )
        checks["world_person_boundary"] = {
            "result": "warn",
            "detail": f"{len(collisions)} exact-name collision(s)",
        }
    else:
        checks["world_person_boundary"] = {"result": "pass", "detail": "no exact-name collisions"}

    # ── 9. Source profile present (soft warn) ─────────────────────────────────
    if not state.get("source_profile"):
        warnings.append("source_profile absent from state — orchestrator may not have run planning phase")
        suggested_next_actions.append("Ensure _ensure_orchestrator_plan() has been called")
        checks["source_profile"] = {"result": "warn", "detail": "absent"}
    else:
        checks["source_profile"] = {"result": "pass", "detail": "present"}

    # ── Verdict ───────────────────────────────────────────────────────────────
    if hard_failures:
        verdict = "fail"
    elif warnings:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "verdict": verdict,
        "warnings": warnings,
        "hard_failures": hard_failures,
        "quality_notes": quality_notes,
        "suggested_next_actions": suggested_next_actions,
        "checks": checks,
        "token_cost_ledger": _token_cost_ledger(state),
    }


def _entity_type(operation: dict) -> str:
    return operation.get("entityType", "")


def _operation_name(operation: dict) -> str:
    fields = operation.get("fields") or {}
    name = fields.get("name") or fields.get("canonicalName") or fields.get("title")
    return str(name or operation.get("entityId") or "").strip()


def _token_cost_ledger(state: dict) -> dict:
    return {
        "live_model_calls": False,
        "full50_run": False,
        "model_used": None,
        "estimated_prompt_windows": _estimated_prompt_windows(state),
        "estimated_api_calls": 0,
    }


def _estimated_prompt_windows(state: dict) -> int:
    for key in (
        "prompt_windows",
        "prompt_window_manifest",
        "prompt_windows_manifest",
        "window_manifest",
    ):
        value = state.get(key)
        if isinstance(value, list):
            return len(value)
    return 0
