from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional, TypedDict


class OrchestratorStep(TypedDict):
    step_id: str
    workflow: str
    config: dict
    rationale: str
    requires_permission: bool
    status: Literal["pending", "running", "done", "failed", "skipped"]


class PermissionRequest(TypedDict):
    step_id: str
    description: str
    risk_level: Literal["low", "medium", "high"]
    affected_entities: List[str]


class OrchestratorState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    goal: str
    context: dict
    plan: List[OrchestratorStep]
    current_step: int
    step_results: List[dict]
    pending_permission: Optional[PermissionRequest]
    status: Literal["planning", "executing", "waiting_permission", "done", "error"]
    progress: float
    errors: List[str]
    proposals: List[dict]


class AliasUpdate(TypedDict):
    canonical_id: str
    new_alias: str
    note: str


class ChunkExtraction(TypedDict):
    chunk_id: int
    new_characters: List[dict]
    updated_aliases: List[AliasUpdate]
    events: List[dict]
    world_mentions: List[str]
    manuscript_content: str
    notes: List[str]


class ChunkLogEntry(TypedDict):
    chunk_id: int
    total_chunks: int
    step: str
    new_characters: int
    updated_characters: int
    new_events: int
    new_world: int
    duration_ms: int
    excerpt: str        # first 200 chars of raw chunk content
    errors: List[str]
    timestamp: str      # ISO-8601


class ManuscriptChapter(TypedDict):
    chapter_id: str
    title: str
    chunk_ids: List[int]
    manuscript_content: str


class ImportCheckpoint(TypedDict):
    project_path: str
    source_file_path: str
    total_chunks: int
    completed_chunk_ids: List[int]
    entity_registry: dict
    chunk_extractions: List[ChunkExtraction]
    started_at: str
    last_updated: str


PromptProfile = Literal["fast", "balanced", "deep", "custom"]


class ToolOperatingSpec(TypedDict, total=False):
    """Soft orchestration parameters planned before W1 supervisor execution."""
    min_characters_per_chapter: float
    event_density_target: float
    max_canonical_events_per_chapter: int
    world_category_policy: Literal["named_only", "boundary_guarded", "full_attributes"]
    language_policy: Literal["preserve_source", "normalize_to_source", "allow_mixed"]
    rerun_budget: int
    judge_pass_threshold: float
    chapters_per_window_min: int
    chapters_per_window_max: int
    timeline_topology_target: Literal["flat", "branched", "full_dag"]
    orchestrator_enabled: bool
    supervisor_enabled: bool
    max_world_entities_per_chapter: int
    thematic_rerun_wave_cap: int
    acceptable_floor_fraction: float   # fraction of expected_min below which needs_targeted_repair
    require_protagonist_coverage: bool  # whether protagonist_list must be fully covered


class ConvergeTarget(TypedDict, total=False):
    """Expected coverage targets used by the deterministic judge pass."""
    expected_min_characters: int
    expected_min_events: int
    expected_max_canonical_events: int
    expected_min_world_entities: int
    expected_language: str
    expected_timeline_topology: Literal["flat", "branched", "full_dag"]
    protagonist_list: List[str]          # canonical names that must appear; missing → needs_targeted_repair
    acceptable_min_characters: int       # floor below expected_min; between floor and target → acceptable_with_warnings
    acceptable_min_events: int           # same floor logic for events


class ImportGranularityProfile(TypedDict, total=False):
    """Source-adaptive granularity constraints selected before extraction begins."""
    profile_name: Literal["coarse_webnovel", "balanced_novel", "fine_short_story", "custom"]
    min_characters_per_chapter: float
    acceptable_floor_fraction: float     # e.g. 0.80 → 80% of expected is acceptable (no rerun)
    min_events_per_chapter: float
    rerun_on_character_gap: bool         # if False: gap below floor → acceptable_with_warnings, no rerun
    max_world_entities_per_chapter: int
    character_granularity: Literal["major_only", "named_only", "all"]
    event_density: Literal["arc_level", "chapter_level", "scene_level"]
    world_density: Literal["named_only", "structural", "full_lore"]
    relationship_depth: Literal["core", "recurring", "dense"]


class SourceProfile(TypedDict, total=False):
    """Deterministic metadata about a manuscript source, computed before LLM extraction."""
    chapter_count: int
    source_language: str
    avg_chars_per_chapter: float
    total_chars: int
    estimated_source_type: Literal["coarse_webnovel", "balanced_novel", "fine_short_story"]
    dialogue_density_hint: Literal["low", "medium", "high"]
    named_entity_density_hint: Literal["sparse", "moderate", "dense"]
    recommended_granularity_profile: Literal["coarse_webnovel", "balanced_novel", "fine_short_story"]
    confidence: float
    evidence: List[str]


class ImportPlanToolStep(TypedDict, total=False):
    """One schema-validated tool step in an import plan."""
    tool: str
    enabled: bool
    order: int
    prompt_domain: str
    prompt_granularity: str
    rerun_allowed: bool
    rationale: str


class ImportPlan(TypedDict, total=False):
    """Schema-first import plan used by the deterministic planner and future LLM planners."""
    plan_version: str
    planner_kind: Literal["deterministic_rules", "llm_proposed"]
    source_type: Literal["coarse_webnovel", "balanced_novel", "fine_short_story", "custom"]
    prompt_profile: str
    source_language: str
    chapter_count: int
    granularity_profile: ImportGranularityProfile
    window_strategy: Dict[str, Any]
    tools: List[ImportPlanToolStep]
    prompt_policy: Dict[str, Any]
    cost_policy: Dict[str, Any]
    safety: Dict[str, Any]


class PlannerProposalToolOverride(TypedDict, total=False):
    """A tool-level override a planner may propose. Only safe fields are accepted."""
    tool: str               # must be in _KNOWN_TOOLS; validated by validate_planner_proposal
    prompt_granularity: str  # must be in per-tool allowlist — NOT raw prompt text
    rerun_allowed: bool


