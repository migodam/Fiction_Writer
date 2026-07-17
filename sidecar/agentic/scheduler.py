from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .models import ExecutionPlan, PlanTask
from .runtime import RuntimePort
from sidecar.runtime.agent_runtime import RuntimeStore


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    fences: Mapping[str, int]


@dataclass(frozen=True)
class DeadLetter:
    task_id: str
    reason: str


class DurableScheduler:
    def __init__(self, runtime: RuntimePort, max_concurrency: int = 4) -> None:
        self.runtime = runtime
        self.max_concurrency = max_concurrency
        self._plans: dict[str, ExecutionPlan] = {}
        self._states: dict[str, dict[str, str]] = {}
        self._running: dict[str, dict[str, ScheduledTask]] = {}
        self._dead_letters: dict[str, list[DeadLetter]] = {}

    def submit(self, run_id: str, plan: ExecutionPlan) -> None:
        self._plans[run_id] = plan
        self._states[run_id] = {task.task_id: "pending" for task in plan.tasks}
        self._running[run_id] = {}
        self._dead_letters[run_id] = []
        self.runtime.emit_event(run_id, "plan_submitted", {"plan_id": plan.plan_id})

    def claim_ready(self, run_id: str) -> list[ScheduledTask]:
        plan = self._plans[run_id]
        states = self._states[run_id]
        running = self._running[run_id]
        claimed: list[ScheduledTask] = []
        for task in plan.tasks:
            if len(running) >= self.max_concurrency or states[task.task_id] != "pending":
                continue
            dependency_states = [states[dependency] for dependency in task.dependencies]
            if any(status in {"failed", "blocked", "cancelled"} for status in dependency_states):
                self._block(run_id, task.task_id, "dependency_failed")
                continue
            if not all(status == "completed" for status in dependency_states):
                continue
            if self._has_write_conflict(plan, task, running):
                continue
            fences = self._acquire_writes(task)
            if fences is None:
                continue
            scheduled = ScheduledTask(task.task_id, MappingProxyType(fences))
            states[task.task_id] = "running"
            running[task.task_id] = scheduled
            claimed.append(scheduled)
            self.runtime.emit_event(run_id, "task_claimed", {"task_id": task.task_id, "fences": dict(fences)})
        return claimed

    def complete(self, run_id: str, task_id: str) -> None:
        self._finish(run_id, task_id, "completed")

    def fail(self, run_id: str, task_id: str, reason: str) -> None:
        self._finish(run_id, task_id, "failed")
        self.runtime.emit_event(run_id, "task_failed", {"task_id": task_id, "reason": reason})
        self._propagate_blocks(run_id)

    def cancel(self, run_id: str) -> None:
        for task_id, state in self._states[run_id].items():
            if state in {"pending", "running"}:
                self._finish(run_id, task_id, "cancelled")
                self._dead_letters[run_id].append(DeadLetter(task_id, "run_cancelled"))
        self.runtime.emit_event(run_id, "run_cancelled", {})

    def status(self, run_id: str, task_id: str) -> str:
        return self._states[run_id][task_id]

    def dead_letters(self, run_id: str) -> tuple[DeadLetter, ...]:
        return tuple(self._dead_letters[run_id])

    def _finish(self, run_id: str, task_id: str, state: str) -> None:
        scheduled = self._running[run_id].pop(task_id, None)
        if scheduled:
            for resource, fence in scheduled.fences.items():
                self.runtime.release_lease(resource, task_id, fence)
        self._states[run_id][task_id] = state

    def _propagate_blocks(self, run_id: str) -> None:
        changed = True
        while changed:
            changed = False
            for task in self._plans[run_id].tasks:
                if self._states[run_id][task.task_id] == "pending" and any(
                    self._states[run_id][dependency] in {"failed", "blocked", "cancelled"} for dependency in task.dependencies
                ):
                    self._block(run_id, task.task_id, "dependency_failed")
                    changed = True

    def _block(self, run_id: str, task_id: str, reason: str) -> None:
        self._states[run_id][task_id] = "blocked"
        self._dead_letters[run_id].append(DeadLetter(task_id, reason))
        self.runtime.emit_event(run_id, "task_blocked", {"task_id": task_id, "reason": reason})

    def _has_write_conflict(self, plan: ExecutionPlan, task: PlanTask, running: dict[str, ScheduledTask]) -> bool:
        if not task.write_set:
            return False
        running_ids = set(running)
        return any(set(task.write_set) & set(candidate.write_set) for candidate in plan.tasks if candidate.task_id in running_ids)

    def _acquire_writes(self, task: PlanTask) -> dict[str, int] | None:
        acquired: dict[str, int] = {}
        for resource in task.write_set:
            fence = self.runtime.acquire_lease(resource, task.task_id)
            if fence is None:
                for acquired_resource, acquired_fence in acquired.items():
                    self.runtime.release_lease(acquired_resource, task.task_id, acquired_fence)
                return None
            acquired[resource] = fence
        return acquired


class RuntimeStoreScheduler:
    """Scheduler adapter whose only state source is :class:`RuntimeStore`."""

    def __init__(self, store: RuntimeStore, *, worker_id: str, max_concurrency: int = 4, claim_ttl_seconds: float = 30) -> None:
        if max_concurrency < 1 or claim_ttl_seconds <= 0:
            raise ValueError("max_concurrency and claim_ttl_seconds must be positive")
        self.store = store
        self.worker_id = worker_id
        self.max_concurrency = max_concurrency
        self.claim_ttl_seconds = claim_ttl_seconds

    def submit(self, run_id: str, plan: ExecutionPlan) -> dict[str, object]:
        return self.store.submit_task_plan(run_id, plan)

    def claim_ready(self, run_id: str) -> list[ScheduledTask]:
        rows = self.store.claim_ready_tasks(
            run_id,
            self.worker_id,
            max_concurrency=self.max_concurrency,
            ttl_seconds=self.claim_ttl_seconds,
        )
        return [ScheduledTask(row["task_id"], MappingProxyType(dict(row["fence_map"]))) for row in rows]

    def complete(self, run_id: str, task_id: str) -> None:
        task = self._task(run_id, task_id)
        self.store.complete_task(run_id, task_id, self.worker_id, dict(task["fence_map"]))

    def fail(self, run_id: str, task_id: str, reason: str) -> None:
        task = self._task(run_id, task_id)
        self.store.fail_task(run_id, task_id, self.worker_id, dict(task["fence_map"]), reason)

    def cancel(self, run_id: str) -> None:
        self.store.cancel_task_plan(run_id)

    def recover_expired(self, run_id: str) -> list[str]:
        return self.store.recover_expired_task_claims(run_id)

    def status(self, run_id: str, task_id: str) -> str:
        return self.store.get_task_status(run_id, task_id)

    def dead_letters(self, run_id: str) -> tuple[DeadLetter, ...]:
        return tuple(DeadLetter(row["task_id"], row["reason"]) for row in self.store.list_dead_letters(run_id))

    def _task(self, run_id: str, task_id: str) -> dict[str, object]:
        for task in self.store.get_task_dag(run_id):
            if task["task_id"] == task_id:
                return task
        raise KeyError(task_id)
