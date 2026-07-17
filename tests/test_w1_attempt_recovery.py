from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sidecar.workflows import w1_import
from sidecar.workflows import w1_recovery


def _identity(source: str = "Chapter 1\nFirst.", **overrides):
    values = {
        "source_text": source,
        "model": "deepseek-chat",
        "profile": "balanced",
        "prompt_version": "w1-prompts-v1",
        "schema_version": "w1-schema-v1",
        "tool_version": "w1-tools-v1",
        "project_digest_hash": "project-digest",
    }
    values.update(overrides)
    return w1_recovery.build_run_identity(**values)


def test_same_input_gets_shared_lineage_and_distinct_attempt_directories(tmp_path):
    identity = _identity()
    first = w1_recovery.allocate_attempt(tmp_path, identity)
    second = w1_recovery.allocate_attempt(tmp_path, identity)

    assert first["lineage_id"] == second["lineage_id"] == identity["lineage_id"]
    assert first["attempt_id"] != second["attempt_id"]
    assert first["attempt_dir"] != second["attempt_dir"]
    assert Path(first["checkpoint_path"]).parent == Path(first["attempt_dir"])


def test_cache_key_is_stable_and_sensitive_to_contract_versions():
    identity = _identity()
    span = {"raw_source_hash": identity["source_hash"], "absolute_start": 0, "absolute_end": 8, "substring_hash": "span"}

    first = w1_recovery.cache_key(identity, span)
    assert first == w1_recovery.cache_key(identity, span)
    assert first != w1_recovery.cache_key(_identity(prompt_version="w1-prompts-v2"), span)
    assert first != w1_recovery.cache_key(_identity(profile="deep"), span)


def test_checkpoint_write_is_atomic_and_has_committed_receipt(tmp_path):
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    checkpoint_path = Path(attempt["checkpoint_path"])
    payload = w1_recovery.build_checkpoint(
        identity=identity,
        attempt=attempt,
        total_chunks=2,
        entity_registry={"characters": {}, "events": {}, "world": {}},
        chunk_extractions=[{"chunk_id": 0, "value": "done"}],
        raw_relationships=[],
        committed_chunk_ids=[0],
    )

    w1_recovery.write_checkpoint_atomic(checkpoint_path, payload)
    stored = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert stored["committed_chunk_ids"] == [0]
    assert stored["committed_chunk_receipts"][0]["chunk_hash"]
    assert not list(checkpoint_path.parent.glob(".checkpoint.json.*.tmp"))


def test_corrupt_checkpoint_fails_closed_as_recoverable_error(tmp_path):
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    checkpoint_path = Path(attempt["checkpoint_path"])
    checkpoint_path.write_text("{broken", encoding="utf-8")

    result = w1_recovery.load_checkpoint(checkpoint_path, identity, attempt)

    assert result["status"] == "recoverable_error"
    assert result["resume"] is False


def test_checkpoint_rejects_source_mutation(tmp_path):
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    checkpoint_path = Path(attempt["checkpoint_path"])
    w1_recovery.write_checkpoint_atomic(checkpoint_path, w1_recovery.build_checkpoint(
        identity=identity, attempt=attempt, total_chunks=1,
        entity_registry={}, chunk_extractions=[], raw_relationships=[], committed_chunk_ids=[],
    ))

    result = w1_recovery.load_checkpoint(checkpoint_path, _identity("Chapter 1\nChanged."), attempt)

    assert result["status"] == "recoverable_error"
    assert "source hash" in result["errors"][0]


@pytest.mark.parametrize("tamper_target", ["extraction", "receipt"])
def test_checkpoint_recomputes_receipt_hashes_and_rejects_tampering(tmp_path, tamper_target):
    identity = _identity()
    attempt = w1_recovery.allocate_attempt(tmp_path, identity)
    checkpoint_path = Path(attempt["checkpoint_path"])
    payload = w1_recovery.build_checkpoint(
        identity=identity, attempt=attempt, total_chunks=1,
        entity_registry={},
        chunk_extractions=[{"chunk_id": 0, "manuscript_content": "Chapter 1\nFirst."}],
        raw_relationships=[], committed_chunk_ids=[0],
    )
    if tamper_target == "extraction":
        payload["chunk_extractions"][0]["manuscript_content"] = "tampered"
    else:
        payload["committed_chunk_receipts"][0]["receipt_hash"] = "tampered"
    w1_recovery.write_checkpoint_atomic(checkpoint_path, payload)

    result = w1_recovery.load_checkpoint(checkpoint_path, identity, attempt)

    assert result["status"] == "recoverable_error"
    assert "receipt" in result["errors"][0].lower()


