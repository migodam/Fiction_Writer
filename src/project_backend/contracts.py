from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4


TaskStatus = Literal["queued", "running", "awaiting_user_input", "completed", "failed", "canceled"]
ReviewPolicy = Literal["manual_workbench", "issue_review", "artifact_only"]
TaskSource = Literal["manual", "local-cli", "langgraph", "external-ai"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


@dataclass
class EntityReference:
    type: str
    id: str


@dataclass
class FailureState:
    code: str
    message: str
    retryable: bool
    details: Optional[str] = None


@dataclass
class RetryState:
    attempt: int
    max_attempts: int
    retry_of_run_id: Optional[str] = None


@dataclass
class AwaitingUserInputPayload:
    prompt: str
    fields: List[str]
    reason: str


@dataclass
class TaskRequest:
    id: str
    taskType: str
    agentType: str
    source: TaskSource
    title: str
    input: Dict[str, Any]
    contextScope: Dict[str, Any]
    reviewPolicy: ReviewPolicy
    createdAt: str
    status: TaskStatus = "queued"
    targetIds: List[EntityReference] = field(default_factory=list)
    prompt: str = ""


@dataclass
class TaskRun:
    id: str
    taskRequestId: str
    status: TaskStatus
    attempt: int
    executor: str
    adapter: str
    startedAt: str
    heartbeatAt: Optional[str] = None
    finishedAt: Optional[str] = None
    artifactIds: List[str] = field(default_factory=list)
    summary: str = ""
    failure: Optional[FailureState] = None
    awaitingUserInput: Optional[AwaitingUserInputPayload] = None


@dataclass
class TaskArtifact:
    id: str
    taskRunId: str
    artifactType: str
    path: Optional[str]
    summary: str
    mimeType: str = "application/json"
    entityRefs: List[EntityReference] = field(default_factory=list)


ProposalBatchArtifact = TaskArtifact
IssueBatchArtifact = TaskArtifact
ContextPackageArtifact = TaskArtifact
ScriptDraftArtifact = TaskArtifact
StoryboardArtifact = TaskArtifact
VideoPackageArtifact = TaskArtifact


@dataclass
class RetrievalRequest:
    id: str
    query: str
    scope: Dict[str, Any]
    filters: Dict[str, Any]
    topK: int = 5
    includeNeighborChunks: bool = False


@dataclass
class RetrievalResultItem:
    chunkId: str
    documentId: str
    excerpt: str
    score: float
    entityRefs: List[EntityReference]
    sourcePath: Optional[str]


@dataclass
class RetrievalResult:
    requestId: str
    backend: str
    items: List[RetrievalResultItem]
