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
_EVENT_DENSITY_VALUES: frozenset[str] = frozenset({"sparse_turning_points", "arc_level", "chapter_level", "scene_level"})
_TOPOLOGY_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})
_WORLD_SCOPE_VALUES: frozenset[str] = frozenset({"minimal", "world_only", "full_lore"})
_LABEL_GRANULARITY_VALUES: frozenset[str] = frozenset({"compact", "standard", "detailed"})

_REVIEWER_MODE_VALUES: frozenset[str] = frozenset({"quality", "fact", "consistency"})
_RERUN_SCOPE_VALUES: frozenset[str] = frozenset({"local_window", "entity_cluster", "timeline_branch", "world_category"})
# organizer_strictness reuses _STRICTNESS_VALUES = frozenset({"low", "medium", "high"})

_REVIEWER_MODE_DIRECTIVES: dict[str, tuple[str, str]] = {
    "quality":      ("reviewer_mode", "Quality review mode: prioritize canonical event classification and world boundary enforcement."),
    "fact":         ("reviewer_mode", "Fact review mode: require evidence refs for all proposed entities."),
    "consistency":  ("reviewer_mode", "Consistency review mode: cross-check against prior import run summaries."),
}
_RERUN_SCOPE_DIRECTIVES: dict[str, tuple[str, str]] = {
    "local_window":     ("rerun_scope", "Rerun scope: local window only — target the specific prompt window that failed."),
    "entity_cluster":   ("rerun_scope", "Rerun scope: entity cluster — re-extract the affected character/event cluster."),
    "timeline_branch":  ("rerun_scope", "Rerun scope: timeline branch — re-run extraction for the affected branch segment."),
    "world_category":   ("rerun_scope", "Rerun scope: world category — re-extract world entities in the affected category."),
}
_ORGANIZER_STRICTNESS_DIRECTIVES: dict[str, tuple[str, str]] = {
    "low":    ("organizer_strictness", "Organizer strictness is low: pass ambiguous world entries with warnings."),
    "medium": ("organizer_strictness", "Organizer strictness is medium: exclude ambiguous person-name world entries."),
    "high":   ("organizer_strictness", "Organizer strictness is high: exclude all boundary-ambiguous entries; route to correct module."),
}

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

_EVENT_DENSITY_DIRECTIVES: dict[str, tuple[str, str]] = {
    "sparse_turning_points": (
        "event_density",
        "Use sparse turning-point density: only irreversible state changes become canonical events; route scene beats to notes.",
    ),
    "arc_level": (
        "event_density",
        "Use arc-level density: keep only phase transitions, breakthroughs, deaths, betrayals, and faction-level shifts.",
    ),
    "chapter_level": (
        "event_density",
        "Use chapter-level density: select a few causally important chapter events, not every action beat.",
    ),
    "scene_level": (
        "event_density",
        "Use scene-level density only for short/dense sources; each event still needs causal state change.",
    ),
}

_TOPOLOGY_DIRECTIVES: dict[str, tuple[str, str]] = {
    "low": ("topology_fidelity", "Keep topology simple unless source evidence clearly requires branches."),
    "medium": ("topology_fidelity", "Preserve recurring arcs and fork/merge hints when supported by source evidence."),
    "high": ("topology_fidelity", "Prioritize branch/fork/merge fidelity; every event should carry arc and causal topology hints."),
}

_WORLD_SCOPE_DIRECTIVES: dict[str, tuple[str, str]] = {
    "minimal": ("world_scope", "World Model scope is minimal: include only reusable setting entities, not people, relationships, or timeline beats."),
    "world_only": ("world_scope", "World Model scope is world-only: exclude relationship graphs, timeline events, ranks-as-characters, and scene beats."),
    "full_lore": ("world_scope", "World Model scope is full lore but still separated from characters, relationships, and timeline modules."),
}

