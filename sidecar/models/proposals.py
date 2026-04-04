from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict


class WriteOperation(TypedDict):
    op_type: Literal["create", "update", "delete"]
    entity_type: str
    entity_id: Optional[str]
    data: Dict[str, object]
    source_workflow: str
    confidence: float
    auto_apply: bool
    depends_on: List[str]


class Proposal(TypedDict):
    id: str
    title: str
    source: str
    kind: str
    operations: List[dict]
    depends_on: List[str]
    conflicts_with: List[str]
    confidence: float
    status: Literal["pending", "accepted", "rejected", "blocked", "archived"]
    created_at: str
    review_policy: str