class PlannerProposal(TypedDict, total=False):
    """Structured proposal from an LLM/RAG planner.

    This is the ONLY channel through which a future LLM planner may influence W1 execution.
    Unknown top-level keys are rejected by validate_planner_proposal().
    The planner may propose; the validator decides; the executor runs deterministically.
    """
    planner_kind: Literal["deterministic_rules", "llm_proposed"]
    source_profile: SourceProfile
    proposed_source_type: Literal["coarse_webnovel", "balanced_novel", "fine_short_story", "custom"]
    proposed_granularity_profile: ImportGranularityProfile  # may be partial; merged with deterministic base
    proposed_window_strategy: Dict[str, Any]               # only known safe keys accepted
    proposed_tool_overrides: List[PlannerProposalToolOverride]
    prompt_variant_preferences: Dict[str, str]             # tool_name → variant_key (allowlist enforced)
    rationale: str                                         # free text; audit only, never executed
    confidence: float                                      # 0.0–1.0
    safety_notes: List[str]                                # audit only, never executed
    prompt_policy_patch: "PromptPolicyPatch"               # optional knob-only patch; validated, not yet applied


class PromptPolicyPatch(TypedDict, total=False):
    """Bounded knob-only patch for prompt behaviour. No raw prompt text allowed.

    This is validated by validate_prompt_policy_patch() in planner.py.
    Application to prompt templates is deferred to a future session.
    """
    emphasize_existing_timeline_topology: bool
    require_source_provenance: bool
    prefer_canonical_events: bool
    suppress_minor_npcs: bool
    relationship_evidence_required: bool
    world_boundary_strictness: Literal["low", "medium", "high"]


class ImportResultClassification(TypedDict, total=False):
    """Four-tier verdict emitted by judge_import. Replaces binary passed/failed."""
    verdict: Literal["pass", "acceptable_with_warnings", "needs_targeted_repair", "hard_fail"]
    warnings: List[str]
    hard_fail_reason: str
    protagonist_coverage: Dict[str, bool]  # {canonical_name: found}
    character_gap: int                     # expected_min_characters - actual (negative = surplus)
    event_gap: int                         # expected_min_events - actual


class ThematicRerunRequest(TypedDict, total=False):
    """A bounded orchestrator request to repair one quality theme."""
    theme: Literal[
        "character_undercoverage",
        "timeline_undercoverage",
        "world_boundary",
        "language_mismatch",
    ]
    target_windows: List[str]
    reason: str
    parameter_overrides: Dict[str, Any]
    expected_repair: str


class JudgeArtifact(TypedDict, total=False):
    """Deterministic post-QA assessment that may request thematic reruns."""
    score: float
    passed: bool
    result_status: Literal["passed", "acceptable_with_warnings", "needs_review", "failed", "budget_exhausted"]
    failed_gates: List[str]
    thematic_rerun_requests: List[ThematicRerunRequest]
    iteration: int
    metrics_snapshot: dict
    rationale: str
    rerun_cap_reached: bool
    artifact_paths: Dict[str, str]


class ImportRunManifest(TypedDict, total=False):
    import_run_id: str
    source_file_path: str
    source_hash: str
    import_mode: Literal["import_content_only", "import_all"]
    prompt_profile: PromptProfile
    model: str
    created_at: str
    segment_count: int
    artifact_dir: str
    segments: List[dict]
    project_structure_digest: dict
    prompt_window_budget: dict
    prompt_windows: List[dict]
    artifact_paths: Dict[str, str]


class EvidenceCard(TypedDict, total=False):
    id: str
    kind: Literal["character", "event", "world", "relationship", "scene"]
    source_chunk_id: int
    source_segment_id: str
    source_span: dict
    summary: str
    candidate_names: List[str]
    candidate_ids: List[str]
    temporal_hint: str
    location_hint: str
    confidence: float
    uncertainty: str
    raw: dict


class ReducerArtifact(TypedDict, total=False):
    import_run_id: str
    existing_matches: dict
    duplicate_candidates: List[dict]
    dependency_edges: List[dict]
    skipped_existing: List[dict]
    warnings: List[str]


class TimelineArchitectureArtifact(TypedDict, total=False):
    import_run_id: str
    root_branch_id: str
    branches: List[dict]
    canonical_events: List[dict]
    event_classifications: List[dict]
    discarded_duplicates: List[dict]
    scene_beats: List[dict]
    background_references: List[dict]
    fork_merge_anchors: List[dict]
    density_policy: dict
    layout_hints: dict
    warnings: List[str]


class CrossValidationArtifact(TypedDict, total=False):
    import_run_id: str
    duplicate_characters: List[dict]
    duplicate_events: List[dict]
    missing_major_characters: List[dict]
    suspicious_groups: List[dict]
    contradictory_aliases: List[dict]
    event_merge_recommendations: List[dict]
    warnings: List[str]


class ImportReviewReport(TypedDict, total=False):
    import_run_id: str
    status: Literal["pass", "warning", "fail"]
    warnings: List[str]
    errors: List[str]
    proposal_counts: Dict[str, int]
    safe_accept_ids: List[str]
    blocked_ids: List[str]
    failed_chunks: List[dict]
    model: str
    prompt_profile: PromptProfile
    artifact_paths: Dict[str, str]
    duplicate_merges: List[dict]
    low_confidence_items: List[dict]


class ProjectStructureDigest(TypedDict, total=False):
    import_run_id: str
    artifact_path: str
    content: str
    estimated_tokens: int
    counts: Dict[str, int]


class PromptWindow(TypedDict, total=False):
    id: str
    chunk_ids: List[int]
    chapter_range: str
    text: str
    source_blocks: List[dict]
    estimated_tokens: int
    total_token_budget: int
    source_budget_tokens: int
    source_token_estimate: int
    source_chars: int
    digest_token_estimate: int
    validation_token_estimate: int
    schema_policy_reserve_tokens: int
    target_fill_ratio: float
    fill_ratio: float
    split_reason: str
    source_span: dict
    output_token_budget: int  # Supervisor: estimated max output tokens for this window


