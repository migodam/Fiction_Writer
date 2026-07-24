from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sidecar.runtime.agent_runtime import LeaseLostError
from sidecar.workflows import w1_import, w1_recovery, w1_truth
from sidecar.workflows.w1_run_events import ProviderCallRequiresHumanConfirmation


def _identity(source: str = "Chapter 1\nFirst.") -> dict[str, str]:
    return w1_recovery.build_run_identity(
        source_text=source,
        model="offline-test",
        profile="balanced",
        prompt_version="w1-prompts-v1",
        schema_version="w1-schema-v1",
        tool_version="w1-tools-v1",
        project_digest_hash="digest",
    )


def test_checkpoint_commits_only_semantic_complete_prefix(tmp_path: Path) -> None:
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    complete = w1_truth.semantic_complete({"chunk_id": 0, "manuscript_content": "Chapter 1\nFirst."})
    failed = w1_truth.failed_extraction(
        {"chunk_id": 1, "manuscript_content": "Chapter 2\nSecond."},
        error="provider timeout",
    )

    payload = w1_recovery.build_checkpoint(
        identity=identity,
        attempt=attempt,
        total_chunks=2,
        entity_registry={"characters": {}, "events": {}, "world": {}},
        chunk_extractions=[complete, failed],
        raw_relationships=[],
    )
    w1_recovery.write_checkpoint_atomic(attempt["checkpoint_path"], payload)
    loaded = w1_recovery.load_checkpoint(attempt["checkpoint_path"], identity, attempt)

    assert payload["committed_chunk_ids"] == [0]
    assert [item["chunk_id"] for item in payload["chunk_extractions"]] == [0]
    assert payload["failed_chunk_ids"] == [1]
    assert loaded["status"] == "ok"
    assert loaded["committed_chunk_ids"] == [0]
    assert loaded["failed_chunk_ids"] == [1]


def test_checkpoint_rejects_claimed_commit_for_failed_chunk(tmp_path: Path) -> None:
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    failed = w1_truth.failed_extraction({"chunk_id": 0, "manuscript_content": "body"}, error="failed")

    with pytest.raises(ValueError, match="semantic_complete"):
        w1_recovery.build_checkpoint(
            identity=identity,
            attempt=attempt,
            total_chunks=1,
            entity_registry={},
            chunk_extractions=[failed],
            raw_relationships=[],
            committed_chunk_ids=[0],
        )


def test_manuscript_only_truth_is_never_committed() -> None:
    extraction = w1_truth.manuscript_only({"chunk_id": 0, "manuscript_content": "body"})

    assert extraction["chunk_truth"] == "manuscript_only"
    assert w1_truth.committed_chunk_ids([extraction]) == []


def _supervisor_state(tmp_path: Path, *, import_run_id: str = "truth_run") -> dict:
    chunks = [{"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": "body", "content": "body"}]
    return {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "novel.txt"),
        "checkpoint_path": str(tmp_path / "checkpoint.json"),
        "import_run_id": import_run_id,
        "prompt_profile": "balanced",
        "context": {},
        "chunks": chunks,
        "prompt_windows": [],
        "project_structure_digest": {"content": "{}", "estimated_tokens": 1, "counts": {}},
        "entity_registry": {"characters": {}, "events": {}, "world": {}},
        "chunk_extractions": [],
        "raw_relationships": [],
        "errors": [],
    }


def test_supervisor_lease_loss_propagates_without_failed_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def lost_lease(*_args, **_kwargs):
        raise LeaseLostError("lease is missing, expired, or fenced")

    monkeypatch.setattr(w1_import, "_invoke_json_prompt", lost_lease)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())

    with pytest.raises(LeaseLostError):
        asyncio.run(w1_import.node_process_chunks(_supervisor_state(tmp_path)))


def test_supervisor_unknown_provider_outcome_propagates_for_human_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def unknown_outcome(*_args, **_kwargs):
        raise ProviderCallRequiresHumanConfirmation("provider-operation")

    monkeypatch.setattr(w1_import, "_invoke_json_prompt", unknown_outcome)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())

    with pytest.raises(ProviderCallRequiresHumanConfirmation):
        asyncio.run(w1_import.node_process_chunks(_supervisor_state(tmp_path)))


