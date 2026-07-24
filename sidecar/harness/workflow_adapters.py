"""Declarative adapters for the W0-W7 workflow harness.

The adapters are deliberately thin.  They expose the existing workflow node
boundaries as typed tools and produce deterministic plans; execution remains
owned by the Harness executor and the injected node handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable, Mapping, Sequence

from .contracts import Budget, ExecutionPlan, PlanTask, ToolSpec
from .registry import HarnessRegistry


Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class WorkflowAdapterDefinition:
    workflow_id: str
    title: str
    description: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    risk: str
    approval_policy: str
    steps: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...]
    completion_predicate: str
    handlers: Mapping[str, Handler] = field(default_factory=dict, compare=False, repr=False)


class RegisteredWorkflowAdapter:
    """A deterministic WorkflowAdapter backed by injected existing handlers."""

    def __init__(self, definition: WorkflowAdapterDefinition) -> None:
        self.definition = definition
        self.workflow_id = definition.workflow_id
        self._tools = _tool_specs(definition)

    def describe(self) -> Mapping[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "title": self.definition.title,
            "description": self.definition.description,
            "read_scope": list(self.definition.read_scope),
            "write_scope": list(self.definition.write_scope),
            "risk": self.definition.risk,
            "approval_policy": self.definition.approval_policy,
            "tools": [tool.to_dict() for tool in self._tools],
        }

    def tools(self) -> tuple[ToolSpec, ...]:
        return self._tools

    def build_plan(self, context: Mapping[str, Any]) -> ExecutionPlan:
        plan_key = f"{self.workflow_id}:{context.get('lineage_id', 'default')}"
        plan_id = sha256(plan_key.encode("utf-8")).hexdigest()[:24]
        tasks = tuple(
            PlanTask(
                task_id=task_id,
                title=title,
                tool_name=tool_name,
                dependencies=dependencies,
                read_set=self.definition.read_scope,
                write_set=write_set,
                approval_mode=("before_commit" if tool_name.endswith("canonical_commit") else "never"),
                artifact_contract=f"{self.workflow_id}/{task_id}/v1",
            )
            for task_id, title, tool_name, dependencies, write_set in self.definition.steps
        )
        return ExecutionPlan(
            plan_id=plan_id,
            workflow_id=self.workflow_id,
            tasks=tasks,
            budget=Budget(
                max_steps=max(1, len(tasks) * 2),
                max_tokens=int(context.get("max_tokens", 100_000)),
                max_cost_usd=float(context.get("max_cost_usd", 10.0)),
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
        if not set(plan.available_tools) <= allowed:
            raise ValueError("plan contains tools outside the adapter registry")
        for task in plan.tasks:
            if set(task.read_set) - set(self.definition.read_scope):
                raise ValueError(f"task {task.task_id} reads outside adapter scope")
            if set(task.write_set) - set(self.definition.write_scope):
                raise ValueError(f"task {task.task_id} writes outside adapter scope")

    def execute_tool(self, task: PlanTask, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        handler = self.definition.handlers.get(task.tool_name)
        if handler is None:
            raise ValueError(f"no injected handler for {task.tool_name}")
        return handler(arguments)

    def observe_artifact(self, artifact: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"workflow_id": self.workflow_id, "observed": dict(artifact)}

    def evaluate_completion(self, plan: ExecutionPlan, observations: Sequence[Mapping[str, Any]]) -> bool:
        return bool(observations) and all(observation.get("status") not in {"failed", "blocked", "unknown_outcome"} for observation in observations)

    def publish_proposal(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]:
        if proposal.get("canonical_write"):
            raise ValueError("canonical writes must be committed through before_commit approval")
        return {"workflow_id": self.workflow_id, "proposal": dict(proposal), "status": "staged"}


def _tool_specs(definition: WorkflowAdapterDefinition) -> tuple[ToolSpec, ...]:
    specs: list[ToolSpec] = []
    for _, title, tool_name, _, _ in definition.steps:
        canonical = tool_name.endswith("canonical_commit")
        specs.append(ToolSpec(
            name=tool_name,
            version="v2",
            description=title,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler_ref=f"injected:{definition.workflow_id}:{tool_name}",
            read_set=definition.read_scope,
            write_set=definition.write_scope if canonical else (),
            risk="canonical_write" if canonical else ("external_call" if "extract" in tool_name or "generate" in tool_name else "draft"),
            approval_policy="before_commit" if canonical else "never",
            idempotency="required" if canonical or "extract" in tool_name else "optional",
        ))
    specs.append(ToolSpec(
        name=f"{definition.workflow_id.lower()}.canonical_commit",
        version="v2",
        description="Commit an approved proposal package to canonical storage",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler_ref=f"injected:{definition.workflow_id}:canonical_commit",
        read_set=("runtime:proposal",),
        write_set=("project:canonical",),
        risk="canonical_write",
        approval_policy="before_commit",
        idempotency="required",
    ))
    return tuple(specs)


def _definition(workflow_id: str, title: str, description: str, read_scope: tuple[str, ...], write_scope: tuple[str, ...], steps: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...], predicate: str) -> WorkflowAdapterDefinition:
    return WorkflowAdapterDefinition(workflow_id, title, description, read_scope, write_scope, "canonical_write", "before_commit", steps, predicate)


def build_workflow_adapters(handlers: Mapping[str, Mapping[str, Handler]] | None = None) -> dict[str, RegisteredWorkflowAdapter]:
    """Build all adapters.  ``handlers`` is dependency injection only."""
    handlers = handlers or {}
    common = {
        "read": ("project:source", "project:canonical", "runtime:checkpoint"),
        "proposal": ("runtime:proposal",),
    }
    definitions = (
        _definition("W0", "Orchestrator", "Plan and dispatch child workflows", common["read"], ("runtime:proposal",), (("parse_goal", "Parse goal", "w0.parse_goal", (), ()), ("validate_plan", "Validate plan", "w0.validate_plan", ("parse_goal",), ("runtime:proposal",))), "all_steps_valid"),
        _definition("W1", "Import", "Extract evidence and stage an import package", common["read"], ("runtime:proposal", "runtime:semantic_coverage", "runtime:package_graph"), (("extract", "Extract source windows", "w1.extract", (), ()), ("semantic_coverage", "Compile semantic coverage", "w1.semantic_coverage_compiler", ("extract",), ("runtime:semantic_coverage",)), ("package_graph", "Compile package graph", "w1.package_graph_compiler", ("semantic_coverage",), ("runtime:package_graph",)), ("proposal_write", "Stage proposal package", "w1.proposal_write", ("package_graph",), ("runtime:proposal",))), "semantic_coverage_passed_and_package_graph_valid"),
        _definition("W2", "Manuscript sync", "Sync manuscript drafts and stage proposals", common["read"], common["proposal"], (("load", "Load manuscript", "w2.load", (), ()), ("diff", "Diff project", "w2.diff", ("load",), ("runtime:proposal",)), ("proposal", "Stage proposals", "w2.proposal", ("diff",), common["proposal"])), "proposal_gate_ready"),
        _definition("W3", "Writing assistant", "Generate draft content and stage entities", common["read"], common["proposal"], (("context", "Build context", "w3.context", (), ()), ("generate", "Generate draft", "w3.generate", ("context",), ("runtime:proposal",)), ("proposal", "Stage proposals", "w3.proposal", ("generate",), common["proposal"])), "proposal_gate_ready"),
        _definition("W4", "Consistency check", "Find consistency issues and stage fixes", common["read"], common["proposal"], (("context", "Build context", "w4.context", (), ()), ("check", "Check consistency", "w4.check", ("context",), ("runtime:proposal",)), ("proposal", "Stage fix proposals", "w4.proposal", ("check",), common["proposal"])), "proposal_gate_ready"),
        _definition("W5", "Simulation", "Run scenario analysis and stage report", common["read"], common["proposal"], (("context", "Load affected context", "w5.context", (), ()), ("simulate", "Run simulation", "w5.simulate", ("context",), ("runtime:proposal",)), ("proposal", "Stage simulation report", "w5.proposal", ("simulate",), common["proposal"])), "proposal_gate_ready"),
        _definition("W6", "Beta reader", "Run reader analysis and stage feedback", common["read"], common["proposal"], (("context", "Build reader context", "w6.context", (), ()), ("analyze", "Analyze manuscript", "w6.analyze", ("context",), ("runtime:proposal",)), ("proposal", "Stage feedback", "w6.proposal", ("analyze",), common["proposal"])), "proposal_gate_ready"),
        _definition("W7", "Metadata ingestion", "Extract metadata and stage updates", common["read"], common["proposal"], (("parse", "Parse metadata", "w7.parse", (), ()), ("proposal", "Stage metadata proposals", "w7.proposal", ("parse",), common["proposal"])), "proposal_gate_ready"),
    )
    return {definition.workflow_id: RegisteredWorkflowAdapter(WorkflowAdapterDefinition(**{**definition.__dict__, "handlers": handlers.get(definition.workflow_id, {})})) for definition in definitions}


def register_workflow_adapters(registry: HarnessRegistry, handlers: Mapping[str, Mapping[str, Handler]] | None = None) -> HarnessRegistry:
    """Register W0-W7 and their ToolSpec/v2 capabilities, failing closed."""
    for adapter in build_workflow_adapters(handlers).values():
        registry.register_workflow(adapter)
        for tool in adapter.tools():
            registry.register_tool(tool)
    return registry


def create_default_harness_registry(handlers: Mapping[str, Mapping[str, Handler]] | None = None) -> HarnessRegistry:
    return register_workflow_adapters(HarnessRegistry(), handlers)