class ImportProfileConfig(TypedDict, total=False):
    """Multi-dimensional replacement for the flat PromptProfile string."""
    character_granularity: Literal["major_only", "named_only", "all"]
    event_density: Literal["arc_level", "chapter_level", "scene_level"]
    world_strictness: Literal["named_only", "with_description", "full_attributes"]
    timeline_topology_depth: Literal["flat", "branched", "full_dag"]
    validation_strictness: Literal["off", "per_window", "per_arc"]
    input_window_budget: int   # Max source tokens per window
    output_token_budget: int   # Max expected output tokens per window
    max_rerun_iterations: int  # Hard cap on supervisor reruns per window
    chapters_per_window: int   # Primary windowing constraint


class SupervisorDecision(TypedDict):
    """One recorded decision made by the supervisor policy loop."""
    iteration: int
    stage: str
    tool_called: str
    reason: str
    metrics_before: dict
    metrics_after: dict
    action: Literal["proceed", "rerun", "repair", "skip"]
    rerun_targets: List[str]
    timestamp: str


class WindowExtractionMetrics(TypedDict):
    """Per-window quality metrics produced by extract_window and cross_validate_window."""
    window_id: str
    chapter_count: int
    char_count_extracted: int
    event_count_extracted: int
    world_count_extracted: int
    failed_prompts: List[str]
    confidence_distribution: dict
    missing_majors_count: int
    duplicate_count: int
    rerun_count: int
    gate_passed: bool


class ImportState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    source_file_path: str
    import_mode: Literal["import_content_only", "import_all"]
    import_run_id: str
    prompt_profile: PromptProfile
    source_language: str  # ISO 639-1 code detected from source text, e.g. "zh" or "en"
    context: dict
    chunks: List["Chunk"]
    import_run_manifest: ImportRunManifest
    evidence_cards: List[EvidenceCard]
    reducer_artifact: ReducerArtifact
    timeline_architecture: TimelineArchitectureArtifact
    cross_validation: CrossValidationArtifact
    import_review_report: ImportReviewReport
    project_structure_digest: ProjectStructureDigest
    prompt_windows: List[PromptWindow]
    entity_registry: dict
    chunk_extractions: List[ChunkExtraction]
    # Per-chunk raw relationship candidates (resolved post-loop)
    raw_relationships: List[dict]
    # Post-synthesis entities
    relationships: List[dict]
    character_tags: List[dict]
    world_settings: dict
    timeline_branches: List[dict]
    world_containers: List[dict]
    manuscript_chapters: List[ManuscriptChapter]
    proposals: List[dict]
    checkpoint_path: str
    progress: float
    errors: List[str]
    status: Literal["running", "done", "error", "cancelled"]


# Canonical profile configurations for the supervisor path.
PROFILE_CONFIGS: "Dict[str, ImportProfileConfig]" = {
    "fast": {
        "character_granularity": "major_only",
        "event_density": "arc_level",
        "world_strictness": "named_only",
        "timeline_topology_depth": "flat",
        "validation_strictness": "off",
        "input_window_budget": 64_000,
        "output_token_budget": 3000,
        "max_rerun_iterations": 1,
        "chapters_per_window": 20,
    },
    "balanced": {
        "character_granularity": "named_only",
        "event_density": "chapter_level",
        "world_strictness": "with_description",
        "timeline_topology_depth": "branched",
        "validation_strictness": "per_window",
        "input_window_budget": 48_000,
        "output_token_budget": 3000,
        "max_rerun_iterations": 2,
        "chapters_per_window": 12,
    },
    "deep": {
        "character_granularity": "all",
        "event_density": "chapter_level",
        "world_strictness": "full_attributes",
        "timeline_topology_depth": "full_dag",
        "validation_strictness": "per_window",
        "input_window_budget": 32_000,
        "output_token_budget": 3000,
        "max_rerun_iterations": 2,
        "chapters_per_window": 8,
    },
    "custom": {
        "character_granularity": "all",
        "event_density": "scene_level",
        "world_strictness": "full_attributes",
        "timeline_topology_depth": "full_dag",
        "validation_strictness": "per_arc",
        "input_window_budget": 24_000,
        "output_token_budget": 3000,
        "max_rerun_iterations": 3,
        "chapters_per_window": 6,
    },
}


_TOS_DEFAULTS: "Dict[str, ToolOperatingSpec]" = {
    "fast": {
        "min_characters_per_chapter": 0.5,
        "event_density_target": 0.5,
        "max_canonical_events_per_chapter": 2,
        "world_category_policy": "named_only",
        "language_policy": "preserve_source",
        "rerun_budget": 0,
        "judge_pass_threshold": 0.70,
        "chapters_per_window_min": 10,
        "chapters_per_window_max": 20,
        "timeline_topology_target": "flat",
        "orchestrator_enabled": False,
        "supervisor_enabled": False,
        "max_world_entities_per_chapter": 3,
        "thematic_rerun_wave_cap": 0,
    },
    "balanced": {
        "min_characters_per_chapter": 0.75,
        "event_density_target": 0.75,
        "max_canonical_events_per_chapter": 3,
        "world_category_policy": "boundary_guarded",
        "language_policy": "preserve_source",
        "rerun_budget": 1,
        "judge_pass_threshold": 0.78,
        "chapters_per_window_min": 6,
        "chapters_per_window_max": 12,
        "timeline_topology_target": "branched",
        "orchestrator_enabled": False,
        "supervisor_enabled": False,
        "max_world_entities_per_chapter": 4,
        "thematic_rerun_wave_cap": 1,
    },
    "deep": {
        "min_characters_per_chapter": 1.5,
        "event_density_target": 1.25,
        "max_canonical_events_per_chapter": 4,
        "world_category_policy": "full_attributes",
        "language_policy": "normalize_to_source",
        "rerun_budget": 2,
        "judge_pass_threshold": 0.85,
        "chapters_per_window_min": 3,
        "chapters_per_window_max": 8,
        "timeline_topology_target": "full_dag",
        "orchestrator_enabled": True,
        "supervisor_enabled": True,
        "max_world_entities_per_chapter": 5,
        "thematic_rerun_wave_cap": 1,
    },
    "custom": {
        "min_characters_per_chapter": 1.5,
        "event_density_target": 1.5,
        "max_canonical_events_per_chapter": 5,
        "world_category_policy": "full_attributes",
        "language_policy": "normalize_to_source",
        "rerun_budget": 3,
        "judge_pass_threshold": 0.85,
        "chapters_per_window_min": 2,
        "chapters_per_window_max": 6,
        "timeline_topology_target": "full_dag",
        "orchestrator_enabled": True,
        "supervisor_enabled": True,
        "max_world_entities_per_chapter": 5,
        "thematic_rerun_wave_cap": 2,
    },
}


