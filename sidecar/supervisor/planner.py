"""W1 planner boundary: validate_planner_proposal + planner_proposal_to_import_plan.

Safety principle: LLM may propose. The validator decides. The executor runs deterministically.

This module is the ONLY channel through which a future LLM/RAG planner may influence W1
extraction. It imports from sidecar.models.state only; no model calls are made here.
"""
from __future__ import annotations

from sidecar.models.state import (
    ImportPlan,
    PlannerProposal,
    ToolOperatingSpec,
    _KNOWN_TOOLS,
    _VALID_PLANNER_KINDS,
    _VALID_SOURCE_TYPES,
    plan_import_pipeline,
    select_granularity_profile,
    validate_import_plan,
)
from sidecar.supervisor.prompt_policy import apply_prompt_policy_patch_to_plan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROPOSAL_ALLOWED_FIELDS: frozenset = frozenset({
    "planner_kind",
    "source_profile",
    "proposed_source_type",
    "proposed_granularity_profile",
    "proposed_window_strategy",
    "proposed_tool_overrides",
    "prompt_variant_preferences",
    "rationale",
    "confidence",
    "safety_notes",
    "prompt_policy_patch",
})

# ---------------------------------------------------------------------------
# PromptPolicyPatch constants
# ---------------------------------------------------------------------------

_PPP_ALLOWED_FIELDS: frozenset = frozenset({
    "emphasize_existing_timeline_topology",
    "require_source_provenance",
    "prefer_canonical_events",
    "suppress_minor_npcs",
    "relationship_evidence_required",
    "world_boundary_strictness",
})
_PPP_BOOL_FIELDS: frozenset = frozenset({
    "emphasize_existing_timeline_topology",
    "require_source_provenance",
    "prefer_canonical_events",
    "suppress_minor_npcs",
    "relationship_evidence_required",
})
_PPP_STRICTNESS_VALUES: frozenset = frozenset({"low", "medium", "high"})

_TOOL_VARIANT_ALLOWLISTS: dict = {
    "extract_character": frozenset({"major_only", "named_only", "all"}),
    "extract_event": frozenset({"arc_level", "chapter_level", "scene_level"}),
    "extract_world": frozenset({"named_only", "structural", "full_lore"}),
    "extract_relationship": frozenset({"core", "recurring", "dense"}),
    "extract_scene_summary": frozenset({"fixed"}),
}

_GP_ALLOWED_FIELDS: frozenset = frozenset({
    "profile_name",
    "min_characters_per_chapter",
    "acceptable_floor_fraction",
    "min_events_per_chapter",
    "rerun_on_character_gap",
    "max_world_entities_per_chapter",
    "character_granularity",
    "event_density",
    "world_density",
    "relationship_depth",
})
_GP_LITERAL_FIELDS: dict = {
    "profile_name": frozenset({"coarse_webnovel", "balanced_novel", "fine_short_story", "custom"}),
    "character_granularity": frozenset({"major_only", "named_only", "all"}),
    "event_density": frozenset({"arc_level", "chapter_level", "scene_level"}),
    "world_density": frozenset({"named_only", "structural", "full_lore"}),
    "relationship_depth": frozenset({"core", "recurring", "dense"}),
}
_GP_NUMERIC_BOUNDS: dict = {
    "min_characters_per_chapter": (0.1, 3.0),
    "min_events_per_chapter": (0.1, 5.0),
    "acceptable_floor_fraction": (0.0, 1.0),
    "max_world_entities_per_chapter": (0, 20),
}

_KNOWN_WINDOW_STRATEGY_KEYS: frozenset = frozenset({
    "strategy",
    "chapters_per_window_max",
    "late_window_cap_enabled",
    "parallel_window_batch_size",
})
_VALID_WINDOW_STRATEGIES: frozenset = frozenset({"supervised_chapter_batching"})
_WINDOW_NUMERIC_BOUNDS: dict = {
    "chapters_per_window_max": (1, 12),
    "parallel_window_batch_size": (1, 8),
}

_OVERRIDE_ALLOWED_FIELDS: frozenset = frozenset({"tool", "prompt_granularity", "rerun_allowed"})


# ---------------------------------------------------------------------------
# validate_planner_proposal
# ---------------------------------------------------------------------------

