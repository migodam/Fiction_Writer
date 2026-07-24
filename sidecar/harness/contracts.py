"""Stable, serializable contracts for the sidecar agent harness.

These contracts intentionally describe operational facts, not prompts, source
text, or model reasoning. They are shared boundaries between planners, tools,
the durable runtime, and future UI adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol, Sequence


ActorKind = Literal["system", "planner", "agent", "tool", "human"]
RiskLevel = Literal["read", "draft", "external_call", "canonical_write"]
ApprovalPolicy = Literal["never", "before_start", "before_commit"]
IdempotencyPolicy = Literal["required", "optional", "none"]
ApprovalAction = Literal["execute_tool", "retry_unknown", "accept_package", "fork_checkpoint", "canonical_commit"]
ApprovalRisk = Literal["low", "medium", "high"]
ApprovalOutcome = Literal["approve", "reject", "approve_once", "cancel", "fork"]


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _non_negative(value: float | int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class Budget:
    max_steps: int
    max_tokens: int
    max_cost_usd: float
    max_seconds: float

    def __post_init__(self) -> None:
        for field_name in ("max_steps", "max_tokens", "max_cost_usd", "max_seconds"):
            _non_negative(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_seconds": self.max_seconds,
        }


@dataclass(frozen=True)
class AgentEvent:
    event_id: str
    run_id: str
    lineage_id: str
    attempt_id: str
    sequence: int
    event_type: str
    actor_kind: ActorKind
    actor_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    causation_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    contract_version: str = "AgentEvent/v1"

    def __post_init__(self) -> None:
        for field_name in ("event_id", "run_id", "lineage_id", "attempt_id", "event_type", "actor_id"):
            _required(getattr(self, field_name), field_name)
        if self.contract_version != "AgentEvent/v1":
            raise ValueError("unsupported AgentEvent contract_version")
        if self.actor_kind not in {"system", "planner", "agent", "tool", "human"}:
            raise ValueError("unsupported actor_kind")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        for field_name in ("causation_id", "correlation_id", "idempotency_key"):
            value = getattr(self, field_name)
            if value is not None:
                _required(value, field_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "lineage_id": self.lineage_id,
            "attempt_id": self.attempt_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "actor": {"kind": self.actor_kind, "id": self.actor_id},
            "payload": dict(self.payload),
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    handler_ref: str
    read_set: tuple[str, ...] = ()
    write_set: tuple[str, ...] = ()
    risk: RiskLevel = "read"
    approval_policy: ApprovalPolicy = "never"
    idempotency: IdempotencyPolicy = "optional"
    estimated_cost_usd: float = 0.0
    estimated_tokens: int = 0
    timeout_seconds: float = 0.0
    contract_version: str = "ToolSpec/v2"

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "description", "handler_ref"):
            _required(getattr(self, field_name), field_name)
        if self.contract_version != "ToolSpec/v2":
            raise ValueError("unsupported ToolSpec contract_version")
        if self.risk not in {"read", "draft", "external_call", "canonical_write"}:
            raise ValueError("unsupported tool risk")
        if self.approval_policy not in {"never", "before_start", "before_commit"}:
            raise ValueError("unsupported approval_policy")
        if self.idempotency not in {"required", "optional", "none"}:
            raise ValueError("unsupported idempotency policy")
        for field_name in ("estimated_cost_usd", "estimated_tokens", "timeout_seconds"):
            _non_negative(getattr(self, field_name), field_name)
        if self.risk == "canonical_write" and self.approval_policy != "before_commit":
            raise ValueError("canonical_write tools require before_commit approval")
        if self.risk == "external_call" and self.idempotency == "none":
            raise ValueError("external_call tools require an idempotency policy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "handler_ref": self.handler_ref,
            "read_set": list(self.read_set),
            "write_set": list(self.write_set),
            "risk": self.risk,
            "approval_policy": self.approval_policy,
            "idempotency": self.idempotency,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_tokens": self.estimated_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class PlanTask:
    task_id: str
    title: str
    tool_name: str
    dependencies: tuple[str, ...] = ()
    read_set: tuple[str, ...] = ()
    write_set: tuple[str, ...] = ()
    approval_mode: ApprovalPolicy = "never"
    retry_limit: int = 0
    artifact_contract: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("task_id", "title", "tool_name"):
            _required(getattr(self, field_name), field_name)
        if self.approval_mode not in {"never", "before_start", "before_commit"}:
            raise ValueError("unsupported task approval_mode")
        if self.retry_limit < 0:
            raise ValueError("retry_limit must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "tool_name": self.tool_name,
            "dependencies": list(self.dependencies),
            "read_set": list(self.read_set),
            "write_set": list(self.write_set),
            "approval_mode": self.approval_mode,
            "retry_limit": self.retry_limit,
            "artifact_contract": self.artifact_contract,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    workflow_id: str
    tasks: tuple[PlanTask, ...]
    budget: Budget
    completion_predicate: str
    available_tools: frozenset[str]
    max_replans: int = 0
    policy_version: str = "v2"
    generated_by: Literal["deterministic", "model"] = "deterministic"
    unresolved_questions: tuple[str, ...] = ()
    contract_version: str = "ExecutionPlan/v2"

    def __post_init__(self) -> None:
        for field_name in ("plan_id", "workflow_id", "completion_predicate", "policy_version"):
            _required(getattr(self, field_name), field_name)
        if self.contract_version != "ExecutionPlan/v2":
            raise ValueError("unsupported ExecutionPlan contract_version")
        if self.max_replans < 0:
            raise ValueError("max_replans must be non-negative")
        if self.generated_by not in {"deterministic", "model"}:
            raise ValueError("unsupported generated_by")
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task ids must be unique")
        task_map = {task.task_id: task for task in self.tasks}
        for task in self.tasks:
            unknown_dependencies = set(task.dependencies) - set(task_map)
            if unknown_dependencies:
                raise ValueError(f"unknown dependency for {task.task_id}: {sorted(unknown_dependencies)}")
            if task.tool_name not in self.available_tools:
                raise ValueError(f"unknown tool for {task.task_id}: {task.tool_name}")
        self._validate_acyclic(task_map)
        self._validate_write_conflicts(task_map)

    @staticmethod
    def _validate_acyclic(tasks: Mapping[str, PlanTask]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("cycle detected in execution plan")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in tasks[task_id].dependencies:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in tasks:
            visit(task_id)

    @staticmethod
    def _validate_write_conflicts(tasks: Mapping[str, PlanTask]) -> None:
        def depends_on(task_id: str, candidate_id: str, seen: set[str] | None = None) -> bool:
            seen = seen or set()
            if task_id in seen:
                return False
            seen.add(task_id)
            dependencies = tasks[task_id].dependencies
            return candidate_id in dependencies or any(depends_on(dependency, candidate_id, seen) for dependency in dependencies)

        entries = list(tasks.values())
        for index, left in enumerate(entries):
            for right in entries[index + 1:]:
                if not (set(left.write_set) & set(right.write_set)):
                    continue
                if not depends_on(left.task_id, right.task_id) and not depends_on(right.task_id, left.task_id):
                    raise ValueError(f"write conflict between {left.task_id} and {right.task_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "plan_id": self.plan_id,
            "workflow_id": self.workflow_id,
            "tasks": [task.to_dict() for task in self.tasks],
            "budget": self.budget.to_dict(),
            "completion_predicate": self.completion_predicate,
            "available_tools": sorted(self.available_tools),
            "max_replans": self.max_replans,
            "policy_version": self.policy_version,
            "generated_by": self.generated_by,
            "unresolved_questions": list(self.unresolved_questions),
        }


@dataclass(frozen=True)
class ApprovalRequest:
    decision_id: str
    decision_key: str
    run_id: str
    attempt_id: str
    action: ApprovalAction
    risk: ApprovalRisk
    summary: str
    affected_scopes: tuple[str, ...]
    cost_estimate_usd: float | None = None
    evidence_refs: tuple[str, ...] = ()
    expires_at: float | None = None
    contract_version: str = "ApprovalRequest/v1"

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "decision_key", "run_id", "attempt_id", "summary"):
            _required(getattr(self, field_name), field_name)
        if self.contract_version != "ApprovalRequest/v1":
            raise ValueError("unsupported ApprovalRequest contract_version")
        if self.action not in {"execute_tool", "retry_unknown", "accept_package", "fork_checkpoint", "canonical_commit"}:
            raise ValueError("unsupported approval action")
        if self.risk not in {"low", "medium", "high"}:
            raise ValueError("unsupported approval risk")
        if self.cost_estimate_usd is not None:
            _non_negative(self.cost_estimate_usd, "cost_estimate_usd")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "decision_id": self.decision_id,
            "decision_key": self.decision_key,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "action": self.action,
            "risk": self.risk,
            "summary": self.summary,
            "affected_scopes": list(self.affected_scopes),
            "cost_estimate_usd": self.cost_estimate_usd,
            "evidence_refs": list(self.evidence_refs),
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ApprovalDecision:
    decision_id: str
    decision_key: str
    attempt_id: str
    decision: ApprovalOutcome
    actor_id: str
    expected_version: int
    payload: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = "ApprovalDecision/v1"

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "decision_key", "attempt_id", "actor_id"):
            _required(getattr(self, field_name), field_name)
        if self.contract_version != "ApprovalDecision/v1":
            raise ValueError("unsupported ApprovalDecision contract_version")
        if self.decision not in {"approve", "reject", "approve_once", "cancel", "fork"}:
            raise ValueError("unsupported approval decision")
        if self.expected_version < 0:
            raise ValueError("expected_version must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "decision_id": self.decision_id,
            "decision_key": self.decision_key,
            "attempt_id": self.attempt_id,
            "decision": self.decision,
            "actor_id": self.actor_id,
            "expected_version": self.expected_version,
            "payload": dict(self.payload),
        }


class WorkflowAdapter(Protocol):
    """A workflow-specific adapter controlled by the common Harness Kernel."""

    workflow_id: str

    def describe(self) -> Mapping[str, Any]: ...

    def build_plan(self, context: Mapping[str, Any]) -> ExecutionPlan: ...

    def validate_plan(self, plan: ExecutionPlan) -> None: ...

    def execute_tool(self, task: PlanTask, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def observe_artifact(self, artifact: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def evaluate_completion(self, plan: ExecutionPlan, observations: Sequence[Mapping[str, Any]]) -> bool: ...

    def publish_proposal(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]: ...