def plan_tool_operating_spec(
    prompt_profile: str = "balanced",
    source_language: str = "en",
    chapter_count: int = 1,
    overrides: Optional[Dict[str, Any]] = None,
    use_supervisor: Optional[bool] = None,
    use_orchestrator: Optional[bool] = None,
) -> ToolOperatingSpec:
    """Derive deterministic W1 supervisor soft parameters from profile/config."""
    profile = prompt_profile if prompt_profile in _TOS_DEFAULTS else "balanced"
    chapter_count = max(int(chapter_count or 1), 1)
    spec: ToolOperatingSpec = dict(_TOS_DEFAULTS[profile])  # type: ignore[assignment]

    if use_supervisor is True:
        spec["supervisor_enabled"] = True
    if use_orchestrator is True:
        spec["orchestrator_enabled"] = True
        spec["supervisor_enabled"] = True

    if source_language and source_language != "en":
        spec["language_policy"] = "normalize_to_source"

    # Keep very short imports from over-windowing even in deep/custom mode.
    max_window = int(spec.get("chapters_per_window_max", chapter_count))
    spec["chapters_per_window_max"] = min(max(max_window, 1), chapter_count or max_window)
    spec["chapters_per_window_min"] = min(
        int(spec.get("chapters_per_window_min", 1)),
        int(spec["chapters_per_window_max"]),
    )

    for key, value in (overrides or {}).items():
        if key in ToolOperatingSpec.__annotations__:
            spec[key] = value

    # UI Custom mode speaks in user-facing profile terms. Normalize those into
    # the deterministic TOS contract so sent controls actually affect runtime.
    if overrides:
        if "max_chapters_per_window" in overrides and "chapters_per_window_max" not in overrides:
            spec["chapters_per_window_max"] = int(overrides["max_chapters_per_window"])
        if "event_density" in overrides and "event_density_target" not in overrides:
            density = str(overrides.get("event_density") or "")
            spec["event_density_target"] = {
                "arc_level": 0.5,
                "chapter_level": 1.25,
                "scene_level": 1.75,
            }.get(density, float(spec.get("event_density_target", 0.75)))
        if "world_strictness" in overrides and "world_category_policy" not in overrides:
            strictness = str(overrides.get("world_strictness") or "")
            spec["world_category_policy"] = {
                "named_only": "named_only",
                "with_description": "boundary_guarded",
                "full_attributes": "full_attributes",
            }.get(strictness, spec.get("world_category_policy", "boundary_guarded"))
        if "timeline_topology_depth" in overrides and "timeline_topology_target" not in overrides:
            topology = str(overrides.get("timeline_topology_depth") or "")
            spec["timeline_topology_target"] = {
                "flat": "flat",
                "branched": "branched",
                "full_dag": "full_dag",
            }.get(topology, spec.get("timeline_topology_target", "branched"))

    spec["rerun_budget"] = max(int(spec.get("rerun_budget", 0)), 0)
    spec["judge_pass_threshold"] = min(max(float(spec.get("judge_pass_threshold", 0.8)), 0.0), 1.0)
    spec["chapters_per_window_max"] = max(int(spec.get("chapters_per_window_max", 1)), 1)
    spec["chapters_per_window_min"] = min(
        max(int(spec.get("chapters_per_window_min", 1)), 1),
        int(spec["chapters_per_window_max"]),
    )
    return spec


def plan_converge_target(
    tool_operating_spec: ToolOperatingSpec,
    source_language: str = "en",
    chapter_count: int = 1,
    granularity_profile: "Optional[ImportGranularityProfile]" = None,
) -> ConvergeTarget:
    """Build deterministic convergence targets from the active tool spec.

    When granularity_profile is provided, character and event targets are derived
    from the profile rather than TOS defaults. All other fields come from TOS.
    Omitting granularity_profile produces identical output to the 3-arg call.
    """
    chapter_count = max(int(chapter_count or 1), 1)
    min_chars = float(tool_operating_spec.get("min_characters_per_chapter", 0.75))
    event_density = float(tool_operating_spec.get("event_density_target", 0.75))
    max_events = int(tool_operating_spec.get("max_canonical_events_per_chapter", 3))

    expected_min_characters = max(1, math.ceil(chapter_count * min_chars))
    expected_min_events = max(1, math.ceil(chapter_count * event_density))

    target: ConvergeTarget = {
        "expected_min_characters": expected_min_characters,
        "expected_min_events": expected_min_events,
        "expected_max_canonical_events": max(1, chapter_count * max_events),
        "expected_min_world_entities": max(1, math.ceil(chapter_count * 0.4)),
        "expected_language": source_language or "en",
        "expected_timeline_topology": tool_operating_spec.get("timeline_topology_target", "branched"),
    }

    if granularity_profile is not None:
        profile_min_chars = float(granularity_profile.get("min_characters_per_chapter", min_chars))
        profile_floor_frac = float(granularity_profile.get("acceptable_floor_fraction", 1.0))
        profile_min_events = float(granularity_profile.get("min_events_per_chapter", event_density))

        profile_expected_chars = max(1, int(profile_min_chars * chapter_count))
        profile_expected_events = max(1, int(profile_min_events * chapter_count))

        target["expected_min_characters"] = profile_expected_chars
        target["acceptable_min_characters"] = max(1, int(profile_expected_chars * profile_floor_frac))
        target["expected_min_events"] = profile_expected_events
        target["acceptable_min_events"] = max(1, int(profile_expected_events * profile_floor_frac))

    return target


