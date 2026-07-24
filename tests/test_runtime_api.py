from __future__ import annotations

import sqlite3
import asyncio
import hashlib
import json

import pytest

from fastapi.testclient import TestClient

from sidecar.main import create_app


def _client(tmp_path):
    return TestClient(create_app(str(tmp_path)))


def _attempt(client: TestClient) -> str:
    store = client.app.state.runtime_store
    project_path = client.app.state.project_path
    source_path = f"{project_path}/source.txt"
    with open(source_path, "w", encoding="utf-8") as source:
        source.write("Chapter 1\nRuntime fixture.")
    run = store.create_run(
        workflow_id="W1", lineage_id="lineage-test", thread_id="thread-test",
        config={"project_path": project_path, "source_file_path": source_path, "source_hash": hashlib.sha256(open(source_path, "rb").read()).hexdigest(), "profile": "balanced"},
    )
    return store.create_attempt(run["run_id"], attempt_id="attempt-test")["attempt_id"]


def test_runtime_rejects_project_identity_mismatch(tmp_path):
    with _client(tmp_path) as client:
        response = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path / "other"),
            "source_file_path": "source.txt",
        })

    assert response.status_code == 409
    assert response.json()["detail"] == "project_path_mismatch"


def test_reopen_exposes_recoverable_attempt(tmp_path):
    first = _client(tmp_path)
    attempt_id = _attempt(first)
    first.app.state.runtime_store.acquire_lease(attempt_id, "old-sidecar", ttl_seconds=300)
    first.close()

    with _client(tmp_path) as reopened:
        response = reopened.get("/runtime/runs/recoverable")

    assert response.status_code == 200
    assert [item["attempt_id"] for item in response.json()["runs"]] == [attempt_id]


def test_event_cursor_is_monotonic_and_deduplicated(tmp_path):
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        store = client.app.state.runtime_store
        lease = store.acquire_lease(attempt_id, "test-worker", ttl_seconds=30)
        for message in ("one", "two", "three"):
            store.append_event(attempt_id, "activity", {"message": message}, owner_id="test-worker", fence_token=lease["fence_token"])

        assert [event["sequence"] for event in client.get(f"/runtime/runs/{attempt_id}/events?afterSequence=1").json()["events"]] == [2, 3]
        stream = client.get(f"/workflow/stream?attempt_id={attempt_id}", headers={"Last-Event-ID": "2"})

    assert "id: 3" in stream.text
    assert '"sequence":3' in stream.text


def test_checkpoints_endpoint_returns_checkpoint_metadata_not_artifact_receipts(tmp_path):
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        store = client.app.state.runtime_store
        store.record_checkpoint_metadata(attempt_id, "checkpoint-1", node="split_chunks", sequence=1, metadata={"summary": "split"})
        lease = store.acquire_lease(attempt_id, "receipt-worker", ttl_seconds=30)
        store.record_artifact_receipt(
            attempt_id, "proposal", "artifacts/proposal.json",
            owner_id="receipt-worker", fence_token=lease["fence_token"],
        )
        response = client.get(f"/runtime/runs/{attempt_id}/checkpoints")

    assert response.json()["checkpoints"] == [{
        "checkpoint_id": "checkpoint-1", "attempt_id": attempt_id, "parent_checkpoint_id": None,
        "node": "split_chunks", "sequence": 1, "metadata": {"summary": "split"},
        "created_at": response.json()["checkpoints"][0]["created_at"],
    }]


