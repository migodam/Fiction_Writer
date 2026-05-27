"""Zero-cost prompt policy helpers for W1 planner proposals.

The planner may only toggle bounded knobs. These helpers convert those knobs into
static, allowlisted directives so proposal text can never become prompt text.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_BOOL_DEFAULTS: dict[str, bool] = {
    "emphasize_existing_timeline_topology": False,
    "require_source_provenance": True,
    "prefer_canonical_events": False,
    "suppress_minor_npcs": False,
    "relationship_evidence_required": True,
}

_STRICTNESS_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})

_BOOL_DIRECTIVES: dict[tuple[str, bool], tuple[str, str]] = {
    ("emphasize_existing_timeline_topology", True): (
        "timeline_topology",
        "Use existing branch, fork, and merge topology as advisory context.",
    ),
    ("emphasize_existing_timeline_topology", False): (
        "timeline_topology",
        "Do not invent topology pressure beyond source evidence and project digest.",
    ),
    ("require_source_provenance", True): (
        "source_provenance",
        "Every proposed entity or event must preserve source provenance.",
    ),
    ("require_source_provenance", False): (
        "source_provenance",
        "Source provenance remains preferred but non-blocking for low-risk draft hints.",
    ),
    ("prefer_canonical_events", True): (
        "canonical_events",
        "Prefer canonical turning-point events over scene beats when evidence supports promotion.",
    ),
    ("prefer_canonical_events", False): (
        "canonical_events",
        "Keep scene beats demotable unless they are clear story-turning events.",
    ),
    ("suppress_minor_npcs", True): (
        "minor_npcs",
        "Suppress unnamed or one-off minor NPCs unless they recur or affect causality.",
    ),
    ("suppress_minor_npcs", False): (
        "minor_npcs",
        "Allow named minor characters when source evidence is clear.",
    ),
    ("relationship_evidence_required", True): (
        "relationship_evidence",
        "Relationships require explicit source evidence before proposal write.",
    ),
    ("relationship_evidence_required", False): (
        "relationship_evidence",
        "Relationships may remain as low-confidence hints when evidence is partial.",
    ),
}

_STRICTNESS_DIRECTIVES: dict[str, tuple[str, str]] = {
    "low": ("world_boundary", "World boundary strictness is low: accept broad lore hints when grounded."),
    "medium": ("world_boundary", "World boundary strictness is medium: separate entities by likely ontology."),
    "high": (
        "world_boundary",
        "World boundary strictness is high: keep organizations, factions, locations, and systems distinct.",
    ),
}


def normalize_prompt_policy_patch(patch: dict[str, Any] | None) -> dict[str, Any]:
    """Return only valid allowlisted prompt-policy knobs.

    Unknown keys, raw prompt text, and mistyped values are ignored rather than
    copied forward. Validation remains the caller's responsibility when rejection
    is required; normalization is intentionally safe-by-construction.
    """
    if not isinstance(patch, dict):
        return {}

    normalized: dict[str, Any] = {}
    for field in _BOOL_DEFAULTS:
        value = patch.get(field)
        if isinstance(value, bool):
            normalized[field] = value

    strictness = patch.get("world_boundary_strictness")
    if strictness in _STRICTNESS_VALUES:
        normalized["world_boundary_strictness"] = strictness

    return normalized


def prompt_policy_directives(patch: dict[str, Any] | None) -> dict[str, str]:
    """Convert a policy patch into keyed static directives from fixed allowlists."""
    normalized = normalize_prompt_policy_patch(patch)
    directives: dict[str, str] = {}

    for field, default in _BOOL_DEFAULTS.items():
        value = bool(normalized.get(field, default))
        key, directive = _BOOL_DIRECTIVES[(field, value)]
        directives[key] = directive

    strictness = str(normalized.get("world_boundary_strictness", "medium"))
    key, directive = _STRICTNESS_DIRECTIVES[strictness]
    directives[key] = directive
    return directives


def apply_prompt_policy_patch_to_plan(
    plan: dict[str, Any],
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a copy of plan with normalized prompt-policy metadata attached."""
    updated = deepcopy(plan)
    prompt_policy = dict(updated.get("prompt_policy") or {})
    normalized = normalize_prompt_policy_patch(patch)
    directives = prompt_policy_directives(normalized)
    prompt_policy["prompt_policy_patch"] = normalized
    prompt_policy["directive_keys"] = sorted(directives)
    prompt_policy["static_policy_directives"] = directives
    prompt_policy["dynamic_prompt_edits_allowed"] = False
    updated["prompt_policy"] = prompt_policy
    return updated
