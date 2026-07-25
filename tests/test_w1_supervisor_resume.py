from __future__ import annotations

import asyncio
import copy
import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidecar.main import create_app
from sidecar.models.state import make_source_span
from sidecar.runtime.agent_runtime import RuntimeStore
from sidecar.runtime.w1_supervisor_snapshot import (
    SnapshotValidationError,
    load_w1_supervisor_snapshot,
    write_w1_supervisor_snapshot,
)
from sidecar.supervisor import policy
from sidecar.workflows import w1_import
from sidecar.workflows import w1_run_events as events
from sidecar.workflows.w1_agentic_adapter import build_supervisor_snapshot_identities


def _collect(stream):
    async def run():
        return [item async for item in stream]

    return asyncio.run(run())


def _parent(tmp_path: Path):
    source_text = "第1章\n独特原文句子：星门在雨夜开启，任何快照都不能保存这一句。\n"
    source = tmp_path / "source.txt"
    source.write_text(source_text, encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    store = RuntimeStore(tmp_path)
    run = store.create_run(
        workflow_id="W1", lineage_id="lineage_resume", thread_id="thread_resume",
        config={
            "project_path": str(tmp_path), "source_file_path": str(source), "source_hash": source_hash,
            "model": "deepseek-v4-flash", "profile": "balanced", "prompt_profile": "balanced",
            "execution_mode": "supervisor", "import_mode": "import_all", "budget_config": {"max_cost_usd": 3.0},
        },
    )
    attempt = store.create_attempt(run["run_id"], attempt_id="attempt_parent")
    lease = store.acquire_lease(attempt["attempt_id"], "resume-test", ttl_seconds=60)
    config = {
        "project_path": str(tmp_path), "source_file_path": str(source), "source_hash": source_hash,
        "model": "deepseek-v4-flash", "prompt_profile": "balanced", "execution_mode": "supervisor",
        "import_mode": "import_all", "budget_config": {"max_cost_usd": 3.0}, "runtime_store": store,
        "attempt_id": attempt["attempt_id"], "runtime_owner_id": "resume-test",
        "runtime_fence_token": lease["fence_token"], "lineage_id": run["lineage_id"],
        "w1_supervisor_staged_source_relative_path": "system/imports/lineage_resume/attempts/attempt_parent/raw_source.txt",
    }
    staged_source = tmp_path / config["w1_supervisor_staged_source_relative_path"]
    staged_source.parent.mkdir(parents=True, exist_ok=True)
    staged_source.write_text(source_text, encoding="utf-8")
    span = make_source_span(source_text, 0, len(source_text))
    snapshot_state = policy._snapshot_state({
        "source_text": source_text,
        "import_run_id": "sup_parent_identity",
        "source_language": "zh",
        "chunks": [{"chunk_id": 0, "source_span": span, "content": source_text, "raw_content": source_text}],
        "chunk_extractions": [{"chunk_id": 0, "truth": "complete", "domain_receipts": {}, "manuscript_content": source_text, "summary": "星门开启"}],
        "entity_registry": {
            "characters": {"char_han": {"id": "char_han", "canonical_name": "韩立", "background": "山村少年", "experience": [{"title": "入门"}]}},
            "events": {"event_gate": {"id": "event_gate", "title": "星门开启", "timelineClass": "canonical_event"}},
            "world": {"七玄门": "organization"},
            "world_detailed": {"七玄门": {"id": "world_qixuan", "name": "七玄门", "category": "organization", "containerId": "world_container_organizations"}},
        },
        "relationships": [{"id": "rel_teacher", "sourceId": "char_han", "targetId": "char_teacher", "type": "师徒关系"}],
        "raw_relationships": [{"id": "rel_teacher", "source_character_name": "韩立", "target_character_name": "墨大夫", "type": "师徒关系"}],
        "character_tags": [{"id": "tag_cultivator", "name": "修仙者"}],
        "world_settings": {}, "world_containers": [{"id": "world_container_organizations", "name": "门派组织", "importCategoryKey": "organizations"}],
        "organizer_output": {"world_containers": [{"id": "world_container_organizations", "name": "门派组织"}], "world_items": [{"id": "world_qixuan", "name": "七玄门"}]},
        "timeline_architecture": {}, "timeline_branches": [], "reducer_artifact": {},
        "import_review_report": {}, "judge_artifact": {}, "gate_failures": [], "manuscript_chapters": [{"chapter_id": "chap_1", "scene_id": "scene_1", "title": "第1章", "summary": "星门开启", "chunk_ids": [0], "source_span": span, "manuscript_content": source_text}],
        "proposals": [], "evidence_cards": [], "import_run_manifest": {"import_run_id": "sup_parent_identity"}, "project_structure_digest": {},
    })
    source_identity, config_identity = build_supervisor_snapshot_identities(config, project_path=tmp_path)
    checkpoint_id = "checkpoint_parent_reduce"
    ref = write_w1_supervisor_snapshot(
        tmp_path, lineage_id=run["lineage_id"], attempt_id=attempt["attempt_id"], checkpoint_id=checkpoint_id,
        node="reduce_repair", next_node="architect_timeline", source_identity=source_identity,
        config_identity=config_identity, state=snapshot_state,
        completed_nodes=["validate_file", "extract_window", "reduce_repair"], budget_snapshot={"budget_limit_usd": 3.0, "spent_usd": 0.0},
    )
    store.record_checkpoint_metadata(
        attempt["attempt_id"], checkpoint_id, node="reduce_repair", sequence=1,
        metadata={"recovery_mode": "resumable", "snapshot_ref": ref.to_dict(), "next_node": "architect_timeline"},
        owner_id="resume-test", fence_token=lease["fence_token"],
    )
    store.set_attempt_status(attempt["attempt_id"], "paused", owner_id="resume-test", fence_token=lease["fence_token"])
    checkpoint = store.list_checkpoint_metadata(attempt["attempt_id"])[-1]
    return source, source_text, store, run, attempt, config, checkpoint


def test_snapshot_never_persists_source_body_and_child_skips_completed_tools(tmp_path, monkeypatch):
    source, source_text, store, run, parent, config, checkpoint = _parent(tmp_path)
    snapshot_ref = checkpoint["metadata"]["snapshot_ref"]
    snapshot_root = tmp_path / snapshot_ref["relative_path"]
    assert source_text not in "\n".join(
        path.read_text(encoding="utf-8") for path in snapshot_root.rglob("*.json")
    )

    child = store.fork_attempt(parent["attempt_id"], checkpoint_id=checkpoint["checkpoint_id"], decision_id="fork-resume")
    child_id = child["attempt"]["attempt_id"]
    child_lease = store.acquire_lease(child_id, "resume-test", ttl_seconds=60)
    fork = store.get_fork_snapshot(child_id)
    assert fork and fork["resumable"] is True

    calls = {name: 0 for name in ("validate", "split", "extract", "reduce", "architect", "qa", "judge", "proposal")}

    async def forbidden_validate(_state):
        calls["validate"] += 1
        raise AssertionError("validate must not replay")

    async def forbidden_split(_state):
        calls["split"] += 1
        raise AssertionError("split must not replay")

    async def architect(state):
        calls["architect"] += 1
        assert state["chunks"][0]["content"] == source_text
        assert state["import_run_id"] == "sup_parent_identity"
        assert state["character_tags"][0]["name"] == "修仙者"
        return {"timeline_architecture": {"ok": True}, "timeline_branches": []}

    async def qa(_state):
        calls["qa"] += 1
        return {"gate_failures": []}

    async def proposal(_state):
        calls["proposal"] += 1
        assert _state["manuscript_chapters"][0]["manuscript_content"] == source_text
        assert _state["organizer_output"]["world_items"][0]["name"] == "七玄门"
        return {"proposals": [{"id": "proposal_resume"}]}

    async def judge(state, _tools):
        calls["judge"] += 1
        return {**state, "judge_artifact": {"passed": True}}

    monkeypatch.setattr(policy, "node_validate_file", forbidden_validate)
    monkeypatch.setattr(policy, "node_split_chunks", forbidden_split)
    monkeypatch.setattr(policy, "_prepare_reviewer_staging_state", lambda state: state)
    monkeypatch.setattr(policy, "enforce_timeline_density", lambda state: state)
    monkeypatch.setattr(policy, "_run_judge_import", judge)
    monkeypatch.setattr(policy, "_apply_thematic_reruns", lambda state, *_args: asyncio.sleep(0, result=state))
    monkeypatch.setattr(policy, "build_tool_registry", lambda: {
        "architect_timeline": architect,
        "qa_review": qa,
        "proposal_write": proposal,
        "reduce_entities": lambda _state: (_ for _ in ()).throw(AssertionError("reduce must not replay")),
        "minor_repair": lambda _state: (_ for _ in ()).throw(AssertionError("repair must not replay")),
        "judge_import": object(),
    })

    resumed = {
        **config,
        "attempt_id": child_id,
        "w1_supervisor_resume_snapshot_ref": fork["state_reference"]["snapshot_ref"],
        "snapshot_source_attempt_id": parent["attempt_id"],
        "runtime_fence_token": child_lease["fence_token"],
        "session_id": "",
    }
    updates = _collect(w1_import.run_streaming(str(tmp_path), resumed))
    assert calls == {"validate": 0, "split": 0, "extract": 0, "reduce": 0, "architect": 1, "qa": 1, "judge": 1, "proposal": 1}
    assert [item["current_node"] for item in updates] == ["architect_timeline", "qa_review", "judge_import", "proposal_write", "done"]


def test_proposal_gate_resume_does_not_rewrite_and_stays_awaiting_acceptance(tmp_path, monkeypatch):
    _source, _source_text, _store, run, parent, config, checkpoint = _parent(tmp_path)
    state = load_w1_supervisor_snapshot(tmp_path, checkpoint["metadata"]["snapshot_ref"])["state"]
    source_identity, config_identity = build_supervisor_snapshot_identities(config, project_path=tmp_path)
    gate_ref = write_w1_supervisor_snapshot(
        tmp_path, lineage_id=run["lineage_id"], attempt_id=parent["attempt_id"], checkpoint_id="checkpoint_proposal_gate",
        node="proposal_write", next_node=None, source_identity=source_identity, config_identity=config_identity,
        state=state, completed_nodes=["validate_file", "extract_window", "reduce_repair", "architect_timeline", "qa_review", "judge_import", "proposal_write"],
    )
    called = {"proposal": 0}

    async def forbidden_proposal(_state):
        called["proposal"] += 1
        raise AssertionError("proposal_write must not run from proposal_gate")

    monkeypatch.setattr(policy, "build_tool_registry", lambda: {"proposal_write": forbidden_proposal})
    updates = _collect(policy.run_supervisor_streaming(str(tmp_path), {
        **config,
        "w1_supervisor_resume_snapshot_ref": gate_ref.to_dict(),
        "snapshot_source_attempt_id": parent["attempt_id"],
    }))
    assert called["proposal"] == 0
    assert updates[-1]["current_node"] == "done"
    assert updates[-1]["converge_status"] == "awaiting_acceptance"
    assert updates[-1]["orchestrator_phase"] == "proposal_gate"


def test_tampered_source_config_and_unknown_outcome_fail_closed(tmp_path):
    source, _source_text, store, _run, parent, config, checkpoint = _parent(tmp_path)
    reference = checkpoint["metadata"]["snapshot_ref"]
    changed = tmp_path / "changed.txt"
    changed.write_text("different source", encoding="utf-8")
    with pytest.raises(SnapshotValidationError):
        _collect(policy.run_supervisor_streaming(str(tmp_path), {
            **config, "source_file_path": str(changed), "attempt_id": parent["attempt_id"],
            "w1_supervisor_resume_snapshot_ref": reference,
            "snapshot_source_attempt_id": parent["attempt_id"],
        }))
    with pytest.raises(SnapshotValidationError):
        _collect(policy.run_supervisor_streaming(str(tmp_path), {
            **config, "model": "deepseek-v4-pro", "attempt_id": parent["attempt_id"],
            "w1_supervisor_resume_snapshot_ref": reference,
            "snapshot_source_attempt_id": parent["attempt_id"],
        }))
    intent = store.record_tool_intent(parent["attempt_id"], "provider.call", {"idempotency_key": "x" * 64})
    store.record_tool_unknown_outcome(intent["tool_call_id"], "runtime_interrupted")
    fork = store.fork_attempt(parent["attempt_id"], checkpoint_id=checkpoint["checkpoint_id"], decision_id="fork-unknown")
    snapshot = store.get_fork_snapshot(fork["attempt"]["attempt_id"])
    assert snapshot and snapshot["resumable"] is False
    assert snapshot["non_resumable_reason"] == "fork_snapshot_unknown_tool_calls_mismatch"


def test_runtime_child_resume_api_passes_the_validated_snapshot_to_worker(tmp_path, monkeypatch):
    _source, _source_text, store, _run, parent, _config, checkpoint = _parent(tmp_path)
    child = store.fork_attempt(parent["attempt_id"], checkpoint_id=checkpoint["checkpoint_id"], decision_id="fork-api")
    child_id = child["attempt"]["attempt_id"]
    captured: dict[str, object] = {}

    async def fake_resume(**kwargs):
        captured.update(kwargs["persisted_config"])
        return True

    from sidecar.routers import workflows

    monkeypatch.setattr(workflows, "resume_w1_attempt", fake_resume)
    with TestClient(create_app(str(tmp_path))) as client:
        client.app.state.runtime_store = store
        response = client.post(f"/runtime/runs/{child_id}/resume", json={"api_key": "transient-key"})

    assert response.status_code == 200
    assert captured["snapshot_source_attempt_id"] == parent["attempt_id"]
    assert captured["w1_supervisor_resume_snapshot_ref"] == checkpoint["metadata"]["snapshot_ref"]


def test_runtime_fork_api_exposes_the_single_nested_snapshot_reference_contract(tmp_path):
    _source, _source_text, store, _run, parent, _config, checkpoint = _parent(tmp_path)
    with TestClient(create_app(str(tmp_path))) as client:
        client.app.state.runtime_store = store
        response = client.post(
            f"/runtime/runs/{parent['attempt_id']}/fork",
            json={"checkpoint_id": checkpoint["checkpoint_id"], "decision_id": "fork-api-contract"},
        )

    assert response.status_code == 200
    fork_snapshot = response.json()["fork_snapshot"]
    state_reference = fork_snapshot["state_reference"]
    assert fork_snapshot["resumable"] is True
    assert state_reference["kind"] == "w1_supervisor_snapshot/v1"
    assert state_reference["immutable"] is True
    assert state_reference["resumable"] is True
    assert state_reference["snapshot_ref"] == checkpoint["metadata"]["snapshot_ref"]
    assert "snapshot_ref" not in fork_snapshot


def test_fork_rejects_snapshot_when_database_parent_chain_is_tampered(tmp_path):
    _source, _source_text, store, _run, parent, _config, checkpoint = _parent(tmp_path)

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE checkpoint_metadata SET parent_checkpoint_id = ? WHERE checkpoint_id = ?",
            ("tampered_parent", checkpoint["checkpoint_id"]),
        )

    child = store.fork_attempt(
        parent["attempt_id"], checkpoint_id=checkpoint["checkpoint_id"], decision_id="fork-parent-tamper",
    )
    snapshot = store.get_fork_snapshot(child["attempt"]["attempt_id"])

    assert snapshot is not None
    assert snapshot["resumable"] is False
    assert snapshot["non_resumable_reason"] == "fork_snapshot_parent_checkpoint_mismatch"


