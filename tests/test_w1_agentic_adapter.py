from __future__ import annotations

import asyncio

from sidecar.runtime.agent_runtime import RuntimeStore
from sidecar.workflows.w1_agentic_adapter import STAGED_PROPOSAL_PUBLICATION, W1AgenticAdapter, build_execution_plan


def _runtime(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1")
    return store, run["run_id"]


def test_dag_order_and_parallel_extraction_are_stable():
    plan = build_execution_plan("import_all", window_ids=("b", "a"))
    by_id = {task.task_id: task for task in plan.tasks}
    extractions = [task for task in plan.tasks if task.task_id.startswith("extract.window.")]
    assert len(extractions) == 2
    assert all(task.dependencies == ("split_chunks",) for task in extractions)
    assert by_id["resolve_low_confidence"].dependencies == tuple(task.task_id for task in extractions)
    assert by_id["proposal_write"].dependencies == ("review_import",)


def test_proposal_write_is_the_only_staged_publication_writer_and_never_accepts_canonical_data():
    for mode in ("import_content_only", "import_all"):
        plan = build_execution_plan(mode)
        writers = [task.task_id for task in plan.tasks if STAGED_PROPOSAL_PUBLICATION in task.write_set]
        assert writers == ["proposal_write"]
        assert all("canonical" not in resource for task in plan.tasks for resource in task.write_set)


def test_hook_ordering_and_restart_resume(tmp_path):
    store, run_id = _runtime(tmp_path)
    adapter = W1AgenticAdapter(import_mode="import_content_only", runtime_store=store, run_id=run_id, worker_id="worker")
    adapter.before_run()
    adapter.on_node_yielded("validate_file")
    reopened = W1AgenticAdapter(import_mode="import_content_only", runtime_store=RuntimeStore(tmp_path), run_id=run_id, worker_id="worker")
    reopened.before_run()
    assert reopened.scheduler.status(run_id, "validate_file") == "completed"
    assert reopened.scheduler.status(run_id, "checkpoint_load") == "running"


def test_config_hook_resolves_the_run_from_an_attempt(tmp_path):
    store, run_id = _runtime(tmp_path)
    attempt = store.create_attempt(run_id)
    adapter = W1AgenticAdapter.from_config({"import_mode": "import_content_only", "runtime_store": store, "attempt_id": attempt["attempt_id"]})
    assert adapter.run_id == run_id


def test_failure_and_cancel_are_durable(tmp_path):
    store, run_id = _runtime(tmp_path)
    adapter = W1AgenticAdapter(import_mode="import_content_only", runtime_store=store, run_id=run_id)
    adapter.before_run()
    adapter.on_failure("validate_file", RuntimeError("failed"))
    assert adapter.scheduler.status(run_id, "validate_file") == "failed"
    assert adapter.scheduler.status(run_id, "checkpoint_load") == "blocked"
    adapter.scheduler.cancel(run_id)
    assert adapter.scheduler.status(run_id, "proposal_write") == "blocked"
    store, clean_run_id = _runtime(tmp_path / "clean")
    clean = W1AgenticAdapter(import_mode="import_content_only", runtime_store=store, run_id=clean_run_id)
    clean.before_run()
    clean.scheduler.cancel(clean_run_id)
    assert clean.scheduler.status(clean_run_id, "proposal_write") == "cancelled"


def test_bounded_allowlisted_decisions_and_no_hidden_evidence(tmp_path):
    store, run_id = _runtime(tmp_path)
    adapter = W1AgenticAdapter(import_mode="import_content_only", runtime_store=store, run_id=run_id)
    decision = adapter.choose_tool("ask_missing_evidence", reason="missing receipt", evidence={"node": "review_import", "source_text": "do not store", "api_key": "nope"})
    assert decision.evidence == {"node": "review_import"}
    for _ in range(3):
        adapter.choose_tool("execute_next_node", reason="ready")
    assert adapter.choose_tool("execute_next_node", reason="over").stopped
    records = store.query_blackboard(run_id=run_id)
    assert all("source_text" not in record["reference"] and "api_key" not in record["reference"] for record in records)


def test_self_ask_and_replan_are_bounded_to_allowed_triggers():
    adapter = W1AgenticAdapter(import_mode="import_all")
    assert len(adapter.ask_missing_evidence(("timeline anchor", "relationship evidence", "extra"))) == 2
    initial = adapter.plan
    assert adapter.replan("task_completed") is initial
    assert adapter.replan("new_evidence") is initial
    assert adapter.replan("task_failed") is initial
    assert adapter.replan("human_modified") is initial


def test_stream_wrapper_calls_lifecycle_hooks_without_a_runtime_store():
    adapter = W1AgenticAdapter(import_mode="import_content_only")

    async def updates():
        yield {"validate_file": {}}

    assert asyncio.run(_collect(adapter.observe_stream(updates()))) == [{"validate_file": {}}]


async def _collect(stream):
    return [item async for item in stream]
