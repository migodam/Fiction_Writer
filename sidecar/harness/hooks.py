"""Small policy hooks used by the constrained Harness executor.

Hooks are deliberately synchronous and side-effect free.  They make policy
decisions testable without introducing an LLM or a second orchestration loop.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .contracts import ExecutionPlan, PlanTask, ToolSpec


class HarnessPolicyError(RuntimeError):
    pass


def _overlap(requested: tuple[str, ...], allowed: tuple[str, ...]) -> set[str]:
    return {scope for scope in requested if scope not in allowed}


def enforce_scopes(task: PlanTask, tool: ToolSpec) -> None:
    """Ensure a task cannot widen the registered tool's declared access."""
    missing_reads = _overlap(task.read_set, tool.read_set)
    missing_writes = _overlap(task.write_set, tool.write_set)
    if missing_reads or missing_writes:
        raise HarnessPolicyError(
            f"scope violation: reads={sorted(missing_reads)} writes={sorted(missing_writes)}"
        )


def enforce_budget(plan: ExecutionPlan, *, steps: int, tokens: int, cost_usd: float, elapsed_seconds: float) -> None:
    budget = plan.budget
    if steps >= budget.max_steps:
        raise HarnessPolicyError("step budget exceeded")
    if tokens > budget.max_tokens:
        raise HarnessPolicyError("token budget exceeded")
    if cost_usd > budget.max_cost_usd:
        raise HarnessPolicyError("cost budget exceeded")
    if elapsed_seconds > budget.max_seconds:
        raise HarnessPolicyError("time budget exceeded")


def completion_predicate(name: str, plan: ExecutionPlan, observations: list[Mapping[str, Any]], adapter: Any) -> bool:
    """Evaluate only an explicit adapter predicate; never interpret model text."""
    if not name or name != plan.completion_predicate:
        raise HarnessPolicyError("completion predicate mismatch")
    return bool(adapter.evaluate_completion(plan, observations))


ApprovalChecker = Callable[[PlanTask, ToolSpec], bool]