def test_resume_rejects_tampered_database_parent_chain_before_launch(tmp_path, monkeypatch):
    _source, _source_text, store, _run, parent, _config, checkpoint = _parent(tmp_path)
    child = store.fork_attempt(parent["attempt_id"], checkpoint_id=checkpoint["checkpoint_id"], decision_id="fork-api-parent-tamper")
    child_id = child["attempt"]["attempt_id"]
    assert store.get_fork_snapshot(child_id)["resumable"] is True

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE checkpoint_metadata SET parent_checkpoint_id = ? WHERE checkpoint_id = ?",
            ("tampered_parent", checkpoint["checkpoint_id"]),
        )

    from sidecar.routers import workflows

    async def forbidden_resume(**_kwargs):
        raise AssertionError("resume must not launch after a parent-chain mismatch")

    monkeypatch.setattr(workflows, "resume_w1_attempt", forbidden_resume)
    with TestClient(create_app(str(tmp_path))) as client:
        client.app.state.runtime_store = store
        response = client.post(f"/runtime/runs/{child_id}/resume", json={"api_key": "transient-key"})

    assert response.status_code == 409
    assert response.json()["detail"] == "fork_snapshot_parent_checkpoint_mismatch"


def test_authorized_unknown_snapshot_passes_runtime_preflight_without_consuming_call(tmp_path, monkeypatch):
    _source, _source_text, store, run, parent, config, checkpoint = _parent(tmp_path)
    intent = store.record_tool_intent(
        parent["attempt_id"], "provider.chat.completions",
        {"idempotency_key": "x" * 64, "model": "deepseek-v4-flash", "message_hash": "y" * 64},
    )
    store.record_tool_unknown_outcome(intent["tool_call_id"], "runtime_interrupted")
    state = load_w1_supervisor_snapshot(tmp_path, checkpoint["metadata"]["snapshot_ref"])["state"]
    source_identity, config_identity = build_supervisor_snapshot_identities(config, project_path=tmp_path)
    unknown_ref = write_w1_supervisor_snapshot(
        tmp_path,
        lineage_id=run["lineage_id"],
        attempt_id=parent["attempt_id"],
        checkpoint_id="checkpoint_unknown_authorized",
        node="reduce_repair",
        next_node="architect_timeline",
        source_identity=source_identity,
        config_identity=config_identity,
        state=state,
        parent_checkpoint_id=checkpoint["checkpoint_id"],
        unknown_tool_call_ids=[intent["tool_call_id"]],
    )
    lease = store.acquire_lease(parent["attempt_id"], "resume-test", ttl_seconds=60)
    store.record_checkpoint_metadata(
        parent["attempt_id"], "checkpoint_unknown_authorized", node="reduce_repair", sequence=2,
        parent_checkpoint_id=checkpoint["checkpoint_id"],
        metadata={"recovery_mode": "resumable", "snapshot_ref": unknown_ref.to_dict()},
        owner_id="resume-test", fence_token=lease["fence_token"],
    )
    store.set_attempt_status(parent["attempt_id"], "waiting_human", owner_id="resume-test", fence_token=lease["fence_token"])
    captured: dict[str, object] = {}

    async def fake_resume(**kwargs):
        captured.update(kwargs["persisted_config"])
        return True

    from sidecar.routers import workflows

    monkeypatch.setattr(workflows, "resume_w1_attempt", fake_resume)
    decision_key = f"retry_provider_call:{'x' * 64}"
    with TestClient(create_app(str(tmp_path))) as client:
        client.app.state.runtime_store = store
        blocked = client.post(f"/runtime/runs/{parent['attempt_id']}/resume", json={"api_key": "transient-key"})
        decision = client.post(
            f"/runtime/decisions/{decision_key}",
            json={"attempt_id": parent["attempt_id"], "decision": "authorize_retry_once"},
        )
        repeated = client.post(
            f"/runtime/decisions/{decision_key}",
            json={"attempt_id": parent["attempt_id"], "decision": "authorize_retry_once"},
        )
        resumed = client.post(f"/runtime/runs/{parent['attempt_id']}/resume", json={"api_key": "transient-key"})

    calls = {call["tool_call_id"]: call for call in store.list_tool_calls(parent["attempt_id"])}
    assert blocked.status_code == 409
    assert decision.status_code == repeated.status_code == 200
    assert decision.json()["decision_id"] == repeated.json()["decision_id"]
    assert resumed.status_code == 200
    assert captured["w1_authorized_unknown_call_ids"] == [intent["tool_call_id"]]
    assert captured["w1_authorized_unknown_decision_keys"] == [decision_key]
    assert calls[intent["tool_call_id"]]["status"] == "unknown_outcome"


