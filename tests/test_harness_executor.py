from __future__ import annotations

import time
import threading
import subprocess
import sys

import pytest

from sidecar.harness.contracts import Budget, ExecutionPlan, PlanTask, ToolSpec
from sidecar.harness.executor import ApprovalRequired, HarnessExecutor, HarnessExecutionError, UnknownToolOutcome
from sidecar.harness.registry import HarnessRegistry
from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore


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


def setup(tmp_path, fn=lambda task, args: {"task": task.task_id}, *, version="1", **tool_kwargs):
    runtime = RuntimeStore(tmp_path)
    run = runtime.create_run(workflow_id="test")
    attempt = runtime.create_attempt(run["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "worker", ttl_seconds=300)
    registry = HarnessRegistry()
    registry.register_workflow(Adapter(fn))
    input_schema = tool_kwargs.pop("input_schema", {})
    output_schema = tool_kwargs.pop("output_schema", {})
    registry.register_tool(ToolSpec(
        name="echo", version=version, description="test",
        input_schema=input_schema, output_schema=output_schema,
        handler_ref="test.echo", **tool_kwargs,
    ))
    executor = HarnessExecutor(registry=registry, runtime=runtime, run=run, attempt=attempt, owner_id="worker", fence_token=lease["fence_token"])
    return executor, runtime


def restart(executor, runtime):
    attempt = runtime.get_attempt(executor.attempt_id)
    run = runtime.get_run(attempt["run_id"])
    return HarnessExecutor(
        registry=executor.registry, runtime=runtime, run=run, attempt=attempt,
        owner_id="worker", fence_token=executor.fence_token,
    )


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


def test_dependency_order_is_respected(tmp_path):
    order = []
    ex, _ = setup(tmp_path, fn=lambda task, args: (order.append(task.task_id) or {"task": task.task_id}))
    ex.registry.resolve_workflow("test").evaluate_completion = lambda plan, observations: len(observations) == 2
    state = ex.execute(plan(
        PlanTask("b", "B", "echo", dependencies=("a",)),
        PlanTask("a", "A", "echo"),
    ))
    assert state.status == "completed"
    assert order == ["a", "b"]


def test_completion_predicate_controls_completion(tmp_path):
    ex, _ = setup(tmp_path)
    ex.registry.resolve_workflow("test").evaluate_completion = lambda plan, observations: len(observations) == 2
    state = ex.execute(plan(PlanTask("a", "A", "echo"), PlanTask("b", "B", "echo")))
    assert state.status == "completed"
    assert state.completed == {"a", "b"}


def test_scope_violation(tmp_path):
    ex, _ = setup(tmp_path, read_set=("characters",))
    with pytest.raises(HarnessExecutionError, match="scope violation"):
        ex.execute(plan(PlanTask("a", "A", "echo", read_set=("world",))))


def test_tool_cannot_use_undeclared_plan_scope(tmp_path):
    ex, _ = setup(tmp_path, write_set=("canonical",))
    with pytest.raises(HarnessExecutionError, match="scope violation"):
        ex.execute(plan(PlanTask("a", "A", "echo")))


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
    replay = restart(ex, runtime)
    assert replay.execute(p).status == "completed"
    assert len(runtime.list_tool_calls(ex.attempt_id)) == 1
    second_replay = restart(ex, runtime)
    second_replay.execute(p)
    event_types = [event["event_type"] for event in runtime.list_events(ex.attempt_id)]
    assert event_types.count("tool.completed") == 1
    assert event_types.count("tool.replayed") == 1
    assert event_types.count("run.completed") == 1


def test_unknown_outcome_is_human_gated(tmp_path):
    ex, runtime = setup(tmp_path, fn=lambda task, args: (_ for _ in ()).throw(UnknownToolOutcome("provider interrupted")))
    with pytest.raises(UnknownToolOutcome):
        ex.execute(plan(PlanTask("a", "A", "echo")))
    assert runtime.get_attempt(ex.attempt_id)["status"] == "waiting_human"


def test_unknown_outcome_never_repeats_without_durable_authorization(tmp_path):
    calls = []

    def provider(task, arguments):
        calls.append(task.task_id)
        if len(calls) == 1:
            raise UnknownToolOutcome("provider interrupted")
        return {"task": task.task_id}

    ex, runtime = setup(tmp_path, fn=provider, risk="external_call")
    workflow_plan = plan(PlanTask("a", "A", "echo"))
    with pytest.raises(UnknownToolOutcome):
        ex.execute(workflow_plan)
    with pytest.raises(ApprovalRequired):
        ex.execute(workflow_plan)
    assert calls == ["a"]
    unknown = runtime.list_unknown_call_summaries(ex.attempt_id)[0]
    runtime.record_unknown_call_decision(
        ex.attempt_id, unknown["decision_key"], "authorize_retry_once"
    )
    assert restart(ex, runtime).execute(workflow_plan).status == "completed"
    assert calls == ["a", "a"]


def test_failure_retry_limit_is_enforced(tmp_path):
    calls = []

    def flaky(task, arguments):
        calls.append(task.task_id)
        raise RuntimeError("local failure")

    ex, runtime = setup(tmp_path, fn=flaky)
    workflow_plan = plan(PlanTask("a", "A", "echo", retry_limit=1))
    with pytest.raises(RuntimeError):
        ex.execute(workflow_plan)
    with pytest.raises(RuntimeError):
        restart(ex, runtime).execute(workflow_plan)
    with pytest.raises(HarnessExecutionError, match="retry limit exceeded"):
        restart(ex, runtime).execute(workflow_plan)
    assert len(calls) == 2


def test_unique_tool_version_resolves_and_ambiguous_version_fails_closed(tmp_path):
    ex, _ = setup(tmp_path, version="2")
    assert ex.execute(plan(PlanTask("a", "A", "echo"))).status == "completed"

    ambiguous, _ = setup(tmp_path / "ambiguous", version="1")
    ambiguous.registry.register_tool(ToolSpec(
        name="echo", version="2", description="test", input_schema={},
        output_schema={}, handler_ref="test.echo.v2",
    ))
    with pytest.raises(ValueError, match="ambiguous"):
        ambiguous.execute(plan(PlanTask("a", "A", "echo")))
    explicit = restart(ambiguous, ambiguous.runtime)
    assert explicit.execute(
        plan(PlanTask("a", "A", "echo")),
        {"a": {"tool_version": "2"}},
    ).status == "completed"


def test_input_and_output_schema_fail_closed(tmp_path):
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }
    ex, runtime = setup(
        tmp_path, fn=lambda task, args: {"name": 7},
        input_schema=schema, output_schema=schema,
    )
    workflow_plan = plan(PlanTask("a", "A", "echo"))
    with pytest.raises(HarnessExecutionError, match="missing required"):
        ex.execute(workflow_plan, {"a": {}})
    with pytest.raises(HarnessExecutionError, match="output.name"):
        restart(ex, runtime).execute(workflow_plan, {"a": {"name": "valid"}})


@pytest.mark.parametrize(
    ("risk", "error_type", "status"),
    [
        ("read", HarnessExecutionError, "failed"),
        ("external_call", UnknownToolOutcome, "unknown_outcome"),
    ],
)
def test_timeout_classification(tmp_path, risk, error_type, status):
    ex, runtime = setup(
        tmp_path, fn=lambda task, args: (time.sleep(0.03) or {"task": task.task_id}),
        risk=risk, timeout_seconds=0.001,
    )
    with pytest.raises(error_type, match="tool_timeout"):
        ex.execute(plan(PlanTask("a", "A", "echo")))
    assert runtime.list_tool_calls(ex.attempt_id)[0]["status"] == status


def test_plan_time_budget_caps_local_tool(tmp_path):
    ex, runtime = setup(
        tmp_path,
        fn=lambda task, args: (time.sleep(0.2) or {"task": task.task_id}),
    )
    with pytest.raises(HarnessExecutionError, match="tool_timeout"):
        ex.execute(
            plan(
                PlanTask("a", "A", "echo"),
                budget=Budget(10, 100, 10, 0.05),
            )
        )
    assert runtime.list_tool_calls(ex.attempt_id)[0]["status"] == "failed"


def test_timeout_worker_is_daemon_and_late_result_is_never_recorded(tmp_path):
    worker_daemon = []

    def slow_handler(task, arguments):
        worker_daemon.append(threading.current_thread().daemon)
        time.sleep(0.08)
        return {"task": task.task_id, "late": True}

    ex, runtime = setup(
        tmp_path, fn=slow_handler, timeout_seconds=0.005,
    )
    started = time.monotonic()
    with pytest.raises(HarnessExecutionError, match="tool_timeout"):
        ex.execute(plan(PlanTask("a", "A", "echo")))
    elapsed = time.monotonic() - started
    assert elapsed < 0.05
    assert worker_daemon == [True]

    time.sleep(0.1)
    tool_call = runtime.list_tool_calls(ex.attempt_id)[0]
    assert tool_call["status"] == "failed"
    assert tool_call["result_payload"] == {"failure_type": "HarnessExecutionError"}
    event_types = [event["event_type"] for event in runtime.list_events(ex.attempt_id)]
    assert "tool.completed" not in event_types
    assert "run.completed" not in event_types


def test_timed_out_worker_does_not_block_python_process_exit():
    script = """
import tempfile
import time
from sidecar.harness.contracts import Budget, ExecutionPlan, PlanTask, ToolSpec
from sidecar.harness.executor import HarnessExecutionError, HarnessExecutor
from sidecar.harness.registry import HarnessRegistry
from sidecar.runtime.agent_runtime import RuntimeStore

class Adapter:
    workflow_id = "exit-test"
    def validate_plan(self, plan): pass
    def execute_tool(self, task, arguments):
        time.sleep(5)
        return {"late": True}
    def evaluate_completion(self, plan, observations): return True

store = RuntimeStore(tempfile.mkdtemp())
run = store.create_run(workflow_id="exit-test")
attempt = store.create_attempt(run["run_id"])
lease = store.acquire_lease(attempt["attempt_id"], "worker", ttl_seconds=30)
registry = HarnessRegistry()
registry.register_workflow(Adapter())
registry.register_tool(ToolSpec(
    name="slow", version="1", description="slow", input_schema={},
    output_schema={}, handler_ref="test.slow", timeout_seconds=0.005,
))
executor = HarnessExecutor(
    registry=registry, runtime=store, run=run, attempt=attempt,
    owner_id="worker", fence_token=lease["fence_token"],
)
plan = ExecutionPlan(
    plan_id="exit", workflow_id="exit-test",
    tasks=(PlanTask("slow", "Slow", "slow"),),
    budget=Budget(2, 0, 0, 10), completion_predicate="done",
    available_tools=frozenset({"slow"}),
)
try:
    executor.execute(plan)
except HarnessExecutionError:
    pass
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(__file__).rsplit("/tests/", 1)[0],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_canonical_write_requires_cancellable_transaction_executor(tmp_path):
    invoked = []
    ex, runtime = setup(
        tmp_path,
        fn=lambda task, arguments: invoked.append(task.task_id) or {"ok": True},
        risk="canonical_write",
        approval_policy="before_commit",
        write_set=("canonical",),
    )
    with pytest.raises(
        HarnessExecutionError,
        match="canonical_write requires a cancellable transaction executor",
    ):
        ex.execute(
            plan(PlanTask(
                "a", "A", "echo", write_set=("canonical",),
                approval_mode="before_commit",
            ))
        )
    assert invoked == []
    assert runtime.list_tool_calls(ex.attempt_id) == []


def test_events_are_redacted(tmp_path):
    ex, runtime = setup(tmp_path, fn=lambda task, args: {
        "api_key": "sk-1234567890",
        "token": "secret-token",
        "authorization": "Bearer abcdefghijklmnop",
        "raw_prompt": "private manuscript prompt",
    })
    ex.execute(plan(PlanTask("a", "A", "echo")))
    completed = next(
        event for event in runtime.list_events(ex.attempt_id)
        if event["event_type"] == "tool.completed"
    )
    result = completed["payload"]["result"]
    assert set(result.values()) == {"[REDACTED]"}


def test_lease_lost_is_not_converted_to_tool_failure(tmp_path):
    ex, runtime = setup(
        tmp_path,
        fn=lambda task, args: (_ for _ in ()).throw(LeaseLostError("fenced")),
    )
    with pytest.raises(LeaseLostError):
        ex.execute(plan(PlanTask("a", "A", "echo")))
    assert runtime.list_tool_calls(ex.attempt_id)[0]["status"] == "intent"
