from __future__ import annotations

import pytest

from sidecar.harness import HarnessRegistry
from sidecar.harness.workflow_adapters import (
    build_workflow_adapters,
    create_default_harness_registry,
    register_workflow_adapters,
)


def test_registers_all_workflows_and_tools() -> None:
    registry = create_default_harness_registry()
    assert set(registry._workflows) == {f"W{i}" for i in range(8)}
    for workflow_id in registry._workflows:
        adapter = registry.resolve_workflow(workflow_id)
        plan = adapter.build_plan({"lineage_id": "test"})
        adapter.validate_plan(plan)
        assert all(tool.contract_version == "ToolSpec/v2" for tool in adapter.tools())


def test_w1_has_two_compiler_gates_and_canonical_approval() -> None:
    adapter = build_workflow_adapters()["W1"]
    plan = adapter.build_plan({})
    names = [task.tool_name for task in plan.tasks]
    assert names[1:3] == ["w1.semantic_coverage_compiler", "w1.package_graph_compiler"]
    commit = next(tool for tool in adapter.tools() if tool.name == "w1.proposal_write")
    assert commit.approval_policy == "never"
    canonical = next(tool for tool in adapter.tools() if tool.name == "w1.canonical_commit")
    assert canonical.approval_policy == "before_commit"
    assert "semantic_coverage_passed" in plan.completion_predicate


def test_canonical_tool_is_always_before_commit() -> None:
    adapters = build_workflow_adapters()
    for adapter in adapters.values():
        for tool in adapter.tools():
            if tool.risk == "canonical_write":
                assert tool.approval_policy == "before_commit"


def test_shared_writes_are_ordered_by_dag() -> None:
    adapters = build_workflow_adapters()
    for adapter in adapters.values():
        plan = adapter.build_plan({})
        adapter.validate_plan(plan)
        task_by_id = {task.task_id: task for task in plan.tasks}
        for task in plan.tasks:
            for dependency in task.dependencies:
                assert dependency in task_by_id


def test_unknown_workflow_and_tool_fail_closed() -> None:
    registry = HarnessRegistry()
    register_workflow_adapters(registry)
    with pytest.raises(ValueError, match="workflow not registered"):
        registry.resolve_workflow("W8")
    with pytest.raises(ValueError, match="tool not registered"):
        registry.resolve_tool("w8.inject", "v2")


def test_injected_handler_is_the_only_execution_path() -> None:
    seen: list[dict] = []
    adapter = build_workflow_adapters({"W0": {"w0.parse_goal": lambda args: seen.append(dict(args)) or {"status": "ok"}}})["W0"]
    task = adapter.build_plan({}).tasks[0]
    assert adapter.execute_tool(task, {"goal": "test"}) == {"status": "ok"}
    assert seen == [{"goal": "test"}]
    with pytest.raises(ValueError, match="no injected handler"):
        adapter.execute_tool(adapter.build_plan({}).tasks[1], {})