def _unknown_resume_reference(tmp_path, *, spent_usd: float = 0.0):
    _source, _source_text, store, run, parent, config, checkpoint = _parent(tmp_path)
    intent = store.record_tool_intent(
        parent["attempt_id"], "provider.chat.completions",
        {"idempotency_key": "u" * 64, "model": "deepseek-v4-flash", "message_hash": "m" * 64},
    )
    store.record_tool_unknown_outcome(intent["tool_call_id"], "runtime_interrupted")
    state = load_w1_supervisor_snapshot(tmp_path, checkpoint["metadata"]["snapshot_ref"])["state"]
    source_identity, config_identity = build_supervisor_snapshot_identities(config, project_path=tmp_path)
    reference = write_w1_supervisor_snapshot(
        tmp_path,
        lineage_id=run["lineage_id"],
        attempt_id=parent["attempt_id"],
        checkpoint_id="checkpoint_unknown_policy",
        node="proposal_write",
        next_node=None,
        source_identity=source_identity,
        config_identity=config_identity,
        state=state,
        parent_checkpoint_id=checkpoint["checkpoint_id"],
        completed_nodes=["validate_file", "extract_window", "reduce_repair", "architect_timeline", "qa_review", "judge_import", "proposal_write"],
        budget_snapshot={"budget_limit_usd": 3.0, "spent_usd": spent_usd},
        unknown_tool_call_ids=[intent["tool_call_id"]],
    )
    return store, parent, config, intent, reference