_WEBNOVEL_LANGUAGES = frozenset({"zh", "ko", "ja"})

_GRANULARITY_DEFAULTS: Dict[str, ImportGranularityProfile] = {
    "coarse_webnovel": {
        "profile_name": "coarse_webnovel",
        "min_characters_per_chapter": 1.0,
        "acceptable_floor_fraction": 0.80,
        "min_events_per_chapter": 1.0,
        "rerun_on_character_gap": False,
        "max_world_entities_per_chapter": 4,
        "character_granularity": "named_only",
        "event_density": "chapter_level",
        "world_density": "named_only",
        "relationship_depth": "core",
    },
    "balanced_novel": {
        "profile_name": "balanced_novel",
        "min_characters_per_chapter": 1.2,
        "acceptable_floor_fraction": 0.85,
        "min_events_per_chapter": 1.2,
        "rerun_on_character_gap": True,
        "max_world_entities_per_chapter": 5,
        "character_granularity": "named_only",
        "event_density": "chapter_level",
        "world_density": "structural",
        "relationship_depth": "recurring",
    },
    "fine_short_story": {
        "profile_name": "fine_short_story",
        "min_characters_per_chapter": 1.5,
        "acceptable_floor_fraction": 0.90,
        "min_events_per_chapter": 1.5,
        "rerun_on_character_gap": True,
        "max_world_entities_per_chapter": 5,
        "character_granularity": "all",
        "event_density": "scene_level",
        "world_density": "full_lore",
        "relationship_depth": "dense",
    },
}

# Variant for large fast runs (lower world cap)
_GRANULARITY_DEFAULTS["coarse_fast"] = {
    **_GRANULARITY_DEFAULTS["coarse_webnovel"],
    "profile_name": "coarse_webnovel",
    "min_characters_per_chapter": 0.5,
    "acceptable_floor_fraction": 0.70,
    "min_events_per_chapter": 0.5,
    "rerun_on_character_gap": False,
    "max_world_entities_per_chapter": 3,
    "event_density": "arc_level",
    "world_density": "named_only",
    "relationship_depth": "core",
}


def select_granularity_profile(
    chapter_count: int,
    source_language: str,
    prompt_profile: str,
    import_mode: str = "import_all",
) -> ImportGranularityProfile:
    """Select a source-adaptive granularity profile before extraction begins.

    Decision rules (first match wins):
    1. fast profile → coarse (low token budget)
    2. Long CJK source (>30 chapters) → coarse_webnovel regardless of prompt_profile
    3. Long non-CJK source (>30 chapters) → balanced_novel
    4. Medium source (15–30 chapters) → balanced_novel
    5. Short source (≤15 chapters) → fine_short_story
    6. Default (custom without override, or any unmatched) → balanced_novel

    Note: prompt_profile="custom" does NOT force fine_short_story; only short
    chapter_count (≤15) triggers fine. This avoids over-extraction on long webnovels
    where users choose "custom" for other reasons.
    """
    chapter_count = max(int(chapter_count or 1), 1)
    lang = (source_language or "en").lower().split("-")[0]

    if prompt_profile == "fast":
        return dict(_GRANULARITY_DEFAULTS["coarse_fast"])  # type: ignore[return-value]

    if chapter_count > 30 and lang in _WEBNOVEL_LANGUAGES:
        return dict(_GRANULARITY_DEFAULTS["coarse_webnovel"])  # type: ignore[return-value]

    if chapter_count > 30:
        profile = dict(_GRANULARITY_DEFAULTS["balanced_novel"])
        # Long sources: relax floor slightly and disable character gap rerun
        profile["min_characters_per_chapter"] = 1.0
        profile["acceptable_floor_fraction"] = 0.80
        profile["min_events_per_chapter"] = 1.0
        profile["rerun_on_character_gap"] = False
        profile["max_world_entities_per_chapter"] = 4
        return profile  # type: ignore[return-value]

    if chapter_count > 15:
        return dict(_GRANULARITY_DEFAULTS["balanced_novel"])  # type: ignore[return-value]

    if chapter_count <= 15:
        return dict(_GRANULARITY_DEFAULTS["fine_short_story"])  # type: ignore[return-value]

    # Default — catches custom profile without explicit granularity override
    return dict(_GRANULARITY_DEFAULTS["balanced_novel"])  # type: ignore[return-value]


