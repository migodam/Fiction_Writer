from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import hashlib
import json

import pytest

from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore, SecretValueError


@pytest.fixture
def runtime(tmp_path):
    store = RuntimeStore(tmp_path)
    store.initialize()
    return store


def test_schema_uses_project_wal_database(runtime, tmp_path):
    expected = tmp_path / "system" / "runtime" / "agent_runtime.db"
    assert runtime.database_path == expected
    assert expected.exists()

    with sqlite3.connect(expected) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert runtime.pragma("foreign_keys") == 1
    assert {
        "agent_runs",
        "agent_attempts",
        "run_leases",
        "run_events",
        "tool_calls",
        "artifact_receipts",
        "human_decisions",
        "outbox",
        "schema_migrations",
    } <= tables


def test_concurrent_events_receive_monotonic_sequences(runtime):
    run = runtime.create_run(workflow_id="W0")
    attempt = runtime.create_attempt(run["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=30)

    def append(index: int):
        return runtime.append_event(
            attempt["attempt_id"],
            "progress",
            {"index": index},
            owner_id="worker-a",
            fence_token=lease["fence_token"],
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        events = list(executor.map(append, range(24)))

    assert sorted(event["sequence"] for event in events) == list(range(1, 25))
    assert [event["sequence"] for event in runtime.list_events(attempt["attempt_id"], after_sequence=20)] == [21, 22, 23, 24]


def test_expired_lease_can_be_fenced_by_a_new_worker(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    first = runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=1, now=10)
    assert runtime.expire_leases(now=12) == [attempt["attempt_id"]]

    second = runtime.acquire_lease(attempt["attempt_id"], "worker-b", ttl_seconds=10, now=12)
    assert second["fence_token"] == first["fence_token"] + 1


def test_release_lease_is_fenced_and_immediately_expires_the_owner(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=60)

    with pytest.raises(LeaseLostError):
        runtime.release_lease(
            attempt["attempt_id"], "worker-b", lease["fence_token"],
        )

    runtime.release_lease(
        attempt["attempt_id"], "worker-a", lease["fence_token"],
    )

    assert attempt["attempt_id"] in runtime.expire_leases()


def test_expired_running_attempt_is_interrupted_before_recovery_is_reported(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=1, now=10)

    recoverable = runtime.scan_recoverable_attempts(now=12)

    assert recoverable[0]["status"] == "interrupted"
    assert runtime.get_attempt(attempt["attempt_id"])["status"] == "interrupted"
    assert runtime.set_attempt_status(attempt["attempt_id"], "running")["status"] == "running"


def test_restart_interrupts_running_attempts_and_expires_all_leases(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W0")["run_id"])
    runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=30)

    runtime.invalidate_leases_for_restart()

    assert runtime.get_attempt(attempt["attempt_id"])["status"] == "interrupted"
    assert runtime.expire_leases() == [attempt["attempt_id"]]


def test_restart_reconciles_unfinished_provider_intents_as_unknown_outcome(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    runtime.acquire_lease(attempt["attempt_id"], "paid-worker", ttl_seconds=30)
    for index in range(5):
        call = runtime.record_tool_intent(attempt["attempt_id"], "provider.call", {"index": index})
        runtime.record_tool_result(call["tool_call_id"], {"ok": True})
    pending = runtime.record_tool_intent(attempt["attempt_id"], "provider.call", {"index": 5})

    runtime.invalidate_leases_for_restart()

    assert runtime.get_attempt(attempt["attempt_id"])["status"] == "interrupted"
    calls = runtime.list_tool_calls(attempt["attempt_id"])
    assert sum(call["status"] == "result" for call in calls) == 5
    assert [call["status"] for call in calls if call["tool_call_id"] == pending["tool_call_id"]] == ["unknown_outcome"]
    assert calls[-1]["unknown_reason"] == "runtime_interrupted"
    assert runtime.list_unknown_call_summaries(attempt["attempt_id"])[0]["decision_state"] == "pending"

    runtime.invalidate_leases_for_restart()
    assert len(runtime.list_tool_calls(attempt["attempt_id"])) == 6
    assert len(runtime.list_unknown_call_summaries(attempt["attempt_id"])) == 1


def test_stale_fencing_token_is_rejected(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    old = runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=1, now=10)
    current = runtime.acquire_lease(attempt["attempt_id"], "worker-b", ttl_seconds=10, now=12)

    with pytest.raises(LeaseLostError):
        runtime.append_event(attempt["attempt_id"], "progress", {}, owner_id="worker-a", fence_token=old["fence_token"], now=12)

    assert runtime.append_event(attempt["attempt_id"], "progress", {}, owner_id="worker-b", fence_token=current["fence_token"], now=12)["sequence"] == 1


def test_repeated_human_decisions_are_idempotent(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W0")["run_id"])
    initial = runtime.record_human_decision(attempt["attempt_id"], "approve-plan", "approved", {"by": "mia"})
    repeated = runtime.record_human_decision(attempt["attempt_id"], "approve-plan", "approved", {"by": "mia"})

    assert repeated == initial
    with pytest.raises(ValueError, match="decision_key_conflict"):
        runtime.record_human_decision(
            attempt["attempt_id"], "approve-plan", "approved", {"by": "other"}
        )
    assert len(runtime.list_human_decisions(attempt["attempt_id"])) == 1


def test_tool_unknown_outcome_is_durable(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W2")["run_id"])
    call = runtime.record_tool_intent(attempt["attempt_id"], "filesystem.write", {"path": "draft.md"})
    unknown = runtime.record_tool_unknown_outcome(call["tool_call_id"], "sidecar restarted")

    assert unknown["status"] == "unknown_outcome"
    assert unknown["unknown_reason"] == "sidecar restarted"


def _authorized_provider_unknown(runtime, idempotency_key):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "artifact-worker", ttl_seconds=30)
    call = runtime.record_tool_intent(
        attempt["attempt_id"],
        "provider.chat.completions",
        {"idempotency_key": idempotency_key, "model": "deepseek-chat", "message_hash": "a" * 64},
    )
    runtime.record_tool_unknown_outcome(call["tool_call_id"], "runtime_interrupted")
    decision_key = f"retry_provider_call:{idempotency_key}"
    runtime.record_unknown_call_decision(attempt["attempt_id"], decision_key, "authorize_retry_once")
    return attempt, lease, call, decision_key


def _write_minimal_provider_artifact(runtime, operation_key, **extra_payload):
    payload = {
        "contract": "W1ProviderResponse/v1",
        "operation_key": operation_key,
        **extra_payload,
    }
    artifact_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
    relative_path = (
        f"system/imports/lineage/provider_responses/{operation_key}/{artifact_hash}.json"
    )
    artifact_path = runtime.project_root / relative_path
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)
    return {
        "operation_key": operation_key,
        "artifact_path": relative_path,
        "artifact_hash": artifact_hash,
    }


def test_authorized_unknown_can_be_atomically_resolved_from_verified_artifact(runtime):
    attempt, lease, call, decision_key = _authorized_provider_unknown(runtime, "artifact-retry-key")
    receipt = _write_minimal_provider_artifact(runtime, "b" * 64)

    resolved = runtime.resolve_authorized_unknown_with_artifact(
        attempt["attempt_id"], call["tool_call_id"], decision_key, receipt,
        owner_id="artifact-worker", fence_token=lease["fence_token"],
    )
    repeated = runtime.resolve_authorized_unknown_with_artifact(
        attempt["attempt_id"], call["tool_call_id"], decision_key, receipt,
        owner_id="artifact-worker", fence_token=lease["fence_token"],
    )

    assert resolved["status"] == "retry_consumed"
    assert resolved["result_payload"]["outcome"] == "resolved_from_verified_artifact"
    assert resolved["result_payload"]["artifact_receipt"] == receipt
    assert resolved["idempotent"] is False
    assert repeated["idempotent"] is True
    different_receipt = _write_minimal_provider_artifact(runtime, "b" * 64, variant=2)
    with pytest.raises(ValueError, match="unknown_retry_already_consumed"):
        runtime.resolve_authorized_unknown_with_artifact(
            attempt["attempt_id"], call["tool_call_id"], decision_key,
            different_receipt,
            owner_id="artifact-worker", fence_token=lease["fence_token"],
        )


def test_authorized_unknown_missing_artifact_does_not_consume_authorization(runtime):
    attempt, lease, call, decision_key = _authorized_provider_unknown(runtime, "missing-artifact-key")
    receipt = {
        "operation_key": "c" * 64,
        "artifact_path": "system/imports/lineage/provider_responses/missing/artifact.json",
        "artifact_hash": "d" * 64,
    }

    with pytest.raises(ValueError, match="artifact_missing"):
        runtime.resolve_authorized_unknown_with_artifact(
            attempt["attempt_id"], call["tool_call_id"], decision_key, receipt,
            owner_id="artifact-worker", fence_token=lease["fence_token"],
        )

    persisted = {item["tool_call_id"]: item for item in runtime.list_tool_calls(attempt["attempt_id"])}
    assert persisted[call["tool_call_id"]]["status"] == "unknown_outcome"


def test_authorized_unknown_hash_mismatch_does_not_consume_authorization(runtime):
    attempt, lease, call, decision_key = _authorized_provider_unknown(runtime, "hash-mismatch-key")
    receipt = _write_minimal_provider_artifact(runtime, "e" * 64)
    receipt["artifact_hash"] = "f" * 64

    with pytest.raises(ValueError, match="artifact_hash_mismatch"):
        runtime.resolve_authorized_unknown_with_artifact(
            attempt["attempt_id"], call["tool_call_id"], decision_key, receipt,
            owner_id="artifact-worker", fence_token=lease["fence_token"],
        )

    persisted = {item["tool_call_id"]: item for item in runtime.list_tool_calls(attempt["attempt_id"])}
    assert persisted[call["tool_call_id"]]["status"] == "unknown_outcome"


def test_secrets_are_rejected_in_identifiers_and_redacted_in_payloads(runtime):
    with pytest.raises(SecretValueError):
        runtime.create_run(workflow_id="W0", cache_key="sk-this-is-a-secret")

    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W0")["run_id"])
    call = runtime.record_tool_intent(attempt["attempt_id"], "remote.call", {"api_key": "super-secret", "note": "safe"})
    assert call["intent_payload"] == {"api_key": "[REDACTED]", "note": "safe"}
    with sqlite3.connect(runtime.database_path) as connection:
        persisted = connection.execute("SELECT intent_payload_json FROM tool_calls WHERE tool_call_id = ?", (call["tool_call_id"],)).fetchone()[0]
    assert "super-secret" not in persisted


def test_reopen_preserves_runs_receipts_and_recoverable_attempts(tmp_path):
    first = RuntimeStore(tmp_path)
    run = first.create_run(workflow_id="W3", thread_id="thread-1")
    attempt = first.create_attempt(run["run_id"], checkpoint_id="checkpoint-1")
    lease = first.acquire_lease(attempt["attempt_id"], "receipt-worker", ttl_seconds=30)
    receipt = first.record_artifact_receipt(
        attempt["attempt_id"], "proposal", "artifacts/proposal.json", "abc123",
        owner_id="receipt-worker", fence_token=lease["fence_token"],
    )
    first.invalidate_leases_for_restart()

    reopened = RuntimeStore(tmp_path)
    assert reopened.get_run(run["run_id"])["thread_id"] == "thread-1"
    assert reopened.list_artifact_receipts(attempt["attempt_id"])[0] == receipt
    assert [item["attempt_id"] for item in reopened.scan_recoverable_attempts()] == [attempt["attempt_id"]]


def test_concurrent_runtime_initialization_is_migration_safe(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: RuntimeStore(tmp_path), range(16)))

    assert all(store.database_path.exists() for store in stores)
    with sqlite3.connect(stores[0].database_path) as connection:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_runs)")}
    assert {1, 2} <= versions
    assert "config_json" in columns


def test_concurrent_v2_migration_is_transactional_and_idempotent(tmp_path):
    store = RuntimeStore(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("ALTER TABLE agent_runs DROP COLUMN config_json")
        connection.execute("DELETE FROM schema_migrations WHERE version >= 2")

    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: RuntimeStore(tmp_path), range(16)))

    with sqlite3.connect(stores[0].database_path) as connection:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_runs)")}
    assert {1, 2, 3} <= versions
    assert "config_json" in columns