def test_policy_snapshot_unknown_outcome_requires_exact_durable_authorization(tmp_path):
    store, parent, config, intent, reference = _unknown_resume_reference(tmp_path)
    session_id = "unknown-policy-reject"
    lease = store.acquire_lease(parent["attempt_id"], "resume-test", ttl_seconds=60)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, parent["attempt_id"], "resume-test", lease["fence_token"])

    with pytest.raises(SnapshotValidationError, match="require_human_confirmation"):
        _collect(policy.run_supervisor_streaming(str(tmp_path), {
            **config,
            "session_id": session_id,
            "w1_supervisor_resume_snapshot_ref": reference.to_dict(),
            "snapshot_source_attempt_id": parent["attempt_id"],
        }))
    assert store.list_tool_calls(parent["attempt_id"])[0]["status"] == "unknown_outcome"
    events.clear_session(session_id)


def test_policy_snapshot_unknown_outcome_accepts_only_matching_authorization(tmp_path):
    store, parent, config, intent, reference = _unknown_resume_reference(tmp_path)
    session_id = "unknown-policy-authorized"
    lease = store.acquire_lease(parent["attempt_id"], "resume-test", ttl_seconds=60)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, parent["attempt_id"], "resume-test", lease["fence_token"])
    decision_key = "retry_provider_call:" + "u" * 64
    store.record_unknown_call_decision(parent["attempt_id"], decision_key, "authorize_retry_once")

    updates = _collect(policy.run_supervisor_streaming(str(tmp_path), {
        **config,
        "session_id": session_id,
        "w1_supervisor_resume_snapshot_ref": reference.to_dict(),
        "snapshot_source_attempt_id": parent["attempt_id"],
        "w1_authorized_unknown_call_ids": [intent["tool_call_id"]],
        "w1_authorized_unknown_decision_keys": [decision_key],
    }))
    assert updates[-1]["converge_status"] == "awaiting_acceptance"
    configured = events._authorized_unknown_resumes[session_id]
    assert configured.tool_call_ids == frozenset({intent["tool_call_id"]})
    assert configured.decision_keys == {intent["tool_call_id"]: decision_key}
    assert store.list_tool_calls(parent["attempt_id"])[0]["status"] == "unknown_outcome"
    events.clear_session(session_id)


