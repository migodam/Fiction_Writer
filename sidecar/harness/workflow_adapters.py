"""Declarative W0-W7 adapters for the durable Harness kernel.

Each adapter exposes existing workflow boundaries as typed tools. Handlers are
dependency-injected; this module neither copies workflow logic nor performs
network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable, Mapping, Sequence

from .contracts import Budget, ExecutionPlan, PlanTask, ToolSpec
from .registry import HarnessRegistry


Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]]
TERMINAL_FAILURES = {"failed", "blocked", "unknown_outcome", "cancelled"}


class WorkflowGateBlocked(RuntimeError):
    """Raised when a deterministic workflow gate refuses downstream work."""


@dataclass(frozen=True)
class WorkflowStepDefinition:
    task_id: str
    title: str
    tool_name: str
    dependencies: tuple[str, ...]
    read_set: tuple[str, ...]
    write_set: tuple[str, ...]
    risk: str = "draft"
    approval_policy: str = "never"
    idempotency: str = "optional"


@dataclass(frozen=True)
class WorkflowAdapterDefinition:
    workflow_id: str
    title: str
    description: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    steps: tuple[WorkflowStepDefinition, ...]
    completion_predicate: str
    handlers: Mapping[str, Handler] = field(default_factory=dict, compare=False, repr=False)
    risk: str = "draft"
    approval_policy: str = "before_commit"


class RegisteredWorkflowAdapter:
    """Deterministic WorkflowAdapter backed only by injected node handlers."""

    def __init__(self, definition: WorkflowAdapterDefinition) -> None:
        self.definition = definition
        self.workflow_id = definition.workflow_id
        self._tools = tuple(_tool_spec(definition, step) for step in definition.steps)

    def describe(self) -> Mapping[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "title": self.definition.title,
            "description": self.definition.description,
            "read_scope": list(self.definition.read_scope),
            "write_scope": list(self.definition.write_scope),
            "risk": self.definition.risk,
            "approval_policy": self.definition.approval_policy,
            "canonical_commit_owner": "human_acceptance_adapter",
            "tools": [tool.to_dict() for tool in self._tools],
        }

    def tools(self) -> tuple[ToolSpec, ...]:
        return self._tools

    def build_plan(self, context: Mapping[str, Any]) -> ExecutionPlan:
        plan_key = f"{self.workflow_id}:{context.get('lineage_id', 'default')}"
        plan_id = sha256(plan_key.encode("utf-8")).hexdigest()[:24]
        tasks = tuple(
            PlanTask(
                task_id=step.task_id,
                title=step.title,
                tool_name=step.tool_name,
                dependencies=step.dependencies,
                read_set=step.read_set,
                write_set=step.write_set,
                approval_mode=step.approval_policy,
                artifact_contract=f"{self.workflow_id}/{step.task_id}/v1",
            )
            for step in self.definition.steps
        )
        return ExecutionPlan(
            plan_id=plan_id,
            workflow_id=self.workflow_id,
            tasks=tasks,
            budget=Budget(
                max_steps=max(1, len(tasks) * 2),
                max_tokens=int(context.get("max_tokens", 0)),
                max_cost_usd=float(context.get("max_cost_usd", 0.0)),
                max_seconds=float(context.get("max_seconds", 3_600)),
            ),
            completion_predicate=self.definition.completion_predicate,
            available_tools=frozenset(tool.name for tool in self._tools),
            max_replans=int(context.get("max_replans", 2)),
        )

    def validate_plan(self, plan: ExecutionPlan) -> None:
        if plan.workflow_id != self.workflow_id:
            raise ValueError(f"plan belongs to {plan.workflow_id}, not {self.workflow_id}")
        allowed = {tool.name for tool in self._tools}
        if set(plan.available_tools) != allowed:
            raise ValueError("plan tool set differs from the adapter registry")
        for task in plan.tasks:
            if set(task.read_set) - set(self.definition.read_scope):
                raise ValueError(f"task {task.task_id} reads outside adapter scope")
            if set(task.write_set) - set(self.definition.write_scope):
                raise ValueError(f"task {task.task_id} writes outside adapter scope")

    def execute_tool(self, task: PlanTask, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        handler = self.definition.handlers.get(task.tool_name)
        if handler is None:
            raise ValueError(f"no injected handler for {task.tool_name}")
        raw_result = handler(arguments)
        if not isinstance(raw_result, Mapping):
            raise TypeError(f"handler for {task.tool_name} must return a mapping")
        result = dict(raw_result)
        result.setdefault("_harness_task_id", task.task_id)
        result.setdefault("status", "success")
        self._enforce_runtime_gate(task.task_id, result)
        return result

    def _enforce_runtime_gate(self, task_id: str, result: Mapping[str, Any]) -> None:
        status = str(result.get("status", "")).lower()
        if status in TERMINAL_FAILURES:
            raise WorkflowGateBlocked(f"{self.workflow_id} {task_id} returned {status}")
        if self.workflow_id != "W1":
            return
        if task_id == "semantic_coverage":
            verdict = str(result.get("verdict", "")).lower()
            warning_approved = bool(result.get("warning_approved"))
            if verdict == "warning" and not warning_approved:
                raise WorkflowGateBlocked("W1 semantic coverage warning requires human approval")
            if verdict not in {"pass", "warning"}:
                raise WorkflowGateBlocked("W1 semantic coverage did not pass")
        if task_id == "package_graph":
            if result.get("atomic") is not True:
                raise WorkflowGateBlocked("W1 package graph is not atomic")
            if result.get("valid") is not True:
                raise WorkflowGateBlocked("W1 package graph is invalid")

    def observe_artifact(self, artifact: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"workflow_id": self.workflow_id, "observed": dict(artifact)}

    def evaluate_completion(self, plan: ExecutionPlan, observations: Sequence[Mapping[str, Any]]) -> bool:
        by_task = {
            str(observation.get("_harness_task_id")): observation
            for observation in observations
            if isinstance(observation, Mapping)
        }
        if set(by_task) != {task.task_id for task in plan.tasks}:
            return False
        if any(str(item.get("status", "")).lower() in TERMINAL_FAILURES for item in by_task.values()):
            return False
        if self.workflow_id != "W1":
            return True
        semantic = by_task.get("semantic_coverage", {})
        package = by_task.get("package_graph", {})
        verdict = str(semantic.get("verdict", "")).lower()
        semantic_ok = verdict == "pass" or (
            verdict == "warning" and bool(semantic.get("warning_approved"))
        )
        return semantic_ok and package.get("valid") is True and package.get("atomic") is True

    def publish_proposal(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]:
        if proposal.get("canonical_write"):
            raise ValueError("canonical writes belong to the human acceptance adapter")
        return {"workflow_id": self.workflow_id, "proposal": dict(proposal), "status": "staged"}


def _tool_spec(definition: WorkflowAdapterDefinition, step: WorkflowStepDefinition) -> ToolSpec:
    return ToolSpec(
        name=step.tool_name,
        version="v2",
        description=step.title,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler_ref=f"injected:{definition.workflow_id}:{step.tool_name}",
        read_set=step.read_set,
        write_set=step.write_set,
        risk=step.risk,
        approval_policy=step.approval_policy,
        idempotency=step.idempotency,
        estimated_cost_usd=0.000001 if step.risk == "external_call" else 0.0,
        estimated_tokens=1 if step.risk == "external_call" else 0,
    )


def _step(
    task_id: str,
    title: str,
    tool_name: str,
    dependencies: tuple[str, ...],
    read_set: tuple[str, ...],
    write_set: tuple[str, ...] = (),
    *,
    external: bool = False,
) -> WorkflowStepDefinition:
    return WorkflowStepDefinition(
        task_id=task_id,
        title=title,
        tool_name=tool_name,
        dependencies=dependencies,
        read_set=read_set,
        write_set=write_set,
        risk="external_call" if external else "draft",
        idempotency="required" if external else "optional",
    )


def _definitions() -> tuple[WorkflowAdapterDefinition, ...]:
    read = ("project:source", "project:canonical", "runtime:checkpoint")
    proposal = ("runtime:proposal",)
    return (
        WorkflowAdapterDefinition(
            "W0", "Orchestrator", "Plan and dispatch child workflows", read, proposal,
            (
                _step("parse_goal", "Parse goal", "w0.parse_goal", (), read, external=True),
                _step("validate_plan", "Validate plan", "w0.validate_plan", ("parse_goal",), read, proposal),
            ),
            "all_steps_succeeded",
        ),
        WorkflowAdapterDefinition(
            "W1", "Import", "Extract evidence and stage an import package", read,
            ("runtime:proposal", "runtime:semantic_coverage", "runtime:package_graph"),
            (
                _step("extract", "Extract source windows", "w1.extract", (), read, external=True),
                _step("semantic_coverage", "Compile semantic coverage", "w1.semantic_coverage_compiler", ("extract",), read, ("runtime:semantic_coverage",)),
                _step("package_graph", "Compile package graph", "w1.package_graph_compiler", ("semantic_coverage",), read, ("runtime:package_graph",)),
                _step("proposal_write", "Stage proposal package", "w1.proposal_write", ("package_graph",), read, proposal),
            ),
            "all_tasks_succeeded_and_w1_gates_passed",
        ),
        WorkflowAdapterDefinition(
            "W2", "Manuscript sync", "Sync manuscript drafts and stage proposals", read, proposal,
            (
                _step("load", "Load manuscript", "w2.load", (), read),
                _step("diff", "Extract and diff project entities", "w2.diff", ("load",), read, proposal, external=True),
                _step("proposal", "Stage proposals", "w2.proposal", ("diff",), read, proposal),
            ),
            "all_tasks_succeeded_at_proposal_gate",
        ),
        WorkflowAdapterDefinition(
            "W3", "Writing assistant", "Generate draft content and stage entities", read, proposal,
            (
                _step("context", "Build context", "w3.context", (), read),
                _step("generate", "Generate draft", "w3.generate", ("context",), read, proposal, external=True),
                _step("proposal", "Stage proposals", "w3.proposal", ("generate",), read, proposal),
            ),
            "all_tasks_succeeded_at_proposal_gate",
        ),
        WorkflowAdapterDefinition(
            "W4", "Consistency check", "Find consistency issues and stage fixes", read, proposal,
            (
                _step("context", "Build context", "w4.context", (), read),
                _step("check", "Check consistency", "w4.check", ("context",), read, proposal, external=True),
                _step("proposal", "Stage fix proposals", "w4.proposal", ("check",), read, proposal),
            ),
            "all_tasks_succeeded_at_proposal_gate",
        ),
        WorkflowAdapterDefinition(
            "W5", "Simulation", "Run scenario analysis and stage report", read, proposal,
            (
                _step("context", "Load affected context", "w5.context", (), read),
                _step("simulate", "Run simulation", "w5.simulate", ("context",), read, proposal, external=True),
                _step("proposal", "Stage simulation report", "w5.proposal", ("simulate",), read, proposal),
            ),
            "all_tasks_succeeded_at_proposal_gate",
        ),
        WorkflowAdapterDefinition(
            "W6", "Beta reader", "Run reader analysis and stage feedback", read, proposal,
            (
                _step("context", "Build reader context", "w6.context", (), read),
                _step("analyze", "Analyze manuscript", "w6.analyze", ("context",), read, proposal, external=True),
                _step("proposal", "Stage feedback", "w6.proposal", ("analyze",), read, proposal),
            ),
            "all_tasks_succeeded_at_proposal_gate",
        ),
        WorkflowAdapterDefinition(
            "W7", "Metadata ingestion", "Extract metadata and stage updates", read, proposal,
            (
                _step("parse", "Parse metadata", "w7.parse", (), read, proposal, external=True),
                _step("proposal", "Stage metadata proposals", "w7.proposal", ("parse",), read, proposal),
            ),
            "all_tasks_succeeded_at_proposal_gate",
        ),
    )


def build_workflow_adapters(
    handlers: Mapping[str, Mapping[str, Handler]] | None = None,
) -> dict[str, RegisteredWorkflowAdapter]:
    """Build all adapters with optional dependency-injected node handlers."""
    handlers = handlers or {}
    adapters: dict[str, RegisteredWorkflowAdapter] = {}
    for definition in _definitions():
        configured = WorkflowAdapterDefinition(
            **{**definition.__dict__, "handlers": handlers.get(definition.workflow_id, {})}
        )
        adapters[definition.workflow_id] = RegisteredWorkflowAdapter(configured)
    return adapters


def register_workflow_adapters(
    registry: HarnessRegistry,
    handlers: Mapping[str, Mapping[str, Handler]] | None = None,
) -> HarnessRegistry:
    """Register W0-W7 and their ToolSpec/v2 capabilities, failing closed."""
    for adapter in build_workflow_adapters(handlers).values():
        registry.register_workflow(adapter)
        for tool in adapter.tools():
            registry.register_tool(tool)
    return registry


def create_default_harness_registry(
    handlers: Mapping[str, Mapping[str, Handler]] | None = None,
) -> HarnessRegistry:
    return register_workflow_adapters(HarnessRegistry(), handlers)