def test_runtime_commands_are_idempotent_and_fork_keeps_parent_immutable(tmp_path):
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        client.app.state.runtime_store.record_checkpoint_metadata(attempt_id, "fork-checkpoint", node="process_chunks", sequence=1)
        first = client.post(f"/runtime/runs/{attempt_id}/pause").json()
        second = client.post(f"/runtime/runs/{attempt_id}/pause").json()
        cancelled = client.post(f"/runtime/runs/{attempt_id}/cancel").json()
        duplicate_cancel = client.post(f"/runtime/runs/{attempt_id}/cancel").json()
        fork = client.post(f"/runtime/runs/{attempt_id}/fork", json={"checkpoint_id": "fork-checkpoint", "decision_id": "fork-1"}).json()
        duplicate_fork = client.post(f"/runtime/runs/{attempt_id}/fork", json={"checkpoint_id": "fork-checkpoint", "decision_id": "fork-1"}).json()
        parent = client.get(f"/runtime/runs/{attempt_id}").json()

    assert first["status"] == second["status"] == "paused"
    assert cancelled["status"] == duplicate_cancel["status"] == "cancelled"
    assert fork["attempt"]["attempt_id"] != attempt_id
    assert duplicate_fork["attempt"]["attempt_id"] == fork["attempt"]["attempt_id"]
    assert duplicate_fork["idempotent"] is True
    assert fork["attempt"]["checkpoint_id"] == "fork-checkpoint"
    assert fork["attempt"]["parent_attempt_id"] == attempt_id
    assert fork["attempt"]["fork_checkpoint_id"] == "fork-checkpoint"
    assert parent["attempt"]["status"] == "cancelled"


def test_fork_rejects_checkpoint_from_a_different_attempt(tmp_path):
    with _client(tmp_path) as client:
        parent_id = _attempt(client)
        other_run = client.app.state.runtime_store.create_run(workflow_id="W1")
        other_id = client.app.state.runtime_store.create_attempt(other_run["run_id"])["attempt_id"]
        client.app.state.runtime_store.record_checkpoint_metadata(other_id, "other-checkpoint", node="split_chunks", sequence=1)
        response = client.post(f"/runtime/runs/{parent_id}/fork", json={"checkpoint_id": "other-checkpoint", "decision_id": "wrong-checkpoint"})
        parent = client.get(f"/runtime/runs/{parent_id}").json()

    assert response.status_code == 409
    assert response.json()["detail"] == "checkpoint_does_not_belong_to_parent_attempt"
    assert parent["attempt"]["attempt_id"] == parent_id
    assert parent["attempt"]["checkpoint_id"] is None


def test_preview_only_fork_cannot_resume_and_never_replays_the_parent(tmp_path):
    with _client(tmp_path) as client:
        parent_id = _attempt(client)
        store = client.app.state.runtime_store
        store.record_checkpoint_metadata(parent_id, "fork-checkpoint", node="process_chunks", sequence=1)
        fork = client.post(
            f"/runtime/runs/{parent_id}/fork",
            json={"checkpoint_id": "fork-checkpoint", "decision_id": "fork-preview-only"},
        )
        child_id = fork.json()["attempt"]["attempt_id"]
        response = client.post(f"/runtime/runs/{child_id}/resume", json={})
        child_events = client.get(f"/runtime/runs/{child_id}/events").json()["events"]

    assert fork.status_code == 200
    assert fork.json()["attempt"]["status"] == "paused"
    assert response.status_code == 409
    assert response.json()["detail"] == "fork_snapshot_not_resumable"
    assert [event["event_type"] for event in child_events] == ["fork_snapshot"]


def test_later_pause_after_a_resume_transition_uses_a_new_control_decision(tmp_path):
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        first = client.post(f"/runtime/runs/{attempt_id}/pause")
        client.app.state.runtime_store.set_attempt_status(attempt_id, "running")
        second = client.post(f"/runtime/runs/{attempt_id}/pause")
        repeated = client.post(f"/runtime/runs/{attempt_id}/pause")
        controls = [
            event for event in client.get(f"/runtime/runs/{attempt_id}/events").json()["events"]
            if event["event_type"] == "control"
        ]

    assert first.status_code == second.status_code == repeated.status_code == 200
    assert len(controls) == 2
    assert controls[0]["causation_id"] != controls[1]["causation_id"]