@pytest.fixture
def import_text_18_legacy_fixture(tmp_path):
    chapter_texts = [f"Chapter {index + 1}\nText {index}.\n" for index in range(10)]
    source_text = "".join(chapter_texts)
    source_path = tmp_path / "Import Text 18.txt"
    source_path.write_text(source_text, encoding="utf-8")
    chunks = [
        {"chunk_id": index, "manuscript_content": content}
        for index, content in enumerate(chapter_texts)
    ]
    checkpoint_path = tmp_path / "import_progress.json"
    checkpoint_path.write_text(json.dumps({
        "source_file_path": str(source_path),
        "total_chunks": 10,
        "completed_chunk_ids": [0, 1, 2, 3],
        "chunk_extractions": [
            {
                "chunk_id": index,
                "manuscript_content": chapter_texts[index],
                "new_characters": [{"canonical_id": f"char_{index}", "canonical_name": f"Character {index}"}],
                "events": [],
                "world_mentions": [],
            }
            for index in range(4)
        ],
        "entity_registry": {"characters": {"trusted": {"canonical_name": "Trusted"}}, "events": {}, "world": {}},
    }), encoding="utf-8")
    stale_dir = tmp_path / "system" / "imports" / "old_attempt" / "chunks"
    stale_dir.mkdir(parents=True)
    for index in range(4, 10):
        (stale_dir / f"chunk_{index}.json").write_text(json.dumps({
            "chunk_id": index,
            "manuscript_content": chapter_texts[index],
            "entity_registry": {"characters": {f"stale_{index}": {}}},
        }), encoding="utf-8")
    return source_path, source_text, chunks, checkpoint_path


def test_actual_legacy_shape_migrates_verified_prefix_and_ignores_stale_files(import_text_18_legacy_fixture):
    source_path, source_text, chunks, legacy = import_text_18_legacy_fixture
    identity = _identity(source_text)

    migrated = w1_recovery.read_legacy_progress(
        legacy, identity,
        current_source_path=source_path,
        current_source_text=source_text,
        current_chunks=chunks,
    )

    assert migrated["status"] == "ok"
    assert migrated["committed_chunk_ids"] == [0, 1, 2, 3]
    assert migrated["ignored_chunk_ids"] == []
    assert migrated["entity_registry"]["characters"] == {"trusted": {"canonical_name": "Trusted"}}
    assert all("stale" not in key for key in migrated["entity_registry"]["characters"])


def test_legacy_progress_accepts_any_verified_contiguous_prefix(tmp_path):
    texts = [f"chunk-{index}" for index in range(6)]
    source_text = "".join(texts)
    source = tmp_path / "novel.txt"
    source.write_text(source_text, encoding="utf-8")
    legacy = tmp_path / "import_progress.json"
    legacy.write_text(json.dumps({
        "source_file_path": str(source),
        "completed_chunk_ids": list(range(6)),
        "chunk_extractions": [{"chunk_id": index, "manuscript_content": texts[index]} for index in range(6)],
        "entity_registry": {"characters": {}, "events": {}, "world": {}},
    }), encoding="utf-8")

    migrated = w1_recovery.read_legacy_progress(
        legacy, _identity(source_text),
        current_source_path=source,
        current_source_text=source_text,
        current_chunks=[{"chunk_id": index, "manuscript_content": text} for index, text in enumerate(texts)],
    )

    assert migrated["committed_chunk_ids"] == list(range(6))


def test_legacy_progress_stops_at_first_unverifiable_chunk_and_rebuilds_registry(tmp_path):
    texts = ["zero", "one", "two"]
    source_text = "".join(texts)
    source = tmp_path / "novel.txt"
    source.write_text(source_text, encoding="utf-8")
    legacy = tmp_path / "import_progress.json"
    legacy.write_text(json.dumps({
        "source_file_path": str(source),
        "completed_chunk_ids": [0, 1, 2],
        "chunk_extractions": [
            {"chunk_id": 0, "manuscript_content": "zero", "new_characters": [{"canonical_id": "char_safe", "canonical_name": "Safe"}]},
            {"chunk_id": 1, "manuscript_content": "tampered", "new_characters": [{"canonical_id": "char_bad", "canonical_name": "Bad"}]},
            {"chunk_id": 2, "manuscript_content": "two", "new_characters": [{"canonical_id": "char_late", "canonical_name": "Late"}]},
        ],
        "entity_registry": {"characters": {"unsafe": {"canonical_name": "Unsafe"}}},
    }), encoding="utf-8")

    migrated = w1_recovery.read_legacy_progress(
        legacy, _identity(source_text),
        current_source_path=source,
        current_source_text=source_text,
        current_chunks=[{"chunk_id": index, "manuscript_content": text} for index, text in enumerate(texts)],
    )

    assert migrated["committed_chunk_ids"] == [0]
    assert migrated["ignored_chunk_ids"] == [1, 2]
    assert set(migrated["entity_registry"]["characters"]) == {"char_safe"}


