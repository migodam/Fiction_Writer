from __future__ import annotations

import pytest

from sidecar.harness.contracts import Budget, ExecutionPlan, PlanTask, ToolSpec
from sidecar.harness.executor import ApprovalRequired, HarnessExecutor, HarnessExecutionError, UnknownToolOutcome
from sidecar.harness.registry import HarnessRegistry
from sidecar.runtime.agent_runtime import RuntimeStore


class Adapter:
    workflow_id = "test"
    def __init__(self, fn=lambda task, args: {"task": task.task_id}): self.fn = fn
    def describe(self): return {"workflow_id": self.workflow_id}
    def build_plan(self, context): raise NotImplementedError
    def validate_plan(self, plan): return None
    def execute_tool(self, task, arguments): return self.fn(task, arguments)
    def observe_artifact(self, artifact): return artifact
    def evaluate_completion(self, plan, observations): return len(observations) >= 1
    def publish_proposal(self, proposal): return proposal


def setup(tmp_path, fn=lambda task, args: {"task": task.task_id}, **tool_kwargs):
    runtime = RuntimeStore(tmp_path)
    run = runtime.create_run(workflow_id="test")
    attempt = runtime.create_attempt(run["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "worker", ttl_seconds=300)
    registry = HarnessRegistry()
    registry.register_workflow(Adapter(fn))
    registry.register_tool(ToolSpec(name="echo", version="1", description="test", input_schema={}, output_schema={}, handler_ref="test.echo", **tool_kwargs))
    executor = HarnessExecutor(registry=registry, runtime=runtime, run=run, attempt=attempt, owner_id="worker", fence_token=lease["fence_token"])
    return executor, runtime


def plan(*tasks, **kwargs):
    return ExecutionPlan(plan_id="p", workflow_id="test", tasks=tuple(tasks), available_tools=frozenset({"echo"}), completion_predicate="done", budget=kwargs.pop("budget", Budget(10, 100, 10, 60)), **kwargs)


def test_happy_path_and_events(tmp_path):
    ex, runtime = setup(tmp_path)
    state = ex.execute(plan(PlanTask("a", "A", "echo")))
    assert state.status == "completed"
    assert any(e["event_type"] == "tool.completed" for e in runtime.list_events(ex.attempt_id))


def test_dependency_and_cycle_validation(tmp_path):
    ex, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="unknown dependency"):
        ex.execute(plan(PlanTask("b", "B", "echo", dependencies=("a",))))


def test_scope_violation(tmp_path):
    ex, _ = setup(tmp_path, read_set=("characters",))
    with pytest.raises(HarnessExecutionError, match="scope violation"):
        ex.execute(plan(PlanTask("a", "A", "echo", read_set=("world",))))


def test_budget(tmp_path):
    ex, _ = setup(tmp_path, estimated_tokens=20)
    with pytest.raises(HarnessExecutionError, match="budget"):
        ex.execute(plan(PlanTask("a", "A", "echo"), budget=Budget(10, 1, 10, 60)))


def test_approval_gate(tmp_path):
    ex, _ = setup(tmp_path, approval_policy="before_start")
    with pytest.raises(ApprovalRequired):
        ex.execute(plan(PlanTask("a", "A", "echo")))


def test_idempotent_replay(tmp_path):
    ex, runtime = setup(tmp_path)
    p = plan(PlanTask("a", "A", "echo"))
    first = ex.execute(p)
    attempt = runtime.get_attempt(ex.attempt_id)
    run = runtime.get_run(attempt["run_id"])
    replay = HarnessExecutor(registry=ex.registry, runtime=runtime, run=run, attempt=attempt, owner_id="worker", fence_token=ex.fence_token)
    assert replay.execute(p).status == "completed"
    assert len(runtime.list_tool_calls(ex.attempt_id)) == 1


def test_unknown_outcome_is_human_gated(tmp_path):
    ex, runtime = setup(tmp_path, fn=lambda task, args: (_ for _ in ()).throw(UnknownToolOutcome("provider interrupted")))
    with pytest.raises(UnknownToolOutcome):
        ex.execute(plan(PlanTask("a", "A", "echo")))
    assert runtime.get_attempt(ex.attempt_id)["status"] == "waiting_human"
