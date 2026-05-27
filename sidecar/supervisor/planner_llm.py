"""Zero-cost scaffolding for future W1 LLM planner proposals.

This module intentionally performs no model calls and reads no API keys. It only
builds safe prompt context, parses structured JSON, and emits a deterministic
stub proposal that must pass the existing planner validator.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sidecar.models.state import (
    PlannerProposal,
    analyze_source_profile,
    select_granularity_profile,
)
from sidecar.supervisor.planner import validate_planner_proposal
from sidecar.supervisor.prompt_policy import normalize_prompt_policy_patch


_FENCED_JSON_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _chapter_count(state: dict[str, Any]) -> int:
    chunks = state.get("chunks")
    if isinstance(chunks, list):
        return len(chunks)
    source_profile = state.get("source_profile")
    if isinstance(source_profile, dict):
        try:
            return max(int(source_profile.get("chapter_count", 0)), 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _source_profile(state: dict[str, Any]) -> dict[str, Any]:
    existing = state.get("source_profile")
    if isinstance(existing, dict) and existing:
        return dict(existing)
    return dict(
        analyze_source_profile(
            state.get("chunks", []) if isinstance(state.get("chunks"), list) else [],
            source_language=str(state.get("source_language", "en") or "en"),
            prompt_profile=str(state.get("prompt_profile", "balanced") or "balanced"),
        )
    )


def build_planner_proposal_prompt_context(state: dict[str, Any]) -> dict[str, Any]:
    """Build bounded, schema-oriented context for a future planner prompt."""
    source_language = str(state.get("source_language", "en") or "en")
    prompt_profile = str(state.get("prompt_profile", "balanced") or "balanced")
    chapter_count = _chapter_count(state)
    source_profile = _source_profile(state)
    granularity_profile = state.get("import_granularity_profile")
    if not isinstance(granularity_profile, dict) or not granularity_profile:
        granularity_profile = select_granularity_profile(
            chapter_count,
            source_language,
            prompt_profile,
        )

    return {
        "schema": "PlannerProposal",
        "source_language": source_language,
        "prompt_profile": prompt_profile,
        "chapter_count": chapter_count,
        "source_profile": source_profile,
        "recommended_granularity_profile": dict(granularity_profile),
        "tool_operating_spec": dict(state.get("tool_operating_spec") or {}),
        "allowed_prompt_policy_patch_keys": [
            "emphasize_existing_timeline_topology",
            "require_source_provenance",
            "prefer_canonical_events",
            "suppress_minor_npcs",
            "relationship_evidence_required",
            "world_boundary_strictness",
        ],
        "safety_contract": {
            "llm_planner_can_propose_only": True,
            "raw_prompt_text_allowed": False,
            "dynamic_prompt_edits_allowed": False,
        },
    }


def parse_planner_proposal_json(payload: str | bytes) -> PlannerProposal:
    """Parse and validate a PlannerProposal JSON payload."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if not isinstance(payload, str):
        raise TypeError("payload must be str or bytes")

    match = _FENCED_JSON_RE.match(payload)
    raw = match.group(1) if match else payload
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("PlannerProposal payload must decode to an object")

    ok, errors = validate_planner_proposal(parsed)
    if not ok:
        raise ValueError(f"Invalid PlannerProposal: {errors}")
    if "prompt_policy_patch" in parsed:
        parsed["prompt_policy_patch"] = normalize_prompt_policy_patch(
            parsed.get("prompt_policy_patch")
        )
    return parsed  # type: ignore[return-value]


def generate_planner_proposal_stub(state: dict[str, Any]) -> PlannerProposal:
    """Generate a deterministic proposal shaped like the future LLM output."""
    context = build_planner_proposal_prompt_context(state)
    source_profile = dict(context["source_profile"])
    proposed_source_type = str(
        source_profile.get(
            "recommended_granularity_profile",
            source_profile.get("estimated_source_type", "balanced_novel"),
        )
    )
    granularity_profile = dict(context["recommended_granularity_profile"])
    granularity_profile["profile_name"] = proposed_source_type

    proposal: PlannerProposal = {
        "planner_kind": "llm_proposed",
        "source_profile": source_profile,  # type: ignore[typeddict-item]
        "proposed_source_type": proposed_source_type,  # type: ignore[typeddict-item]
        "proposed_granularity_profile": granularity_profile,  # type: ignore[typeddict-item]
        "rationale": "zero-cost deterministic stub for validator integration",
        "confidence": float(source_profile.get("confidence", 0.5) or 0.5),
        "safety_notes": [
            "stub performs no model call",
            "stub does not read API keys",
        ],
        "prompt_policy_patch": {},
    }
    ok, errors = validate_planner_proposal(proposal)
    if not ok:
        raise ValueError(f"Generated PlannerProposal stub failed validation: {errors}")
    return proposal
