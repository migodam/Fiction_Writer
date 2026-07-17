"""Bounded durable execution metadata for the deterministic W1 graph.

This module deliberately does not execute W1 nodes.  It mirrors a validated
deterministic route into RuntimeStore so recovery and a constrained agentic
control surface cannot bypass W1 validation, budgets, or proposal staging.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, AsyncIterable, AsyncIterator, Iterable, Mapping

from sidecar.agentic import ExecutionPlan, OpenQuestion, PlanExecuteController, PlanTask, RuntimeStoreScheduler, SelfAsk
from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore


CONTENT_ONLY = "content_only"
IMPORT_ALL = "import_all"
STAGED_PROPOSAL_PUBLICATION = "w1:proposal_package_publication"
ALLOWED_TOOLS = frozenset({"execute_next_node", "rerun_failed_window", "ask_missing_evidence", "stop_at_proposal_gate"})
REPLAN_EVENTS = frozenset({"new_evidence", "task_failed", "human_modified"})


@dataclass(frozen=True)
class ToolDecision:
    tool_name: str
    reason: str
    evidence: dict[str, str]
    stopped: bool = False


def _route(mode: str) -> str:
    if mode == "import_content_only":
        return CONTENT_ONLY
    if mode == IMPORT_ALL:
        return IMPORT_ALL
    raise ValueError(f"unsupported W1 import mode: {mode}")


def _window_task_id(window_id: str) -> str:
    digest = sha256(window_id.encode("utf-8")).hexdigest()[:12]
    return f"extract.window.{digest}"


def build_execution_plan(import_mode: str, *, window_ids: Iterable[str] = ()) -> ExecutionPlan:
    """Create the stable W1 task DAG after deterministic route validation."""
    route = _route(import_mode)
    windows = tuple(sorted(set(str(item) for item in window_ids if str(item)))) or ("deterministic-window-0",)
    tasks: list[PlanTask] = [
        PlanTask("validate_file", "Validate import input", read_set=("w1:source",)),
        PlanTask("checkpoint_load", "Load import checkpoint", dependencies=("validate_file",), read_set=("w1:checkpoint",)),
        PlanTask("split_chunks", "Create segment manifest", dependencies=("checkpoint_load",), read_set=("w1:source",), write_set=("w1:segment_manifest",)),
    ]
    if route == CONTENT_ONLY:
        tasks.extend(_content_tasks("split_chunks"))
    else:
        extraction_ids = tuple(_window_task_id(window_id) for window_id in windows)
        tasks.extend(
            PlanTask(task_id, "Extract prompt window", dependencies=("split_chunks",), read_set=("w1:segment_manifest", f"w1:window:{window_id}"), write_set=(f"w1:evidence:{task_id}",))
            for task_id, window_id in zip(extraction_ids, windows)
        )
        tasks.extend(_import_all_tasks(extraction_ids))
    plan_id = f"w1-{route}-v1-" + sha256("\0".join(windows).encode("utf-8")).hexdigest()[:12]
    return ExecutionPlan(plan_id=plan_id, tasks=tuple(tasks), policy_version="w1-agentic-v1")


def _content_tasks(after: str) -> tuple[PlanTask, ...]:
    return (
        PlanTask("build_manuscript", "Build staged manuscript", dependencies=(after,), read_set=("w1:segment_manifest",), write_set=("w1:manuscript_draft",)),
        *_publication_tail("build_manuscript"),
    )


def _import_all_tasks(extractions: tuple[str, ...]) -> tuple[PlanTask, ...]:
    return (
        PlanTask("resolve_low_confidence", "Resolve low confidence", dependencies=extractions, read_set=("w1:evidence",), write_set=("w1:resolved_evidence",)),
        PlanTask("build_manuscript", "Build staged manuscript", dependencies=("resolve_low_confidence",), read_set=("w1:resolved_evidence",), write_set=("w1:manuscript_draft",)),
        PlanTask("synthesize_relationships", "Synthesize relationships", dependencies=("build_manuscript",), read_set=("w1:resolved_evidence",), write_set=("w1:relationships",)),
        PlanTask("classify_character_tags", "Classify character tags", dependencies=("synthesize_relationships",), read_set=("w1:relationships",), write_set=("w1:character_tags",)),
        PlanTask("infer_world_settings", "Infer world settings", dependencies=("classify_character_tags",), read_set=("w1:resolved_evidence",), write_set=("w1:world_settings",)),
        PlanTask("build_evidence_cards", "Build evidence cards", dependencies=("infer_world_settings",), read_set=("w1:resolved_evidence",), write_set=("w1:evidence_cards",)),
        PlanTask("reconcile_entities", "Reconcile entities", dependencies=("build_evidence_cards",), read_set=("w1:evidence_cards",), write_set=("w1:reducer_artifact",)),
        PlanTask("architect_timeline", "Architect timeline", dependencies=("reconcile_entities",), read_set=("w1:reducer_artifact",), write_set=("w1:timeline_architecture",)),
        PlanTask("organize_world_items", "Organize world items", dependencies=("architect_timeline",), read_set=("w1:timeline_architecture",), write_set=("w1:organizer_output",)),
        *_publication_tail("organize_world_items"),
    )


def _publication_tail(after: str) -> tuple[PlanTask, ...]:
    return (
        PlanTask("generate_import_todos", "Generate import todos", dependencies=(after,), read_set=("w1:manuscript_draft",), write_set=("w1:proposal_draft",)),
        PlanTask("review_import", "Review staged proposals", dependencies=("generate_import_todos",), read_set=("w1:proposal_draft",), write_set=("w1:review_report",)),
        PlanTask("proposal_write", "Stage proposal package", dependencies=("review_import",), read_set=("w1:review_report",), write_set=(STAGED_PROPOSAL_PUBLICATION,)),
    )


class W1AgenticAdapter:
    """Idempotent hooks for wiring W1 streaming to a durable task DAG."""

    def __init__(self, *, import_mode: str, runtime_store: RuntimeStore | None = None, run_id: str | None = None, attempt_id: str | None = None, worker_id: str = "w1-agentic", window_ids: Iterable[str] = (), max_concurrency: int = 4) -> None:
        self.plan = build_execution_plan(import_mode, window_ids=window_ids)
        self.runtime_store, self.run_id, self.attempt_id = runtime_store, run_id, attempt_id
        self.scheduler = RuntimeStoreScheduler(runtime_store, worker_id=worker_id, max_concurrency=max_concurrency) if runtime_store and run_id else None
        self._decisions = 0
        self._last_node = ""
        self._self_ask = SelfAsk(max_questions=2, max_rounds=2)
        self._controller = PlanExecuteController(lambda _: self.plan)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "W1AgenticAdapter":
        context = config.get("context") if isinstance(config.get("context"), Mapping) else {}
        runtime_store = config.get("runtime_store")
        attempt_id = config.get("attempt_id") or context.get("w1_attempt_id")
        attempt = runtime_store.get_attempt(attempt_id) if runtime_store and attempt_id else None
        return cls(
            import_mode=str(config.get("import_mode", IMPORT_ALL)), runtime_store=runtime_store,
            run_id=config.get("runtime_run_id") or config.get("run_id") or (attempt or {}).get("run_id"),
            attempt_id=attempt_id,
            worker_id=str(config.get("runtime_owner_id") or "w1-agentic"),
            window_ids=config.get("prompt_window_ids") or (),
        )

    def before_run(self) -> ExecutionPlan:
        if not self.scheduler or not self.run_id:
            return self.plan
        self.scheduler.submit(self.run_id, self.plan)
        self.scheduler.recover_expired(self.run_id)
        self.scheduler.claim_ready(self.run_id)
        return self.plan

    async def observe_stream(self, updates: AsyncIterable[Mapping[str, Any]]) -> AsyncIterator[Mapping[str, Any]]:
        """Apply all lifecycle hooks around an existing deterministic W1 stream."""
        self.before_run()
        try:
            async for update in updates:
                node_name = str(update.get("current_node", ""))
                if not node_name and len(update) == 1:
                    node_name = str(next(iter(update)))
                if node_name:
                    self._last_node = node_name
                    self.on_node_yielded(node_name, update)
                yield update
        except BaseException as error:
            self.on_failure(self._last_node, error)
            raise
        else:
            self.on_completion()

    def on_node_yielded(self, node_name: str, payload: Mapping[str, Any] | None = None) -> None:
        if not self.scheduler or not self.run_id:
            return
        task_ids = self._task_ids_for_node(node_name)
        for task_id in task_ids:
            if self._status(task_id) == "running":
                self.scheduler.complete(self.run_id, task_id)
        self.scheduler.claim_ready(self.run_id)

    def on_failure(self, node_name: str, error: BaseException) -> None:
        if not self.scheduler or not self.run_id:
            return
        for task_id in self._task_ids_for_node(node_name):
            if self._status(task_id) == "running":
                self.scheduler.fail(self.run_id, task_id, type(error).__name__)
        self.record_decision("task_failed", "node_failure", {"node": node_name, "error": type(error).__name__})

    def on_completion(self) -> None:
        if self.scheduler and self.run_id:
            for task in self.plan.tasks:
                if self._status(task.task_id) == "running":
                    self.scheduler.complete(self.run_id, task.task_id)
                self.scheduler.claim_ready(self.run_id)

    def choose_tool(self, tool_name: str, *, reason: str, evidence: Mapping[str, Any] | None = None) -> ToolDecision:
        if tool_name not in ALLOWED_TOOLS:
            raise ValueError("tool is not allowed for W1 agentic execution")
        if self._decisions >= 4:
            return ToolDecision("stop_at_proposal_gate", "decision_budget_reached", {}, stopped=True)
        self._decisions += 1
        decision = ToolDecision(tool_name, reason[:120], _concise_evidence(evidence), tool_name == "stop_at_proposal_gate")
        self.record_decision(tool_name, decision.reason, decision.evidence)
        return decision

    def ask_missing_evidence(self, candidates: Iterable[str], resolved: set[str] | None = None) -> tuple[OpenQuestion, ...]:
        return self._self_ask.ask(tuple(candidates), resolved or set())

    def replan(self, event: str) -> ExecutionPlan:
        return self._controller.maybe_replan(self.plan, event) if event in REPLAN_EVENTS else self.plan

    def record_decision(self, decision: str, reason: str, evidence: Mapping[str, Any] | None = None) -> None:
        if not self.runtime_store or not self.run_id:
            return
        sequence = self._decisions
        memory_id = f"w1-agentic-{self.run_id}-{sequence}-{decision}"[:120]
        self.runtime_store.record_memory(
            layer="episodic", record_type="decision_summary", memory_id=memory_id, run_id=self.run_id,
            provenance="w1_agentic_adapter", confidence=1.0,
            content=f"decision={decision}; reason={reason[:120]}", references=_concise_evidence(evidence),
            policy_version="w1-agentic-v1",
        )

    def _task_ids_for_node(self, node_name: str) -> tuple[str, ...]:
        if node_name == "process_chunks":
            return tuple(task.task_id for task in self.plan.tasks if task.task_id.startswith("extract.window."))
        aliases = {"load_or_init_checkpoint": "checkpoint_load", "write_to_project": "proposal_write"}
        task_id = aliases.get(node_name, node_name)
        return (task_id,) if any(task.task_id == task_id for task in self.plan.tasks) else ()

    def _status(self, task_id: str) -> str | None:
        try:
            return self.scheduler.status(self.run_id, task_id) if self.scheduler and self.run_id else None
        except KeyError:
            return None


def _concise_evidence(evidence: Mapping[str, Any] | None) -> dict[str, str]:
    if not evidence:
        return {}
    blocked = ("source", "key", "token", "secret", "prompt", "reasoning")
    return {str(name)[:40]: str(value)[:120] for name, value in evidence.items() if not any(term in str(name).lower() for term in blocked)}
