"""Focused contract tests for the standalone W1 Supervisor snapshot codec."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from sidecar.runtime.w1_supervisor_snapshot import (
    SNAPSHOT_CONTRACT_VERSION,
    SnapshotConflictError,
    SnapshotValidationError,
    load_w1_supervisor_snapshot,
    load_w1_supervisor_snapshot_for_resume,
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


def _prepare_resume_source(project: Path) -> None:
    source = project / "sources" / "novel.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("novel", encoding="utf-8")


def _artifact(project: Path, relative_path: str, contents: str) -> dict[str, str]:
    path = project / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return {
        "relative_path": relative_path,
        "sha256": _sha(contents),
        "contract_version": "ArtifactRef/v2",
        "lineage_id": "lineage_01",
        "attempt_id": "attempt_01",
    }


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


def test_source_body_keys_are_recursively_rejected_and_never_persisted(tmp_path: Path) -> None:
    unique_body = "UNIQUE_W1_SOURCE_BODY_SENTENCE_DO_NOT_PERSIST_8f2d7a"
    ref = _write(
        tmp_path,
        state={
            "chunks": [
                {
                    "summary": "A concise structural summary is allowed.",
                    "description": "A durable description is allowed.",
                    "evidence": [{"span_start": 0, "span_end": 5, "kind": "chapter"}],
                }
            ]
        },
    )
    assert load_w1_supervisor_snapshot(tmp_path, ref)["state"]["chunks"][0]["summary"]

    for index, body_key in enumerate(
        [
            "content",
            "raw_content",
            "manuscript_content",
            "text",
            "source_text",
            "chapter_text",
            "window_text",
            "input_text",
            "rawContent",
            "fullText",
        ],
        start=2,
    ):
        with pytest.raises(SnapshotValidationError, match="source_body_key"):
            _write(
                tmp_path,
                checkpoint_id=f"checkpoint_{index:02d}",
                state={"chunks": [{"nested": {body_key: unique_body}}]},
            )

    persisted = b"".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    assert unique_body.encode("utf-8") not in persisted


def test_hidden_reasoning_and_long_source_substrings_are_rejected(tmp_path: Path) -> None:
    source_text = "A uniquely long source sentence that must never be stored in a durable checkpoint. " * 3
    source = tmp_path / "sources" / "novel.txt"
    source.parent.mkdir(parents=True)
    source.write_text(source_text, encoding="utf-8")
    source_identity = _source() | {"source_sha256": _sha(source_text), "source_size": len(source_text)}
    for unsafe_field in ("excerpt", "quote", "analysis", "thought", "rationale", "reasoning", "chainOfThought", "cot"):
        with pytest.raises(SnapshotValidationError):
            _write(
                tmp_path,
                checkpoint_id=f"checkpoint_{unsafe_field}",
                source_identity=source_identity,
                state={"chunks": [{unsafe_field: "short metadata is still forbidden"}]},
            )
    with pytest.raises(SnapshotValidationError, match="source_substring"):
        _write(
            tmp_path,
            checkpoint_id="checkpoint_source_substring",
            source_identity=source_identity,
            state={"chunks": [{"summary": source_text}]},
        )


@pytest.mark.parametrize(
    "state",
    [
        {"resume_context": {"character_tags": [{"name": "第1章\n韩立入门。"}]}},
        {"resume_context": {"manuscript_chapters": [{"title": "第1章\n韩立入门。"}]}},
        {"timeline": {"timeline_architecture": {"label": "第1章\n韩立入门。"}}},
        {"entity_registry": {"characters": {"char_han": {"aliases": ["第1章\n韩立入门。"]}}}},
    ],
)
def test_snapshot_codec_rejects_stable_label_source_body_bypass(
    tmp_path: Path, state: dict[str, object],
) -> None:
    source_text = "第1章\n韩立入门。"
    source = tmp_path / "sources" / "novel.txt"
    source.parent.mkdir(parents=True)
    source.write_text(source_text, encoding="utf-8")
    source_identity = _source() | {
        "source_sha256": _sha(source_text),
        "source_size": len(source_text.encode("utf-8")),
    }

    with pytest.raises(SnapshotValidationError, match=r"invalid_(?:name|title|label|alias)"):
        _write(tmp_path, source_identity=source_identity, state=state)


def test_snapshot_codec_preserves_valid_short_chinese_display_labels(tmp_path: Path) -> None:
    source_text = "第1章 山边小村\n韩立进入七玄门，成为核心人物。"
    source = tmp_path / "sources" / "novel.txt"
    source.parent.mkdir(parents=True)
    source.write_text(source_text, encoding="utf-8")
    source_identity = _source() | {
        "source_sha256": _sha(source_text),
        "source_size": len(source_text.encode("utf-8")),
    }
    state = {
        "resume_context": {
            "character_tags": [{"name": "核心人物"}],
            "manuscript_chapters": [{"title": "第1章 山边小村"}],
        },
        "timeline": {"timeline_architecture": {"label": "主时间线"}},
        "entity_registry": {"characters": {"char_han": {"name": "韩立", "aliases": ["韩二愣"]}}},
    }

    ref = _write(tmp_path, source_identity=source_identity, state=state)
    persisted = load_w1_supervisor_snapshot(tmp_path, ref)["state"]

    assert persisted == state


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


def test_resume_loader_requires_matching_source_and_config_identity(tmp_path: Path) -> None:
    _prepare_resume_source(tmp_path)
    ref = _write(tmp_path)
    with pytest.raises(SnapshotValidationError, match="source_identity_must_be_an_object"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=None, expected_config_identity=_config()  # type: ignore[arg-type]
        )
    with pytest.raises(SnapshotValidationError, match="config_identity_must_be_an_object"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=_source(), expected_config_identity=None  # type: ignore[arg-type]
        )
    with pytest.raises(SnapshotValidationError, match="resume_source_hash_mismatch"):
        (tmp_path / "sources" / "novel.txt").write_text("changed", encoding="utf-8")
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=_source(), expected_config_identity=_config()
        )
    _prepare_resume_source(tmp_path)
    with pytest.raises(SnapshotValidationError, match="snapshot_config_identity_mismatch"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path,
            ref,
            expected_source_identity=_source(),
            expected_config_identity=_config() | {"model": "deepseek-v4-pro"},
        )


def test_resume_loader_rejects_missing_and_hash_mismatched_artifacts(tmp_path: Path) -> None:
    _prepare_resume_source(tmp_path)
    missing = {
        "relative_path": "artifacts/usage.json",
        "sha256": _sha("missing"),
        "contract_version": "ArtifactRef/v2",
        "lineage_id": "lineage_01",
        "attempt_id": "attempt_01",
    }
    ref = _write(tmp_path, usage_ledger_ref=missing)
    with pytest.raises(SnapshotValidationError, match="usage_ledger_ref_missing"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=_source(), expected_config_identity=_config()
        )

    ref = _write(
        tmp_path,
        checkpoint_id="checkpoint_02",
        semantic_coverage_ref=_artifact(tmp_path, "artifacts/coverage.json", "correct"),
    )
    (tmp_path / "artifacts" / "coverage.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(SnapshotValidationError, match="semantic_coverage_ref_hash_mismatch"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=_source(), expected_config_identity=_config()
        )


def test_resume_loader_rejects_symlink_and_snapshot_internal_artifacts(tmp_path: Path) -> None:
    _prepare_resume_source(tmp_path)
    target = tmp_path / "outside.json"
    target.write_text("usage", encoding="utf-8")
    artifact_path = tmp_path / "artifacts" / "usage.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.symlink_to(target)
    symlink_ref = {
        "relative_path": "artifacts/usage.json",
        "sha256": _sha("usage"),
        "contract_version": "ArtifactRef/v2",
        "lineage_id": "lineage_01",
        "attempt_id": "attempt_01",
    }
    ref = _write(tmp_path, usage_ledger_ref=symlink_ref)
    with pytest.raises(SnapshotValidationError, match="symlink|cannot_be_opened_safely"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=_source(), expected_config_identity=_config()
        )

    snapshot_file_ref = {
        "relative_path": "system/imports/lineage_01/attempts/attempt_01/snapshots/checkpoint_02/snapshot.json",
        "sha256": _sha("placeholder"),
        "contract_version": "ArtifactRef/v2",
        "lineage_id": "lineage_01",
        "attempt_id": "attempt_01",
    }
    ref = _write(tmp_path, checkpoint_id="checkpoint_02", usage_ledger_ref=snapshot_file_ref)
    with pytest.raises(SnapshotValidationError, match="must_not_reference_snapshot_contents"):
        load_w1_supervisor_snapshot_for_resume(
            tmp_path, ref, expected_source_identity=_source(), expected_config_identity=_config()
        )


@pytest.mark.parametrize(
    ("budget", "message"),
    [
        ({"budget_limit_usd": 1, "spent_usd": 0.8, "reserved_usd": 0.3}, "spent_and_reserved"),
        ({"input_tokens": 2, "output_tokens": 3, "total_tokens": 4}, "token_total"),
        ({"call_count": 3, "max_steps": 2}, "call_count_exceeds"),
    ],
)
def test_budget_invariants_fail_closed(tmp_path: Path, budget: dict[str, int | float], message: str) -> None:
    with pytest.raises(SnapshotValidationError, match=message):
        _write(tmp_path, budget_snapshot=budget)


def test_actual_nul_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SnapshotValidationError, match="nonempty_relative_path"):
        _write(tmp_path, source_identity=_source() | {"source_relative_path": "sources/novel\x00.txt"})


def test_concurrent_same_checkpoint_is_idempotent_and_conflicts_fail_closed(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=6) as executor:
        refs = list(executor.map(lambda _index: _write(tmp_path), range(6)))
    assert len({ref.manifest_sha256 for ref in refs}) == 1
    assert load_w1_supervisor_snapshot(tmp_path, refs[0])["snapshot"]["checkpoint_id"] == "checkpoint_01"
    with pytest.raises(SnapshotConflictError, match="different_snapshot_content"):
        _write(tmp_path, state={"chunks": [{"id": "different"}]})