def test_legacy_progress_rejects_noncanonical_source_path(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("source", encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text("source", encoding="utf-8")
    legacy = tmp_path / "import_progress.json"
    legacy.write_text(json.dumps({"source_file_path": str(other), "completed_chunk_ids": []}), encoding="utf-8")

    migrated = w1_recovery.read_legacy_progress(
        legacy, _identity("source"),
        current_source_path=source,
        current_source_text="source",
        current_chunks=[],
    )

    assert migrated["status"] == "ignored"


def _split_state(project_path: Path, source_path: Path, *, lineage_id: str = "", attempt_id: str = "") -> dict:
    return {
        "project_path": str(project_path),
        "source_file_path": str(source_path),
        "import_mode": "import_all",
        "prompt_profile": "balanced",
        "runtime_lineage_id": lineage_id,
        "context": {"runtime_lineage_id": lineage_id, "w1_attempt_id": attempt_id},
        "errors": [],
    }


def test_supplied_runtime_lineage_and_attempt_own_the_artifact_tree(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFirst.", encoding="utf-8")
    lineage_id = "runtime-lineage-123"
    attempt_id = "runtime-attempt-456"

    result = asyncio.run(w1_import.node_split_chunks(
        _split_state(tmp_path, source, lineage_id=lineage_id, attempt_id=attempt_id)
    ))

    expected_dir = tmp_path / "system" / "imports" / lineage_id / "attempts" / attempt_id
    assert result["import_run_id"] == lineage_id
    assert result["import_run_manifest"]["lineage_id"] == lineage_id
    assert result["import_run_manifest"]["attempt_id"] == attempt_id
    assert Path(result["import_run_manifest"]["artifact_dir"]) == expected_dir
    assert Path(result["checkpoint_path"]) == expected_dir / "checkpoint.json"
    assert (expected_dir / "manifest.json").exists()
    assert (expected_dir / "project_structure_digest.json").exists()
    assert (expected_dir / "prompt_windows.json").exists()


def test_runtime_lineage_override_does_not_change_cache_identity_fields(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFirst.", encoding="utf-8")

    computed = asyncio.run(w1_import.node_split_chunks(_split_state(tmp_path, source)))
    supplied = asyncio.run(w1_import.node_split_chunks(
        _split_state(tmp_path, source, lineage_id="runtime-lineage", attempt_id="runtime-attempt")
    ))

    computed_identity = computed["context"]["w1_recovery_identity"]
    supplied_identity = supplied["context"]["w1_recovery_identity"]
    assert supplied_identity["lineage_id"] == "runtime-lineage"
    assert {key: value for key, value in supplied_identity.items() if key != "lineage_id"} == {
        key: value for key, value in computed_identity.items() if key != "lineage_id"
    }


def test_sequential_import_preflight_and_artifacts_are_attempt_isolated(tmp_path, monkeypatch):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFirst.", encoding="utf-8")
    observed_preflight_paths = []
    original = w1_import._build_project_structure_digest

    def recording_digest(state, import_run_id):
        result = original(state, import_run_id)
        if import_run_id == "recovery_preflight":
            observed_preflight_paths.append(result["artifact_path"])
        return result

    monkeypatch.setattr(w1_import, "_build_project_structure_digest", recording_digest)

    async def run_sequentially():
        first = await w1_import.node_split_chunks(_split_state(tmp_path, source))
        second = await w1_import.node_split_chunks(_split_state(tmp_path, source))
        return first, second

    first, second = asyncio.run(run_sequentially())

    expected_preflight = str(tmp_path / "system" / "imports" / "recovery_preflight" / "project_structure_digest.json")
    assert observed_preflight_paths == [expected_preflight, expected_preflight]
    assert first["import_run_manifest"]["attempt_id"] != second["import_run_manifest"]["attempt_id"]
    assert Path(first["import_run_manifest"]["artifact_dir"]) != Path(second["import_run_manifest"]["artifact_dir"])


def test_concurrent_same_lineage_imports_keep_artifacts_in_their_attempts(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFirst.", encoding="utf-8")

    async def run_concurrently():
        return await asyncio.gather(
            w1_import.node_split_chunks(_split_state(tmp_path, source)),
            w1_import.node_split_chunks(_split_state(tmp_path, source)),
        )

    first, second = asyncio.run(run_concurrently())
    first_dir = Path(first["import_run_manifest"]["artifact_dir"])
    second_dir = Path(second["import_run_manifest"]["artifact_dir"])

    assert first["import_run_id"] == second["import_run_id"]
    assert first_dir != second_dir
    assert (first_dir / "manifest.json").exists()
    assert (second_dir / "manifest.json").exists()
