"""In-memory registry for validated, versioned harness capabilities."""

from __future__ import annotations

from typing import Mapping

from .contracts import ToolSpec, WorkflowAdapter


class HarnessRegistry:
    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], ToolSpec] = {}
        self._workflows: dict[str, WorkflowAdapter] = {}

    def register_tool(self, tool: ToolSpec) -> None:
        key = (tool.name, tool.version)
        if key in self._tools:
            raise ValueError(f"tool already registered: {tool.name}@{tool.version}")
        self._tools[key] = tool

    def resolve_tool(self, name: str, version: str) -> ToolSpec:
        try:
            return self._tools[(name, version)]
        except KeyError as error:
            raise ValueError(f"tool not registered: {name}@{version}") from error

    def tools(self) -> Mapping[tuple[str, str], ToolSpec]:
        return dict(self._tools)

    def register_workflow(self, adapter: WorkflowAdapter) -> None:
        if adapter.workflow_id in self._workflows:
            raise ValueError(f"workflow already registered: {adapter.workflow_id}")
        self._workflows[adapter.workflow_id] = adapter

    def resolve_workflow(self, workflow_id: str) -> WorkflowAdapter:
        try:
            return self._workflows[workflow_id]
        except KeyError as error:
            raise ValueError(f"workflow not registered: {workflow_id}") from error