def plan_import_pipeline(
    granularity_profile: ImportGranularityProfile,
    tool_operating_spec: ToolOperatingSpec,
    *,
    source_language: str = "en",
    prompt_profile: str = "balanced",
    chapter_count: int = 1,
) -> ImportPlan:
    """Build a schema-first W1 import plan from selected profile and TOS.

    This is intentionally deterministic: future LLM/RAG planners may propose the
    same schema, but execution should continue to validate against this shape
    rather than letting free-form text mutate the pipeline.
    """
    chapter_count = max(int(chapter_count or 1), 1)
    profile_name = granularity_profile.get("profile_name", "balanced_novel")
    chapters_per_window = int(tool_operating_spec.get("chapters_per_window_max", 1) or 1)
    rerun_budget = int(tool_operating_spec.get("rerun_budget", 0) or 0)
    wave_cap = int(tool_operating_spec.get("thematic_rerun_wave_cap", 0) or 0)
    tool_steps: List[ImportPlanToolStep] = [
        {
            "tool": "segment_manifest",
            "enabled": True,
            "order": 1,
            "rationale": "Build source windows before extraction.",
        },
        {
            "tool": "extract_character",
            "enabled": True,
            "order": 2,
            "prompt_domain": "character",
            "prompt_granularity": str(granularity_profile.get("character_granularity", "named_only")),
            "rerun_allowed": bool(granularity_profile.get("rerun_on_character_gap", True)),
            "rationale": "Extract character cards at the selected source granularity.",
        },
        {
            "tool": "extract_event",
            "enabled": True,
            "order": 3,
            "prompt_domain": "event",
            "prompt_granularity": str(granularity_profile.get("event_density", "chapter_level")),
            "rerun_allowed": True,
            "rationale": "Extract timeline candidates at the selected event density.",
        },
        {
            "tool": "extract_world",
            "enabled": True,
            "order": 4,
            "prompt_domain": "world",
            "prompt_granularity": str(granularity_profile.get("world_density", "structural")),
            "rerun_allowed": False,
            "rationale": "Extract world entities with deterministic boundary repair downstream.",
        },
        {
            "tool": "extract_relationship",
            "enabled": True,
            "order": 5,
            "prompt_domain": "relationship",
            "prompt_granularity": str(granularity_profile.get("relationship_depth", "recurring")),
            "rerun_allowed": False,
            "rationale": "Extract relationship evidence to support identity and topology.",
        },
        {
            "tool": "extract_scene_summary",
            "enabled": True,
            "order": 6,
            "prompt_domain": "scene",
            "prompt_granularity": "fixed",
            "rerun_allowed": False,
            "rationale": "Scene summaries remain fixed until a dedicated scene granularity profile exists.",
        },
        {
            "tool": "judge_import",
            "enabled": True,
            "order": 10,
            "rationale": "Apply deterministic convergence gates after reduce/repair/architect passes.",
        },
        {
            "tool": "reduce_entities",
            "enabled": True,
            "order": 7,
            "rationale": "Deduplicate and reconcile extracted entities across windows.",
        },
        {
            "tool": "minor_repair",
            "enabled": True,
            "order": 8,
            "rationale": "Apply deterministic language, grouping, and world/person boundary repairs.",
        },
        {
            "tool": "architect_timeline",
            "enabled": True,
            "order": 9,
            "rationale": "Build branch-aware timeline topology before judgment.",
        },
        {
            "tool": "proposal_write",
            "enabled": True,
            "order": 11,
            "rationale": "Write gated proposals and manuscript artifacts after convergence.",
        },
    ]
    tool_steps = sorted(tool_steps, key=lambda step: int(step.get("order", 0)))
    return {
        "plan_version": "w1-import-plan-v1",
        "planner_kind": "deterministic_rules",
        "source_type": profile_name,  # type: ignore[typeddict-item]
        "prompt_profile": prompt_profile,
        "source_language": source_language or "en",
        "chapter_count": chapter_count,
        "granularity_profile": dict(granularity_profile),  # type: ignore[typeddict-item]
        "window_strategy": {
            "strategy": "supervised_chapter_batching",
            "chapters_per_window_max": chapters_per_window,
            "late_window_cap_enabled": True,
            "parallel_window_batch_size": 3,
        },
        "tools": tool_steps,
        "prompt_policy": {
            "variant_dispatch": True,
            "dynamic_prompt_edits_allowed": False,
            "prompt_variants_source": "sidecar.prompts.w1_prompts",
        },
        "cost_policy": {
            "rerun_budget": rerun_budget,
            "thematic_rerun_wave_cap": wave_cap,
            "stop_on_api_402": True,
            "max_world_entities_per_chapter": int(
                granularity_profile.get(
                    "max_world_entities_per_chapter",
                    tool_operating_spec.get("max_world_entities_per_chapter", 4),
                )
            ),
        },
        "safety": {
            "schema_validated_plan": True,
            "proposal_gate_required": True,
            "llm_planner_can_propose_only": True,
        },
    }


_KNOWN_TOOLS: frozenset = frozenset({
    "segment_manifest",
    "extract_character",
    "extract_event",
    "extract_world",
    "extract_relationship",
    "extract_scene_summary",
    "reduce_entities",
    "minor_repair",
    "architect_timeline",
    "judge_import",
    "proposal_write",
})
_VALID_PLANNER_KINDS: frozenset = frozenset({"deterministic_rules", "llm_proposed"})
_VALID_SOURCE_TYPES: frozenset = frozenset({
    "coarse_webnovel", "balanced_novel", "fine_short_story", "custom"
})


