"""Constrained Plan-Execute/ReAct executor.

The executor is an operational kernel: registered tools, typed plans, durable
events and explicit human gates. It has no network or model-calling behavior.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from sidecar.runtime.agent_runtime import RuntimeStore

from .contracts import AgentEvent, ExecutionPlan, PlanTask, ToolSpec
from .hooks import ApprovalChecker, HarnessPolicyError, completion_predicate, enforce_budget, enforce_scopes
from .planner import ready_tasks, validate_plan
from .registry import HarnessRegistry

# The repository's concrete registry is HarnessRegistry; this public alias
# makes the executor contract explicit for callers that use the versioned name.
VersionedToolRegistry = HarnessRegistry


class HarnessExecutionError(RuntimeError):
    pass


class UnknownToolOutcome(HarnessExecutionError):
    pass


class ApprovalRequired(HarnessExecutionError):
    pass


@dataclass
class ExecutionState:
    completed: set[str] = field(default_factory=set)
    observations: list[Mapping[str, Any]] = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    status: str = "running"


class HarnessExecutor:
    def __init__(
        self,
        *,
        registry: HarnessRegistry,
        runtime: RuntimeStore,
        run: Mapping[str, Any],
        attempt: Mapping[str, Any],
        owner_id: str,
        fence_token: int,
        approval_checker: ApprovalChecker | None = None,
        clock: callable = time.monotonic,
    ) -> None:
        self.registry = registry
        self.runtime = runtime
        self.run = run
        self.attempt = attempt
        self.owner_id = owner_id
        self.fence_token = fence_token
        self.approval_checker = approval_checker
        self.clock = clock
        self.state = ExecutionState(started_at=clock())
        self._sequence = max((event["sequence"] for event in runtime.list_events(attempt["attempt_id"])), default=0)

    @property
    def attempt_id(self) -> str:
        return str(self.attempt["attempt_id"])

    def _event(self, event_type: str, actor_kind: str, actor_id: str, payload: Mapping[str, Any], *, key: str | None = None) -> dict[str, Any]:
        self._sequence += 1
        event = AgentEvent(
            event_id=str(uuid4()), run_id=str(self.run["run_id"]), lineage_id=str(self.run["lineage_id"]),
            attempt_id=self.attempt_id, sequence=self._sequence, event_type=event_type,
            actor_kind=actor_kind, actor_id=actor_id, payload=dict(payload), idempotency_key=key,
        )
        return self.runtime.append_harness_event(event, owner_id=self.owner_id, fence_token=self.fence_token)

    def pause(self) -> None:
        self.state.status = "paused"
        self.runtime.set_attempt_status(self.attempt_id, "paused", owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("run.paused", "human", self.owner_id, {})

    def cancel(self) -> None:
        self.state.status = "cancelled"
        self.runtime.set_attempt_status(self.attempt_id, "cancelled", owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("run.cancelled", "human", self.owner_id, {})

    def execute(self, plan: ExecutionPlan, arguments: Mapping[str, Mapping[str, Any]] | None = None) -> ExecutionState:
        validate_plan(plan)
        adapter = self.registry.resolve_workflow(plan.workflow_id)
        adapter.validate_plan(plan)
        args = arguments or {}
        self._event("plan.started", "planner", plan.plan_id, {"plan": plan.to_dict()}, key=f"plan:{plan.plan_id}")
        while len(self.state.completed) < len(plan.tasks):
            if self.state.status != "running":
                return self.state
            ready = ready_tasks(plan, self.state.completed).tasks
            if not ready:
                raise HarnessExecutionError("no ready tasks; plan dependency state is inconsistent")
            for task in ready:
                self._execute_task(plan, adapter, task, args.get(task.task_id, {}))
                if completion_predicate(plan.completion_predicate, plan, self.state.observations, adapter):
                    self.state.status = "completed"
                    self.runtime.set_attempt_status(self.attempt_id, "completed", owner_id=self.owner_id, fence_token=self.fence_token)
                    self._event("run.completed", "system", "harness", {"completed_tasks": sorted(self.state.completed)})
                    return self.state
        self.state.status = "completed"
        self.runtime.set_attempt_status(self.attempt_id, "completed", owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("run.completed", "system", "harness", {"completed_tasks": sorted(self.state.completed)})
        return self.state

    def _execute_task(self, plan: ExecutionPlan, adapter: Any, task: PlanTask, arguments: Mapping[str, Any]) -> None:
        tool = self.registry.resolve_tool(task.tool_name, str(arguments.get("tool_version", "1")))
        try:
            enforce_scopes(task, tool)
            enforce_budget(plan, steps=self.state.steps, tokens=self.state.tokens + tool.estimated_tokens, cost_usd=self.state.cost_usd + tool.estimated_cost_usd, elapsed_seconds=self.clock() - self.state.started_at)
        except HarnessPolicyError as exc:
            self._event("policy.rejected", "system", "harness", {"task_id": task.task_id, "reason": str(exc)})
            raise HarnessExecutionError(str(exc)) from exc
        if task.approval_mode != "never" or tool.approval_policy != "never":
            if self.approval_checker is None or not self.approval_checker(task, tool):
                self.state.status = "waiting_human"
                self.runtime.set_attempt_status(self.attempt_id, "waiting_human", owner_id=self.owner_id, fence_token=self.fence_token)
                self._event("approval.required", "system", "harness", {"task_id": task.task_id, "tool": tool.name})
                raise ApprovalRequired(task.task_id)
        idempotency_key = str(arguments.get("idempotency_key", f"{self.attempt_id}:{task.task_id}"))
        prior = next((call for call in self.runtime.list_tool_calls(self.attempt_id) if call["intent_payload"].get("idempotency_key") == idempotency_key), None)
        if prior and prior["status"] == "result":
            result = prior.get("result_payload") or {}
            self.state.completed.add(task.task_id)
            self.state.observations.append(result)
            self._event("tool.replayed", "tool", tool.name, {"task_id": task.task_id}, key=f"replay:{idempotency_key}")
            return
        call = self.runtime.record_tool_intent(self.attempt_id, tool.name, {"task_id": task.task_id, "idempotency_key": idempotency_key}, owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("tool.started", "tool", tool.name, {"task_id": task.task_id}, key=f"start:{idempotency_key}")
        try:
            result = adapter.execute_tool(task, arguments)
        except UnknownToolOutcome as exc:
            self.runtime.record_tool_unknown_outcome(call["tool_call_id"], str(exc), owner_id=self.owner_id, fence_token=self.fence_token)
            self.state.status = "waiting_human"
            self.runtime.set_attempt_status(self.attempt_id, "waiting_human", owner_id=self.owner_id, fence_token=self.fence_token)
            self._event("tool.unknown_outcome", "tool", tool.name, {"task_id": task.task_id, "reason": str(exc)})
            raise
        except BaseException as exc:
            self.runtime.record_tool_failure(call["tool_call_id"], {"failure_type": type(exc).__name__, "message": str(exc)}, owner_id=self.owner_id, fence_token=self.fence_token)
            self._event("tool.failed", "tool", tool.name, {"task_id": task.task_id, "error": type(exc).__name__})
            raise
        self.runtime.record_tool_result(call["tool_call_id"], result, owner_id=self.owner_id, fence_token=self.fence_token)
        self.state.steps += 1
        self.state.tokens += tool.estimated_tokens
        self.state.cost_usd += tool.estimated_cost_usd
        self.state.completed.add(task.task_id)
        self.state.observations.append(result)
        self._event("tool.completed", "tool", tool.name, {"task_id": task.task_id, "result": dict(result)})
