from __future__ import annotations

import asyncio

import pytest

from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore
from sidecar.workflows.w1_agentic_adapter import (
    COMPATIBILITY_DIRECT,
    SUPERVISOR,
    W1AgenticAdapter,
    W1AgenticTransitionError,
    build_execution_plan,
)


def _runtime(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", lineage_id="lineage-w1", thread_id="thread-w1")
    attempt = store.create_attempt(run["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "observer", ttl_seconds=60)
    return store, run, attempt, lease


def test_supervisor_plan_uses_execution_plan_v2_and_typed_tools():
    plan = build_execution_plan("import_all")
    assert plan.contract_version == "ExecutionPlan/v2"
    assert plan.tasks[0].task_id == "validate_file"
    assert plan.tasks[-1].task_id == "done"
    assert all(task.tool_name.startswith("w1.observe.") for task in plan.tasks)
    assert "w1.observe.proposal_write" in plan.available_tools


def test_content_only_and_compatibility_are_the_only_direct_routes():
    assert W1AgenticAdapter(import_mode="import_all").route == SUPERVISOR
    assert W1AgenticAdapter(import_mode="import_all", execution_mode=COMPATIBILITY_DIRECT).route == COMPATIBILITY_DIRECT
    content = W1AgenticAdapter(import_mode="import_content_only")
    assert content.route == "content_only"
    assert "process_chunks" not in {task.task_id for task in content.plan.tasks}


def test_observer_writes_agent_event_v1_and_supervisor_checkpoints(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    adapter = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"], checkpoint_observer=True,
    )

    async def updates():
        # Exact observable supervisor route. Windowing/segment manifest are
        # internal and must not be required by the observer.
        for node in ("validate_file", "extract_windows", "reduce_repair", "architect_timeline", "qa_review", "judge_import", "proposal_write", "done"):
            yield {"current_node": node, "progress": 0.5, "completed_chunks": 1, "total_chunks": 2}

    assert asyncio.run(_collect(adapter.observe_stream(updates())))
    events = store.list_events(attempt["attempt_id"])
    harness_events = [event for event in events if event["contract_version"] == "AgentEvent/v1"]
    assert any(event["event_type"] == "tool.started" for event in harness_events)
    assert any(event["event_type"] == "tool.result" for event in harness_events)
    assert all(event["actor"]["id"].startswith("w1.observe.") for event in harness_events)
    assert [item["node"] for item in store.list_checkpoint_metadata(attempt["attempt_id"])] == [
        "validate_file", "extract_windows", "reduce_repair", "architect_timeline", "qa_review",
        "judge_import", "proposal_write", "done",
    ]


def test_invalid_transition_fails_closed_without_a_result_event(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    adapter = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"],
    )
    with pytest.raises(W1AgenticTransitionError, match="missing"):
        adapter.on_node_yielded("architect_timeline", {"progress": 0.1})
    assert not [event for event in store.list_events(attempt["attempt_id"]) if event["event_type"] == "tool.result"]


def test_lease_loss_is_never_swallowed(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    adapter = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"] + 1,
    )
    with pytest.raises(LeaseLostError):
        adapter.on_node_yielded("validate_file", {"progress": 0.1})


def test_stream_that_stops_before_proposal_gate_is_rejected():
    adapter = W1AgenticAdapter(import_mode="import_content_only")

    async def updates():
        yield {"current_node": "validate_file"}

    with pytest.raises(W1AgenticTransitionError, match="proposal gate"):
        asyncio.run(_collect(adapter.observe_stream(updates())))


def test_empty_window_supervisor_route_can_reduce_directly_after_validation(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    adapter = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"],
    )
    for node in ("validate_file", "reduce_repair", "architect_timeline", "qa_review", "judge_import", "proposal_write", "done"):
        adapter.on_node_yielded(node, {"current_node": node})
    adapter.on_completion()


def test_optional_legacy_progress_events_do_not_change_supervisor_dependencies(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    adapter = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"],
    )
    adapter.on_node_yielded("validate_file", {"current_node": "validate_file"})
    adapter.on_node_yielded("split_chunks", {"current_node": "split_chunks"})
    adapter.on_node_yielded("segment_manifest", {"current_node": "segment_manifest"})
    adapter.on_node_yielded("reduce_repair", {"current_node": "reduce_repair"})
    nodes = [event["payload"].get("node") for event in store.list_events(attempt["attempt_id"])]
    assert nodes.count("split_chunks") == 2
    assert nodes.count("segment_manifest") == 2


def test_repeated_qa_rerun_is_an_allowed_observable_transition(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    adapter = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"],
    )
    for node in ("validate_file", "extract_windows", "reduce_repair", "architect_timeline", "qa_review", "qa_review", "judge_import", "proposal_write", "done"):
        adapter.on_node_yielded(node, {"current_node": node})
    qa_events = [event for event in store.list_events(attempt["attempt_id"]) if event["payload"].get("node") == "qa_review"]
    assert len([event for event in qa_events if event["event_type"] == "tool.result"]) == 2


def test_resume_restores_occurrences_before_repeated_qa_event(tmp_path):
    store, run, attempt, lease = _runtime(tmp_path)
    first = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"],
    )
    for node in ("validate_file", "extract_windows", "reduce_repair", "architect_timeline", "qa_review"):
        first.on_node_yielded(node, {"current_node": node})
    resumed = W1AgenticAdapter(
        import_mode="import_all", runtime_store=store, run_id=run["run_id"],
        attempt_id=attempt["attempt_id"], lineage_id=run["lineage_id"],
        worker_id="observer", fence_token=lease["fence_token"],
    )
    resumed.on_node_yielded("qa_review", {"current_node": "qa_review"})
    keys = [event["idempotency_key"] for event in store.list_events(attempt["attempt_id"])]
    assert "w1-observer:%s:qa_review:1:result" % attempt["attempt_id"] in keys
    assert "w1-observer:%s:qa_review:2:result" % attempt["attempt_id"] in keys


async def _collect(stream):
    return [item async for item in stream]
