from __future__ import annotations

import pytest

from sidecar.harness.contracts import (
    AgentEvent,
    ApprovalDecision,
    ApprovalRequest,
    Budget,
    ExecutionPlan,
    PlanTask,
    ToolSpec,
)
from sidecar.harness.registry import HarnessRegistry


def test_agent_event_v1_serializes_auditable_operational_metadata() -> None:
    event = AgentEvent(
        event_id="event-1",
        run_id="run-1",
        lineage_id="lineage-1",
        attempt_id="attempt-1",
        sequence=4,
        event_type="tool.result",
        actor_kind="tool",
        actor_id="extract.characters",
        payload={"summary": "characters extracted"},
        causation_id="call-1",
        correlation_id="plan-1",
        idempotency_key="tool-result:call-1",
    )

    assert event.to_dict()["contract_version"] == "AgentEvent/v1"
    assert event.to_dict()["actor"] == {"kind": "tool", "id": "extract.characters"}


def test_tool_spec_v2_requires_scopes_and_stable_handler_reference() -> None:
    tool = ToolSpec(
        name="extract.characters",
        version="2",
        description="Extract character candidates.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        read_set=("source:chapter",),
        write_set=("proposal:characters",),
        risk="external_call",
        approval_policy="before_start",
        idempotency="required",
        handler_ref="w1.extract_characters",
    )

    assert tool.contract_version == "ToolSpec/v2"
    assert tool.to_dict()["handler_ref"] == "w1.extract_characters"
    with pytest.raises(ValueError, match="handler_ref"):
        ToolSpec(
            name="bad",
            version="2",
            description="bad",
            input_schema={},
            output_schema={},
            handler_ref="",
        )


def test_execution_plan_v2_rejects_unknown_tools_and_write_conflicts() -> None:
    tasks = (
        PlanTask(task_id="read", title="Read", tool_name="source.read"),
        PlanTask(
            task_id="write-a",
            title="Write A",
            tool_name="proposal.write",
            write_set=("proposal:characters",),
        ),
        PlanTask(
            task_id="write-b",
            title="Write B",
            tool_name="proposal.write",
            write_set=("proposal:characters",),
        ),
    )
    with pytest.raises(ValueError, match="write conflict"):
        ExecutionPlan(
            plan_id="plan-1",
            workflow_id="W1",
            tasks=tasks,
            budget=Budget(max_steps=3, max_tokens=100, max_cost_usd=1, max_seconds=30),
            completion_predicate="semantic_gate_passed",
            available_tools={"source.read", "proposal.write"},
        )

    with pytest.raises(ValueError, match="unknown tool"):
        ExecutionPlan(
            plan_id="plan-2",
            workflow_id="W1",
            tasks=(PlanTask(task_id="bad", title="Bad", tool_name="not.registered"),),
            budget=Budget(max_steps=1, max_tokens=1, max_cost_usd=0, max_seconds=1),
            completion_predicate="done",
            available_tools={"source.read"},
        )


def test_execution_plan_v2_serializes_its_validated_dag() -> None:
    plan = ExecutionPlan(
        plan_id="plan-3",
        workflow_id="W1",
        tasks=(PlanTask(task_id="read", title="Read", tool_name="source.read"),),
        budget=Budget(max_steps=1, max_tokens=10, max_cost_usd=0, max_seconds=30),
        completion_predicate="source_read",
        available_tools={"source.read"},
    )

    assert plan.to_dict()["contract_version"] == "ExecutionPlan/v2"
    assert plan.to_dict()["tasks"][0]["tool_name"] == "source.read"


def test_approval_contracts_are_versioned_and_idempotency_keyed() -> None:
    request = ApprovalRequest(
        decision_id="decision-1",
        decision_key="accept:package-1",
        run_id="run-1",
        attempt_id="attempt-1",
        action="accept_package",
        risk="high",
        summary="Accept package",
        affected_scopes=("canonical:project",),
    )
    decision = ApprovalDecision(
        decision_id="decision-1",
        decision_key=request.decision_key,
        attempt_id="attempt-1",
        decision="approve",
        actor_id="user-1",
        expected_version=1,
    )

    assert request.to_dict()["contract_version"] == "ApprovalRequest/v1"
    assert decision.to_dict()["contract_version"] == "ApprovalDecision/v1"


def test_registry_resolves_only_explicitly_versioned_tools() -> None:
    registry = HarnessRegistry()
    tool = ToolSpec(
        name="source.read",
        version="2",
        description="Read a source span.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler_ref="source.read",
    )
    registry.register_tool(tool)

    assert registry.resolve_tool("source.read", "2") is tool
    with pytest.raises(ValueError, match="not registered"):
        registry.resolve_tool("source.read", "1")
