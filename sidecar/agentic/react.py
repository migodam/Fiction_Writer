from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Mapping, Sequence

from .models import Budget, DecisionRecord, ToolSpec
from .runtime import RuntimePort


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ValueError(f"tool not allowlisted: {name}") from error


@dataclass(frozen=True)
class ReActResult:
    stop_reason: str
    steps: int
    tokens: int
    cost: float


class ReActExecutor:
    def __init__(self, registry: ToolRegistry, budget: Budget, runtime: RuntimePort | None = None, failure_threshold: int = 3) -> None:
        self.registry = registry
        self.budget = budget
        self.runtime = runtime
        self.failure_threshold = failure_threshold

    def run(self, run_id: str, actions: Sequence[tuple[str, Mapping[str, Any]]], cancelled: Callable[[], bool] | None = None) -> ReActResult:
        started = monotonic()
        steps = tokens = 0
        cost = 0.0
        failures = 0
        for sequence, (tool_name, arguments) in enumerate(actions, start=1):
            if cancelled and cancelled():
                return ReActResult("cancelled", steps, tokens, cost)
            if monotonic() - started >= self.budget.max_seconds:
                return ReActResult("max_seconds", steps, tokens, cost)
            if steps >= self.budget.max_steps:
                return ReActResult("max_steps", steps, tokens, cost)
            spec = self.registry.get(tool_name)
            if tokens + spec.estimated_tokens > self.budget.max_tokens:
                return ReActResult("max_tokens", steps, tokens, cost)
            if cost + spec.estimated_cost > self.budget.max_cost:
                return ReActResult("max_cost", steps, tokens, cost)
            intent = {"run_id": run_id, "sequence": sequence, "tool": tool_name, "arguments": dict(arguments), "policy_version": spec.policy_version}
            if self.runtime:
                self.runtime.record_tool_intent(intent)
            try:
                output = spec.handler(arguments)
                result = {**intent, "status": "succeeded", "output": output}
                failures = 0
            except Exception as error:  # Records a concise operational error, never model reasoning.
                failures += 1
                result = {**intent, "status": "failed", "error": type(error).__name__}
            if self.runtime:
                self.runtime.record_tool_result(result)
                self.runtime.record_decision(DecisionRecord(run_id, sequence, result["status"], f"tool:{tool_name}").as_dict())
            steps += 1
            tokens += spec.estimated_tokens
            cost += spec.estimated_cost
            if failures >= self.failure_threshold:
                return ReActResult("failure_circuit_open", steps, tokens, cost)
        return ReActResult("completed", steps, tokens, cost)