def test_policy_snapshot_unknown_outcome_rejects_wrong_call_id_and_exhausted_budget(tmp_path):
    store, parent, config, intent, reference = _unknown_resume_reference(tmp_path, spent_usd=2.0)
    session_id = "unknown-policy-priority"
    lease = store.acquire_lease(parent["attempt_id"], "resume-test", ttl_seconds=60)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, parent["attempt_id"], "resume-test", lease["fence_token"])
    decision_key = "retry_provider_call:" + "u" * 64
    store.record_unknown_call_decision(parent["attempt_id"], decision_key, "authorize_retry_once")

    with pytest.raises(SnapshotValidationError, match="budget_is_not_compatible"):
        _collect(policy.run_supervisor_streaming(str(tmp_path), {
            **config,
            "session_id": session_id,
            "budget_config": {"max_cost_usd": 1.0},
            "w1_supervisor_resume_snapshot_ref": reference.to_dict(),
            "snapshot_source_attempt_id": parent["attempt_id"],
            "w1_authorized_unknown_call_ids": ["wrong-call-id"],
            "w1_authorized_unknown_decision_keys": ["retry_provider_call:wrong"],
        }))

    with pytest.raises(SnapshotValidationError, match="require_human_confirmation"):
        _collect(policy.run_supervisor_streaming(str(tmp_path), {
            **config,
            "session_id": session_id,
            "w1_supervisor_resume_snapshot_ref": reference.to_dict(),
            "snapshot_source_attempt_id": parent["attempt_id"],
            "w1_authorized_unknown_call_ids": ["wrong-call-id"],
            "w1_authorized_unknown_decision_keys": ["retry_provider_call:wrong"],
        }))
    assert store.list_tool_calls(parent["attempt_id"])[0]["status"] == "unknown_outcome"
    events.clear_session(session_id)


def test_policy_snapshot_cancelled_source_beats_retry_authorization(tmp_path):
    store, parent, config, intent, reference = _unknown_resume_reference(tmp_path)
    session_id = "unknown-policy-cancelled"
    lease = store.acquire_lease(parent["attempt_id"], "resume-test", ttl_seconds=60)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, parent["attempt_id"], "resume-test", lease["fence_token"])
    decision_key = "retry_provider_call:" + "u" * 64
    store.record_unknown_call_decision(parent["attempt_id"], decision_key, "authorize_retry_once")
    store.set_attempt_status(
        parent["attempt_id"], "cancelled", owner_id="resume-test", fence_token=lease["fence_token"],
    )

    with pytest.raises(SnapshotValidationError, match="resume_cancelled"):
        _collect(policy.run_supervisor_streaming(str(tmp_path), {
            **config,
            "session_id": session_id,
            "w1_supervisor_resume_snapshot_ref": reference.to_dict(),
            "snapshot_source_attempt_id": parent["attempt_id"],
            "w1_authorized_unknown_call_ids": [intent["tool_call_id"]],
            "w1_authorized_unknown_decision_keys": [decision_key],
        }))
    assert store.list_tool_calls(parent["attempt_id"])[0]["status"] == "unknown_outcome"
    events.clear_session(session_id)


