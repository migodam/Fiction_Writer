from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class Budget:
    max_steps: int
    max_tokens: int
    max_cost: float
    max_seconds: float

    def __post_init__(self) -> None:
        if min(self.max_steps, self.max_tokens, self.max_cost, self.max_seconds) < 0:
            raise ValueError("budget limits must be non-negative")


@dataclass(frozen=True)
class OpenQuestion:
    question_id: str
    subject: str
    prompt: str
    evidence_required: str
    round_number: int


@dataclass(frozen=True)
class PlanTask:
    task_id: str
    title: str
    dependencies: tuple[str, ...] = ()
    read_set: tuple[str, ...] = ()
    write_set: tuple[str, ...] = ()
    budget: Budget | None = None
    policy_version: str = "v1"


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    tasks: tuple[PlanTask, ...]
    budget: Budget | None = None
    policy_version: str = "v1"

    def __post_init__(self) -> None:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task ids must be unique")
        known = set(task_ids)
        for task in self.tasks:
            unknown = set(task.dependencies) - known
            if unknown:
                raise ValueError(f"unknown dependency for {task.task_id}: {sorted(unknown)}")
            if task.task_id in task.dependencies:
                raise ValueError(f"cycle detected at {task.task_id}")
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {task.task_id: task for task in self.tasks}

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("cycle detected in execution plan")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in by_id[task_id].dependencies:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[[Mapping[str, Any]], Any]
    estimated_tokens: int = 0
    estimated_cost: float = 0.0
    policy_version: str = "v1"


@dataclass(frozen=True)
class DecisionRecord:
    run_id: str
    sequence: int
    decision: str
    reason: str
    policy_version: str = "v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "decision": self.decision,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "metadata": dict(self.metadata),
        }
