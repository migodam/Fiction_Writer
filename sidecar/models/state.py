from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict


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
    discarded_duplicates: List[dict]
    density_policy: dict
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


class ImportState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    source_file_path: str
    import_mode: Literal["import_content_only", "import_all"]
    import_run_id: str
    prompt_profile: PromptProfile
    context: dict
    chunks: List["Chunk"]
    import_run_manifest: ImportRunManifest
    evidence_cards: List[EvidenceCard]
    reducer_artifact: ReducerArtifact
    timeline_architecture: TimelineArchitectureArtifact
    cross_validation: CrossValidationArtifact
    import_review_report: ImportReviewReport
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
