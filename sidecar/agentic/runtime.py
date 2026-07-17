from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol


class RuntimePort(Protocol):
    """The durable-runtime boundary used by agentic control flow."""

    def emit_event(self, run_id: str, event: str, payload: Mapping[str, Any]) -> None: ...
    def record_tool_intent(self, record: Mapping[str, Any]) -> None: ...
    def record_tool_result(self, record: Mapping[str, Any]) -> None: ...
    def acquire_lease(self, resource: str, owner: str) -> int | None: ...
    def release_lease(self, resource: str, owner: str, fence: int) -> None: ...
    def record_decision(self, record: Mapping[str, Any]) -> None: ...


def redact_decision_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Keep operational outcomes while excluding rationale and model traces."""
    return {
        "run_id": record.get("run_id"),
        "sequence": record.get("sequence"),
        "decision": record.get("decision"),
        "policy_version": record.get("policy_version", "v1"),
    }


class RuntimePortAdapter:
    """Maps agentic operations onto a durable runtime without storage assumptions."""

    def __init__(
        self,
        *,
        emit_event: Callable[[str, str, Mapping[str, Any]], None],
        acquire_lease: Callable[[str, str], int | None],
        release_lease: Callable[[str, str, int], None],
        record_decision: Callable[[Mapping[str, Any]], None],
        record_tool_intent: Callable[[Mapping[str, Any]], None] | None = None,
        record_tool_result: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._emit_event = emit_event
        self._acquire_lease = acquire_lease
        self._release_lease = release_lease
        self._record_decision = record_decision
        self._record_tool_intent = record_tool_intent or (lambda _: None)
        self._record_tool_result = record_tool_result or (lambda _: None)

    def emit_event(self, run_id: str, event: str, payload: Mapping[str, Any]) -> None:
        self._emit_event(run_id, event, dict(payload))

    def record_tool_intent(self, record: Mapping[str, Any]) -> None:
        self._record_tool_intent(dict(record))

    def record_tool_result(self, record: Mapping[str, Any]) -> None:
        self._record_tool_result(dict(record))

    def acquire_lease(self, resource: str, owner: str) -> int | None:
        return self._acquire_lease(resource, owner)

    def release_lease(self, resource: str, owner: str, fence: int) -> None:
        self._release_lease(resource, owner, fence)

    def record_decision(self, record: Mapping[str, Any]) -> None:
        self._record_decision(redact_decision_record(record))
