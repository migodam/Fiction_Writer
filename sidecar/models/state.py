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


class ConvergeTarget(TypedDict, total=False):
    """Expected coverage targets used by the deterministic judge pass."""
    expected_min_characters: int
    expected_min_events: int
    expected_max_canonical_events: int
    expected_min_world_entities: int
    expected_language: str
    expected_timeline_topology: Literal["flat", "branched", "full_dag"]


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
    failed_gates: List[str]
    thematic_rerun_requests: List[ThematicRerunRequest]
    iteration: int
    metrics_snapshot: dict
    rationale: str
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
) -> ConvergeTarget:
    """Build deterministic convergence targets from the active tool spec."""
    chapter_count = max(int(chapter_count or 1), 1)
    min_chars = float(tool_operating_spec.get("min_characters_per_chapter", 0.75))
    event_density = float(tool_operating_spec.get("event_density_target", 0.75))
    max_events = int(tool_operating_spec.get("max_canonical_events_per_chapter", 3))
    return {
        "expected_min_characters": max(1, math.ceil(chapter_count * min_chars)),
        "expected_min_events": max(1, math.ceil(chapter_count * event_density)),
        "expected_max_canonical_events": max(1, chapter_count * max_events),
        "expected_min_world_entities": max(1, math.ceil(chapter_count * 0.4)),
        "expected_language": source_language or "en",
        "expected_timeline_topology": tool_operating_spec.get("timeline_topology_target", "branched"),
    }


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
    converge_status: Literal["not_started", "planning", "extracting", "judging", "rerunning", "passed", "failed", "writing"]


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