def validate_planner_proposal(proposal: PlannerProposal) -> tuple[bool, list[str]]:
    """Validate a PlannerProposal against the W1 safety contract.

    Returns (True, []) for valid proposals, (False, [errors]) otherwise.
    All checks run — callers see the full error list.
    """
    errors: list[str] = []

    # --- top-level keys -------------------------------------------------------
    unknown_keys = set(proposal) - _PROPOSAL_ALLOWED_FIELDS
    if unknown_keys:
        errors.append(f"unknown top-level keys: {sorted(unknown_keys)}")

    # --- planner_kind ---------------------------------------------------------
    if proposal.get("planner_kind") not in _VALID_PLANNER_KINDS:
        errors.append(f"unknown planner_kind: {proposal.get('planner_kind')!r}")

    # --- proposed_source_type -------------------------------------------------
    if proposal.get("proposed_source_type") not in _VALID_SOURCE_TYPES:
        errors.append(f"unknown proposed_source_type: {proposal.get('proposed_source_type')!r}")

    # --- proposed_granularity_profile -----------------------------------------
    gp = proposal.get("proposed_granularity_profile") or {}
    unknown_gp_keys = set(gp) - _GP_ALLOWED_FIELDS
    if unknown_gp_keys:
        errors.append(f"proposed_granularity_profile: unknown keys {sorted(unknown_gp_keys)}")
    for field, allowed in _GP_LITERAL_FIELDS.items():
        if field in gp and gp[field] not in allowed:
            errors.append(
                f"proposed_granularity_profile.{field}: {gp[field]!r} not in {sorted(allowed)}"
            )
    for field, (lo, hi) in _GP_NUMERIC_BOUNDS.items():
        if field in gp:
            try:
                val = float(gp[field])
            except (TypeError, ValueError):
                errors.append(f"proposed_granularity_profile.{field}: must be numeric")
                continue
            if not (lo <= val <= hi):
                errors.append(
                    f"proposed_granularity_profile.{field}: {val} out of range [{lo}, {hi}]"
                )
    if "rerun_on_character_gap" in gp and not isinstance(gp["rerun_on_character_gap"], bool):
        errors.append("proposed_granularity_profile.rerun_on_character_gap: must be bool")

    # --- proposed_tool_overrides ----------------------------------------------
    for i, override in enumerate(proposal.get("proposed_tool_overrides") or []):
        tool_name = override.get("tool")
        if tool_name not in _KNOWN_TOOLS:
            errors.append(f"tool override[{i}]: unknown tool {tool_name!r}")
        extra_keys = set(override) - _OVERRIDE_ALLOWED_FIELDS
        if extra_keys:
            errors.append(f"tool override[{i}]: forbidden fields {sorted(extra_keys)}")
        pv = override.get("prompt_granularity")
        if pv is not None:
            allowed_variants = _TOOL_VARIANT_ALLOWLISTS.get(tool_name)
            if allowed_variants is None:
                errors.append(
                    f"tool override[{i}]: tool {tool_name!r} does not accept prompt_granularity"
                )
            elif pv not in allowed_variants:
                errors.append(
                    f"tool override[{i}]: prompt_granularity {pv!r} not in allowlist for {tool_name!r}"
                )

    # --- prompt_variant_preferences -------------------------------------------
    for tool_name, variant_key in (proposal.get("prompt_variant_preferences") or {}).items():
        if tool_name not in _KNOWN_TOOLS:
            errors.append(f"prompt_variant_preferences: unknown tool {tool_name!r}")
            continue
        allowed_variants = _TOOL_VARIANT_ALLOWLISTS.get(tool_name)
        if allowed_variants is None:
            errors.append(
                f"prompt_variant_preferences: tool {tool_name!r} does not accept variant preferences"
            )
        elif variant_key not in allowed_variants:
            errors.append(
                f"prompt_variant_preferences[{tool_name!r}]: {variant_key!r} not in allowlist "
                f"{sorted(allowed_variants)} — raw prompt text is not allowed"
            )

    # --- proposed_window_strategy ---------------------------------------------
    ws = proposal.get("proposed_window_strategy") or {}
    unknown_ws = set(ws) - _KNOWN_WINDOW_STRATEGY_KEYS
    if unknown_ws:
        errors.append(f"proposed_window_strategy: unknown keys {sorted(unknown_ws)}")
    if "strategy" in ws and ws["strategy"] not in _VALID_WINDOW_STRATEGIES:
        errors.append(
            f"proposed_window_strategy.strategy: {ws['strategy']!r} is not supported"
        )
    for field, (lo, hi) in _WINDOW_NUMERIC_BOUNDS.items():
        if field in ws:
            try:
                val = int(ws[field])
            except (TypeError, ValueError):
                errors.append(f"proposed_window_strategy.{field}: must be integer")
                continue
            if not (lo <= val <= hi):
                errors.append(
                    f"proposed_window_strategy.{field}: {val} out of range [{lo}, {hi}]"
                )
    if "late_window_cap_enabled" in ws and not isinstance(ws["late_window_cap_enabled"], bool):
        errors.append("proposed_window_strategy.late_window_cap_enabled: must be bool")

    # --- confidence -----------------------------------------------------------
    confidence = proposal.get("confidence")
    if confidence is not None:
        try:
            val = float(confidence)
        except (TypeError, ValueError):
            errors.append(f"confidence: must be numeric, got {confidence!r}")
        else:
            if not (0.0 <= val <= 1.0):
                errors.append(f"confidence: {val} out of range [0.0, 1.0]")

    # --- prompt_policy_patch --------------------------------------------------
    ppp = proposal.get("prompt_policy_patch")
    if ppp is not None:
        ppp_ok, ppp_errors = validate_prompt_policy_patch(ppp)
        if not ppp_ok:
            errors.extend(f"prompt_policy_patch: {e}" for e in ppp_errors)

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# validate_prompt_policy_patch
# ---------------------------------------------------------------------------