def test_span_rehydration_uses_project_staged_source_when_original_is_missing(tmp_path):
    source, source_text, _store, _run, _parent_attempt, _config, checkpoint = _parent(tmp_path)
    reference = checkpoint["metadata"]["snapshot_ref"]
    loaded = load_w1_supervisor_snapshot(tmp_path, reference)
    source.unlink()
    restored = policy._restore_snapshot_state({}, loaded["state"])
    staged_source = tmp_path / "system" / "imports" / reference["lineage_id"] / "attempts" / reference["attempt_id"] / "raw_source.txt"
    rebuilt = policy._rehydrate_snapshot_chunks(restored, str(staged_source))
    assert rebuilt["chunks"][0]["content"] == source_text


@pytest.mark.parametrize(
    ("boundary", "expected_next", "expected_completed"),
    [
        ("reduce_repair", "architect_timeline", ["validate_file", "extract_window", "reduce_repair"]),
        ("architect_timeline", "qa_review", ["validate_file", "extract_window", "reduce_repair", "architect_timeline"]),
        ("qa_review", "judge_import", ["validate_file", "extract_window", "reduce_repair", "architect_timeline", "qa_review"]),
        ("judge_import", "proposal_write", ["validate_file", "extract_window", "reduce_repair", "architect_timeline", "qa_review", "judge_import"]),
        ("proposal_write", None, ["validate_file", "extract_window", "reduce_repair", "architect_timeline", "qa_review", "judge_import", "proposal_write"]),
    ],
)
def test_body_free_resume_dto_preserves_real_proposal_serializer_inputs(
    tmp_path, monkeypatch, boundary, expected_next, expected_completed,
):
    """Each boundary advances differently but retains a real serializer input."""
    source_text = "第1章 星门\n韩立在七玄门拜墨大夫为师，星门于雨夜开启。\n"
    source = tmp_path / "source.txt"
    source.write_text(source_text, encoding="utf-8")
    span = make_source_span(source_text, 0, len(source_text))
    import_run_id = "sup_resume_identity"
    source_state = {
        "source_text": source_text,
        "source_file_path": str(source),
        "project_path": str(tmp_path),
        "import_run_id": import_run_id,
        "source_language": "zh",
        "chunks": [{"chunk_id": 0, "chapter_hint": "第1章 星门", "source_span": span, "content": source_text}],
        "chunk_extractions": [{"chunk_id": 0, "truth": "complete", "domain_receipts": {}}],
        "entity_registry": {
            "characters": {"char_han": {"id": "char_han", "canonical_name": "韩立", "background": "山村少年", "experience": [{"title": "拜师"}], "confidence": 0.9}},
            "events": {"event_gate": {"id": "event_gate", "title": "星门开启", "timelineClass": "canonical_event", "branchId": "branch_main", "orderIndex": 0}},
            "world": {"七玄门": "organization"},
            "world_detailed": {"七玄门": {"id": "world_qixuan", "name": "七玄门", "category": "organization", "containerId": "world_container_organizations"}},
        },
        "relationships": [{"id": "rel_teacher", "sourceId": "char_han", "targetId": "char_teacher", "type": "师徒关系"}],
        "raw_relationships": [{"id": "rel_teacher", "source_character_name": "韩立", "target_character_name": "墨大夫", "type": "师徒关系"}],
        "character_tags": [{"id": "tag_cultivator", "name": "修仙者"}],
        "world_containers": [{"id": "world_container_organizations", "name": "门派组织", "importCategoryKey": "organizations"}],
        "organizer_output": {"world_containers": [{"id": "world_container_organizations", "name": "门派组织"}], "world_items": [{"id": "world_qixuan", "name": "七玄门"}]},
        "timeline_architecture": {"canonical_events": [{"id": "event_gate", "title": "星门开启", "branchId": "branch_main"}]},
        "timeline_branches": [{"id": "branch_main", "name": "主线"}],
        "world_settings": {}, "reducer_artifact": {}, "cross_validation": {}, "import_review_report": {},
        "judge_artifact": {"passed": True}, "gate_failures": [], "proposals": [], "operations": {},
        "import_run_manifest": {"import_run_id": import_run_id}, "project_structure_digest": {},
        "manuscript_chapters": [{"chapter_id": "chap_1", "scene_id": "scene_1", "title": "第1章 星门", "summary": "韩立拜师", "chunk_ids": [0], "source_span": span, "manuscript_content": source_text}],
    }
    snapshot_state = policy._snapshot_state(source_state)
    serialized = "\n".join(str(value) for value in snapshot_state.values())
    assert source_text not in serialized
    assert "manuscript_content" not in serialized

    restored = policy._restore_snapshot_state({"project_path": str(tmp_path), "source_file_path": str(source)}, snapshot_state)
    restored = policy._rehydrate_snapshot_chunks(restored, str(source))
    restored = policy._rehydrate_snapshot_manuscript_chapters(restored, str(source))
    assert restored["import_run_id"] == import_run_id
    assert restored["manuscript_chapters"][0]["manuscript_content"] == source_text
    assert restored["character_tags"][0]["name"] == "修仙者"
    assert restored["organizer_output"]["world_items"][0]["name"] == "七玄门"

    operations: list[dict] = []

    async def capture(operation, _project_path):
        operations.append(operation)
        return {"id": f"proposal_{operation['entity_id']}", "status": "pending", "confidence": operation["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture)
    result = asyncio.run(w1_import.node_write_to_project({
        **restored,
        "project_path": str(tmp_path), "source_file_path": str(source), "source_text": source_text,
        "errors": [], "context": {}, "workflow_id": "W1", "checkpoint_path": "",
    }))
    entity_types = {operation["entity_type"] for operation in operations}
    assert {"chapter", "scene", "character_tag", "world_container", "world_item", "relationship"} <= entity_types
    assert result["status"] == "done"
    assert all(operation["data"].get("importRunId") == import_run_id for operation in operations)

    staged_relative = f"system/imports/lineage_{boundary}/attempts/attempt_{boundary}/raw_source.txt"
    staged_source = tmp_path / staged_relative
    staged_source.parent.mkdir(parents=True, exist_ok=True)
    staged_source.write_text(source_text, encoding="utf-8")
    source_identity, config_identity = build_supervisor_snapshot_identities(
        {
            "project_path": str(tmp_path), "source_file_path": str(source),
            "model": "deepseek-v4-flash", "prompt_profile": "balanced",
            "execution_mode": "supervisor", "import_mode": "import_all",
            "w1_supervisor_staged_source_relative_path": staged_relative,
        },
        project_path=tmp_path,
    )
    ref = write_w1_supervisor_snapshot(
        tmp_path,
        lineage_id=f"lineage_{boundary}",
        attempt_id=f"attempt_{boundary}",
        checkpoint_id=f"checkpoint_{boundary}",
        node=boundary,
        next_node=expected_next,
        source_identity=source_identity,
        config_identity=config_identity,
        state=snapshot_state,
        completed_nodes=expected_completed,
    )
    persisted = load_w1_supervisor_snapshot(tmp_path, ref)["snapshot"]
    assert persisted["node"] == boundary
    assert persisted["next_node"] == expected_next
    assert persisted["completed_nodes"] == expected_completed


def test_resume_dto_preserves_writer_dependency_graph_before_and_after_snapshot(tmp_path, monkeypatch):
    """A matched character must remain an update across a durable resume."""
    source_text = "第1章 星门\n韩立在七玄门拜墨大夫为师，星门于雨夜开启。\n"
    source = tmp_path / "source.txt"
    source.write_text(source_text, encoding="utf-8")
    span = make_source_span(source_text, 0, len(source_text))
    import_run_id = "sup_writer_dependency_graph"
    state = {
        "source_text": source_text,
        "source_file_path": str(source),
        "import_run_id": import_run_id,
        "source_language": "zh",
        "chunks": [{"chunk_id": 0, "source_span": span, "content": source_text}],
        "chunk_extractions": [{"chunk_id": 0, "truth": "complete", "domain_receipts": {}}],
        "entity_registry": {
            "characters": {
                "char_han": {
                    "id": "char_han", "canonical_name": "韩立", "skip_create": True,
                    "existing_project_id": "character_existing_han", "confidence": 0.94,
                    "entity_merge_decision": {
                        "fields": {
                            "aliases": {"value": ["韩二愣"]},
                            "background": {"value": "山村少年"},
                            "experience": {"value": [{"fact": "拜墨大夫为师"}]},
                            "personality_traits": {"value": ["谨慎"]},
                            "confidence": {"value": 0.94},
                        },
                        "conflicts": [],
                    },
                    "personality_traits": ["谨慎"], "role_in_story": "主角",
                    "open_questions": ["后续确认机缘"], "tag_ids": ["tag_cultivator"],
                },
                "char_teacher": {
                    "id": "char_teacher", "canonical_name": "墨大夫", "background": "七玄门医师",
                    "experience": [{"fact": "收韩立为徒"}], "personality_traits": ["冷静"],
                    "role_in_story": "导师", "open_questions": [], "tag_ids": ["tag_cultivator"], "confidence": 0.83,
                },
            },
            "character_id_map": {"char_han": "character_existing_han"},
            "events": {
                "event_gate": {
                    "id": "event_gate", "title": "星门开启", "branchId": "branch_main", "orderIndex": 0,
                    "character_ids": ["char_han", "char_teacher"], "linkedSceneIds": ["scene_1"],
                    "linkedWorldItemIds": ["world_qixuan"], "tags": ["导入"],
                },
            },
            "world": {"七玄门": "organization"},
            "world_detailed": {
                "七玄门": {
                    "id": "world_qixuan", "name": "七玄门", "category": "organization",
                    "containerId": "world_container_organizations", "parentId": "world_container_organizations",
                    "description": "修仙门派", "attributes": [{"key": "驻地", "value": "青州"}],
                },
            },
        },
        "relationships": [{
            "id": "rel_teacher", "sourceId": "char_han", "targetId": "char_teacher", "type": "师徒关系",
            "category": "mentor_disciple", "directionality": "source_to_target", "sourceNotes": "师徒事实",
            "importConfidence": 0.91,
        }],
        "raw_relationships": [{"id": "rel_teacher", "source_character_name": "韩立", "target_character_name": "墨大夫", "type": "师徒关系"}],
        "character_tags": [{
            "id": "tag_cultivator", "name": "修仙者", "color": "#38bdf8",
            "characterIds": ["character_existing_han", "char_teacher"],
        }],
        "world_containers": [{"id": "world_container_organizations", "name": "门派组织", "importCategoryKey": "organizations", "sortOrder": 0}],
        "organizer_output": {"world_containers": [{"id": "world_container_organizations"}], "world_items": [{"id": "world_qixuan"}]},
        "timeline_architecture": {}, "timeline_branches": [{"id": "branch_main", "name": "主线", "mode": "root", "isDefault": True}],
        "world_settings": {}, "reducer_artifact": {}, "cross_validation": {}, "import_review_report": {},
        "judge_artifact": {"passed": True}, "gate_failures": [], "proposals": [], "operations": {},
        "evidence_cards": [{"id": "card_han", "kind": "character", "candidate_ids": ["char_han"], "source_span": span, "raw": {"canonical_id": "char_han"}}],
        "import_run_manifest": {"import_run_id": import_run_id}, "project_structure_digest": {},
        "manuscript_chapters": [{"chapter_id": "chap_1", "scene_id": "scene_1", "title": "第1章 星门", "summary": "韩立拜师", "chunk_ids": [0], "source_span": span, "manuscript_content": source_text}],
    }
    snapshot = policy._snapshot_state(state)
    restored = policy._restore_snapshot_state({}, snapshot)
    restored = policy._rehydrate_snapshot_chunks(restored, str(source))
    restored = policy._rehydrate_snapshot_manuscript_chapters(restored, str(source))

    assert restored["entity_registry"]["character_id_map"] == {"char_han": "character_existing_han"}
    assert restored["entity_registry"]["characters"]["char_han"]["skip_create"] is True
    assert restored["entity_registry"]["characters"]["char_han"]["existing_project_id"] == "character_existing_han"
    assert restored["entity_registry"]["characters"]["char_han"]["open_questions"] == ["后续确认机缘"]
    assert restored["entity_registry"]["events"]["event_gate"]["character_ids"] == ["char_han", "char_teacher"]
    assert restored["character_tags"][0]["characterIds"] == ["character_existing_han", "char_teacher"]

    def payload(value, project_path):
        return {
            **copy.deepcopy(value),
            "project_path": str(project_path), "source_file_path": str(source), "source_text": source_text,
            "errors": [], "context": {}, "workflow_id": "W1", "checkpoint_path": "",
        }

    before_ops: list[dict] = []
    after_ops: list[dict] = []

    async def capture_before(operation, _project_path):
        before_ops.append(copy.deepcopy(operation))
        return {"id": f"proposal_{operation['entity_id']}", "status": "pending", "confidence": operation["confidence"]}

    async def capture_after(operation, _project_path):
        after_ops.append(copy.deepcopy(operation))
        return {"id": f"proposal_{operation['entity_id']}", "status": "pending", "confidence": operation["confidence"]}

    before_project = tmp_path / "before"
    after_project = tmp_path / "after"
    before_project.mkdir()
    after_project.mkdir()
    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture_before)
    asyncio.run(w1_import.node_write_to_project(payload(state, before_project)))
    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture_after)
    asyncio.run(w1_import.node_write_to_project(payload(restored, after_project)))

    def select(operations, entity_type, *, op_type=None):
        return next(
            operation for operation in operations
            if operation["entity_type"] == entity_type and (op_type is None or operation["op_type"] == op_type)
        )

    for operations in (before_ops, after_ops):
        character_update = select(operations, "character", op_type="update")
        assert character_update["entity_id"] == "character_existing_han"
        event = select(operations, "timeline_event")
        assert event["data"]["participantCharacterIds"] == ["character_existing_han", "char_teacher"]
        tag = select(operations, "character_tag")
        assert tag["data"]["characterIds"] == ["character_existing_han", "char_teacher"]
        world = select(operations, "world_item")
        assert world["data"]["containerId"] == "world_container_organizations"
        relationship = select(operations, "relationship")
        assert relationship["depends_on"] == ["character_existing_han", "char_teacher"]
        assert relationship["data"]["sourceNotes"] == "师徒事实"