def test_decisions_tools_and_config_redact_secrets(tmp_path):
    secret = "sk-secret-should-never-persist"
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        first = client.post("/runtime/decisions/approve-1", json={"attempt_id": attempt_id, "decision": "approve", "api_key": secret}).json()
        second = client.post("/runtime/decisions/approve-1", json={"attempt_id": attempt_id, "decision": "approve"}).json()
        tool = client.app.state.runtime_store.record_tool_intent(attempt_id, "remote.call", {"api_key": secret})
        client.app.state.runtime_store.record_tool_unknown_outcome(tool["tool_call_id"], "restart")
        detail = client.get(f"/runtime/runs/{attempt_id}").json()
        resume = client.post(f"/runtime/runs/{attempt_id}/resume", json={"api_key": secret, "provider": "deepseek", "model": "deepseek-chat"})
        db = client.app.state.runtime_store.database_path

    assert first["decision_id"] == second["decision_id"]
    assert detail["unknown_calls"][0]["tool_call_id"] == tool["tool_call_id"]
    assert "intent_payload" not in detail["unknown_calls"][0]
    assert resume.status_code == 409
    with sqlite3.connect(db) as connection:
        dumped = "\n".join(str(row) for row in connection.execute("SELECT * FROM agent_runs, agent_attempts, human_decisions, tool_calls"))
    assert secret not in dumped


def test_human_decision_id_and_key_conflicts_return_409(tmp_path):
    with _client(tmp_path) as client:
        first_attempt = _attempt(client)
        other_run = client.app.state.runtime_store.create_run(workflow_id="W1")
        second_attempt = client.app.state.runtime_store.create_attempt(other_run["run_id"])["attempt_id"]
        payload = {"attempt_id": first_attempt, "decision": "approve", "payload": {"mode": "safe"}}
        first = client.post("/runtime/decisions/shared-decision", json=payload)
        exact_repeat = client.post("/runtime/decisions/shared-decision", json=payload)
        conflicting_key = client.post("/runtime/decisions/shared-decision", json={
            **payload, "decision": "reject",
        })
        wrong_attempt = client.post("/runtime/decisions/shared-decision", json={
            **payload, "attempt_id": second_attempt,
        })

    assert first.status_code == exact_repeat.status_code == 200
    assert first.json() == exact_repeat.json()
    assert conflicting_key.status_code == 409
    assert conflicting_key.json()["detail"] == "decision_id_conflict"
    assert wrong_attempt.status_code == 409
    assert wrong_attempt.json()["detail"] == "decision_id_conflict"


def test_unknown_outcome_detail_decision_and_resume_gate_are_sanitized(tmp_path, monkeypatch):
    from sidecar.routers import workflows

    async def fake_resume(**_kwargs):
        return True

    monkeypatch.setattr(workflows, "resume_w1_attempt", fake_resume)
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        store = client.app.state.runtime_store
        idempotency_key = "a" * 64
        call = store.record_tool_intent(attempt_id, "provider.chat.completions", {
            "message_hash": "b" * 64,
            "model": "deepseek-chat",
            "estimated_input_tokens": 10,
            "estimated_output_tokens": 5,
            "sequence": 1,
            "idempotency_key": idempotency_key,
            "prompt": "private source sk-never-return",
        })
        store.record_tool_unknown_outcome(call["tool_call_id"], "socket failed with sk-never-return")
        store.set_attempt_status(attempt_id, "waiting_human")
        detail = client.get(f"/runtime/runs/{attempt_id}")
        recoverable = client.get("/runtime/runs/recoverable")
        blocked = client.post(f"/runtime/runs/{attempt_id}/resume", json={"api_key": "sk-transient"})
        decision_key = f"retry_provider_call:{idempotency_key}"
        authorized = client.post(f"/runtime/decisions/{decision_key}", json={
            "attempt_id": attempt_id, "decision": "authorize_retry_once",
        })
        authorized_detail = client.get(f"/runtime/runs/{attempt_id}")
        resumed = client.post(f"/runtime/runs/{attempt_id}/resume", json={"api_key": "sk-transient"})

    expected_unknown = {
        "tool_call_id": call["tool_call_id"],
        "idempotency_key": idempotency_key,
        "decision_key": decision_key,
        "safe_reason": "transport_outcome_unknown",
        "decision_state": "pending",
    }
    assert detail.json()["unknown_calls"] == [expected_unknown]
    assert recoverable.json()["runs"][0]["unknown_calls"] == [expected_unknown]
    assert "private source" not in detail.text
    assert "sk-never-return" not in detail.text
    assert "intent_payload" not in detail.text
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["unknown_calls"] == [expected_unknown]
    assert authorized.status_code == 200
    assert authorized_detail.json()["unknown_calls"][0]["decision_state"] == "authorize_retry_once"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "resumed"