def validate_import_plan(plan: ImportPlan) -> tuple[bool, list[str]]:
    """Validate a schema-first import plan against the W1 execution contract.

    Returns (True, []) for valid plans, (False, [error, ...]) otherwise.
    All checks run regardless of earlier failures — callers see the full picture.
    """
    errors: list[str] = []

    if plan.get("planner_kind") not in _VALID_PLANNER_KINDS:
        errors.append(f"unknown planner_kind: {plan.get('planner_kind')!r}")

    if plan.get("source_type") not in _VALID_SOURCE_TYPES:
        errors.append(f"unknown source_type: {plan.get('source_type')!r}")

    tools = plan.get("tools") or []
    if not tools:
        errors.append("plan.tools must be present and non-empty")
    else:
        present_enabled_tools: set = set()
        seen_orders: set = set()
        for i, step in enumerate(tools):
            for key in ("tool", "enabled", "order"):
                if key not in step:
                    errors.append(f"tool step[{i}] missing required key {key!r}")
            tool_name = step.get("tool")
            if tool_name is not None:
                if tool_name not in _KNOWN_TOOLS:
                    errors.append(f"unknown tool: {tool_name!r}")
                elif step.get("enabled") is True:
                    present_enabled_tools.add(tool_name)
            order = step.get("order")
            if order is not None:
                if order in seen_orders:
                    errors.append(f"duplicate order value: {order}")
                else:
                    seen_orders.add(order)
        missing_or_disabled = _KNOWN_TOOLS - present_enabled_tools
        if missing_or_disabled:
            errors.append(f"missing or disabled required tools: {sorted(missing_or_disabled)}")

    prompt_policy = plan.get("prompt_policy") or {}
    if prompt_policy.get("dynamic_prompt_edits_allowed") is not False:
        errors.append("prompt_policy.dynamic_prompt_edits_allowed must be False")

    cost_policy = plan.get("cost_policy") or {}
    if cost_policy.get("stop_on_api_402") is not True:
        errors.append("cost_policy.stop_on_api_402 must be True")

    safety = plan.get("safety") or {}
    if safety.get("proposal_gate_required") is not True:
        errors.append("safety.proposal_gate_required must be True")
    if safety.get("schema_validated_plan") is not True:
        errors.append("safety.schema_validated_plan must be True")
    if safety.get("llm_planner_can_propose_only") is not True:
        errors.append("safety.llm_planner_can_propose_only must be True")

    return len(errors) == 0, errors


def plan_orchestrator_targets(
    prompt_profile: str = "balanced",
    source_language: str = "en",
    chapter_count: int = 1,
    overrides: Optional[Dict[str, Any]] = None,
    use_supervisor: Optional[bool] = None,
    use_orchestrator: Optional[bool] = None,
) -> tuple[ToolOperatingSpec, ConvergeTarget]:
    """Return the planned ToolOperatingSpec and matching ConvergeTarget."""
    spec = plan_tool_operating_spec(
        prompt_profile=prompt_profile,
        source_language=source_language,
        chapter_count=chapter_count,
        overrides=overrides,
        use_supervisor=use_supervisor,
        use_orchestrator=use_orchestrator,
    )
    return spec, plan_converge_target(spec, source_language, chapter_count)


def _chunk_text(c: dict) -> str:
    return c.get("content") or c.get("manuscript_content") or c.get("raw_content") or ""


def analyze_source_profile(
    chunks: List["Chunk"],
    source_language: str = "en",
    prompt_profile: str = "balanced",
) -> "SourceProfile":
    """Deterministic source profiler — no LLM calls, no API.

    Classifies the manuscript source using the same chapter/language thresholds as
    select_granularity_profile(). The prompt_profile 'fast' override is intentionally
    omitted: this profiler is descriptive (what the source is), not prescriptive (how
    to extract it). Dialogue and named-entity density hints are heuristic estimates only.
    """
    chapter_count = len(chunks)
    if chapter_count == 0:
        return {
            "chapter_count": 0,
            "source_language": source_language or "en",
            "avg_chars_per_chapter": 0.0,
            "total_chars": 0,
            "estimated_source_type": "fine_short_story",
            "dialogue_density_hint": "low",
            "named_entity_density_hint": "sparse",
            "recommended_granularity_profile": "fine_short_story",
            "confidence": 0.5,
            "evidence": ["no chunks provided; defaulting to fine_short_story"],
        }  # type: ignore[return-value]

    lang = (source_language or "en").lower().split("-")[0]
    is_cjk = lang in _WEBNOVEL_LANGUAGES

    total_chars = sum(len(_chunk_text(c)) for c in chunks)
    avg_chars = round(total_chars / chapter_count, 1)

    evidence: List[str] = [f"{chapter_count} chapters detected"]

    if chapter_count <= 15:
        source_type: str = "fine_short_story"
        confidence = 0.90
        evidence.append("short source (<=15 chapters) → fine_short_story")
    elif chapter_count > 30 and is_cjk:
        source_type = "coarse_webnovel"
        confidence = 0.95
        evidence.append(f"long CJK source (>30 chapters, lang={lang}) → coarse_webnovel")
    elif chapter_count > 30:
        source_type = "balanced_novel"
        confidence = 0.85
        evidence.append("long non-CJK source (>30 chapters) → balanced_novel")
    else:
        source_type = "balanced_novel"
        confidence = 0.80
        evidence.append("medium source (16–30 chapters) → balanced_novel")

    # Dialogue density heuristic — advisory only, not a precise measurement
    dialogue_markers = 0
    for c in chunks:
        text = _chunk_text(c)
        dialogue_markers += (
            text.count("「")  # 「
            + text.count("」")  # 」
            + text.count("“")  # "
            + text.count("”")  # "
            + text.count('"')
        )
    dialogue_ratio = dialogue_markers / max(total_chars, 1)
    if dialogue_ratio > 0.05:
        dialogue_density: str = "high"
    elif dialogue_ratio > 0.02:
        dialogue_density = "medium"
    else:
        dialogue_density = "low"

    # Named entity density — missing entity_mentions treated as empty (not an error)
    total_mentions = sum(len(c.get("entity_mentions") or []) for c in chunks)
    avg_mentions = total_mentions / chapter_count
    if avg_mentions > 8:
        entity_density: str = "dense"
    elif avg_mentions >= 3:
        entity_density = "moderate"
    else:
        entity_density = "sparse"

    return {
        "chapter_count": chapter_count,
        "source_language": source_language or "en",
        "avg_chars_per_chapter": avg_chars,
        "total_chars": total_chars,
        "estimated_source_type": source_type,  # type: ignore[typeddict-item]
        "dialogue_density_hint": dialogue_density,  # type: ignore[typeddict-item]
        "named_entity_density_hint": entity_density,  # type: ignore[typeddict-item]
        "recommended_granularity_profile": source_type,  # type: ignore[typeddict-item]
        "confidence": confidence,
        "evidence": evidence,
    }  # type: ignore[return-value]


