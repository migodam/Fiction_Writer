from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from sidecar.agentic import ExecutionPlan, PlanTask, RuntimeStoreScheduler
from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore, SecretValueError


def plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="durable-plan",
        tasks=(
            PlanTask("prepare", "Prepare", write_set=("project:story",)),
            PlanTask("write", "Write", dependencies=("prepare",), read_set=("project:story",), write_set=("project:chapter",)),
        ),
    )


def test_restart_reconstructs_dag_and_idempotent_submission(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W0")
    first = RuntimeStoreScheduler(store, worker_id="worker-a")
    assert first.submit(run["run_id"], plan())["idempotent"] is False
    claimed = first.claim_ready(run["run_id"])
    assert [task.task_id for task in claimed] == ["prepare"]

    reopened = RuntimeStoreScheduler(RuntimeStore(tmp_path), worker_id="worker-a")
    assert reopened.submit(run["run_id"], plan())["idempotent"] is True
    reopened.complete(run["run_id"], "prepare")
    assert [task.task_id for task in reopened.claim_ready(run["run_id"])] == ["write"]


def test_concurrent_workers_have_one_claim_winner_and_stale_fence_cannot_finish(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W0")
    RuntimeStoreScheduler(store, worker_id="setup").submit(run["run_id"], plan())

    def claim(worker: str):
        return RuntimeStoreScheduler(RuntimeStore(tmp_path), worker_id=worker).claim_ready(run["run_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("worker-a", "worker-b")))
    assert sum(len(result) for result in results) == 1

    task = store.get_task_dag(run["run_id"])[0]
    old_fences = dict(task["fence_map"])
    store.recover_expired_task_claims(run["run_id"], now=task["claim_expires_at"] + 1)
    new_row = store.claim_ready_tasks(run["run_id"], "worker-b", now=task["claim_expires_at"] + 1)[0]
    with pytest.raises(LeaseLostError):
        store.complete_task(run["run_id"], "prepare", "worker-a", old_fences, now=task["claim_expires_at"] + 1)
    assert new_row["fence_map"]["project:story"] > old_fences["project:story"]


def test_cancel_propagates_dead_letters_and_failed_task_can_be_recovered(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W0")
    scheduler = RuntimeStoreScheduler(store, worker_id="worker-a")
    scheduler.submit(run["run_id"], plan())
    scheduler.claim_ready(run["run_id"])
    scheduler.fail(run["run_id"], "prepare", "tool failed")
    assert scheduler.status(run["run_id"], "write") == "blocked"
    assert [letter.task_id for letter in scheduler.dead_letters(run["run_id"])] == ["prepare", "write"]
    assert store.recover_dead_letter(run["run_id"], "prepare")["status"] == "pending"
    scheduler.cancel(run["run_id"])
    assert scheduler.status(run["run_id"], "prepare") == "cancelled"


def test_persistent_memory_redacts_rejects_and_compacts_deterministically(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W0")
    token = store.record_memory(layer="working", record_type="token_delta", content="delta only", provenance="run:1", confidence=0.8, run_id=run["run_id"], now=100)
    final = store.record_memory(layer="episodic", record_type="final_summary", content="approved outcome", provenance="human:1", confidence=1, run_id=run["run_id"], now=100)
    semantic = store.record_memory(layer="semantic", record_type="project_entity_reference", content="Character changed", references={"entity_id": "character-1", "source": "proposal-2"}, provenance="proposal:2", confidence=0.9, now=100)
    assert token["expires_at"] == 100 + 7 * 86400
    assert final["expires_at"] is None and semantic["reference"]["entity_id"] == "character-1"
    with pytest.raises(SecretValueError):
        store.record_memory(layer="episodic", record_type="event_summary", content="api_key=secret", provenance="run:1", confidence=0.8)
    with pytest.raises(SecretValueError):
        store.record_memory(layer="procedural", record_type="prompt_version", content="hidden chain of thought", provenance="run:1", confidence=0.8)
    with pytest.raises(SecretValueError):
        store.record_memory(layer="procedural", record_type="prompt_version", content="prompt v2", references={"prompt_body": "do not persist"}, provenance="run:1", confidence=0.8)
    assert store.compact_memory(now=100 + 7 * 86400)["deleted"] == 1
    assert [record["memory_id"] for record in store.query_blackboard(now=100 + 7 * 86400)] == [final["memory_id"], semantic["memory_id"]]
