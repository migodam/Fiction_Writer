from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from sidecar.agentic import (
    Budget,
    DurableScheduler,
    ExecutionPlan,
    MemoryItem,
    MemoryLayer,
    MemoryPolicy,
    PlanExecuteController,
    PlanTask,
    ReActExecutor,
    RuntimePortAdapter,
    RuntimePort,
    SelfAsk,
    ToolRegistry,
    ToolSpec,
)


class RecordingRuntime(RuntimePort):
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self.intents: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.leases: dict[str, tuple[str, int]] = {}
        self.available_fences: dict[str, int] = {}
        self.releases: list[tuple[str, str, int]] = []

    def emit_event(self, run_id: str, event: str, payload: dict[str, Any]) -> None:
        self.events.append((run_id, event, payload))

    def record_tool_intent(self, record: dict[str, Any]) -> None:
        self.intents.append(record)

    def record_tool_result(self, record: dict[str, Any]) -> None:
        self.results.append(record)

    def acquire_lease(self, resource: str, owner: str) -> int | None:
        if resource in self.leases:
            return None
        fence = self.available_fences.get(resource, 1)
        self.leases[resource] = (owner, fence)
        return fence

    def release_lease(self, resource: str, owner: str, fence: int) -> None:
        self.releases.append((resource, owner, fence))
        if self.leases.get(resource) == (owner, fence):
            self.leases.pop(resource)

    def record_decision(self, record: dict[str, Any]) -> None:
        self.decisions.append(record)


def task(task_id: str, *, deps: tuple[str, ...] = (), writes: tuple[str, ...] = ()) -> PlanTask:
    return PlanTask(task_id=task_id, title=task_id, dependencies=deps, write_set=writes)


def test_plan_rejects_cycles_and_missing_dependencies() -> None:
    with pytest.raises(ValueError, match="unknown dependency"):
        ExecutionPlan(plan_id="p", tasks=(task("a", deps=("missing",)),))
    with pytest.raises(ValueError, match="cycle"):
        ExecutionPlan(plan_id="p", tasks=(task("a", deps=("b",)), task("b", deps=("a",))))


def test_scheduler_serializes_write_conflicts_but_allows_reads() -> None:
    runtime = RecordingRuntime()
    scheduler = DurableScheduler(runtime, max_concurrency=2)
    plan = ExecutionPlan(plan_id="p", tasks=(task("write-a", writes=("character:1",)), task("write-b", writes=("character:1",)), task("read")))
    scheduler.submit("run", plan)
    first = scheduler.claim_ready("run")
    assert {item.task_id for item in first} == {"write-a", "read"}
    scheduler.complete("run", "read")
    scheduler.complete("run", "write-a")
    assert [item.task_id for item in scheduler.claim_ready("run")] == ["write-b"]


def test_scheduler_preserves_and_releases_each_resource_fence() -> None:
    runtime = RecordingRuntime()
    runtime.available_fences = {"character:1": 11, "timeline:2": 29}
    scheduler = DurableScheduler(runtime)
    scheduler.submit("run", ExecutionPlan(plan_id="p", tasks=(task("write", writes=("character:1", "timeline:2")),)))

    scheduled = scheduler.claim_ready("run")[0]

    assert scheduled.fences == {"character:1": 11, "timeline:2": 29}
    scheduler.complete("run", "write")
    assert runtime.releases == [("character:1", "write", 11), ("timeline:2", "write", 29)]
    assert runtime.leases == {}


def test_scheduler_rolls_back_partial_acquisition_with_the_matching_fence() -> None:
    runtime = RecordingRuntime()
    runtime.available_fences = {"character:1": 7, "timeline:2": 13}
    runtime.leases["timeline:2"] = ("other", 13)
    scheduler = DurableScheduler(runtime)
    scheduler.submit("run", ExecutionPlan(plan_id="p", tasks=(task("write", writes=("character:1", "timeline:2")),)))

    assert scheduler.claim_ready("run") == []

    assert runtime.releases == [("character:1", "write", 7)]
    assert runtime.leases == {"timeline:2": ("other", 13)}


def test_scheduler_stale_release_cannot_drop_a_newer_lease() -> None:
    runtime = RecordingRuntime()
    runtime.available_fences["character:1"] = 3
    scheduler = DurableScheduler(runtime)
    scheduler.submit("run", ExecutionPlan(plan_id="p", tasks=(task("write", writes=("character:1",)),)))
    scheduler.claim_ready("run")
    runtime.leases["character:1"] = ("write", 4)

    scheduler.complete("run", "write")

    assert runtime.releases == [("character:1", "write", 3)]
    assert runtime.leases == {"character:1": ("write", 4)}


def test_scheduler_cancellation_releases_running_resource_fences() -> None:
    runtime = RecordingRuntime()
    runtime.available_fences = {"character:1": 5, "timeline:2": 8}
    scheduler = DurableScheduler(runtime)
    scheduler.submit("run", ExecutionPlan(plan_id="p", tasks=(task("write", writes=("character:1", "timeline:2")), task("later"))))
    scheduler.claim_ready("run")

    scheduler.cancel("run")

    assert runtime.releases == [("character:1", "write", 5), ("timeline:2", "write", 8)]
    assert {letter.task_id for letter in scheduler.dead_letters("run")} == {"write", "later"}


