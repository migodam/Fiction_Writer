"""Durable Harness observer for the existing W1 execution engines.

The supervisor and the compatibility StateGraph remain the only executors of
W1 business logic.  This adapter does not issue model calls or accept
proposals.  It observes real node boundaries, validates the declared route,
and records redacted ``AgentEvent/v1`` plus checkpoint metadata for recovery.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, AsyncIterable, AsyncIterator, Iterable, Mapping
from uuid import uuid4

from sidecar.harness.contracts import AgentEvent, Budget, ExecutionPlan, PlanTask, ToolSpec
from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore


CONTENT_ONLY = "content_only"
IMPORT_ALL = "import_all"
SUPERVISOR = "supervisor"
COMPATIBILITY_DIRECT = "compatibility_direct"
STAGED_PROPOSAL_PUBLICATION = "runtime:proposal"
ALLOWED_TOOLS = frozenset({"execute_next_node", "rerun_failed_window", "ask_missing_evidence", "stop_at_proposal_gate"})
REPLAN_EVENTS = frozenset({"new_evidence", "task_failed", "human_modified"})

_READ_SCOPE = ("project:source", "project:canonical", "runtime:checkpoint")
_DRAFT_SCOPE = ("runtime:proposal",)
_SUPERVISOR_NODES = (
    "validate_file", "extract_windows", "reduce_repair", "architect_timeline",
    "qa_review", "judge_import", "proposal_write", "done",
)
_DIRECT_NODES = (
    "validate_file", "load_or_init_checkpoint", "split_chunks", "process_chunks",
    "resolve_low_confidence", "build_manuscript", "synthesize_relationships",
    "classify_character_tags", "infer_world_settings", "build_evidence_cards",
    "reconcile_entities", "architect_timeline", "organize_world_items",
    "generate_import_todos", "review_import", "write_to_project",
)
_CONTENT_NODES = (
    "validate_file", "load_or_init_checkpoint", "split_chunks", "build_manuscript",
    "generate_import_todos", "review_import", "write_to_project",
)
_TERMINAL_FAILURE_NODES = frozenset({"error", "planner_stop", "budget_stop"})
_REPEATABLE_NODES = frozenset({"extract_windows", "qa_review", "judge_import"})
# Older supervisor builds may surface these as progress-only events. They are
# not stable graph boundaries, so observing them must not impose dependencies.
_OPTIONAL_SUPERVISOR_OBSERVATIONS = frozenset({"split_chunks", "segment_manifest"})


class W1AgenticTransitionError(RuntimeError):
    """A stream update fell outside the declared W1 Harness route."""


@dataclass(frozen=True)
class ToolDecision:
    tool_name: str
    reason: str
    evidence: dict[str, str]
    stopped: bool = False


def _route(import_mode: str, execution_mode: str = "") -> str:
    if import_mode == "import_content_only":
        return CONTENT_ONLY
    if import_mode != IMPORT_ALL:
        raise ValueError(f"unsupported W1 import mode: {import_mode}")
    if execution_mode in {"", SUPERVISOR}:
        return SUPERVISOR
    if execution_mode == COMPATIBILITY_DIRECT:
        return COMPATIBILITY_DIRECT
    raise ValueError(f"unsupported W1 execution mode: {execution_mode}")


def _nodes_for_route(route: str) -> tuple[str, ...]:
    if route == SUPERVISOR:
        return _SUPERVISOR_NODES
    if route == CONTENT_ONLY:
        return _CONTENT_NODES
    return _DIRECT_NODES


def _tool_name(node_name: str) -> str:
    return f"w1.observe.{node_name}"


def build_execution_plan(
    import_mode: str,
    *,
    execution_mode: str = "",
    window_ids: Iterable[str] = (),
) -> ExecutionPlan:
    """Declare the actual W1 node route using the v2 Harness contract.

    ``window_ids`` remains accepted for callers from the former adapter but is
    deliberately not a plan input: the supervisor owns bounded parallel window
    scheduling and retry policy.
    """
    del window_ids
    route = _route(import_mode, execution_mode)
    nodes = _nodes_for_route(route)
    tasks: list[PlanTask] = []
    for index, node_name in enumerate(nodes):
        writes = _DRAFT_SCOPE if node_name in {"proposal_write", "write_to_project"} else ()
        dependencies = _dependencies_for(route, nodes, index)
        tasks.append(PlanTask(
            task_id=node_name,
            title=node_name.replace("_", " ").title(),
            tool_name=_tool_name(node_name),
            dependencies=dependencies,
            read_set=_READ_SCOPE,
            write_set=writes,
            artifact_contract=f"W1/{route}/{node_name}/v1",
        ))
    plan_key = f"W1\0{route}\0" + "\0".join(nodes)
    return ExecutionPlan(
        plan_id=f"w1-{route}-{hashlib.sha256(plan_key.encode()).hexdigest()[:16]}",
        workflow_id="W1",
        tasks=tuple(tasks),
        budget=Budget(max_steps=max(1, len(tasks) * 4), max_tokens=0, max_cost_usd=0.0, max_seconds=86_400),
        completion_predicate="observed_graph_reached_proposal_gate",
        available_tools=frozenset(_tool_name(node_name) for node_name in nodes),
        max_replans=3,
        policy_version="w1-observer-v2",
    )


def _dependencies_for(route: str, nodes: tuple[str, ...], index: int) -> tuple[str, ...]:
    """Declare only observable supervisor dependencies.

    ``split_chunks`` and ``segment_manifest`` are internal supervisor work and
    currently do not have a stable stream event.  In an empty-window run the
    next observable result after validation is ``reduce_repair``; it must not
    be rejected merely because there was no extraction event.
    """
    node_name = nodes[index]
    if route != SUPERVISOR:
        return () if index == 0 else (nodes[index - 1],)
    dependencies: dict[str, tuple[str, ...]] = {
        "validate_file": (),
        "extract_windows": ("validate_file",),
        "reduce_repair": ("validate_file",),
        "architect_timeline": ("reduce_repair",),
        "qa_review": ("architect_timeline",),
        "judge_import": ("qa_review",),
        "proposal_write": ("judge_import",),
        "done": ("proposal_write",),
    }
    return dependencies[node_name]


def _tool_specs(plan: ExecutionPlan) -> dict[str, ToolSpec]:
    specs: dict[str, ToolSpec] = {}
    for task in plan.tasks:
        specs[task.task_id] = ToolSpec(
            name=task.tool_name,
            version="v2",
            description=task.title,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler_ref=f"observer:{task.task_id}",
            read_set=task.read_set,
            write_set=task.write_set,
            risk="draft",
            idempotency="required",
        )
    return specs


class W1AgenticAdapter:
    """Observer bridge between W1 graph streams and the durable Harness."""

    def __init__(
        self,
        *,
        import_mode: str,
        execution_mode: str = "",
        runtime_store: RuntimeStore | None = None,
        run_id: str | None = None,
        attempt_id: str | None = None,
        lineage_id: str | None = None,
        worker_id: str = "w1-agentic-observer",
        fence_token: int | None = None,
        checkpoint_observer: bool = False,
        lease_ttl_seconds: float = 60,
        window_ids: Iterable[str] = (),
        **_: Any,
    ) -> None:
        self.route = _route(import_mode, execution_mode)
        self.plan = build_execution_plan(import_mode, execution_mode=self.route, window_ids=window_ids)
        self.tools = _tool_specs(self.plan)
        self.runtime_store = runtime_store
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.lineage_id = lineage_id
        self.worker_id = worker_id
        self.fence_token = fence_token
        self.checkpoint_observer = checkpoint_observer
        self.lease_ttl_seconds = lease_ttl_seconds
        self._completed: set[str] = set()
        self._occurrences: dict[str, int] = {}
        self._sequence = 0
        self._checkpoint_sequence = 0
        self._parent_checkpoint_id: str | None = None
        self._last_node = ""
        self._decisions = 0
        self._initialize_durable_state()

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "W1AgenticAdapter":
        context = config.get("context") if isinstance(config.get("context"), Mapping) else {}
        runtime_store = config.get("runtime_store")
        attempt_id = str(config.get("attempt_id") or context.get("w1_attempt_id") or "") or None
        attempt = runtime_store.get_attempt(attempt_id) if runtime_store and attempt_id else None
        run = runtime_store.get_run(attempt["run_id"]) if runtime_store and attempt else None
        import_mode = str(config.get("import_mode", IMPORT_ALL))
        execution_mode = str(
            config.get("execution_mode")
            or context.get("execution_mode")
            or (COMPATIBILITY_DIRECT if config.get("compatibility_mode") or context.get("compatibility_mode") else "")
        )
        return cls(
            import_mode=import_mode,
            execution_mode=execution_mode,
            runtime_store=runtime_store,
            run_id=(run or {}).get("run_id"),
            attempt_id=attempt_id,
            lineage_id=(run or {}).get("lineage_id"),
            worker_id=str(config.get("runtime_owner_id") or "w1-agentic-observer"),
            fence_token=config.get("runtime_fence_token"),
            checkpoint_observer=_route(import_mode, execution_mode) == SUPERVISOR,
            lease_ttl_seconds=float(config.get("runtime_lease_ttl_seconds", 60)),
            window_ids=config.get("prompt_window_ids") or (),
        )

    def before_run(self) -> ExecutionPlan:
        return self.plan

    async def observe_stream(self, updates: AsyncIterable[Mapping[str, Any]]) -> AsyncIterator[Mapping[str, Any]]:
        self.before_run()
        stop = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(stop))
        stream = updates.__aiter__()
        try:
            while True:
                update_task = asyncio.create_task(anext(stream))
                done, _ = await asyncio.wait({update_task, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    update_task.cancel()
                    await asyncio.gather(update_task, return_exceptions=True)
                    heartbeat.result()
                try:
                    update = update_task.result()
                except StopAsyncIteration:
                    break
                node_name = self._node_name(update)
                if node_name:
                    self._last_node = node_name
                    self.on_node_yielded(node_name, update)
                yield update
            self.on_completion()
        except BaseException as error:
            self.on_failure(self._last_node, error)
            raise
        finally:
            stop.set()
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(self, stop: asyncio.Event) -> None:
        if not self.runtime_store or not self.attempt_id or self.fence_token is None:
            await stop.wait()
            return
        interval = max(0.25, self.lease_ttl_seconds / 3)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                self.runtime_store.heartbeat_lease(
                    self.attempt_id, self.worker_id, self.fence_token,
                    ttl_seconds=self.lease_ttl_seconds,
                )

    def on_node_yielded(self, node_name: str, payload: Mapping[str, Any] | None = None) -> None:
        if node_name in _TERMINAL_FAILURE_NODES:
            self.on_failure(node_name, W1AgenticTransitionError(node_name))
            return
        if self.route == SUPERVISOR and node_name in _OPTIONAL_SUPERVISOR_OBSERVATIONS:
            self._observe_optional_node(node_name, payload or {})
            return
        task = self._validate_transition(node_name)
        occurrence = self._next_occurrence(node_name)
        key = f"w1-observer:{self.attempt_id or 'local'}:{node_name}:{occurrence}"
        self._emit("tool.started", task, {"node": node_name, "route": self.route}, f"{key}:start")
        summary = _summary(payload or {})
        self._emit("tool.result", task, {"node": node_name, "route": self.route, **summary}, f"{key}:result")
        self._completed.add(node_name)
        if self.checkpoint_observer:
            self._record_checkpoint(node_name, summary)

    def _observe_optional_node(self, node_name: str, payload: Mapping[str, Any]) -> None:
        """Persist compatibility progress without making it a DAG prerequisite."""
        task = PlanTask(
            task_id=f"optional_{node_name}", title=node_name.replace("_", " ").title(),
            tool_name=_tool_name(node_name), read_set=_READ_SCOPE,
        )
        spec = ToolSpec(
            name=task.tool_name, version="v2", description=task.title,
            input_schema={"type": "object"}, output_schema={"type": "object"},
            handler_ref=f"observer:{node_name}", read_set=task.read_set,
            write_set=task.write_set, risk="draft", idempotency="required",
        )
        if task.read_set != spec.read_set or task.write_set != spec.write_set:
            raise W1AgenticTransitionError(f"scope contract mismatch for optional {node_name}")
        occurrence = self._next_occurrence(node_name)
        key = f"w1-observer:{self.attempt_id or 'local'}:{node_name}:{occurrence}"
        self._emit("tool.started", task, {"node": node_name, "route": self.route, "optional": True}, f"{key}:start")
        self._emit("tool.result", task, {"node": node_name, "route": self.route, "optional": True, **_summary(payload)}, f"{key}:result")

    def on_failure(self, node_name: str, error: BaseException) -> None:
        if isinstance(error, LeaseLostError):
            raise error
        task = self._task_for_failure(node_name)
        occurrence = self._next_occurrence(node_name or "workflow")
        key = f"w1-observer:{self.attempt_id or 'local'}:{node_name or 'workflow'}:{occurrence}:failure"
        self._emit("tool.failed", task, {
            "node": node_name or "workflow",
            "route": self.route,
            "error_type": type(error).__name__,
        }, key)

    def on_completion(self) -> None:
        if self.plan.tasks and self.plan.tasks[-1].task_id not in self._completed:
            raise W1AgenticTransitionError("stream ended before proposal gate")

    def choose_tool(self, tool_name: str, *, reason: str, evidence: Mapping[str, Any] | None = None) -> ToolDecision:
        if tool_name not in ALLOWED_TOOLS:
            raise ValueError("tool is not allowed for W1 agentic execution")
        if self._decisions >= 4:
            return ToolDecision("stop_at_proposal_gate", "decision_budget_reached", {}, stopped=True)
        self._decisions += 1
        return ToolDecision(tool_name, reason[:120], _concise_evidence(evidence), tool_name == "stop_at_proposal_gate")

    def _initialize_durable_state(self) -> None:
        if not self.runtime_store or not self.attempt_id:
            return
        events = self.runtime_store.list_events(self.attempt_id)
        self._sequence = max((int(event.get("sequence", 0)) for event in events), default=0)
        for event in events:
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
            node = payload.get("node")
            if event.get("event_type") == "tool.result" and isinstance(node, str):
                self._completed.add(node)
            key = event.get("idempotency_key")
            if isinstance(key, str):
                occurrence = _occurrence_from_key(key, self.attempt_id)
                if occurrence is not None:
                    node_name, count = occurrence
                    self._occurrences[node_name] = max(self._occurrences.get(node_name, 0), count)
        checkpoints = self.runtime_store.list_checkpoint_metadata(self.attempt_id)
        if checkpoints:
            latest = max(checkpoints, key=lambda item: int(item.get("sequence", 0)))
            self._checkpoint_sequence = int(latest.get("sequence", 0))
            self._parent_checkpoint_id = str(latest["checkpoint_id"])

    def _node_name(self, update: Mapping[str, Any]) -> str:
        node = update.get("current_node")
        if isinstance(node, str) and node:
            return node
        if len(update) == 1:
            candidate = next(iter(update))
            if isinstance(candidate, str):
                return candidate
        return ""

    def _validate_transition(self, node_name: str) -> PlanTask:
        try:
            task = next(task for task in self.plan.tasks if task.task_id == node_name)
        except StopIteration as error:
            raise W1AgenticTransitionError(f"undeclared W1 node for {self.route}: {node_name}") from error
        spec = self.tools[node_name]
        if task.tool_name != spec.name or task.read_set != spec.read_set or task.write_set != spec.write_set:
            raise W1AgenticTransitionError(f"scope contract mismatch for {node_name}")
        if node_name in self._completed and node_name not in _REPEATABLE_NODES:
            raise W1AgenticTransitionError(f"duplicate non-repeatable W1 node: {node_name}")
        missing = set(task.dependencies) - self._completed
        if missing:
            raise W1AgenticTransitionError(f"invalid W1 transition to {node_name}; missing {sorted(missing)}")
        return task

    def _task_for_failure(self, node_name: str) -> PlanTask:
        if node_name in {task.task_id for task in self.plan.tasks}:
            return next(task for task in self.plan.tasks if task.task_id == node_name)
        return PlanTask("workflow_failure", "Workflow failure", "w1.observe.workflow_failure", read_set=_READ_SCOPE)

    def _next_occurrence(self, node_name: str) -> int:
        self._occurrences[node_name] = self._occurrences.get(node_name, 0) + 1
        return self._occurrences[node_name]

    def _emit(self, event_type: str, task: PlanTask, payload: Mapping[str, Any], idempotency_key: str) -> None:
        if not self.runtime_store or not self.run_id or not self.attempt_id or not self.lineage_id or self.fence_token is None:
            return
        self._sequence += 1
        event = AgentEvent(
            event_id=str(uuid4()), run_id=self.run_id, lineage_id=self.lineage_id,
            attempt_id=self.attempt_id, sequence=self._sequence, event_type=event_type,
            actor_kind="tool", actor_id=task.tool_name, payload=dict(payload),
            idempotency_key=idempotency_key,
        )
        self.runtime_store.append_harness_event(
            event, owner_id=self.worker_id, fence_token=self.fence_token,
        )

    def _record_checkpoint(self, node_name: str, summary: Mapping[str, Any]) -> None:
        if not self.runtime_store or not self.attempt_id:
            return
        self._checkpoint_sequence += 1
        checkpoint_id = "w1observer_" + hashlib.sha256(
            f"{self.attempt_id}\0{self._checkpoint_sequence}\0{node_name}".encode()
        ).hexdigest()
        self.runtime_store.record_checkpoint_metadata(
            self.attempt_id, checkpoint_id, node=node_name,
            sequence=self._checkpoint_sequence,
            parent_checkpoint_id=self._parent_checkpoint_id,
            metadata={"route": self.route, **summary},
        )
        self._parent_checkpoint_id = checkpoint_id


def _summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors = payload.get("errors")
    return {
        "progress": float(payload.get("progress", 0.0) or 0.0),
        "completed_chunks": int(payload.get("completed_chunks", 0) or 0),
        "total_chunks": int(payload.get("total_chunks", 0) or 0),
        "error_count": len(errors) if isinstance(errors, list) else 0,
        "output_hash": hashlib.sha256(json.dumps(dict(payload), sort_keys=True, default=str).encode()).hexdigest(),
    }


def _concise_evidence(evidence: Mapping[str, Any] | None) -> dict[str, str]:
    if not evidence:
        return {}
    blocked = ("source", "key", "token", "secret", "prompt", "reasoning")
    return {
        str(name)[:40]: str(value)[:120]
        for name, value in evidence.items()
        if not any(term in str(name).lower() for term in blocked)
    }


def _occurrence_from_key(key: str, attempt_id: str | None) -> tuple[str, int] | None:
    """Recover the local event occurrence counter after process restart."""
    if not attempt_id:
        return None
    prefix = f"w1-observer:{attempt_id}:"
    if not key.startswith(prefix):
        return None
    try:
        node_name, raw_count, _kind = key[len(prefix):].rsplit(":", 2)
        count = int(raw_count)
    except (TypeError, ValueError):
        return None
    return (node_name, count) if node_name and count > 0 else None
