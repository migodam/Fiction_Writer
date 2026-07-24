"""Small policy hooks used by the constrained Harness executor.

Hooks are deliberately synchronous and side-effect free.  They make policy
decisions testable without introducing an LLM or a second orchestration loop.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from .contracts import ExecutionPlan, PlanTask, ToolSpec


class HarnessPolicyError(RuntimeError):
    pass


def enforce_scopes(task: PlanTask, tool: ToolSpec) -> None:
    """Require the plan and registered tool to agree on every access scope."""
    task_reads, tool_reads = set(task.read_set), set(tool.read_set)
    task_writes, tool_writes = set(task.write_set), set(tool.write_set)
    if task_reads != tool_reads or task_writes != tool_writes:
        raise HarnessPolicyError(
            "scope violation: "
            f"task_reads={sorted(task_reads)} tool_reads={sorted(tool_reads)} "
            f"task_writes={sorted(task_writes)} tool_writes={sorted(tool_writes)}"
        )


def enforce_budget(plan: ExecutionPlan, *, steps: int, tokens: int, cost_usd: float, elapsed_seconds: float) -> None:
    budget = plan.budget
    if steps >= budget.max_steps:
        raise HarnessPolicyError("step budget exceeded")
    if tokens > budget.max_tokens:
        raise HarnessPolicyError("token budget exceeded")
    if cost_usd > budget.max_cost_usd:
        raise HarnessPolicyError("cost budget exceeded")
    if elapsed_seconds > budget.max_seconds:
        raise HarnessPolicyError("time budget exceeded")


def completion_predicate(name: str, plan: ExecutionPlan, observations: list[Mapping[str, Any]], adapter: Any) -> bool:
    """Evaluate only an explicit adapter predicate; never interpret model text."""
    if not name or name != plan.completion_predicate:
        raise HarnessPolicyError("completion predicate mismatch")
    return bool(adapter.evaluate_completion(plan, observations))


ApprovalChecker = Callable[[PlanTask, ToolSpec], bool]


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|token|"
    r"raw[_-]?prompt|prompt[_-]?(?:body|text)|hidden[_-]?reasoning|chain[_-]?of[_-]?thought)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}\b|\bBearer\s+[A-Za-z0-9._-]{8,}\b)",
    re.IGNORECASE,
)


def redact_event_payload(value: Any) -> Any:
    """Remove credentials and private prompt/reasoning fields before durability."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _SENSITIVE_KEY.search(str(key))
            else redact_event_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_event_payload(item) for item in value]
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        return "[REDACTED]"
    return value


def validate_json_schema(value: Any, schema: Mapping[str, Any], *, label: str) -> None:
    """Validate the JSON-Schema subset used by Harness tool contracts."""
    if not schema:
        return
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        raise HarnessPolicyError(f"{label} schema type mismatch: expected {expected}")
    if expected == "object" or "properties" in schema or "required" in schema:
        if not isinstance(value, Mapping):
            raise HarnessPolicyError(f"{label} schema requires object")
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise HarnessPolicyError(f"{label} schema properties must be an object")
        required = schema.get("required", ())
        if not isinstance(required, (list, tuple)) or not all(
            isinstance(item, str) for item in required
        ):
            raise HarnessPolicyError(f"{label} schema required must be a string array")
        missing = [item for item in required if item not in value]
        if missing:
            raise HarnessPolicyError(f"{label} schema missing required: {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise HarnessPolicyError(
                    f"{label} schema additional properties: {sorted(extras)}"
                )
        for key, property_schema in properties.items():
            if key in value:
                if not isinstance(property_schema, Mapping):
                    raise HarnessPolicyError(
                        f"{label} schema property {key} must be an object"
                    )
                validate_json_schema(
                    value[key], property_schema, label=f"{label}.{key}"
                )
    if expected == "array" and "items" in schema:
        item_schema = schema["items"]
        if not isinstance(item_schema, Mapping):
            raise HarnessPolicyError(f"{label} schema items must be an object")
        for index, item in enumerate(value):
            validate_json_schema(item, item_schema, label=f"{label}[{index}]")


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    mapping = {
        "object": lambda item: isinstance(item, Mapping),
        "array": lambda item: isinstance(item, (list, tuple)),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    validator = mapping.get(expected)
    if validator is None:
        raise HarnessPolicyError(f"unsupported schema type: {expected}")
    return validator(value)
