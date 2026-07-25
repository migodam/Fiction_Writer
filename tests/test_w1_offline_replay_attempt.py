"""Offline replay tests: no provider, no canonical acceptance, fail closed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

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


def _fixture(project: Path, *, completed_domains: bool = True) -> Path:
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
    })
    _write(attempt_dir / "usage_ledger.json", {
        "actual_calls": 5, "actual_input_tokens": 100, "actual_output_tokens": 50, "actual_total_tokens": 150,
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
    return attempt_dir


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


def test_source_tampering_fails_before_creating_replay_artifacts(tmp_path: Path) -> None:
    attempt = _fixture(tmp_path)
    (tmp_path / "novel.txt").write_text("tampered", encoding="utf-8")

    result = replay_attempt(tmp_path, attempt)

    assert result["status"] == "blocked"
    assert "source_hash_mismatch" in result["missing"]
    assert not list((tmp_path / "system/imports/lineage_replay/attempts").glob("replay_*"))
