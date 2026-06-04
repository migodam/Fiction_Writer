"""TypedDict schemas for W1 reviewer reports and repair actions."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict


class ReviewFinding(TypedDict):
    finding_id: str
    check_name: str
    description: str
    severity: Literal["low", "medium", "high"]
    entity_refs: List[str]
    evidence_refs: List[str]


class _RepairActionRequired(TypedDict):
    action_type: str
    target_entity_ids: List[str]
    description: str
    deterministic: bool


class RepairAction(_RepairActionRequired, total=False):
    # Frontend-executable operations; absent means advisory-only (not written to inbox).
    proposed_operations: List[dict]


class OrchestratorRequest(TypedDict):
    request_type: Literal["rerun_window", "reclassify_entity", "merge_entity"]
    theme: str
    target_windows: List[str]
    expected_repair: str
    priority: Literal["low", "medium", "high"]


class ManifestRevisionDiff(TypedDict):
    revision_id: str
    entity_type: str              # "character" | "chapter" | "world_item"
    entity_id: str
    field: str                    # which field changed
    old_value: str                # what was in the existing project
    new_value: str                # what the new import proposes
    action: Literal["protect", "update", "merge"]
    reason: str


class ZeroCostLedger(TypedDict):
    live_model_calls: bool
    full50_run: bool
    model_used: Optional[str]
    estimated_api_calls: int
    estimated_prompt_windows: int


class ReviewReport(TypedDict):
    reviewer: Literal["quality", "fact", "consistency"]
    verdict: Literal["pass", "warn", "needs_repair", "needs_orchestrator_rerun"]
    severity: Literal["low", "medium", "high"]
    findings: List[ReviewFinding]
    local_repair_actions: List[RepairAction]
    orchestrator_requests: List[OrchestratorRequest]
    token_cost_ledger: ZeroCostLedger
    manifest_revision_diffs: List[ManifestRevisionDiff]
