"""Deterministic plan validation helpers for the constrained Harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .contracts import ExecutionPlan, PlanTask, ToolSpec
from .registry import HarnessRegistry


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


def resolve_tool(
    registry: HarnessRegistry,
    task: PlanTask,
    arguments: Mapping[str, Any],
) -> ToolSpec:
    """Resolve an explicit version, or the sole registered version, fail closed."""
    requested = arguments.get("tool_version")
    if requested is not None:
        if not isinstance(requested, str) or not requested.strip():
            raise ValueError("tool_version must be a non-empty string")
        return registry.resolve_tool(task.tool_name, requested)
    candidates = [
        tool
        for (name, _version), tool in registry.tools().items()
        if name == task.tool_name
    ]
    if not candidates:
        raise ValueError(f"tool not registered: {task.tool_name}")
    if len(candidates) != 1:
        versions = sorted(tool.version for tool in candidates)
        raise ValueError(
            f"tool version is ambiguous for {task.tool_name}: {versions}"
        )
    return candidates[0]