_LABEL_DIRECTIVES: dict[str, tuple[str, str]] = {
    "compact": ("timeline_labels", "Timeline labels should be compact and title-like for dense visual layouts."),
    "standard": ("timeline_labels", "Timeline labels should balance readability and specificity."),
    "detailed": ("timeline_labels", "Timeline labels may be more detailed when density is low and readability allows."),
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
    density = patch.get("event_density_strategy")
    if density in _EVENT_DENSITY_VALUES:
        normalized["event_density_strategy"] = density
    topology = patch.get("topology_fidelity")
    if topology in _TOPOLOGY_VALUES:
        normalized["topology_fidelity"] = topology
    world_scope = patch.get("world_model_scope")
    if world_scope in _WORLD_SCOPE_VALUES:
        normalized["world_model_scope"] = world_scope
    label_granularity = patch.get("timeline_label_granularity")
    if label_granularity in _LABEL_GRANULARITY_VALUES:
        normalized["timeline_label_granularity"] = label_granularity
    reviewer_mode = patch.get("reviewer_mode")
    if reviewer_mode in _REVIEWER_MODE_VALUES:
        normalized["reviewer_mode"] = reviewer_mode
    rerun_scope = patch.get("rerun_scope")
    if rerun_scope in _RERUN_SCOPE_VALUES:
        normalized["rerun_scope"] = rerun_scope
    organizer_strictness = patch.get("organizer_strictness")
    if organizer_strictness in _STRICTNESS_VALUES:
        normalized["organizer_strictness"] = organizer_strictness

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
    density = str(normalized.get("event_density_strategy", "chapter_level"))
    key, directive = _EVENT_DENSITY_DIRECTIVES[density]
    directives[key] = directive
    topology = str(normalized.get("topology_fidelity", "medium"))
    key, directive = _TOPOLOGY_DIRECTIVES[topology]
    directives[key] = directive
    world_scope = str(normalized.get("world_model_scope", "world_only"))
    key, directive = _WORLD_SCOPE_DIRECTIVES[world_scope]
    directives[key] = directive
    label_granularity = str(normalized.get("timeline_label_granularity", "compact"))
    key, directive = _LABEL_DIRECTIVES[label_granularity]
    directives[key] = directive
    reviewer_mode_val = str(normalized.get("reviewer_mode", ""))
    if reviewer_mode_val in _REVIEWER_MODE_DIRECTIVES:
        key, directive = _REVIEWER_MODE_DIRECTIVES[reviewer_mode_val]
        directives[key] = directive
    rerun_scope_val = str(normalized.get("rerun_scope", ""))
    if rerun_scope_val in _RERUN_SCOPE_DIRECTIVES:
        key, directive = _RERUN_SCOPE_DIRECTIVES[rerun_scope_val]
        directives[key] = directive
    organizer_strictness_val = str(normalized.get("organizer_strictness", ""))
    if organizer_strictness_val in _ORGANIZER_STRICTNESS_DIRECTIVES:
        key, directive = _ORGANIZER_STRICTNESS_DIRECTIVES[organizer_strictness_val]
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


def build_directives_header(patch_or_policy: dict[str, Any] | None) -> str:
    """Convert allowlisted prompt policy metadata into a bounded static prompt header."""
    if not isinstance(patch_or_policy, dict):
        return ""
    patch = patch_or_policy.get("prompt_policy_patch") if "prompt_policy_patch" in patch_or_policy else patch_or_policy
    directives = prompt_policy_directives(patch if isinstance(patch, dict) else {})
    if not directives:
        return ""
    lines = ["EXTRACTION_POLICY_DIRECTIVES:"]
    for key in sorted(directives):
        lines.append(f"- {key}: {directives[key]}")
    return "\n".join(lines)


def choose_prompt_policy_patch(source_profile: dict[str, Any] | None, quality_hints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministically choose prompt knobs from source/profile signals.

    This is the zero-cost Orchestrator decision layer. It explains density
    choices without letting raw model text become prompt text.
    """
    profile = source_profile if isinstance(source_profile, dict) else {}
    hints = quality_hints if isinstance(quality_hints, dict) else {}
    chapter_count = int(profile.get("chapter_count") or 1)
    avg_chars = float(profile.get("avg_chars_per_chapter") or 0)
    source_language = str(profile.get("source_language") or "").lower()
    estimated_type = str(profile.get("estimated_source_type") or "")
    warnings = hints.get("warnings") or []

    if estimated_type == "coarse_webnovel" or (source_language.startswith(("zh", "ja", "ko")) and chapter_count >= 8 and avg_chars >= 1500):
        density = "sparse_turning_points"
    elif chapter_count > 30:
        density = "arc_level"
    elif chapter_count <= 5 and avg_chars < 2500:
        density = "scene_level"
    else:
        density = "chapter_level"

    if any("timeline" in str(w).lower() or "branch" in str(w).lower() for w in warnings):
        topology = "high"
    else:
        topology = "high" if chapter_count >= 8 else "medium"

    return {
        "emphasize_existing_timeline_topology": topology != "low",
        "require_source_provenance": True,
        "prefer_canonical_events": density in {"sparse_turning_points", "arc_level", "chapter_level"},
        "suppress_minor_npcs": chapter_count >= 8,
        "relationship_evidence_required": True,
        "world_boundary_strictness": "high",
        "event_density_strategy": density,
        "topology_fidelity": topology,
        "world_model_scope": "world_only",
        "timeline_label_granularity": "compact" if density in {"sparse_turning_points", "arc_level"} else "standard",
    }


def prompt_policy_decision(source_profile: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Artifact payload explaining Orchestrator prompt policy choices."""
    normalized = normalize_prompt_policy_patch(patch)
    return {
        "decision_version": "w1-prompt-policy-decision-v1",
        "source_profile": source_profile or {},
        "prompt_policy_patch": normalized,
        "directive_keys": sorted(prompt_policy_directives(normalized)),
        "rationale": [
            "Density is selected by source profile and quality hints, not hard-coded by the prompt author.",
            "Raw prompt text is rejected; only allowlisted static directives are injected.",
            "World Model scope excludes timeline events, relationship graphs, and character-only facts.",
        ],
    }
