"""Deterministic plan validation helpers for the constrained Harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import ExecutionPlan, PlanTask


@dataclass(frozen=True)
class ReadyTasks:
    """A stable, dependency-safe batch of tasks ready to execute."""

    tasks: tuple[PlanTask, ...]


def validate_plan(plan: ExecutionPlan) -> ExecutionPlan:
    """Return a plan only after its contract-level DAG checks have run."""
    if not plan.tasks:
        raise ValueError("execution plan must contain at least one task")
    return plan


def ready_tasks(plan: ExecutionPlan, completed: Iterable[str], *, claimed: Iterable[str] = ()) -> ReadyTasks:
    """Select tasks whose dependencies are complete, preserving plan order."""
    done = set(completed)
    claimed_ids = set(claimed)
    result = tuple(
        task for task in plan.tasks
        if task.task_id not in done
        and task.task_id not in claimed_ids
        and set(task.dependencies).issubset(done)
    )
    return ReadyTasks(result)