def test_normal_streaming_calls_architect_once_without_a_rerun(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("第1章\n普通测试原文。", encoding="utf-8")
    calls = {"architect": 0}

    async def validate(_state):
        return {"errors": []}

    async def split(_state):
        return {"chunks": [], "prompt_windows": [], "errors": []}

    async def noop(_state):
        return {}

    async def architect(_state):
        calls["architect"] += 1
        return {"timeline_architecture": {}, "timeline_branches": []}

    async def judge(state, _tools):
        return {**state, "judge_artifact": {"passed": True}}

    monkeypatch.setattr(policy, "node_validate_file", validate)
    monkeypatch.setattr(policy, "node_split_chunks", split)
    monkeypatch.setattr(policy, "_ensure_orchestrator_plan", lambda state: state)
    monkeypatch.setattr(policy, "_apply_initial_planner_action", lambda state, *_args: asyncio.sleep(0, result=state))
    monkeypatch.setattr(policy, "_persist_supervisor_evidence_cards", lambda state: state)
    monkeypatch.setattr(policy, "_organize_staged_world_candidates", lambda state: asyncio.sleep(0, result=state))
    monkeypatch.setattr(policy, "_prepare_reviewer_staging_state", lambda state: state)
    monkeypatch.setattr(policy, "enforce_timeline_density", lambda state: state)
    monkeypatch.setattr(policy, "_run_judge_import", judge)
    monkeypatch.setattr(policy, "_apply_thematic_reruns", lambda state, *_args: asyncio.sleep(0, result=state))
    monkeypatch.setattr(policy, "build_tool_registry", lambda: {
        "segment_manifest": noop,
        "reduce_entities": noop,
        "minor_repair": noop,
        "architect_timeline": architect,
        "qa_review": lambda _state: asyncio.sleep(0, result={"gate_failures": []}),
        "proposal_write": noop,
        "judge_import": object(),
    })

    _collect(policy.run_supervisor_streaming(str(tmp_path), {
        "project_path": str(tmp_path), "source_file_path": str(source), "import_mode": "import_all",
        "prompt_profile": "balanced", "context": {"api_key": "transient-key", "model": "deepseek-v4-flash"},
    }))
    assert calls["architect"] == 1
