"""Constrained Plan-Execute/ReAct executor.

The executor is an operational kernel: registered tools, typed plans, durable
events and explicit human gates. It has no network or model-calling behavior.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from uuid import uuid4

from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore

from .contracts import AgentEvent, ExecutionPlan, PlanTask, ToolSpec
from .hooks import (
    ApprovalChecker,
    HarnessPolicyError,
    completion_predicate,
    enforce_budget,
    enforce_scopes,
    redact_event_payload,
    validate_json_schema,
)
from .planner import ready_tasks, resolve_tool, validate_plan
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
        clock: Callable[[], float] = time.monotonic,
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
            actor_kind=actor_kind, actor_id=actor_id,
            payload=redact_event_payload(dict(payload)), idempotency_key=key,
        )
        return self.runtime.append_harness_event(event, owner_id=self.owner_id, fence_token=self.fence_token)

    def pause(self) -> None:
        self.state.status = "paused"
        self.runtime.set_attempt_status(self.attempt_id, "paused", owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("run.paused", "human", self.owner_id, {}, key="run:paused")

    def cancel(self) -> None:
        self.state.status = "cancelled"
        self.runtime.set_attempt_status(self.attempt_id, "cancelled", owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("run.cancelled", "human", self.owner_id, {}, key="run:cancelled")

    def execute(self, plan: ExecutionPlan, arguments: Mapping[str, Mapping[str, Any]] | None = None) -> ExecutionState:
        persisted = self.runtime.get_attempt(self.attempt_id)
        if persisted is None:
            raise KeyError(self.attempt_id)
        if persisted["status"] in {"paused", "cancelled"}:
            self.state.status = str(persisted["status"])
            return self.state
        # A resume must re-evaluate the durable approval state. It may proceed
        # only when the specific pending operation has been authorized.
        self.state.status = "running"
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
                    self._event("run.completed", "system", "harness", {"completed_tasks": sorted(self.state.completed)}, key=f"run:completed:{plan.plan_id}")
                    return self.state
        self.state.status = "completed"
        self.runtime.set_attempt_status(self.attempt_id, "completed", owner_id=self.owner_id, fence_token=self.fence_token)
        self._event("run.completed", "system", "harness", {"completed_tasks": sorted(self.state.completed)}, key=f"run:completed:{plan.plan_id}")
        return self.state

    def _execute_task(self, plan: ExecutionPlan, adapter: Any, task: PlanTask, arguments: Mapping[str, Any]) -> None:
        tool = resolve_tool(self.registry, task, arguments)
        tool_arguments = {
            key: value for key, value in arguments.items()
            if key not in {"tool_version", "idempotency_key"}
        }
        try:
            enforce_scopes(task, tool)
            enforce_budget(plan, steps=self.state.steps, tokens=self.state.tokens + tool.estimated_tokens, cost_usd=self.state.cost_usd + tool.estimated_cost_usd, elapsed_seconds=self.clock() - self.state.started_at)
            validate_json_schema(tool_arguments, tool.input_schema, label="input")
        except HarnessPolicyError as exc:
            self._event("policy.rejected", "system", "harness", {"task_id": task.task_id, "reason": str(exc)}, key=f"policy:{plan.plan_id}:{task.task_id}:{hashlib.sha256(str(exc).encode()).hexdigest()}")
            raise HarnessExecutionError(str(exc)) from exc
        if task.approval_mode != "never" or tool.approval_policy != "never":
            if self.approval_checker is None or not self.approval_checker(task, tool):
                self.state.status = "waiting_human"
                self.runtime.set_attempt_status(self.attempt_id, "waiting_human", owner_id=self.owner_id, fence_token=self.fence_token)
                self._event("approval.required", "system", "harness", {"task_id": task.task_id, "tool": tool.name}, key=f"approval:{plan.plan_id}:{task.task_id}")
                raise ApprovalRequired(task.task_id)
        idempotency_key = str(arguments.get(
            "idempotency_key",
            f"{self.attempt_id}:{plan.plan_id}:{task.task_id}:{tool.name}@{tool.version}",
        ))
        calls = [
            call for call in self.runtime.list_tool_calls(self.attempt_id)
            if call["intent_payload"].get("operation_key", call["intent_payload"].get("idempotency_key")) == idempotency_key
            and call["intent_payload"].get("tool_version") == tool.version
        ]
        successful = next((call for call in reversed(calls) if call["status"] == "result"), None)
        if successful:
            result = successful.get("result_payload") or {}
            self.state.completed.add(task.task_id)
            self.state.observations.append(result)
            successful_key = str(successful["intent_payload"]["idempotency_key"])
            self._event(
                "tool.completed", "tool", tool.name,
                {"task_id": task.task_id, "result": dict(result)},
                key=self._event_key("completed", successful_key),
            )
            self._event("tool.replayed", "tool", tool.name, {"task_id": task.task_id}, key=self._event_key("replay", idempotency_key))
            return
        pending_unknown = next((call for call in reversed(calls) if call["status"] == "unknown_outcome"), None)
        if pending_unknown is not None:
            call = self._authorized_retry_intent(
                pending_unknown, tool, task, idempotency_key, len(calls)
            )
        else:
            unresolved = next((call for call in reversed(calls) if call["status"] == "intent"), None)
            if unresolved is not None and tool.risk == "external_call":
                self.runtime.record_tool_unknown_outcome(
                    unresolved["tool_call_id"], "runtime_interrupted",
                    owner_id=self.owner_id, fence_token=self.fence_token,
                )
                self._wait_for_human(task, tool, idempotency_key)
            failures = sum(call["status"] == "failed" for call in calls)
            if failures > task.retry_limit:
                raise HarnessExecutionError(
                    f"retry limit exceeded for {task.task_id}: {failures}/{task.retry_limit}"
                )
            invocation_key = (
                idempotency_key if not calls else f"{idempotency_key}:retry:{len(calls)}"
            )
            call = self.runtime.record_tool_intent(
                self.attempt_id, tool.name,
                {
                    "task_id": task.task_id,
                    "idempotency_key": invocation_key,
                    "operation_key": idempotency_key,
                    "tool_version": tool.version,
                },
                owner_id=self.owner_id, fence_token=self.fence_token,
            )
        invocation_key = str(call["intent_payload"]["idempotency_key"])
        self._event("tool.started", "tool", tool.name, {"task_id": task.task_id}, key=self._event_key("start", invocation_key))
        try:
            remaining_seconds = max(
                0.0,
                plan.budget.max_seconds - (self.clock() - self.state.started_at),
            )
            timeouts = [
                value for value in (tool.timeout_seconds, remaining_seconds)
                if value > 0
            ]
            effective_timeout = min(timeouts) if timeouts else 0.0
            result = self._invoke(
                adapter, task, tool, tool_arguments, effective_timeout
            )
            if not isinstance(result, Mapping):
                raise HarnessPolicyError("output must be an object")
            validate_json_schema(result, tool.output_schema, label="output")
        except UnknownToolOutcome as exc:
            safe_reason = (
                "tool_timeout" if str(exc) == "tool_timeout"
                else "transport_outcome_unknown"
            )
            self.runtime.record_tool_unknown_outcome(call["tool_call_id"], safe_reason, owner_id=self.owner_id, fence_token=self.fence_token)
            self.state.status = "waiting_human"
            self.runtime.set_attempt_status(self.attempt_id, "waiting_human", owner_id=self.owner_id, fence_token=self.fence_token)
            self._event("tool.unknown_outcome", "tool", tool.name, {"task_id": task.task_id, "reason": safe_reason}, key=self._event_key("unknown", invocation_key))
            raise
        except LeaseLostError:
            raise
        except Exception as exc:
            self.runtime.record_tool_failure(call["tool_call_id"], {"failure_type": type(exc).__name__}, owner_id=self.owner_id, fence_token=self.fence_token)
            self._event("tool.failed", "tool", tool.name, {"task_id": task.task_id, "error": type(exc).__name__}, key=self._event_key("failed", invocation_key))
            if isinstance(exc, HarnessPolicyError):
                raise HarnessExecutionError(str(exc)) from exc
            raise
        self.runtime.record_tool_result(call["tool_call_id"], result, owner_id=self.owner_id, fence_token=self.fence_token)
        self.state.steps += 1
        self.state.tokens += tool.estimated_tokens
        self.state.cost_usd += tool.estimated_cost_usd
        self.state.completed.add(task.task_id)
        self.state.observations.append(result)
        self._event("tool.completed", "tool", tool.name, {"task_id": task.task_id, "result": dict(result)}, key=self._event_key("completed", invocation_key))

    def _authorized_retry_intent(
        self,
        unknown: Mapping[str, Any],
        tool: ToolSpec,
        task: PlanTask,
        operation_key: str,
        call_count: int,
    ) -> Mapping[str, Any]:
        unknown_key = str(unknown["intent_payload"]["idempotency_key"])
        decision_key = f"retry_provider_call:{unknown_key}"
        decision = next(
            (
                item for item in self.runtime.list_human_decisions(self.attempt_id)
                if item["decision_key"] == decision_key
                and item["decision"] == "authorize_retry_once"
            ),
            None,
        )
        if decision is None:
            self._wait_for_human(task, tool, unknown_key)
        invocation_key = f"{operation_key}:retry:{call_count}"
        call = self.runtime.record_authorized_retry_intent(
            self.attempt_id, str(unknown["tool_call_id"]), decision_key,
            tool.name,
            {
                "task_id": task.task_id,
                "idempotency_key": invocation_key,
                "operation_key": operation_key,
                "tool_version": tool.version,
            },
            tool_call_id=str(uuid4()), owner_id=self.owner_id,
            fence_token=self.fence_token,
        )
        self.runtime.set_attempt_status(
            self.attempt_id, "running",
            owner_id=self.owner_id, fence_token=self.fence_token,
        )
        return call

    def _wait_for_human(
        self, task: PlanTask, tool: ToolSpec, idempotency_key: str
    ) -> None:
        self.state.status = "waiting_human"
        self.runtime.set_attempt_status(
            self.attempt_id, "waiting_human",
            owner_id=self.owner_id, fence_token=self.fence_token,
        )
        self._event(
            "approval.required", "system", "harness",
            {"task_id": task.task_id, "tool": tool.name, "reason": "unknown_outcome"},
            key=self._event_key("unknown-approval", idempotency_key),
        )
        raise ApprovalRequired(task.task_id)

    def _invoke(
        self,
        adapter: Any,
        task: PlanTask,
        tool: ToolSpec,
        arguments: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        if timeout_seconds <= 0:
            return adapter.execute_tool(task, arguments)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="harness-tool")
        future = pool.submit(adapter.execute_tool, task, arguments)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            if tool.risk == "external_call":
                raise UnknownToolOutcome("tool_timeout") from exc
            raise HarnessExecutionError("tool_timeout") from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _event_key(prefix: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"{prefix}:{digest}"