def test_unknown_outcome_cancel_is_atomic_idempotent_and_conflict_safe(tmp_path):
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        store = client.app.state.runtime_store
        idempotency_key = "c" * 64
        call = store.record_tool_intent(attempt_id, "provider.chat.completions", {
            "idempotency_key": idempotency_key,
        })
        store.record_tool_unknown_outcome(call["tool_call_id"], "ambiguous_transport")
        store.set_attempt_status(attempt_id, "waiting_human")
        decision_key = f"retry_provider_call:{idempotency_key}"
        payload = {"attempt_id": attempt_id, "decision": "cancel"}
        first = client.post(f"/runtime/decisions/{decision_key}", json=payload)
        repeated = client.post(f"/runtime/decisions/{decision_key}", json=payload)
        conflict = client.post(f"/runtime/decisions/{decision_key}", json={
            "attempt_id": attempt_id, "decision": "authorize_retry_once",
        })
        attempt = store.get_attempt(attempt_id)
        cancel_events = [
            event for event in store.list_events(attempt_id)
            if event["event_type"] == "control" and event["payload"].get("command") == "cancel"
        ]

    assert first.status_code == repeated.status_code == 200
    assert first.json()["decision_id"] == repeated.json()["decision_id"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "decision_key_conflict"
    assert attempt["status"] == "cancelled"
    assert len(cancel_events) == 1


def test_resume_rejects_same_hash_source_path_substitution_without_updating_identity(tmp_path):
    outside_source = tmp_path.parent / f"{tmp_path.name}-outside-source.txt"
    outside_source.write_text("Chapter 1\nRuntime fixture.", encoding="utf-8")
    with _client(tmp_path) as client:
        attempt_id = _attempt(client)
        store = client.app.state.runtime_store
        original_run = store.get_run(store.get_attempt(attempt_id)["run_id"])
        response = client.post(f"/runtime/runs/{attempt_id}/resume", json={
            "api_key": "sk-transient",
            "source_file_path": str(outside_source),
            "source_hash": hashlib.sha256(outside_source.read_bytes()).hexdigest(),
        })
        persisted_run = store.get_run(original_run["run_id"])

    assert response.status_code == 409
    assert response.json()["detail"] == "registered_source_path_mismatch"
    assert persisted_run["config"]["source_file_path"] == original_run["config"]["source_file_path"]
    assert persisted_run["config"]["source_hash"] == original_run["config"]["source_hash"]


def test_resume_after_restart_relaunches_once_with_transient_credentials(tmp_path, monkeypatch):
    from sidecar.routers import workflows

    source = tmp_path / "source.txt"
    source.write_text("Chapter 1\nRecovered.", encoding="utf-8")
    launches: list[dict] = []

    async def fake_run(session_id: str, config: dict) -> None:
        launches.append({"session_id": session_id, "api_key": config["context"]["api_key"]})
        await asyncio.sleep(60)

    monkeypatch.setattr(workflows, "_run_w1", fake_run)
    first = _client(tmp_path)
    store = first.app.state.runtime_store
    run = store.create_run(workflow_id="W1", lineage_id="restart-lineage", config={
        "project_path": str(tmp_path), "source_file_path": str(source), "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
        "model": "deepseek-chat", "profile": "balanced",
    })
    attempt_id = store.create_attempt(run["run_id"])["attempt_id"]
    first.close()

    with _client(tmp_path) as restarted:
        payload = {"api_key": "sk-transient-restart-secret", "provider": "deepseek", "model": "deepseek-chat"}
        first_resume = restarted.post(f"/runtime/runs/{attempt_id}/resume", json=payload)
        second_resume = restarted.post(f"/runtime/runs/{attempt_id}/resume", json=payload)
        assert first_resume.json()["restarted"] is True
        assert second_resume.json()["restarted"] is False
        assert launches == [{"session_id": attempt_id, "api_key": "sk-transient-restart-secret"}]
        with sqlite3.connect(restarted.app.state.runtime_store.database_path) as connection:
            dumped = "\n".join(str(row) for row in connection.execute("SELECT * FROM agent_runs, agent_attempts, run_events"))

    assert "sk-transient-restart-secret" not in dumped


def test_startup_discovers_one_validated_legacy_recovery(tmp_path):
    source = tmp_path / "legacy.txt"
    source.write_text("Chapter 1\nLegacy.", encoding="utf-8")
    (tmp_path / "import_progress.json").write_text(json.dumps({
        "source_file_path": str(source), "total_chunks": 4, "completed_chunk_ids": [0, 1],
        "model": "deepseek-chat", "prompt_profile": "balanced",
    }), encoding="utf-8")

    with _client(tmp_path) as client:
        recoverable = client.get("/runtime/runs/recoverable").json()["runs"]

    assert len(recoverable) == 1
    assert recoverable[0]["workflow_id"] == "W1"
    assert recoverable[0]["lineage_id"]
    assert recoverable[0]["attempt_id"]
    assert recoverable[0]["source_compatible"] is True
    assert recoverable[0]["progress"] == 0.5
    assert recoverable[0]["remaining_cost"] == {"max_cost_usd": 3.0, "spent_cost_usd": None, "remaining_cost_usd": None, "unknown_spend": True, "remaining_chunks": 2}
    assert recoverable[0]["unknown_calls"] == []


def test_legacy_resume_applies_fail_closed_three_dollar_budget(tmp_path, monkeypatch):
    from sidecar.routers import workflows

    source = tmp_path / "legacy.txt"
    source.write_text("Chapter 1\nLegacy.", encoding="utf-8")
    (tmp_path / "import_progress.json").write_text(json.dumps({
        "source_file_path": str(source), "total_chunks": 2, "completed_chunk_ids": [0],
    }), encoding="utf-8")
    launches: list[dict] = []

    async def fake_run(_: str, config: dict) -> None:
        launches.append(config)
        await asyncio.sleep(60)

    app = create_app(str(tmp_path))
    monkeypatch.setattr(workflows, "_run_w1", fake_run)
    with TestClient(app) as client:
        attempt_id = client.get("/runtime/runs/recoverable").json()["runs"][0]["attempt_id"]
        response = client.post(f"/runtime/runs/{attempt_id}/resume", json={"api_key": "sk-transient", "provider": "deepseek", "model": "deepseek-chat"})

    assert response.json()["status"] == "resumed"
    assert launches[0]["budget_policy"] == {
        "max_cost_usd": 3.0, "fail_on_unknown_pricing": True, "fail_on_missing_usage": True,
    }
    assert launches[0]["context"]["budget_policy"] == launches[0]["budget_policy"]


def test_lifespan_reuses_runtime_store_and_closes_then_reopens_workflow_saver(tmp_path):
    from sidecar.workflows import w1_import

    app = create_app(str(tmp_path))
    store_id = id(app.state.runtime_store)
    project_key = str(tmp_path.resolve())
    with TestClient(app):
        assert id(app.state.runtime_store) == store_id
        w1_import.get_graph(tmp_path)
        first_saver = w1_import._PROJECT_CHECKPOINTERS[project_key]

    assert project_key not in w1_import._PROJECT_CHECKPOINTERS
    with pytest.raises(Exception):
        first_saver.conn.execute("SELECT 1")

    with TestClient(app):
        assert id(app.state.runtime_store) == store_id
        w1_import.get_graph(tmp_path)
        second_saver = w1_import._PROJECT_CHECKPOINTERS[project_key]

    assert second_saver is not first_saver
