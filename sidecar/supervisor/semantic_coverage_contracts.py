"""JSON-serializable contracts for the read-only W1 semantic coverage compiler."""
from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


ChunkTruth = Literal["semantic_complete", "manuscript_only", "failed", "unknown_outcome"]
DomainStatus = Literal["complete", "empty_valid", "failed", "unknown"]
FindingSeverity = Literal["blocking", "warning", "info"]


class SemanticFinding(TypedDict):
    code: str
    severity: FindingSeverity
    entity_ids: list[str]
    chapter_ids: list[str]
    evidence_refs: list[str]
    message: str
    repair_action: Literal["merge", "quarantine", "demote_to_evidence", "rerun_chunk", "request_human_review", "repair_link", "none"]


class DomainCoverage(TypedDict):
    domain: Literal["chapters", "characters", "relationships", "world", "events", "scenes", "linkage"]
    expected: int
    observed: int
    complete: int
    failed: int
    unknown: int
    coverage_ratio: float


class SemanticCoverageInput(TypedDict):
    contract_version: str
    import_run_id: str
    lineage_id: str
    attempt_id: str
    source_manifest: dict[str, Any]
    chunks: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    entity_merge_decisions: list[dict[str, Any]]
    organizer_output: dict[str, Any]
    timeline_architecture: dict[str, Any]
    manuscript_projection: dict[str, Any]
    existing_project_digest: dict[str, Any]
    profile: str
    relationship_quarantines: NotRequired[list[dict[str, Any]]]


class SemanticCoverageReport(TypedDict):
    contract_version: Literal["w1-semantic-coverage-report/v1"]
    import_run_id: str
    lineage_id: str
    attempt_id: str
    input_hash: str
    verdict: Literal["pass", "warning", "blocked"]
    blocking_findings: list[SemanticFinding]
    warnings: list[SemanticFinding]
    infos: list[SemanticFinding]
    coverage: list[DomainCoverage]
    character_merge_report: dict[str, Any]
    relationship_report: dict[str, Any]
    world_routing_report: dict[str, Any]
    linkage_report: dict[str, Any]
    acceptance_policy: dict[str, Any]
    generated_by: Literal["deterministic"]
    source_manifest_hash: NotRequired[str]
