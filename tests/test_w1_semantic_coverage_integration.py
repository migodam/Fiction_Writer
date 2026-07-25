"""Integration coverage for the W1 semantic compiler proposal gate."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from sidecar.shared.proposal_graph import compile_import_run_package
from sidecar.workflows import w1_import, w1_truth


def _state(tmp_path: Path, extraction: dict | None, *, run_id: str = "run_gate") -> dict:
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nA complete test chapter.", encoding="utf-8")
    return {
        "project_path": str(tmp_path),
        "source_file_path": str(source),
        "import_run_id": run_id,
        "lineage_id": "lineage_gate",
        "workflow_id": "W1-test-run",
        "import_run_manifest": {
            "import_run_id": run_id,
            "lineage_id": "lineage_gate",
            "attempt_id": "attempt_gate",
            "source_hash": "source-hash",
        },
        "prompt_profile": "balanced",
        "context": {"model": "offline-test"},
        "chunks": [{"chunk_id": 0, "chapter_ids": ["chapter_1"], "chapter_hint": "Chapter 1"}],
        "chunk_extractions": [] if extraction is None else [extraction],
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "manuscript_chapters": [],
        "timeline_architecture": {"canonical_events": [], "discarded_duplicates": [], "warnings": []},
        "timeline_branches": [],
        "relationships": [],
        "reducer_artifact": {"warnings": [], "duplicate_candidates": []},
        "errors": [],
        "character_tags": [],
        "project_structure_digest": {},
    }


def _complete() -> dict:
    return w1_truth.semantic_complete({"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": "body"})


def _proposal(proposal_id: str, run_id: str) -> dict:
    return {
        "id": proposal_id,
        "source_workflow": "W1_import",
        "operations": [{
            "op": "create", "entityType": "chapter", "entityId": "chapter_1",
            "fields": {"id": "chapter_1", "importRunId": run_id},
        }],
    }


def test_pass_report_is_atomic_and_traceable(tmp_path: Path) -> None:
    state = _state(tmp_path, _complete())

    result = asyncio.run(w1_import.node_review_import(state))
    report = result["semantic_coverage_report"]
    path = tmp_path / "system" / "imports" / "run_gate" / "attempts" / "attempt_gate" / "semantic_coverage_report.json"

    assert report["verdict"] == "pass"
    assert report["acceptance_policy"]["automatic_acceptance"] is True
    assert report["lineage_id"] == "lineage_gate"
    assert report["attempt_id"] == "attempt_gate"
    assert report["run_id"] == "W1-test-run"
    assert report["input_hash"]
    assert report["semantic_coverage_ref"]["relativePath"] == "system/imports/run_gate/attempts/attempt_gate/semantic_coverage_report.json"
    assert report["semantic_coverage_ref"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert all(not str(value).startswith("/") for value in report["artifact_paths"].values())
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["input_hash"] == report["input_hash"]


def test_failed_chunk_blocks_and_removes_stale_package_before_publication(tmp_path: Path) -> None:
    state = _state(tmp_path, w1_truth.failed_extraction({"chunk_id": 0, "manuscript_content": "body"}, error="lease fenced", failure_code="lease_lost"))
    inbox = tmp_path / "system" / "inbox.json"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(json.dumps([_proposal("stale", "run_gate")]), encoding="utf-8")

    result = asyncio.run(w1_import.node_write_to_project(state))

    assert result["status"] == "blocked"
    assert result["proposals"] == []
    assert json.loads(inbox.read_text(encoding="utf-8")) == []
    report = json.loads((tmp_path / "system" / "imports" / "run_gate" / "attempts" / "attempt_gate" / "semantic_coverage_report.json").read_text(encoding="utf-8"))
    assert report["verdict"] == "blocked"
    assert "chunk_not_semantically_complete" in {item["code"] for item in report["blocking_findings"]}


def test_warning_package_is_published_only_for_manual_review(tmp_path: Path) -> None:
    state = _state(tmp_path, _complete())
    state["entity_registry"]["world_detailed"] = {
        "藏经阁": {"id": "world_library", "name": "藏经阁", "category": "location", "containerId": "world_folder_locations"}
    }
    report = asyncio.run(w1_import.node_review_import(state))["semantic_coverage_report"]
    inbox = tmp_path / "system" / "inbox.json"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(json.dumps([_proposal("warning", "run_gate")]), encoding="utf-8")

    result = compile_import_run_package(tmp_path, "run_gate", semantic_coverage_report=report)
    proposal = json.loads(inbox.read_text(encoding="utf-8"))[0]

    assert report["verdict"] == "warning"
    assert result["atomic"] is True
    assert result["semanticCoverage"]["automatic_acceptance"] is False
    assert proposal["requiresManualReview"] is True
    assert proposal["automaticAcceptance"] is False
    assert proposal["semanticCoverageRef"] == report["semantic_coverage_ref"]
    assert proposal["operations"][0]["semanticCoverageRef"] == report["semantic_coverage_ref"]


def test_pass_without_a_verifiable_artifact_ref_fails_closed(tmp_path: Path) -> None:
    inbox = tmp_path / "system" / "inbox.json"
    inbox.parent.mkdir(parents=True)
    inbox.write_text(json.dumps([_proposal("missing-ref", "run_missing_ref")]), encoding="utf-8")
    report = {
        "verdict": "pass",
        "input_hash": "input-hash",
        "attempt_id": "attempt-missing-ref",
        "acceptance_policy": {"automatic_acceptance": True},
    }

    result = compile_import_run_package(
        tmp_path, "run_missing_ref", remove_invalid_package=True,
        semantic_coverage_report=report,
    )

    assert result["atomic"] is False
    assert any(item["code"] == "semantic_coverage_blocked" for item in result["blockingErrors"])
    assert json.loads(inbox.read_text(encoding="utf-8")) == []


def test_restart_reuses_matching_durable_report(tmp_path: Path, monkeypatch) -> None:
    state = _state(tmp_path, _complete())
    first = w1_import._load_or_compile_semantic_coverage(state)

    import sidecar.supervisor.semantic_coverage as coverage
    monkeypatch.setattr(coverage, "compile_semantic_coverage", lambda _payload: (_ for _ in ()).throw(AssertionError("should reuse durable report")))
    second = w1_import._load_or_compile_semantic_coverage(state)

    assert second == first


def test_missing_legacy_truth_fails_closed_with_migration_status(tmp_path: Path) -> None:
    state = _state(tmp_path, None)

    report = asyncio.run(w1_import.node_review_import(state))["semantic_coverage_report"]

    assert report["verdict"] == "blocked"
    assert report["migration_status"] == "legacy_truth_migration_required"
    assert "chunk_not_semantically_complete" in {item["code"] for item in report["blocking_findings"]}


def test_supervisor_domain_receipts_replace_absent_legacy_chunk_extractions(tmp_path: Path) -> None:
    state = _state(tmp_path, None)
    state["use_supervisor"] = True
    state["supervisor_semantic_receipts"] = [{
        "chunk_id": 0,
        "window_id": "pwin_1",
        "domain_status": {
            "characters": "complete", "events": "complete", "world": "complete",
            "relationships": "complete", "scenes": "complete",
        },
        "completion_evidence": {"contract": "w1-supervisor-window-receipt/v1", "failed_prompts": []},
    }]

    report = asyncio.run(w1_import.node_review_import(state))["semantic_coverage_report"]

    assert report["verdict"] == "pass"
    assert report["migration_status"] == "current"
    assert not {item["code"] for item in report["blocking_findings"] if item["code"].startswith("chunk_")}


def test_supervisor_failed_domain_receipt_remains_blocked(tmp_path: Path) -> None:
    state = _state(tmp_path, None)
    state["use_supervisor"] = True
    state["supervisor_semantic_receipts"] = [{
        "chunk_id": 0,
        "window_id": "pwin_1",
        "domain_status": {
            "characters": "complete", "events": "complete", "world": "complete",
            "relationships": "failed", "scenes": "complete",
        },
        "completion_evidence": {"contract": "w1-supervisor-window-receipt/v1", "failed_prompts": ["relationship:timeout"]},
    }]

    report = asyncio.run(w1_import.node_review_import(state))["semantic_coverage_report"]

    assert report["verdict"] == "blocked"
    assert "chunk_domain_failed" in {item["code"] for item in report["blocking_findings"]}


def test_slim_supervisor_write_input_rebuilds_chunk_coverage_from_receipts(tmp_path: Path) -> None:
    state = _state(tmp_path, None)
    state["chunks"] = []
    state["manuscript_chapters"] = [{"chapter_id": "chapter_1", "chunk_ids": [0], "title": "Outline"}]
    state["supervisor_semantic_receipts"] = [{
        "chunk_id": 0,
        "domain_status": {
            "characters": "complete", "events": "complete", "world": "complete",
            "relationships": "complete", "scenes": "complete",
        },
        "completion_evidence": {"contract": "w1-supervisor-window-receipt/v1", "failed_prompts": []},
    }]

    records, migration_status = w1_import._semantic_chunk_records(state)

    assert migration_status == "current"
    assert records == [
        {
            "chunk_id": 0, "chapter_ids": ["chapter_1"], "semantic_status": "semantic_complete",
            "domain_status": {
                "characters": "complete", "events": "complete", "world": "complete",
                "relationships": "complete", "scenes": "complete",
            },
            "failure_refs": [], "candidate_ids": [],
            "completion_evidence": {"contract": "w1-supervisor-window-receipt/v1", "failed_prompts": []},
        }
    ]


def test_manifest_chapter_count_without_durable_chunk_chapter_ids_blocks(tmp_path: Path) -> None:
    state = _state(tmp_path, _complete())
    state["import_run_manifest"]["chapter_count"] = 2
    state["chunks"] = [{"chunk_id": 0, "chapter_hint": "Chapter 1"}]

    report = asyncio.run(w1_import.node_review_import(state))["semantic_coverage_report"]

    assert report["verdict"] == "blocked"
    assert "chapter_coverage_missing_chunk_ids" in {item["code"] for item in report["blocking_findings"]}