def test_supervisor_failed_domain_preserves_manuscript_but_never_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed_character_prompt(_llm, prompt_template, **_kwargs):
        if "W1 Import Character Compiler" in prompt_template:
            raise RuntimeError("character provider failed")
        if "W1 Import Timeline Scout" in prompt_template:
            return {"events": []}
        if "world extraction" in prompt_template:
            return {"world_mentions": []}
        if "relationship evidence" in prompt_template:
            return {"relationships": []}
        return {"chapter_hint": "Chapter 1", "scenes": []}

    monkeypatch.setattr(w1_import, "_invoke_json_prompt", failed_character_prompt)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())
    result = asyncio.run(w1_import.node_process_chunks(_supervisor_state(tmp_path)))

    extraction = result["chunk_extractions"][0]
    assert extraction["chunk_truth"] == "failed"
    assert extraction["manuscript_content"] == "body"
    assert extraction["domain_receipts"]["characters"] == "failed"
    assert w1_truth.committed_chunk_ids(result["chunk_extractions"]) == []
    failure_path = tmp_path / "system" / "imports" / "truth_run" / "chunks" / "chunk_0_failures.json"
    assert failure_path.exists()


def test_review_reads_durable_failure_artifact_after_memory_log_is_gone(tmp_path: Path) -> None:
    failure_path = tmp_path / "system" / "imports" / "truth_run" / "chunks" / "chunk_0_failures.json"
    failure_path.parent.mkdir(parents=True)
    failure_path.write_text(json.dumps({"chunk_id": 0, "failures": [{"error": "lease fenced"}]}), encoding="utf-8")
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "truth_run",
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "manuscript_chapters": [],
        "timeline_architecture": {"canonical_events": [], "discarded_duplicates": [], "warnings": []},
        "timeline_branches": [],
        "relationships": [],
        "reducer_artifact": {"warnings": [], "duplicate_candidates": []},
        "errors": [],
        "context": {"model": "offline-test"},
        "source_language": "en",
        "character_tags": [],
    }
    w1_import._chunk_log.pop(str(tmp_path), None)

    report = asyncio.run(w1_import.node_review_import(state))["import_review_report"]

    assert report["status"] == "fail"
    assert report["failed_chunks"] == [{"chunk_id": 0, "errors": ["lease fenced"], "source": "failure_artifact"}]
    assert any("Durable semantic extraction failure" in error for error in report["errors"])


def test_durable_failure_scan_reads_checkpoint_truth_without_memory_log(tmp_path: Path) -> None:
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    checkpoint = w1_recovery.build_checkpoint(
        identity=identity,
        attempt=attempt,
        total_chunks=1,
        entity_registry={},
        chunk_extractions=[w1_truth.failed_extraction({"chunk_id": 0, "manuscript_content": "body"}, error="lease fenced", failure_code="lease_lost")],
        raw_relationships=[],
    )
    w1_recovery.write_checkpoint_atomic(attempt["checkpoint_path"], checkpoint)

    failures = w1_truth.durable_failures(attempt["attempt_dir"])

    assert failures == [{"chunk_id": 0, "errors": ["lease_lost"], "source": "checkpoint"}]


def test_legacy_failure_preserves_text_but_is_not_semantic_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed_provider(*_args, **_kwargs):
        raise RuntimeError("legacy provider failed")

    monkeypatch.setattr(w1_import, "_ainvoke_with_budget", failed_provider)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())
    state = _supervisor_state(tmp_path, import_run_id="legacy_truth_run")

    result = asyncio.run(w1_import._legacy_node_process_chunks(state))

    extraction = result["chunk_extractions"][0]
    assert extraction["chunk_truth"] == "failed"
    assert extraction["manuscript_content"] == "body"
    assert w1_truth.committed_chunk_ids(result["chunk_extractions"]) == []


def test_legacy_lease_loss_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def lost_lease(*_args, **_kwargs):
        raise LeaseLostError("lease fenced")

    monkeypatch.setattr(w1_import, "_ainvoke_with_budget", lost_lease)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())

    with pytest.raises(LeaseLostError):
        asyncio.run(w1_import._legacy_node_process_chunks(_supervisor_state(tmp_path, import_run_id="legacy_lease_run")))


def test_legacy_unknown_provider_outcome_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def unknown_outcome(*_args, **_kwargs):
        raise ProviderCallRequiresHumanConfirmation("legacy-provider-operation")

    monkeypatch.setattr(w1_import, "_ainvoke_with_budget", unknown_outcome)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())

    with pytest.raises(ProviderCallRequiresHumanConfirmation):
        asyncio.run(w1_import._legacy_node_process_chunks(_supervisor_state(tmp_path, import_run_id="legacy_unknown_run")))