def validate_prompt_policy_patch(patch: dict) -> tuple[bool, list[str]]:
    """Validate a PromptPolicyPatch against the W1 safety contract.

    Only allowlisted boolean knobs and world_boundary_strictness are accepted.
    Raw prompt text is never allowed. Returns (True, []) or (False, [errors]).
    """
    errors: list[str] = []

    unknown_keys = set(patch) - _PPP_ALLOWED_FIELDS
    if unknown_keys:
        errors.append(f"unknown fields: {sorted(unknown_keys)}")

    for field in _PPP_BOOL_FIELDS:
        if field in patch:
            if not isinstance(patch[field], bool):
                errors.append(
                    f"{field}: must be bool, got {type(patch[field]).__name__} {patch[field]!r}"
                )

    ws = patch.get("world_boundary_strictness")
    if ws is not None and ws not in _PPP_STRICTNESS_VALUES:
        errors.append(
            f"world_boundary_strictness: {ws!r} not in {sorted(_PPP_STRICTNESS_VALUES)}"
        )

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# planner_proposal_to_import_plan
# ---------------------------------------------------------------------------

def planner_proposal_to_import_plan(
    proposal: PlannerProposal,
    tool_operating_spec: ToolOperatingSpec,
    *,
    source_language: str = "en",
    prompt_profile: str = "balanced",
    chapter_count: int = 1,
) -> ImportPlan:
    """Convert a PlannerProposal to a validated ImportPlan.

    Raises ValueError if validate_planner_proposal() or validate_import_plan() fails.
    No model calls are made; conversion is fully deterministic.
    """
    ok, errors = validate_planner_proposal(proposal)
    if not ok:
        raise ValueError(f"Invalid PlannerProposal: {errors}")

    chapter_count = max(int(chapter_count or 1), 1)

    # Build merged granularity profile: deterministic base + safe proposal overrides
    base_profile = dict(select_granularity_profile(chapter_count, source_language, prompt_profile))
    proposed_gp = proposal.get("proposed_granularity_profile") or {}
    merged_profile = {**base_profile}
    for field in _GP_ALLOWED_FIELDS:
        if field in proposed_gp:
            merged_profile[field] = proposed_gp[field]
    if proposal.get("proposed_source_type"):
        merged_profile["profile_name"] = proposal["proposed_source_type"]  # type: ignore[assignment]

    # Build base deterministic plan
    plan = plan_import_pipeline(
        merged_profile,  # type: ignore[arg-type]
        tool_operating_spec,
        source_language=source_language,
        prompt_profile=prompt_profile,
        chapter_count=chapter_count,
    )

    # Apply planner_kind and source_type overrides
    plan["planner_kind"] = proposal.get("planner_kind", "deterministic_rules")  # type: ignore[assignment]
    if proposal.get("proposed_source_type"):
        plan["source_type"] = proposal["proposed_source_type"]  # type: ignore[assignment]

    # Apply tool-level overrides (prompt_granularity and rerun_allowed only)
    override_map: dict = {
        o.get("tool"): o
        for o in (proposal.get("proposed_tool_overrides") or [])
        if o.get("tool") in _KNOWN_TOOLS
    }
    for step in plan["tools"]:
        override = override_map.get(step.get("tool"))
        if override:
            if "prompt_granularity" in override:
                step["prompt_granularity"] = override["prompt_granularity"]
            if "rerun_allowed" in override:
                step["rerun_allowed"] = bool(override["rerun_allowed"])

    # Apply prompt variant preferences
    pvp = proposal.get("prompt_variant_preferences") or {}
    if pvp:
        for step in plan["tools"]:
            pref = pvp.get(step.get("tool"))
            if pref:
                step["prompt_granularity"] = pref

    # Merge safe window strategy fields (strategy is always fixed)
    ws = proposal.get("proposed_window_strategy") or {}
    for key in _KNOWN_WINDOW_STRATEGY_KEYS - {"strategy"}:
        if key in ws:
            plan["window_strategy"][key] = ws[key]

    if proposal.get("prompt_policy_patch") is not None:
        plan = apply_prompt_policy_patch_to_plan(plan, proposal.get("prompt_policy_patch"))  # type: ignore[assignment]

    # Final gate: converted plan must satisfy the full ImportPlan contract
    ok, errors = validate_import_plan(plan)
    if not ok:
        raise ValueError(f"Converted ImportPlan failed validation: {errors}")

    return plan
