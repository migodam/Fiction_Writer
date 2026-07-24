"""Focused contract tests for the standalone W1 Supervisor snapshot codec."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sidecar.runtime.w1_supervisor_snapshot import (
    SNAPSHOT_CONTRACT_VERSION,
    SnapshotConflictError,
    SnapshotValidationError,
    load_w1_supervisor_snapshot,
    write_w1_supervisor_snapshot,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _source() -> dict[str, object]:
    return {
        "source_relative_path": "sources/novel.txt",
        "source_sha256": _sha("novel"),
        "source_size": 5,
        "project_digest": _sha("project"),
    }


def _config() -> dict[str, str]:
    return {
        "model": "deepseek-v4-flash",
        "prompt_profile": "balanced",
        "prompt_version": "w1-v7",
        "schema_version": "w1-schema-v4",
        "tool_registry_version": "tools-v2",
        "policy_version": "policy-v5",
        "execution_mode": "supervisor",
        "import_mode": "import_all",
    }


def _kwargs() -> dict[str, object]:
    return {
        "lineage_id": "lineage_01",
        "attempt_id": "attempt_01",
        "checkpoint_id": "checkpoint_01",
        "node": "extract_window",
        "next_node": "reduce_repair",
        "source_identity": _source(),
        "config_identity": _config(),
        "completed_nodes": ["validate_file", "split_chunks"],
        "completed_window_ids": ["window_01"],
        "repeatable_node_counts": {"extract_window": 1},
        "state": {
            "chunks": [{"id": "chunk_01", "source_span": {"start": 0, "end": 5}}],
            "chunk_extractions": {"window_01": {"artifact_id": "artifact_01", "confidence": 0.9}},
            "entity_registry": {"characters": ["char_01"]},
        },
        "budget_snapshot": {"budget_limit_usd": 3.0, "spent_usd": 0.12, "call_count": 1},
        "unknown_tool_call_ids": [],
    }


def _write(project: Path, **changes: object):
    values = _kwargs()
    values.update(changes)
    return write_w1_supervisor_snapshot(project, **values)  # type: ignore[arg-type]


def test_round_trip_writes_relative_immutable_contract(tmp_path: Path) -> None:
    ref = _write(tmp_path)
    loaded = load_w1_supervisor_snapshot(tmp_path, ref, expected_source_identity=_source(), expected_config_identity=_config())

    assert ref.contract_version == SNAPSHOT_CONTRACT_VERSION
    assert ref.relative_path == "system/imports/lineage_01/attempts/attempt_01/snapshots/checkpoint_01"
    assert loaded["snapshot"]["node"] == "extract_window"
    assert loaded["snapshot"]["state_refs"]["chunks"]["relative_path"] == "state/chunks.json"
    assert loaded["state"]["chunks"][0]["id"] == "chunk_01"
    assert (tmp_path / ref.relative_path / "manifest.json").is_file()


def test_unknown_top_level_state_is_rejected_and_secrets_cannot_be_persisted(tmp_path: Path) -> None:
    with pytest.raises(SnapshotValidationError, match="unsupported_fields"):
        _write(tmp_path, state={"chunks": [], "raw_prompt": "do not write"})
    with pytest.raises(SnapshotValidationError, match="api_key"):
        _write(tmp_path, state={"chunks": [{"api_key": "sk-this-must-never-be-written"}]})
    with pytest.raises(SnapshotValidationError, match="callable"):
        _write(tmp_path, state={"chunks": [{"id": "chunk_01", "value": lambda: None}]})
    with pytest.raises(SnapshotValidationError, match="path_object"):
        _write(tmp_path, state={"chunks": [{"path": Path("relative.txt")} ]})
    with pytest.raises(SnapshotValidationError, match="absolute_path"):
        _write(tmp_path, state={"chunks": [{"artifact_path": "/private/tmp/leak.json"}]})


def test_absolute_paths_and_unsupported_boundaries_are_rejected(tmp_path: Path) -> None:
    absolute_source = _source() | {"source_relative_path": "/Users/unsafe/novel.txt"}
    with pytest.raises(SnapshotValidationError, match="contained"):
        _write(tmp_path, source_identity=absolute_source)
    with pytest.raises(SnapshotValidationError, match="supported_supervisor_boundary"):
        _write(tmp_path, node="done")


def test_manifest_and_state_tampering_fail_closed(tmp_path: Path) -> None:
    ref = _write(tmp_path)
    state_file = tmp_path / ref.relative_path / "state" / "chunks.json"
    state_file.write_text("[]", encoding="utf-8")
    with pytest.raises(SnapshotValidationError, match="hash_mismatch"):
        load_w1_supervisor_snapshot(tmp_path, ref)

    ref = _write(tmp_path, checkpoint_id="checkpoint_02")
    manifest = tmp_path / ref.relative_path / "manifest.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["files"][0]["size"] += 1
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SnapshotValidationError):
        load_w1_supervisor_snapshot(tmp_path, ref)


def test_symlink_and_traversal_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(SnapshotValidationError, match="safe_identifier"):
        _write(tmp_path, checkpoint_id="../checkpoint")
    snapshot_root = tmp_path / "system" / "imports" / "lineage_01"
    snapshot_root.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    snapshot_root.symlink_to(target, target_is_directory=True)
    with pytest.raises(SnapshotValidationError, match="symlink"):
        _write(tmp_path)


def test_source_and_config_mismatch_cannot_resume(tmp_path: Path) -> None:
    ref = _write(tmp_path)
    with pytest.raises(SnapshotValidationError, match="source_identity_mismatch"):
        load_w1_supervisor_snapshot(tmp_path, ref, expected_source_identity=_source() | {"source_sha256": _sha("changed")})
    with pytest.raises(SnapshotValidationError, match="config_identity_mismatch"):
        load_w1_supervisor_snapshot(tmp_path, ref, expected_config_identity=_config() | {"model": "deepseek-v4-pro"})


@pytest.mark.parametrize("stop_at", ["after_state:chunks", "before_manifest", "after_manifest", "before_rename"])
def test_failpoints_never_publish_a_partial_snapshot(tmp_path: Path, stop_at: str) -> None:
    def failpoint(name: str) -> None:
        if name == stop_at:
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match=stop_at):
        _write(tmp_path, failpoint=failpoint)
    final = tmp_path / "system/imports/lineage_01/attempts/attempt_01/snapshots/checkpoint_01"
    assert not final.exists()


def test_after_rename_failpoint_leaves_a_complete_loadable_snapshot(tmp_path: Path) -> None:
    def failpoint(name: str) -> None:
        if name == "after_rename":
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match="after_rename"):
        _write(tmp_path, failpoint=failpoint)
    ref = _write(tmp_path)
    assert load_w1_supervisor_snapshot(tmp_path, ref)["snapshot"]["checkpoint_id"] == "checkpoint_01"


def test_same_checkpoint_is_idempotent_but_different_content_conflicts(tmp_path: Path) -> None:
    first = _write(tmp_path)
    assert _write(tmp_path) == first
    with pytest.raises(SnapshotConflictError, match="different_snapshot_content"):
        _write(tmp_path, state={"chunks": [{"id": "chunk_changed"}]})