def test_checkpoint_metadata_is_ordered_and_never_persists_state_blobs(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    runtime.record_checkpoint_metadata(attempt["attempt_id"], "checkpoint-1", node="split_chunks", sequence=1, metadata={"diff": {"chunks": 1}})
    runtime.record_checkpoint_metadata(
        attempt["attempt_id"], "checkpoint-2", node="process_chunks", sequence=2,
        parent_checkpoint_id="checkpoint-1", metadata={"summary": "two chunks", "state": {"api_key": "sk-secret"}},
    )

    checkpoints = runtime.list_checkpoint_metadata(attempt["attempt_id"])
    assert [item["checkpoint_id"] for item in checkpoints] == ["checkpoint-1", "checkpoint-2"]
    assert checkpoints[1]["metadata"] == {"state": {"api_key": "[REDACTED]"}, "summary": "two chunks"}


def test_checkpoint_parent_must_belong_to_same_attempt_and_precede_child(runtime):
    first = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    second = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    runtime.record_checkpoint_metadata(first["attempt_id"], "first-parent", node="split", sequence=2)
    runtime.record_checkpoint_metadata(second["attempt_id"], "second-parent", node="split", sequence=1)

    with pytest.raises(ValueError, match="parent_checkpoint_does_not_belong_to_attempt"):
        runtime.record_checkpoint_metadata(
            second["attempt_id"], "wrong-parent", node="reduce", sequence=2,
            parent_checkpoint_id="first-parent",
        )
    with pytest.raises(ValueError, match="parent_checkpoint_must_precede_checkpoint"):
        runtime.record_checkpoint_metadata(
            first["attempt_id"], "backwards-parent", node="reduce", sequence=2,
            parent_checkpoint_id="first-parent",
        )


def test_resumable_checkpoint_requires_current_unexpired_fence(runtime, monkeypatch):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    first = runtime.acquire_lease(attempt["attempt_id"], "worker-a", ttl_seconds=1, now=10)
    current = runtime.acquire_lease(attempt["attempt_id"], "worker-b", ttl_seconds=30, now=12)
    metadata = {"recovery_mode": "resumable", "snapshot_ref": {"contract_version": "W1SupervisorSnapshot/v1"}}

    with pytest.raises(LeaseLostError):
        runtime.record_checkpoint_metadata(
            attempt["attempt_id"], "stale-fence", node="reduce", sequence=1,
            metadata=metadata, owner_id="worker-a", fence_token=first["fence_token"],
        )

    monkeypatch.setattr("sidecar.runtime.agent_runtime._now", lambda value=None: 43 if value is None else value)
    with pytest.raises(LeaseLostError):
        runtime.record_checkpoint_metadata(
            attempt["attempt_id"], "expired-fence", node="reduce", sequence=1,
            metadata=metadata, owner_id="worker-b", fence_token=current["fence_token"],
        )


def test_fork_creates_an_isolated_checkpoint_snapshot_and_scoped_receipt_copy(runtime):
    run = runtime.create_run(workflow_id="W1", lineage_id="lineage-fork", thread_id="thread-parent")
    parent = runtime.create_attempt(run["run_id"])
    parent_id = parent["attempt_id"]
    runtime.record_checkpoint_metadata(
        parent_id, "checkpoint-1", node="split_chunks", sequence=1,
        metadata={"summary": "one chunk", "api_key": "sk-never-persist"},
    )
    runtime.record_checkpoint_metadata(parent_id, "checkpoint-2", node="extract", sequence=2)
    lease = runtime.acquire_lease(parent_id, "parent-worker", ttl_seconds=30)
    included = runtime.record_artifact_receipt(
        parent_id, "cache", "cache/chunk-1.json", "hash-1",
        {"checkpoint_id": "checkpoint-1", "cache_key": "chunk-1"},
        owner_id="parent-worker", fence_token=lease["fence_token"],
    )
    runtime.record_artifact_receipt(
        parent_id, "cache", "cache/unscoped.json", "hash-unscoped",
        owner_id="parent-worker", fence_token=lease["fence_token"],
    )
    runtime.record_artifact_receipt(
        parent_id, "cache", "cache/future.json", "hash-2",
        {"checkpoint_sequence": 2}, owner_id="parent-worker", fence_token=lease["fence_token"],
    )
    unknown = runtime.record_tool_intent(parent_id, "provider.call", {"operation": "unresolved"})
    runtime.record_tool_unknown_outcome(unknown["tool_call_id"], "restart")
    runtime.enqueue_outbox("proposal.publish", {"proposal": "parent"}, attempt_id=parent_id)
    runtime.set_attempt_status(parent_id, "paused")

    fork = runtime.fork_attempt(parent_id, checkpoint_id="checkpoint-1", decision_id="fork-at-one")
    child_id = fork["attempt"]["attempt_id"]
    repeated = runtime.fork_attempt(parent_id, checkpoint_id="checkpoint-1", decision_id="fork-at-one")
    snapshot = runtime.get_fork_snapshot(child_id)

    assert fork["idempotent"] is False
    assert repeated["idempotent"] is True
    assert repeated["attempt"]["attempt_id"] == child_id
    assert fork["attempt"]["status"] == "paused"
    assert snapshot is not None
    assert snapshot["parent_attempt_id"] == parent_id
    assert snapshot["source_checkpoint_id"] == "checkpoint-1"
    assert snapshot["checkpoint_metadata"] == {"api_key": "[REDACTED]", "summary": "one chunk"}
    assert snapshot["state_reference"] == {
        "checkpoint_id": "checkpoint-1",
        "immutable": True,
        "kind": "external_checkpoint_reference/v1",
        "lineage_id": "lineage-fork",
        "mode": "preview_only",
        "resumable": False,
        "thread_id": "thread-parent",
        "workflow_id": "W1",
    }
    assert snapshot["resumable"] is False
    assert snapshot["non_resumable_reason"] == "fork_snapshot_not_resumable"
    child_receipts = runtime.list_artifact_receipts(child_id)
    assert len(child_receipts) == 1
    assert child_receipts[0]["artifact_uri"] == "cache/chunk-1.json"
    assert child_receipts[0]["metadata"]["fork_provenance"] == {
        "snapshot_id": snapshot["snapshot_id"],
        "source_attempt_id": parent_id,
        "source_receipt_id": included["receipt_id"],
        "source_checkpoint_id": "checkpoint-1",
    }
    assert runtime.list_tool_calls(child_id) == []
    with sqlite3.connect(runtime.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox WHERE attempt_id = ?", (child_id,)).fetchone()[0] == 0

    child_lease = runtime.acquire_lease(child_id, "child-worker", ttl_seconds=30)
    runtime.record_artifact_receipt(
        child_id, "cache", "cache/child-only.json", "child-hash", {"checkpoint_id": "checkpoint-1"},
        owner_id="child-worker", fence_token=child_lease["fence_token"],
    )
    child_tool = runtime.record_tool_intent(
        child_id, "filesystem.read", {"path": "child-only"},
        owner_id="child-worker", fence_token=child_lease["fence_token"],
    )
    runtime.enqueue_outbox("proposal.publish", {"proposal": "child"}, attempt_id=child_id)

    assert len(runtime.list_artifact_receipts(parent_id)) == 3
    assert [call["tool_call_id"] for call in runtime.list_tool_calls(parent_id)] == [unknown["tool_call_id"]]
    assert [call["tool_call_id"] for call in runtime.list_tool_calls(child_id)] == [child_tool["tool_call_id"]]
    with sqlite3.connect(runtime.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox WHERE attempt_id = ?", (parent_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM outbox WHERE attempt_id = ?", (child_id,)).fetchone()[0] == 1


def test_fork_decision_cannot_be_reused_for_a_different_checkpoint(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    runtime.record_checkpoint_metadata(attempt["attempt_id"], "checkpoint-1", node="split", sequence=1)
    runtime.record_checkpoint_metadata(attempt["attempt_id"], "checkpoint-2", node="extract", sequence=2)
    runtime.set_attempt_status(attempt["attempt_id"], "paused")
    runtime.fork_attempt(attempt["attempt_id"], checkpoint_id="checkpoint-1", decision_id="fork-key")

    with pytest.raises(ValueError, match="fork_decision_conflict"):
        runtime.fork_attempt(attempt["attempt_id"], checkpoint_id="checkpoint-2", decision_id="fork-key")


def test_fork_rejects_running_parent_without_recording_a_decision(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    runtime.record_checkpoint_metadata(attempt["attempt_id"], "checkpoint-1", node="split", sequence=1)

    with pytest.raises(ValueError, match="parent_attempt_must_be_stable_to_fork"):
        runtime.fork_attempt(attempt["attempt_id"], checkpoint_id="checkpoint-1", decision_id="fork-running")

    assert runtime.list_human_decisions(attempt["attempt_id"]) == []


def test_artifact_receipts_require_the_current_worker_lease(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "current-worker", ttl_seconds=30)

    with pytest.raises(LeaseLostError):
        runtime.record_artifact_receipt(
            attempt["attempt_id"], "proposal", "artifacts/stale.json",
            owner_id="other-worker", fence_token=lease["fence_token"],
        )
    receipt = runtime.record_artifact_receipt(
        attempt["attempt_id"], "proposal", "artifacts/current.json",
        owner_id="current-worker", fence_token=lease["fence_token"],
    )
    migration = runtime.record_system_artifact_receipt(
        attempt["attempt_id"], "migration", "artifacts/legacy.json", system_reason="legacy_import_migration",
    )

    assert receipt["artifact_uri"] == "artifacts/current.json"
    assert migration["metadata"] == {"metadata": {}, "system_reason": "legacy_import_migration"}


def test_control_events_are_durable_idempotent_and_conflict_safe(runtime):
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1")["run_id"])
    first = runtime.append_control_event(
        attempt["attempt_id"], "pause", {"reason": "user"}, decision_key="control-pause-1",
    )
    repeated = runtime.append_control_event(
        attempt["attempt_id"], "pause", {"reason": "user"}, decision_key="control-pause-1",
    )

    assert first["idempotent"] is False
    assert repeated["idempotent"] is True
    assert repeated["event_id"] == first["event_id"]
    assert len(runtime.list_human_decisions(attempt["attempt_id"])) == 1
    assert len(runtime.list_events(attempt["attempt_id"])) == 1
    with pytest.raises(ValueError, match="control_decision_conflict"):
        runtime.append_control_event(
            attempt["attempt_id"], "cancel", {"reason": "user"}, decision_key="control-pause-1",
        )


def test_resource_lease_is_single_writer_and_stale_fence_cannot_release(runtime):
    first = runtime.acquire_resource_lease("project:story.json", "worker-a", ttl_seconds=1, now=10)
    with pytest.raises(LeaseLostError):
        runtime.acquire_resource_lease("project:story.json", "worker-b", ttl_seconds=10, now=10)

    second = runtime.acquire_resource_lease("project:story.json", "worker-b", ttl_seconds=10, now=12)
    assert second["fence_token"] == first["fence_token"] + 1
    with pytest.raises(LeaseLostError):
        runtime.release_resource_lease("project:story.json", "worker-a", first["fence_token"])
    runtime.release_resource_lease("project:story.json", "worker-b", second["fence_token"])


def test_resource_lease_concurrent_acquire_has_one_winner(runtime):
    def acquire(index: int) -> str:
        try:
            runtime.acquire_resource_lease("project:canonical-write", f"worker-{index}", ttl_seconds=30)
            return "won"
        except LeaseLostError:
            return "lost"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(acquire, range(8)))

    assert results.count("won") == 1
    assert results.count("lost") == 7


def test_recoverable_source_compatibility_is_recomputed_from_disk(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("unchanged", encoding="utf-8")
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", config={
        "source_file_path": str(source), "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
    })
    attempt_id = store.create_attempt(run["run_id"])["attempt_id"]

    assert store.scan_recoverable_attempts()[0]["source_compatible"] is True
    source.write_text("modified", encoding="utf-8")
    assert store.scan_recoverable_attempts()[0]["source_compatible"] is False
    source.unlink()
    assert store.scan_recoverable_attempts()[0]["source_compatible"] is False


def test_recoverable_remaining_cost_uses_durable_usage_ledger(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", lineage_id="lineage-cost", config={
        "source_file_path": str(source), "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
        "budget_config": {"max_cost_usd": 3.0},
    })
    attempt = store.create_attempt(run["run_id"])
    ledger_path = tmp_path / "system" / "imports" / "lineage-cost" / "attempts" / attempt["attempt_id"] / "usage_ledger.json"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(json.dumps({"cost_usd": 0.75}), encoding="utf-8")

    remaining = store.scan_recoverable_attempts()[0]["remaining_cost"]
    assert remaining == {"max_cost_usd": 3.0, "spent_cost_usd": 0.75, "remaining_cost_usd": 2.25, "unknown_spend": False, "remaining_chunks": 0}
