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


class ImportState(TypedDict, total=False):
    project_path: str
    workflow_id: str
    source_file_path: str
    import_mode: Literal["import_content_only", "import_all"]
    context: dict
    chunks: List["Chunk"]
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
