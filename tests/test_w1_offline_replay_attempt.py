"""Offline replay tests: no provider, no canonical acceptance, fail closed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sidecar.runtime.agent_runtime import RuntimeStore
from tools.w1_offline_replay_attempt import replay_attempt


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _span(source: str, start: int, end: int) -> dict[str, object]:
    return {
        "raw_source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "absolute_start": start,
        "absolute_end": end,
        "substring_hash": hashlib.sha256(source[start:end].encode("utf-8")).hexdigest(),
    }


def _fixture(project: Path, *, completed_domains: bool = True, runtime_evidence: bool = False) -> Path:
    source_parts = [f"第{i + 1}章 正文。" for i in range(10)]
    source = "".join(source_parts)
    source_path = project / "novel.txt"
    source_path.write_text(source, encoding="utf-8")
    lineage = "lineage_replay"
    attempt = "attempt_original"
    attempt_dir = project / "system/imports" / lineage / "attempts" / attempt
    offset = 0
    segments = []
    for index, part in enumerate(source_parts):
        end = offset + len(part)
        segments.append({"chunk_id": index, "chapter_index": index, "title": f"第{index + 1}章", "source_span": _span(source, offset, end)})
        offset = end
    windows = [{"id": "pwin_1", "chunk_ids": list(range(10))}]
    _write(attempt_dir / "manifest.json", {
        "lineage_id": lineage, "attempt_id": attempt, "import_run_id": lineage,
        "source_file_path": str(source_path), "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "segment_count": 10, "segments": segments, "prompt_windows": windows, "prompt_profile": "balanced",
        "model": "offline-fixture",
    })
    call_count = 15 if runtime_evidence else 5
    _write(attempt_dir / "usage_ledger.json", {
        "actual_calls": call_count, "actual_input_tokens": call_count * 10, "actual_output_tokens": call_count * 5,
        "actual_total_tokens": call_count * 15,
        "cost_usd": 0.01, "model": "offline-fixture",
    })
    completed = ["character", "event", "world", "relationship", "scene"] if completed_domains else []
    _write(project / "system/imports" / lineage / "window_metrics.json", {
        "pwin_1": {"gate_passed": True, "failed_prompts": [], "completed_domains": completed},
    })
    first_span = segments[0]["source_span"]
    _write(attempt_dir / "evidence_cards.json", [{
        "id": "ev_char", "kind": "character", "entity_id": "char_hero", "candidate_ids": ["char_hero"],
        "source_chunk_id": 0, "source_span": first_span,
        "raw": {"canonical_id": "char_hero", "canonical_name": "主角", "importance": "core", "background": "村中少年", "aliases": [], "notes": [], "confidence": 0.9, "source_span": first_span},
    }, {
        "id": "ev_event", "kind": "event", "entity_id": "event_1", "candidate_ids": ["event_1"],
        "source_chunk_id": 0, "source_span": first_span,
        "raw": {"event_id": "event_1"},
    }, {
        "id": "ev_world", "kind": "world", "entity_id": "world_sect", "candidate_ids": ["world_sect"],
        "source_chunk_id": 0, "source_span": first_span,
        "raw": {"entity_id": "world_sect", "name": "宗门"},
    }])
    _write(attempt_dir / "timeline_architecture.json", {
        "canonical_events": [{
            "event_id": "event_1", "title": "入门", "description": "主角入门", "confidence": 0.9,
            "branchId": "branch_main", "orderIndex": 0, "locationIds": [], "participantCharacterIds": ["char_hero"],
            "linkedSceneIds": [], "linkedWorldItemIds": [], "tags": ["imported"], "chunk_id": 0,
            "source_span": first_span, "evidence_refs": ["ev_event"],
        }],
        "branches": [{"id": "branch_main", "isDefault": True, "mode": "root"}],
    })
    _write(project / "system/imports" / lineage / "organizer_output.json", {
        "world_containers": [{"id": "world_container_organizations", "importCategoryKey": "organizations", "name": "门派组织"}],
        "world_items": [{"entity_id": "world_sect", "name": "宗门", "category": "organization", "containerId": "world_container_organizations", "container_key": "organizations"}],
    })
    if runtime_evidence:
        _write_runtime_evidence(project, source, source_path, windows, call_count)
    return attempt_dir


def _write_runtime_evidence(project: Path, source: str, source_path: Path, windows: list[dict], call_count: int) -> None:
    store = RuntimeStore(project)
    run = store.create_run(
        workflow_id="W1", lineage_id="runtime_legacy_lineage", run_id="runtime_run",
        config={"source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(), "model": "offline-fixture", "source_file_path": str(source_path)},
    )
    attempt = store.create_attempt(run["run_id"], attempt_id="runtime_attempt")
    lease = store.acquire_lease(attempt["attempt_id"], "test_worker", ttl_seconds=60)
    for window in windows:
        for domain in ("character", "event", "world", "relationship", "scene"):
            store.append_event(attempt["attempt_id"], "w1_activity", {"phase": "extracting", "status": "start", "message": f"Running {domain} prompt for {window['id']}."}, owner_id="test_worker", fence_token=lease["fence_token"])
            store.append_event(attempt["attempt_id"], "w1_activity", {"phase": "extracting", "status": "success", "message": f"Finished {domain} prompt for {window['id']}."}, owner_id="test_worker", fence_token=lease["fence_token"])
    for index in range(call_count):
        artifact = project / "system/imports/runtime_legacy_lineage/provider_responses" / f"{index}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"index": index}), encoding="utf-8")
        call = store.record_tool_intent(attempt["attempt_id"], "provider.chat.completions", {"sequence": index})
        store.record_tool_result(call["tool_call_id"], {
            "model": "offline-fixture", "input_tokens": 10, "output_tokens": 5,
            "artifact_receipt": {
                "artifact_path": artifact.relative_to(project).as_posix(),
                "artifact_hash": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            },
        })


def test_dry_run_validates_and_does_not_write(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)

    result = replay_attempt(tmp_path, attempt)

    assert result["status"] == "dry_run"
    assert result["provider_calls"] == 0
    assert not list((tmp_path / "system/imports/lineage_replay/attempts").glob("replay_*"))


def test_apply_creates_pending_replay_package_with_backup(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)

    result = replay_attempt(tmp_path, attempt, apply=True)

    assert result["status"] == "applied"
    receipt = tmp_path / result["receipt_path"]
    assert receipt.is_file()
    assert json.loads(receipt.read_text(encoding="utf-8"))["phase"] == "completed"
    assert json.loads((tmp_path / "system/inbox.json").read_text(encoding="utf-8"))


def test_legacy_metrics_without_completed_domains_fail_closed_and_apply_only_receipts(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path, completed_domains=False)

    dry_run = replay_attempt(tmp_path, attempt)
    applied = replay_attempt(tmp_path, attempt, apply=True)

    assert dry_run["status"] == "blocked"
    assert "window_domain_completion_receipt_missing:pwin_1" in dry_run["receipt_missing"]
    assert applied["status"] == "blocked"
    assert not (tmp_path / "system/inbox.json").exists()
    assert (tmp_path / applied["receipt_path"]).is_file()


def test_partial_native_completion_receipt_requires_runtime_bridge(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)
    metrics_path = tmp_path / "system/imports/lineage_replay/window_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["pwin_1"]["completed_domains"] = ["character"]
    _write(metrics_path, metrics)

    result = replay_attempt(tmp_path, attempt)

    assert result["status"] == "blocked"
    assert "legacy_bridge_runtime_db_missing" in result["receipt_missing"]


def test_runtime_legacy_identity_bridge_backfills_only_verified_domain_receipts(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path, completed_domains=False, runtime_evidence=True)

    result = replay_attempt(tmp_path, attempt)

    assert result["status"] == "dry_run"
    bridge = result["legacy_identity_bridge"]
    assert bridge["verified"] is True
    assert bridge["runtime_lineage_id"] == "runtime_legacy_lineage"
    assert bridge["artifact_lineage_id"] == "lineage_replay"
    assert bridge["completed_domains_by_window"]["pwin_1"] == ["character", "event", "relationship", "scene", "world"]


def test_runtime_legacy_identity_bridge_rejects_unknown_tool_outcome(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path, completed_domains=False, runtime_evidence=True)
    store = RuntimeStore(tmp_path)
    call = store.list_tool_calls("runtime_attempt")[0]
    store.record_tool_unknown_outcome(call["tool_call_id"], "simulated interruption")

    result = replay_attempt(tmp_path, attempt)

    assert result["status"] == "blocked"
    assert f"legacy_bridge_tool_not_result:{call['tool_call_id']}" in result["receipt_missing"]


def test_semantic_gate_blocks_dry_run_and_apply_without_touching_inbox(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)
    cards_path = attempt / "evidence_cards.json"
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    cards[0]["raw"].pop("background")
    _write(cards_path, cards)

    dry_run = replay_attempt(tmp_path, attempt)
    applied = replay_attempt(tmp_path, attempt, apply=True)

    assert dry_run["status"] == "blocked"
    assert "major_character_missing_background" in dry_run["semantic_blocking_codes"]
    assert applied["status"] == "blocked"
    assert not (tmp_path / "system/inbox.json").exists()


def test_deterministic_finalize_backfills_evidence_bound_identity_background(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)
    cards_path = attempt / "evidence_cards.json"
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    cards[0]["raw"].pop("background")
    cards[0]["raw"]["summary"] = "农家少年，参加入门测试。"
    _write(cards_path, cards)

    result = replay_attempt(tmp_path, attempt)

    assert "major_character_missing_background" not in result["semantic_blocking_codes"]


def test_source_tampering_fails_before_creating_replay_artifacts(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)
    (tmp_path / "novel.txt").write_text("tampered", encoding="utf-8")

    result = replay_attempt(tmp_path, attempt)

    assert result["status"] == "blocked"
    assert "source_hash_mismatch" in result["missing"]
    assert not list((tmp_path / "system/imports/lineage_replay/attempts").glob("replay_*"))
