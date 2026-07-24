from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidecar.main import create_app
from sidecar.models.state import make_source_span
from sidecar.runtime.agent_runtime import RuntimeStore
from sidecar.runtime.w1_supervisor_snapshot import SnapshotValidationError, load_w1_supervisor_snapshot
from sidecar.supervisor import policy
from sidecar.workflows import w1_import
from sidecar.workflows.w1_agentic_adapter import W1AgenticAdapter


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
    }
    span = make_source_span(source_text, 0, len(source_text))
    state = policy._snapshot_state({
        "chunks": [{"chunk_id": 0, "source_span": span, "content": source_text, "raw_content": source_text}],
        "chunk_extractions": [{"chunk_id": 0, "manuscript_content": source_text, "summary": "星门开启"}],
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "relationships": [], "world_settings": {}, "world_containers": [],
        "timeline_architecture": {}, "timeline_branches": [], "reducer_artifact": {},
        "import_review_report": {}, "judge_artifact": {}, "gate_failures": [],
        "proposals": [], "evidence_cards": [], "import_run_manifest": {}, "project_structure_digest": {},
    })
    adapter = W1AgenticAdapter.from_config(config)
    adapter.on_node_yielded("validate_file", {"current_node": "validate_file"})
    adapter.on_node_yielded("reduce_repair", {
        "current_node": "reduce_repair",
        "_w1_supervisor_snapshot": {
            "state": state,
            "completed_nodes": ["validate_file", "extract_window", "reduce_repair"],
            "completed_window_ids": [],
            "repeatable_node_counts": {},
            "budget_snapshot": {"budget_limit_usd": 3.0, "spent_usd": 0.0},
            "unknown_tool_call_ids": [],
        },
    })
    checkpoint = store.list_checkpoint_metadata(attempt["attempt_id"])[-1]
    assert checkpoint["metadata"]["recovery_mode"] == "resumable"
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
        return {"timeline_architecture": {"ok": True}, "timeline_branches": []}

    async def qa(_state):
        calls["qa"] += 1
        return {"gate_failures": []}

    async def proposal(_state):
        calls["proposal"] += 1
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


def test_span_rehydration_uses_project_staged_source_when_original_is_missing(tmp_path):
    source, source_text, _store, _run, _parent_attempt, _config, checkpoint = _parent(tmp_path)
    reference = checkpoint["metadata"]["snapshot_ref"]
    loaded = load_w1_supervisor_snapshot(tmp_path, reference)
    source.unlink()
    restored = policy._restore_snapshot_state({}, loaded["state"])
    staged_source = tmp_path / "system" / "imports" / reference["lineage_id"] / "attempts" / reference["attempt_id"] / "raw_source.txt"
    rebuilt = policy._rehydrate_snapshot_chunks(restored, str(staged_source))
    assert rebuilt["chunks"][0]["content"] == source_text


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
