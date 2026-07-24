from __future__ import annotations

import sqlite3

import pytest

from sidecar.harness.contracts import AgentEvent, ApprovalDecision
from sidecar.runtime.agent_runtime import RuntimeStore


@pytest.fixture
def runtime(tmp_path):
    return RuntimeStore(tmp_path)


def _attempt(runtime: RuntimeStore) -> tuple[dict, dict]:
    attempt = runtime.create_attempt(runtime.create_run(workflow_id="W1", lineage_id="lineage-1")["run_id"])
    lease = runtime.acquire_lease(attempt["attempt_id"], "worker-1", ttl_seconds=30)
    return attempt, lease


def test_schema_v6_preserves_legacy_events_and_persists_v1_event_metadata(runtime: RuntimeStore) -> None:
    attempt, lease = _attempt(runtime)
    legacy = runtime.append_event(
        attempt["attempt_id"], "legacy.progress", {"message": "old"},
        owner_id="worker-1", fence_token=lease["fence_token"],
    )
    event = runtime.append_harness_event(
        AgentEvent(
            event_id="event-v1",
            run_id=attempt["run_id"],
            lineage_id="lineage-1",
            attempt_id=attempt["attempt_id"],
            sequence=0,
            event_type="tool.result",
            actor_kind="tool",
            actor_id="w1.extract",
            payload={"summary": "done"},
            causation_id="call-1",
            correlation_id="plan-1",
            idempotency_key="result:call-1",
        ),
        owner_id="worker-1",
        fence_token=lease["fence_token"],
    )

    assert legacy["contract_version"] == "legacy/v0"
    assert event["contract_version"] == "AgentEvent/v1"
    assert event["actor"] == {"kind": "tool", "id": "w1.extract"}
    assert event["causation_id"] == "call-1"
    assert event["correlation_id"] == "plan-1"
    assert runtime.get_event_by_idempotency(attempt["attempt_id"], "result:call-1") == event
    assert [item["sequence"] for item in runtime.list_events(attempt["attempt_id"])] == [1, 2]


def test_harness_event_idempotency_replays_same_event_and_rejects_conflict(runtime: RuntimeStore) -> None:
    attempt, lease = _attempt(runtime)
    event = AgentEvent(
        event_id="event-v1",
        run_id=attempt["run_id"],
        lineage_id="lineage-1",
        attempt_id=attempt["attempt_id"],
        sequence=0,
        event_type="tool.intent",
        actor_kind="agent",
        actor_id="worker-1",
        payload={"tool": "source.read"},
        idempotency_key="intent:source.read:1",
    )
    first = runtime.append_harness_event(event, owner_id="worker-1", fence_token=lease["fence_token"])
    second = runtime.append_harness_event(event, owner_id="worker-1", fence_token=lease["fence_token"])

    assert second == first
    with pytest.raises(ValueError, match="event_idempotency_conflict"):
        runtime.append_event(
            attempt["attempt_id"], "tool.result", {"tool": "source.read"},
            owner_id="worker-1", fence_token=lease["fence_token"],
            idempotency_key="intent:source.read:1",
        )

    with pytest.raises(ValueError, match="event_id_conflict"):
        runtime.append_event(
            attempt["attempt_id"], "tool.result", {"tool": "source.read"},
            owner_id="worker-1", fence_token=lease["fence_token"], event_id="event-v1",
        )


def test_approval_crud_uses_existing_decision_idempotency(runtime: RuntimeStore) -> None:
    attempt, _ = _attempt(runtime)
    approval = ApprovalDecision(
        decision_id="decision-1",
        decision_key="accept:package-1",
        attempt_id=attempt["attempt_id"],
        decision="approve",
        actor_id="user-1",
        expected_version=1,
    )

    first = runtime.record_approval(approval)
    assert runtime.record_approval(approval) == first
    assert runtime.get_approval("decision-1") == first
    assert first["payload"]["contract_version"] == "ApprovalDecision/v1"


def test_v6_migration_adds_event_columns_without_rewriting_legacy_events(tmp_path) -> None:
    store = RuntimeStore(tmp_path)
    attempt, lease = _attempt(store)
    legacy = store.append_event(
        attempt["attempt_id"], "legacy.progress", {"message": "before migration"},
        owner_id="worker-1", fence_token=lease["fence_token"],
    )

    with sqlite3.connect(store.database_path) as connection:
        connection.execute("DROP INDEX run_events_idempotency_key")
        connection.execute("DROP INDEX run_events_correlation_id")
        for column in ("contract_version", "actor_json", "idempotency_key", "causation_id", "correlation_id"):
            connection.execute(f"ALTER TABLE run_events DROP COLUMN {column}")
        connection.execute("DELETE FROM schema_migrations WHERE version = 6")

    migrated = RuntimeStore(tmp_path)
    restored = migrated.get_event(legacy["event_id"])
    with sqlite3.connect(migrated.database_path) as connection:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        columns = {row[1] for row in connection.execute("PRAGMA table_info(run_events)")}

    assert restored is not None
    assert restored["payload"] == {"message": "before migration"}
    assert restored["contract_version"] == "legacy/v0"
    assert {"contract_version", "actor_json", "idempotency_key", "causation_id", "correlation_id"} <= columns
    assert 6 in versions
