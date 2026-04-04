from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict


class OrchestratorStep(TypedDict):
    step_id: str
    workflow_id: str
    title: str
    status: Literal["pending", "running", "waiting_permission", "completed", "failed", "cancelled"]
    config: Dict[str, object]
    requires_permission: bool


class PermissionRequest(TypedDict):
    step_id: str
    description: str
    scope: List[str]
    status: Literal["pending", "granted", "denied"]


class StepResult(TypedDict):
    step_id: str
    status: Literal["completed", "failed", "cancelled"]
    summary: str
    output: Dict[str, object]


class OrchestratorState(TypedDict):
    request_id: str
    project_path: str
    goal: str
    status: Literal["idle", "planning", "running", "waiting_permission", "completed", "failed", "cancelled"]
    steps: List[OrchestratorStep]
    pending_permission: Optional[PermissionRequest]
    results: List[StepResult]
    started_at: Optional[str]
    updated_at: Optional[str]


class AliasUpdate(TypedDict):
    alias: str
    canonical_id: str
    confidence: float


class ChunkExtraction(TypedDict):
    chunk_id: int
    characters: List[str]
    events: List[str]
    locations: List[str]
    alias_updates: List[AliasUpdate]


class ImportState(TypedDict):
    project_path: str
    source_path: str
    status: Literal["queued", "running", "completed", "failed"]
    chunks: List["Chunk"]
    extractions: List[ChunkExtraction]
    imported_entities: Dict[str, List[str]]
    errors: List[str]


class DiffItem(TypedDict):
    entity_type: str
    entity_id: str
    field_name: str
    before: Optional[str]
    after: Optional[str]
    change_type: Literal["create", "update", "delete"]


class ManuscriptSyncState(TypedDict):
    project_path: str
    chapter_id: Optional[str]
    status: Literal["queued", "running", "completed", "failed"]
    diff: List[DiffItem]
    synced_files: List[str]
    errors: List[str]


class WritingState(TypedDict):
    project_path: str
    scene_id: Optional[str]
    prompt: str
    status: Literal["queued", "running", "completed", "failed"]
    draft_text: str
    context_ids: List[str]
    proposals: List[str]


class ConsistencyIssue(TypedDict):
    issue_id: str
    category: Literal["timeline", "character", "world", "style"]
    severity: Literal["low", "medium", "high"]
    description: str
    related_entities: List[str]
    suggested_fix: Optional[str]


class ConsistencyState(TypedDict):
    project_path: str
    scope: Literal["scene", "chapter", "project"]
    status: Literal["queued", "running", "completed", "failed"]
    issues: List[ConsistencyIssue]
    checked_ids: List[str]
    errors: List[str]


class EngineOutput(TypedDict):
    engine_name: str
    status: Literal["queued", "running", "completed", "failed"]
    summary: str
    score: float


class SimulationReport(TypedDict):
    scenario_id: str
    overall_status: Literal["completed", "failed"]
    summary: str
    outputs: List[EngineOutput]
    recommendations: List[str]


class SimulationState(TypedDict):
    project_path: str
    scenario_prompt: str
    status: Literal["queued", "running", "completed", "failed"]
    engine_outputs: List[EngineOutput]
    report: Optional[SimulationReport]
    errors: List[str]


class PersonaProfile(TypedDict):
    persona_id: str
    name: str
    archetype: str
    traits: List[str]
    focus_areas: List[str]


class FeedbackItem(TypedDict):
    item_id: str
    chapter_id: str
    category: Literal["engagement", "pacing", "clarity", "character", "world"]
    sentiment: Literal["positive", "neutral", "negative"]
    comment: str


class BetaReaderReport(TypedDict):
    report_id: str
    status: Literal["completed", "failed"]
    summary: str
    persona: PersonaProfile
    feedback: List[FeedbackItem]


class BetaReaderState(TypedDict):
    project_path: str
    persona: PersonaProfile
    status: Literal["queued", "running", "completed", "failed"]
    target_chapters: List[str]
    feedback: List[FeedbackItem]
    report: Optional[BetaReaderReport]


class StyleProfile(TypedDict):
    tone: str
    pov: str
    tense: str
    motifs: List[str]
    banned_phrases: List[str]


class KnowledgeProfile(TypedDict):
    topics: List[str]
    key_entities: List[str]
    canonical_facts: List[str]
    source_files: List[str]


class MetadataIngestionState(TypedDict):
    project_path: str
    file_id: str
    status: Literal["queued", "running", "completed", "failed"]
    style_profile: Optional[StyleProfile]
    knowledge_profile: Optional[KnowledgeProfile]
    chunk_count: int
    errors: List[str]


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
