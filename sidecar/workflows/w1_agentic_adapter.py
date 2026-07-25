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
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, AsyncIterable, AsyncIterator, Iterable, Mapping
from uuid import uuid4

from sidecar.harness.contracts import AgentEvent, Budget, ExecutionPlan, PlanTask, ToolSpec
from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore
from sidecar.runtime.w1_supervisor_snapshot import (
    SnapshotValidationError,
    load_w1_supervisor_snapshot_for_resume,
    write_w1_supervisor_snapshot,
)


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
_SNAPSHOT_BOUNDARY_NEXT_NODE = {
    "reduce_repair": "architect_timeline",
    "architect_timeline": "qa_review",
    "qa_review": "judge_import",
    "judge_import": "proposal_write",
    "proposal_write": None,
}

class W1AgenticTransitionError(RuntimeError):
    """A stream update fell outside the declared W1 Harness route."""


def build_supervisor_snapshot_identities(
    config: Mapping[str, Any], *, project_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build redacted, stable identities for Supervisor snapshot validation.

    The selected source can live outside a project.  Its on-disk location is
    deliberately never persisted in a snapshot; external sources use a stable
    hash-derived logical path instead.  The runtime still validates the actual
    source path separately before a resumed worker is launched.
    """
    root = Path(project_path or config.get("project_path") or ".").resolve()
    source = Path(str(config.get("source_file_path") or ""))
    source_hash = str(config.get("source_hash") or "")
    source_size: int | None = None
    if source.is_file():
        data = source.read_bytes()
        source_hash = hashlib.sha256(data).hexdigest()
        source_size = len(data)
    if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
        raise SnapshotValidationError("supervisor_snapshot_source_hash_missing")
    staged_relative = str(config.get("w1_supervisor_staged_source_relative_path") or "")
    if not staged_relative:
        raise SnapshotValidationError("supervisor_snapshot_staged_source_missing")
    staged_path = (root / staged_relative).resolve()
    try:
        staged_path.relative_to(root)
    except ValueError as exc:
        raise SnapshotValidationError("supervisor_snapshot_staged_source_outside_project") from exc
    if staged_path.is_symlink() or not staged_path.is_file() or hashlib.sha256(staged_path.read_bytes()).hexdigest() != source_hash:
        raise SnapshotValidationError("supervisor_snapshot_staged_source_hash_mismatch")
    relative_source = staged_path.relative_to(root).as_posix()
    context = config.get("context") if isinstance(config.get("context"), Mapping) else {}
    profile = str(config.get("prompt_profile") or config.get("profile") or context.get("prompt_profile") or "balanced")
    identity = {
        "model": str(config.get("model") or context.get("model") or "deepseek-v4-flash"),
        "prompt_profile": profile,
        "prompt_version": str(config.get("prompt_version") or "w1-supervisor-v1"),
        "schema_version": str(config.get("schema_version") or "w1-schema-v4"),
        "tool_registry_version": str(config.get("tool_registry_version") or "w1-tools-v2"),
        "policy_version": str(config.get("policy_version") or "w1-policy-v1"),
        "execution_mode": str(config.get("execution_mode") or SUPERVISOR),
        "import_mode": str(config.get("import_mode") or IMPORT_ALL),
    }
    source_identity: dict[str, Any] = {
        "source_relative_path": relative_source,
        "source_sha256": source_hash,
    }
    if source_size is not None:
        source_identity["source_size"] = source_size
    return source_identity, identity


def _stage_source_for_supervisor_snapshot(
    project_path: str, source_file_path: str, *, lineage_id: str | None, attempt_id: str | None,
) -> str:
    """Persist an immutable, project-contained source copy for v1 snapshots."""
    if not project_path or not source_file_path or not lineage_id or not attempt_id:
        raise SnapshotValidationError("supervisor_snapshot_stage_identity_missing")
    root = Path(project_path).resolve(strict=True)
    source = Path(source_file_path)
    if not source.is_file():
        raise SnapshotValidationError("supervisor_snapshot_source_missing")
    target = root / "system" / "imports" / lineage_id / "attempts" / attempt_id / "raw_source.txt"
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SnapshotValidationError("supervisor_snapshot_stage_outside_project") from exc
    if any(parent.is_symlink() for parent in (target.parent, *target.parent.parents) if parent.exists()):
        raise SnapshotValidationError("supervisor_snapshot_stage_symlink")
    source_bytes = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or target.read_bytes() != source_bytes:
            raise SnapshotValidationError("supervisor_snapshot_stage_conflict")
        return target.relative_to(root).as_posix()
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(source_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target.relative_to(root).as_posix()


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
        self._resume_snapshot_ref = _.get("w1_supervisor_resume_snapshot_ref")
        self.project_path = str(config_project_path) if (config_project_path := _.get("project_path")) else ""
        self._source_identity: dict[str, Any] | None = None
        self._config_identity: dict[str, str] | None = None
        if self.route == SUPERVISOR and self.project_path:
            try:
                if isinstance(self._resume_snapshot_ref, Mapping):
                    snapshot_lineage = str(self._resume_snapshot_ref.get("lineage_id") or "")
                    snapshot_attempt = str(self._resume_snapshot_ref.get("attempt_id") or "")
                    _.setdefault(
                        "w1_supervisor_staged_source_relative_path",
                        f"system/imports/{snapshot_lineage}/attempts/{snapshot_attempt}/raw_source.txt",
                    )
                else:
                    _.setdefault(
                        "w1_supervisor_staged_source_relative_path",
                        _stage_source_for_supervisor_snapshot(
                            self.project_path,
                            str(_.get("source_file_path") or ""),
                            lineage_id=self.lineage_id,
                            attempt_id=self.attempt_id,
                        ),
                    )
                self._source_identity, self._config_identity = build_supervisor_snapshot_identities(
                    _, project_path=self.project_path,
                )
            except SnapshotValidationError:
                # Snapshotting is optional for a run; the observer records an
                # explicit preview-only checkpoint rather than persisting an
                # incomplete identity.
                self._source_identity = None
                self._config_identity = None
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
            project_path=str(config.get("project_path") or ""),
            source_file_path=str(config.get("source_file_path") or ""),
            source_hash=str(config.get("source_hash") or ""),
            model=str(config.get("model") or context.get("model") or ""),
            prompt_profile=str(config.get("prompt_profile") or context.get("prompt_profile") or ""),
            prompt_version=str(config.get("prompt_version") or ""),
            schema_version=str(config.get("schema_version") or ""),
            tool_registry_version=str(config.get("tool_registry_version") or ""),
            policy_version=str(config.get("policy_version") or ""),
            w1_supervisor_resume_snapshot_ref=config.get("w1_supervisor_resume_snapshot_ref"),
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
                # Snapshot material is an internal, redacted handoff between
                # the policy and the durable observer.  It must never become a
                # UI/SSE payload or a persisted AgentEvent payload.
                yield {key: value for key, value in update.items() if key != "_w1_supervisor_snapshot"}
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
        summary = _summary(payload or {})
        self._completed.add(node_name)
        if self.checkpoint_observer:
            self._record_checkpoint(node_name, summary, payload or {})
        # A yielded node has already completed in the business executor.  Keep
        # the durable observation after the snapshot/checkpoint commit so a
        # recovered attempt never sees a result without its recovery material.
        self._emit("tool.started", task, {"node": node_name, "route": self.route}, f"{key}:start")
        self._emit("tool.result", task, {"node": node_name, "route": self.route, **summary}, f"{key}:result")

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
        self._restore_completed_snapshot_boundary()

    def _restore_completed_snapshot_boundary(self) -> None:
        """Seed dependency checks from an immutable snapshot, never UI input."""
        if self.route != SUPERVISOR or not self.project_path or not isinstance(self._resume_snapshot_ref, Mapping):
            return
        try:
            if self._source_identity is None or self._config_identity is None:
                raise SnapshotValidationError("supervisor_snapshot_identity_unavailable")
            loaded = load_w1_supervisor_snapshot_for_resume(
                self.project_path,
                self._resume_snapshot_ref,
                expected_source_identity=self._source_identity,
                expected_config_identity=self._config_identity,
                artifact_receipt_validator=(
                    (lambda reference, snapshot: self.runtime_store.validate_w1_snapshot_artifact_receipt(reference, snapshot))
                    if self.runtime_store is not None else None
                ),
            )
            for completed in loaded["snapshot"].get("completed_nodes", []):
                node = "extract_windows" if completed == "extract_window" else completed
                if any(task.task_id == node for task in self.plan.tasks):
                    self._completed.add(node)
        except (OSError, SnapshotValidationError, TypeError, ValueError):
            # The policy validates identities before execution.  Leaving this
            # empty here makes an invalid reference fail closed at that layer.
            return

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

    def _snapshot_error_code(self, error: BaseException) -> str:
        if isinstance(error, LeaseLostError):
            return "snapshot_lease_lost"
        if isinstance(error, OSError):
            return "snapshot_io_failed"
        message = str(error).lower()
        if "identity" in message or "staged_source" in message:
            return "snapshot_identity_unavailable"
        if "unknown" in message:
            return "snapshot_unknown_outcome_pending"
        return "snapshot_contract_rejected"

    def _assert_checkpoint_lease(self) -> None:
        if not self.runtime_store or not self.attempt_id:
            return
        if not self.worker_id or self.fence_token is None:
            raise LeaseLostError("checkpoint_requires_current_worker_lease")
        self.runtime_store.assert_current_lease(
            self.attempt_id, self.worker_id, self.fence_token,
        )

    def _record_checkpoint(self, node_name: str, summary: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        if not self.runtime_store or not self.attempt_id:
            return
        # A snapshot can be left as an unreachable artifact after a worker loses
        # its lease.  It may never become a checkpoint unless the same fence is
        # valid both before and after its file publication.
        self._assert_checkpoint_lease()
        self._checkpoint_sequence += 1
        checkpoint_id = "w1observer_" + hashlib.sha256(
            f"{self.attempt_id}\0{self._checkpoint_sequence}\0{node_name}".encode()
        ).hexdigest()
        metadata: dict[str, Any] = {"route": self.route, **summary, "recovery_mode": "preview_only"}
        snapshot_payload = payload.get("_w1_supervisor_snapshot")
        if node_name in _SNAPSHOT_BOUNDARY_NEXT_NODE and isinstance(snapshot_payload, Mapping):
            try:
                if not self.project_path or self._source_identity is None or self._config_identity is None:
                    raise SnapshotValidationError("supervisor_snapshot_identity_unavailable")
                snapshot_state = snapshot_payload.get("state")
                if not isinstance(snapshot_state, Mapping):
                    raise SnapshotValidationError("supervisor_snapshot_state_missing")
                actual_unknown = [
                    str(item.get("tool_call_id"))
                    for item in self.runtime_store.list_unknown_call_summaries(self.attempt_id)
                ]
                declared_unknown = [str(item) for item in snapshot_payload.get("unknown_tool_call_ids") or ()]
                if sorted(actual_unknown) != sorted(declared_unknown):
                    raise SnapshotValidationError("supervisor_snapshot_unknown_tool_calls_mismatch")
                if actual_unknown:
                    raise SnapshotValidationError("supervisor_snapshot_unknown_tool_calls_present")
                snapshot_ref = write_w1_supervisor_snapshot(
                    self.project_path,
                    lineage_id=str(self.lineage_id or ""),
                    attempt_id=self.attempt_id,
                    checkpoint_id=checkpoint_id,
                    node=node_name,
                    next_node=_SNAPSHOT_BOUNDARY_NEXT_NODE[node_name],
                    source_identity=self._source_identity,
                    config_identity=self._config_identity,
                    state=snapshot_state,
                    parent_checkpoint_id=self._parent_checkpoint_id,
                    completed_nodes=tuple(snapshot_payload.get("completed_nodes") or ()),
                    completed_window_ids=tuple(snapshot_payload.get("completed_window_ids") or ()),
                    repeatable_node_counts=snapshot_payload.get("repeatable_node_counts"),
                    budget_snapshot=snapshot_payload.get("budget_snapshot"),
                    unknown_tool_call_ids=tuple(actual_unknown),
                )
                metadata.update({
                    "recovery_mode": "resumable",
                    "snapshot_ref": snapshot_ref.to_dict(),
                    "snapshot_node": node_name,
                    "next_node": _SNAPSHOT_BOUNDARY_NEXT_NODE[node_name],
                })
            except LeaseLostError:
                raise
            except (OSError, SnapshotValidationError, ValueError, TypeError) as error:
                metadata.update({
                    "recovery_mode": "preview_only",
                    "snapshot_error": self._snapshot_error_code(error),
                })
        elif node_name == "extract_windows":
            metadata["preview_reason"] = "per_window_state_is_not_yet_safe_to_resume"
        self._assert_checkpoint_lease()
        self.runtime_store.record_checkpoint_metadata(
            self.attempt_id, checkpoint_id, node=node_name,
            sequence=self._checkpoint_sequence,
            parent_checkpoint_id=self._parent_checkpoint_id,
            metadata=metadata,
            owner_id=self.worker_id,
            fence_token=self.fence_token,
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
