from __future__ import annotations

from typing import Callable

from .models import ExecutionPlan


class PlanExecuteController:
    REPLAN_EVENTS = frozenset({"new_evidence", "task_failed", "human_modified"})

    def __init__(self, planner: Callable[[ExecutionPlan], ExecutionPlan]) -> None:
        self._planner = planner

    def maybe_replan(self, plan: ExecutionPlan, event: str) -> ExecutionPlan:
        return self._planner(plan) if event in self.REPLAN_EVENTS else plan