def test_budget_step_and_time_stops() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="ok", handler=lambda _: {"ok": True}, estimated_cost=2, estimated_tokens=3))
    with pytest.raises(ValueError, match="not allowlisted"):
        registry.get("unknown")
    budget = Budget(max_steps=1, max_tokens=10, max_cost=10, max_seconds=10)
    result = ReActExecutor(registry, budget).run("run", [("ok", {}), ("ok", {})])
    assert result.stop_reason == "max_steps"
    exhausted = ReActExecutor(registry, Budget(max_steps=3, max_tokens=2, max_cost=10, max_seconds=10)).run("run", [("ok", {})])
    assert exhausted.stop_reason == "max_tokens"
    timed_out = ReActExecutor(registry, Budget(max_steps=3, max_tokens=10, max_cost=10, max_seconds=0)).run("run", [("ok", {})])
    assert timed_out.stop_reason == "max_seconds"


def test_repeated_failure_breaker_cancellation_and_deterministic_tool_records() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="bad", handler=lambda _: (_ for _ in ()).throw(RuntimeError("nope"))))
    runtime = RecordingRuntime()
    result = ReActExecutor(registry, Budget(5, 20, 20, 10), runtime=runtime, failure_threshold=2).run("run", [("bad", {}), ("bad", {}), ("bad", {})])
    assert result.stop_reason == "failure_circuit_open"
    assert len(runtime.intents) == len(runtime.results) == 2
    assert runtime.intents[0]["sequence"] == 1
    cancelled = ReActExecutor(registry, Budget(5, 20, 20, 10)).run("run", [("bad", {})], cancelled=lambda: True)
    assert cancelled.stop_reason == "cancelled"


def test_controller_replans_only_for_approved_reasons() -> None:
    controller = PlanExecuteController(lambda _: ExecutionPlan(plan_id="next", tasks=(task("a"),)))
    plan = ExecutionPlan(plan_id="initial", tasks=(task("a"),))
    assert controller.maybe_replan(plan, event="task_completed") is plan
    assert controller.maybe_replan(plan, event="new_evidence").plan_id == "next"
    assert controller.maybe_replan(plan, event="task_failed").plan_id == "next"
    assert controller.maybe_replan(plan, event="human_modified").plan_id == "next"


def test_scheduler_propagates_dependency_failure_and_cancellation_to_dead_letters() -> None:
    runtime = RecordingRuntime()
    scheduler = DurableScheduler(runtime)
    plan = ExecutionPlan(plan_id="p", tasks=(task("a"), task("b", deps=("a",))))
    scheduler.submit("run", plan)
    scheduler.claim_ready("run")
    scheduler.fail("run", "a", "tool failed")
    assert scheduler.status("run", "b") == "blocked"
    assert scheduler.dead_letters("run")[0].task_id == "b"
    scheduler.cancel("run")
    assert scheduler.status("run", "a") == "failed"


def test_scheduler_blocks_transitive_dependencies_and_records_dead_letters() -> None:
    runtime = RecordingRuntime()
    scheduler = DurableScheduler(runtime)
    plan = ExecutionPlan(plan_id="p", tasks=(task("c", deps=("b",)), task("b", deps=("a",)), task("a")))
    scheduler.submit("run", plan)
    scheduler.claim_ready("run")

    scheduler.fail("run", "a", "tool failed")

    assert scheduler.status("run", "b") == scheduler.status("run", "c") == "blocked"
    assert [(letter.task_id, letter.reason) for letter in scheduler.dead_letters("run")] == [
        ("b", "dependency_failed"),
        ("c", "dependency_failed"),
    ]


def test_runtime_adapter_maps_durable_callbacks_and_redacts_decision_records() -> None:
    events: list[tuple[str, str, dict[str, Any]]] = []
    decisions: list[dict[str, Any]] = []
    adapter = RuntimePortAdapter(
        emit_event=lambda run_id, event, payload: events.append((run_id, event, payload)),
        acquire_lease=lambda resource, owner: 17,
        release_lease=lambda resource, owner, fence: None,
        record_decision=decisions.append,
    )

    adapter.emit_event("run", "task_claimed", {"task_id": "write"})
    adapter.record_decision({"run_id": "run", "sequence": 1, "decision": "succeeded", "reason": "private reasoning", "metadata": {"trace": "hidden"}})

    assert events == [("run", "task_claimed", {"task_id": "write"})]
    assert decisions == [{"run_id": "run", "sequence": 1, "decision": "succeeded", "policy_version": "v1"}]


def test_self_ask_only_emits_unresolved_evidence_questions_with_bounds() -> None:
    ask = SelfAsk(max_questions=2, max_rounds=1)
    questions = ask.ask(("source missing", "fact known", "citation missing"), resolved={"fact known"})
    assert [question.subject for question in questions] == ["source missing", "citation missing"]
    assert ask.ask(("another missing",), resolved=set()) == ()


def test_memory_requires_provenance_redacts_and_enforces_retention() -> None:
    policy = MemoryPolicy.default()
    item = MemoryItem(layer=MemoryLayer.EPISODIC, content="contact jane@example.com", provenance="run:1", confidence=0.8)
    stored = policy.prepare(item, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert "jane@example.com" not in stored.content
    assert stored.expires_at is not None
    with pytest.raises(ValueError, match="secret"):
        policy.prepare(MemoryItem(layer=MemoryLayer.WORKING, content="api_key=secret-token", provenance="run:1", confidence=0.8))
    with pytest.raises(ValueError, match="provenance"):
        policy.prepare(MemoryItem(layer=MemoryLayer.SEMANTIC, content="fact", provenance="", confidence=0.9))
    assert policy.is_expired(stored, stored.expires_at + timedelta(seconds=1))