class ImportSupervisorState(TypedDict, total=False):
    """
    Extends ImportState with supervisor orchestration fields.

    All ImportState keys are valid here. The supervisor does NOT replace
    the LangGraph graph — it wraps it with a policy loop when use_supervisor=True.
    """
    # ── All ImportState fields (not redeclared) ──
    # project_path, workflow_id, source_file_path, import_mode, import_run_id,
    # prompt_profile, source_language, context, chunks, import_run_manifest, ...

    # ── Supervisor-only additions ──
    use_supervisor: bool
    profile_config: ImportProfileConfig
    supervisor_decisions: List[SupervisorDecision]
    current_stage: str
    window_metrics: dict        # {window_id: WindowExtractionMetrics}
    rerun_candidates: List[str]
    gate_failures: List[dict]   # [{gate, value, threshold, windows}]
    supervisor_iteration: int
    max_supervisor_iterations: int
    supervisor_log: List[str]
    minor_repair_log: List[str]
    tool_operating_spec: ToolOperatingSpec
    converge_target: ConvergeTarget
    judge_artifact: JudgeArtifact
    thematic_rerun_requests: List[ThematicRerunRequest]
    current_tool: str
    current_window: str
    chapter_range: str
    orchestrator_phase: str
    judge_score: float
    rerun_reason: str
    converge_status: Literal[
        "not_started", "planning", "planning_failed", "extracting",
        "judging", "rerunning", "passed", "acceptable_with_warnings",
        "failed", "hard_fail", "writing",
    ]
    budget_exhausted: bool      # True when API returned HTTP 402 — stops all reruns
    global_rerun_count: int     # Total rerun API calls dispatched this run
    import_granularity_profile: ImportGranularityProfile
    import_plan: ImportPlan
    import_plan_validation: Dict[str, Any]
    source_profile: SourceProfile
    planner_proposal: PlannerProposal
    planner_proposal_validation: Dict[str, Any]


class DiffItem(TypedDict):
    entity_type: str
    entity_id: str
    field_name: str
    before: Optional[str]
    after: Optional[str]
    change_type: Literal["create", "update", "delete"]


class ManuscriptSyncState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    mode: Literal["single_chapter", "post_import", "draft_only"]
    target_chapter_id: Optional[str]
    context: dict
    extracted_entities: List[dict]
    diff: List[dict]
    proposals: List[dict]
    progress: float
    errors: List[str]
    status: Literal["running", "done", "error"]


class WritingState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    scene_id: Optional[str]
    task: str
    context: dict
    active_todos: List[dict]
    metadata_style: Optional[str]
    metadata_chunks: List[dict]
    hitl_mode: str
    options: List[str]
    selected_option: Optional[int]
    output: str
    new_entities: List[dict]
    proposals: List[dict]
    progress: float
    errors: List[str]
    # Legacy fields (kept for backward compat)
    prompt: str
    status: str
    draft_text: str
    context_ids: List[str]


class ConsistencyIssue(TypedDict):
    issue_id: str
    type: Literal["timeline", "character", "world_rule", "item_tracking"]
    severity: Literal["HIGH", "MED", "LOW"]
    description: str
    scene_id: str
    entity_ids: List[str]
    suggested_fix: Optional[str]


class ConsistencyState(TypedDict):
    project_path: str
    workflow_id: str
    scope: Literal["scene", "chapter", "full"]
    target_id: str
    context: dict
    issues: List[ConsistencyIssue]
    severity_counts: Dict[str, int]
    proposals: List[dict]
    progress: float
    errors: List[str]
    status: Literal["running", "done", "error"]


class EngineOutput(TypedDict):
    engine_type: str
    summary: str
    details: List[str]
    confidence: float


class SimulationState(TypedDict):
    project_path: str
    workflow_id: str
    scenario_variable: str
    affected_chapter_ids: List[str]
    engines_selected: List[str]
    context: dict
    engine_results: Dict[str, EngineOutput]
    report_markdown: str
    progress: float
    errors: List[str]
    status: Literal["running", "done", "error"]


class PersonaProfile(TypedDict):
    persona_id: str
    name: str
    type: Literal["scholar", "shipper", "casual", "custom"]
    traits: List[str]
    focus_areas: List[str]
    metadata_reference_id: Optional[str]


class FeedbackItem(TypedDict):
    chapter_id: str
    dimension: Literal["engagement", "pacing", "character", "logic", "world"]
    score: int
    comment: str
    excerpt_reference: Optional[str]


class BetaReaderState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    persona_id: str
    persona: PersonaProfile
    target_chapter_ids: List[str]
    chunks: List["Chunk"]
    feedback_items: List[FeedbackItem]
    report_markdown: str
    progress: float
    errors: List[str]
    status: Literal["running", "done", "error"]
    context: dict
    # Internal pipeline state
    _chapter_text: str
    _style_context: str
    _avg_scores: Dict[str, float]


class StyleProfile(TypedDict):
    avg_sentence_length: float
    dialogue_ratio: float
    pov_style: str
    pacing_descriptor: str
    vocabulary_notes: List[str]


class KnowledgeProfile(TypedDict):
    key_facts: List[str]
    named_entities: List[str]
    domain_tags: List[str]


class MetadataIngestionState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    source_file_path: str
    file_type: Literal["novel", "script", "news", "essay", "draft", "other"]
    file_id: str
    context: dict
    chunks: List["Chunk"]
    style_profile: StyleProfile
    knowledge_profile: KnowledgeProfile
    vector_store_updated: bool
    progress: float
    errors: List[str]
    status: Literal["running", "done", "error"]


class ChunkConfig(TypedDict):
    strategy: Literal["chapter", "paragraph", "fixed"]
    chunk_size: int
    overlap: int


class Chunk(TypedDict):
    chunk_id: int
    char_start: int
    char_end: int
    content: str
    chapter_hint: Optional[str]
    entity_mentions: List[str]
