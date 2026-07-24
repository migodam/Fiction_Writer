from __future__ import annotations

from collections.abc import Mapping

import pytest

from sidecar.harness import HarnessRegistry
from sidecar.harness.executor import HarnessExecutionError, HarnessExecutor
from sidecar.harness.workflow_adapters import (
    WorkflowGateBlocked,
    build_workflow_adapters,
    create_default_harness_registry,
    register_workflow_adapters,
)
from sidecar.runtime.agent_runtime import RuntimeStore


def _executor(tmp_path, registry: HarnessRegistry, workflow_id: str) -> tuple[HarnessExecutor, RuntimeStore]:
    runtime = RuntimeStore(tmp_path)
    run = runtime.create_run(workflow_id=workflow_id)
    attempt = runtime.create_attempt(run["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "r6-test", ttl_seconds=60)
    return (
        HarnessExecutor(
            registry=registry,
            runtime=runtime,
            run=run,
            attempt=attempt,
            owner_id="r6-test",
            fence_token=lease["fence_token"],
        ),
        runtime,
    )


def _success_handlers(workflow_id: str, task_ids: tuple[str, ...], order: list[str]) -> dict[str, dict[str, object]]:
    tool_suffixes = {
        "semantic_coverage": "semantic_coverage_compiler",
        "package_graph": "package_graph_compiler",
    }

    def handler(task_id: str):
        def run(_arguments: Mapping[str, object]) -> dict[str, object]:
            order.append(task_id)
            if task_id == "semantic_coverage":
                return {"verdict": "pass"}
            if task_id == "package_graph":
                return {"valid": True, "atomic": True}
            return {"status": "success"}

        return run

    return {
        workflow_id: {
            f"{workflow_id.lower()}.{tool_suffixes.get(task_id, task_id)}": handler(task_id)
            for task_id in task_ids
        }
    }


def test_registers_all_workflows_and_tools() -> None:
    registry = create_default_harness_registry()
    assert set(registry._workflows) == {f"W{i}" for i in range(8)}
    for workflow_id in registry._workflows:
        adapter = registry.resolve_workflow(workflow_id)
        plan = adapter.build_plan({"lineage_id": "test"})
        adapter.validate_plan(plan)
        assert all(tool.contract_version == "ToolSpec/v2" for tool in adapter.tools())


def test_plan_and_tool_specs_share_exact_scopes() -> None:
    for adapter in build_workflow_adapters().values():
        plan = adapter.build_plan({})
        tools = {tool.name: tool for tool in adapter.tools()}
        for task in plan.tasks:
            assert tools[task.tool_name].read_set == task.read_set
            assert tools[task.tool_name].write_set == task.write_set


def test_w1_has_ordered_two_compiler_gates() -> None:
    adapter = build_workflow_adapters()["W1"]
    plan = adapter.build_plan({})
    names = [task.tool_name for task in plan.tasks]
    assert names == [
        "w1.extract",
        "w1.semantic_coverage_compiler",
        "w1.package_graph_compiler",
        "w1.proposal_write",
    ]
    assert plan.tasks[2].dependencies == ("semantic_coverage",)
    assert plan.tasks[3].dependencies == ("package_graph",)


def test_canonical_commit_is_not_model_available() -> None:
    for adapter in build_workflow_adapters().values():
        plan = adapter.build_plan({})
        assert not any(name.endswith("canonical_commit") for name in plan.available_tools)
        assert adapter.describe()["canonical_commit_owner"] == "human_acceptance_adapter"
        assert adapter.describe()["approval_policy"] == "before_commit"


@pytest.mark.parametrize(
    "tool_name",
    [
        "w0.parse_goal",
        "w1.extract",
        "w2.diff",
        "w3.generate",
        "w4.check",
        "w5.simulate",
        "w6.analyze",
        "w7.parse",
    ],
)
def test_real_provider_nodes_are_external_and_idempotent(tool_name: str) -> None:
    workflow_id = tool_name.split(".", 1)[0].upper()
    tool = next(
        item for item in build_workflow_adapters()[workflow_id].tools()
        if item.name == tool_name
    )
    assert tool.risk == "external_call"
    assert tool.idempotency == "required"


def test_default_external_budget_fails_closed(tmp_path) -> None:
    order: list[str] = []
    handlers = _success_handlers("W0", ("parse_goal", "validate_plan"), order)
    registry = create_default_harness_registry(handlers)
    executor, _ = _executor(tmp_path, registry, "W0")
    with pytest.raises(HarnessExecutionError, match="budget exceeded"):
        executor.execute(registry.resolve_workflow("W0").build_plan({}))
    assert order == []
    assert registry.resolve_workflow("W0").build_plan({}).budget.max_seconds == 300


def test_harness_executor_runs_full_w0_dag_without_scope_violation(tmp_path) -> None:
    order: list[str] = []
    task_ids = ("parse_goal", "validate_plan")
    registry = create_default_harness_registry(_success_handlers("W0", task_ids, order))
    executor, _ = _executor(tmp_path, registry, "W0")
    plan = registry.resolve_workflow("W0").build_plan(
        {"max_cost_usd": 1, "max_tokens": 100}
    )
    state = executor.execute(plan)
    assert state.status == "completed"
    assert state.completed == set(task_ids)
    assert order == list(task_ids)


def test_harness_executor_runs_full_w1_dag_and_both_gates(tmp_path) -> None:
    order: list[str] = []
    task_ids = ("extract", "semantic_coverage", "package_graph", "proposal_write")
    registry = create_default_harness_registry(_success_handlers("W1", task_ids, order))
    executor, _ = _executor(tmp_path, registry, "W1")
    plan = registry.resolve_workflow("W1").build_plan(
        {"max_cost_usd": 1, "max_tokens": 100}
    )
    state = executor.execute(plan)
    assert state.status == "completed"
    assert state.completed == set(task_ids)
    assert order == list(task_ids)


def test_w1_reviewable_warning_stages_package_for_human_action(tmp_path) -> None:
    order: list[str] = []
    handlers = _success_handlers(
        "W1", ("extract", "semantic_coverage", "package_graph", "proposal_write"), order
    )
    handlers["W1"]["w1.semantic_coverage_compiler"] = lambda _arguments: (
        order.append("semantic_coverage")
        or {
            "verdict": "warning",
            "warning_approved": True,
            "acceptance_policy": {
                "requires_human_review": True,
                "automatic_acceptance": False,
            },
            "artifact_ref": {
                "relativePath": "system/imports/run/semantic_coverage.json",
                "sha256": "a" * 64,
                "contractVersion": "SemanticCoverage/v1",
            },
        }
    )
    registry = create_default_harness_registry(handlers)
    executor, runtime = _executor(tmp_path, registry, "W1")
    plan = registry.resolve_workflow("W1").build_plan(
        {"max_cost_usd": 1, "max_tokens": 100}
    )
    state = executor.execute(plan)
    assert state.status == "completed"
    assert order == ["extract", "semantic_coverage", "package_graph", "proposal_write"]
    semantic_call = next(
        call for call in runtime.list_tool_calls(executor.attempt_id)
        if call["tool_name"] == "w1.semantic_coverage_compiler"
    )
    assert semantic_call["result_payload"]["completion_mode"] == "requires_human_action"
    assert semantic_call["result_payload"]["canonical_acceptance_allowed"] is False
    assert not any(name.endswith("canonical_commit") for name in plan.available_tools)


@pytest.mark.parametrize(
    "semantic_result",
    [
        {"verdict": "blocked"},
        {"verdict": "pass", "status": "unknown_outcome"},
    ],
)
def test_w1_blocked_semantic_gate_stops_before_package_graph(
    tmp_path, semantic_result: dict[str, object]
) -> None:
    order: list[str] = []

    def record(name: str, result: dict[str, object]):
        def run(_arguments: Mapping[str, object]) -> dict[str, object]:
            order.append(name)
            return result

        return run

    handlers = {
        "W1": {
            "w1.extract": record("extract", {"status": "success"}),
            "w1.semantic_coverage_compiler": record("semantic_coverage", semantic_result),
            "w1.package_graph_compiler": record("package_graph", {"valid": True, "atomic": True}),
            "w1.proposal_write": record("proposal_write", {"status": "success"}),
        }
    }
    registry = create_default_harness_registry(handlers)
    executor, runtime = _executor(tmp_path, registry, "W1")
    plan = registry.resolve_workflow("W1").build_plan(
        {"max_cost_usd": 1, "max_tokens": 100}
    )
    with pytest.raises(WorkflowGateBlocked):
        executor.execute(plan)
    assert order == ["extract", "semantic_coverage"]
    assert runtime.get_attempt(executor.attempt_id)["status"] != "completed"


@pytest.mark.parametrize(
    "semantic_result",
    [
        {
            "verdict": "warning",
            "acceptance_policy": {
                "requires_human_review": False,
                "automatic_acceptance": False,
            },
            "artifact_ref": {
                "relativePath": "coverage.json",
                "sha256": "a" * 64,
                "contractVersion": "SemanticCoverage/v1",
            },
        },
        {
            "verdict": "warning",
            "acceptance_policy": {
                "requires_human_review": True,
                "automatic_acceptance": True,
            },
            "artifact_ref": {
                "relativePath": "coverage.json",
                "sha256": "a" * 64,
                "contractVersion": "SemanticCoverage/v1",
            },
        },
        {
            "verdict": "warning",
            "warning_approved": True,
            "acceptance_policy": {
                "requires_human_review": True,
                "automatic_acceptance": False,
            },
            "artifact_ref": {
                "relativePath": "../coverage.json",
                "sha256": "not-a-sha256",
                "contractVersion": "SemanticCoverage/v1",
            },
        },
    ],
)
def test_w1_warning_requires_durable_review_policy_and_artifact(
    tmp_path, semantic_result: dict[str, object]
) -> None:
    order: list[str] = []
    handlers = _success_handlers(
        "W1", ("extract", "semantic_coverage", "package_graph", "proposal_write"), order
    )
    handlers["W1"]["w1.semantic_coverage_compiler"] = (
        lambda _arguments: order.append("semantic_coverage") or semantic_result
    )
    registry = create_default_harness_registry(handlers)
    executor, _ = _executor(tmp_path, registry, "W1")
    plan = registry.resolve_workflow("W1").build_plan(
        {"max_cost_usd": 1, "max_tokens": 100}
    )
    with pytest.raises(WorkflowGateBlocked, match="reviewable artifact"):
        executor.execute(plan)
    assert order == ["extract", "semantic_coverage"]


def test_w1_non_atomic_package_stops_before_proposal_write(tmp_path) -> None:
    order: list[str] = []
    handlers = _success_handlers(
        "W1", ("extract", "semantic_coverage", "package_graph", "proposal_write"), order
    )
    handlers["W1"]["w1.package_graph_compiler"] = (
        lambda _arguments: order.append("package_graph") or {"valid": True, "atomic": False}
    )
    registry = create_default_harness_registry(handlers)
    executor, _ = _executor(tmp_path, registry, "W1")
    plan = registry.resolve_workflow("W1").build_plan(
        {"max_cost_usd": 1, "max_tokens": 100}
    )
    with pytest.raises(WorkflowGateBlocked, match="not atomic"):
        executor.execute(plan)
    assert order == ["extract", "semantic_coverage", "package_graph"]


def test_unknown_workflow_tool_and_missing_handler_fail_closed() -> None:
    registry = HarnessRegistry()
    register_workflow_adapters(registry)
    with pytest.raises(ValueError, match="workflow not registered"):
        registry.resolve_workflow("W8")
    with pytest.raises(ValueError, match="tool not registered"):
        registry.resolve_tool("w8.inject", "v2")
    adapter = registry.resolve_workflow("W0")
    with pytest.raises(ValueError, match="no injected handler"):
        adapter.execute_tool(adapter.build_plan({}).tasks[0], {})
