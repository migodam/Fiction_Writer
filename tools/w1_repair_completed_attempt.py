#!/usr/bin/env python3
"""Repair evidence bindings in one completed, still-pending W1 attempt.

This migration is deterministic and offline. It never invokes an LLM, changes
source text, or accepts proposals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sidecar.supervisor.reviewers.consistency_reviewer import ConsistencyReviewer
from sidecar.supervisor.reviewers.fact_reviewer import FactReviewer
from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer
from sidecar.workflows import w1_import


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _match_card(cards: list[dict], entity_id: str, kind: str) -> dict | None:
    for card in cards:
        if card.get("kind") != kind:
            continue
        raw = card.get("raw") if isinstance(card.get("raw"), dict) else {}
        raw_id = raw.get("canonical_id") if kind == "character" else raw.get("event_id")
        if entity_id in (card.get("candidate_ids") or []) or raw_id == entity_id:
            return card
    return None


def _enrich_cards(cards: list[dict], raw_source: str) -> int:
    enriched = 0
    for card in cards:
        card_id = str(card.get("id") or card.get("card_id") or "")
        card["id"] = card_id
        card["card_id"] = card_id
        raw = card.get("raw") if isinstance(card.get("raw"), dict) else {}
        candidate_ids = [str(value) for value in card.get("candidate_ids", []) if value]
        if card.get("kind") in {"character", "event"} and candidate_ids:
            card["entity_id"] = candidate_ids[0]
            card["entityId"] = candidate_ids[0]
        candidates = [
            *card.get("candidate_names", []),
            card.get("summary"),
            *raw.get("character_names", []),
            raw.get("canonical_name"),
            raw.get("source_character_name"),
            raw.get("target_character_name"),
        ]
        snippet = w1_import._claim_local_evidence_snippet(
            raw_source, card.get("source_span"), candidates,
        )
        previous = card.get("snippets") or []
        card["snippets"] = previous or ([snippet] if snippet else [])
        if card["snippets"]:
            enriched += 1
    return enriched


def _repair_character(fields: dict, entity_id: str, card: dict) -> bool:
    raw = dict(card.get("raw") or {})
    raw["notes"] = list(raw.get("notes") or fields.get("notes") or [])
    raw["importance"] = raw.get("importance") or fields.get("importance")
    raw["groupKey"] = fields.get("groupKey", "")
    raw = w1_import._attach_character_evidence_card(raw, entity_id, [card])
    experience, background, profile_evidence = w1_import._backfill_character_profile_at_write_boundary(
        entity_id, raw,
    )
    changed = False
    updates = {
        "evidenceRefs": w1_import._character_evidence_refs(raw, profile_evidence),
        "sourceSpan": w1_import._character_source_span(raw, profile_evidence),
        "sourceSegmentId": card.get("source_segment_id", ""),
    }
    if not fields.get("experience") and experience:
        updates["experience"] = experience
    if not str(fields.get("background") or "").strip() and background:
        updates["background"] = background
    if profile_evidence:
        updates["profile_field_evidence"] = profile_evidence
    for key, value in updates.items():
        if value not in (None, "", []) and fields.get(key) != value:
            fields[key] = value
            changed = True
    return changed


def _repair_event(fields: dict, entity_id: str, card: dict) -> bool:
    updated = w1_import._attach_entity_evidence_card(fields, entity_id, [card], kind="event")
    replacements = {
        "evidenceRefs": updated.get("evidence_refs", []),
        "sourceSpan": updated.get("source_span"),
        "sourceSegmentId": card.get("source_segment_id", ""),
    }
    changed = False
    for key, value in replacements.items():
        if value not in (None, "", []) and fields.get(key) != value:
            fields[key] = value
            changed = True
    return changed


def repair_attempt(project: Path, run_dir: Path, *, apply: bool) -> dict[str, Any]:
    project = project.expanduser().resolve()
    run_dir = run_dir.expanduser().resolve()
    if project not in run_dir.parents:
        raise ValueError("run directory must be inside the project")
    checkpoint_path = run_dir / "checkpoint.json"
    manifest_path = run_dir / "manifest.json"
    evidence_path = run_dir / "evidence_cards.json"
    timeline_path = run_dir / "timeline_architecture.json"
    review_path = run_dir / "review_report.json"
    inbox_path = project / "system" / "inbox.json"
    required = [checkpoint_path, manifest_path, evidence_path, timeline_path, review_path, inbox_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing required artifacts: {missing}")

    checkpoint = _read_json(checkpoint_path)
    manifest = _read_json(manifest_path)
    cards = _read_json(evidence_path)
    timeline = _read_json(timeline_path)
    review = _read_json(review_path)
    inbox = _read_json(inbox_path)
    raw_source = (run_dir / "raw_source.txt").read_text(encoding="utf-8")
    if checkpoint.get("attempt_id") != run_dir.name:
        raise ValueError("checkpoint attempt_id does not match run directory")
    if len(checkpoint.get("committed_chunk_ids") or []) != 10 or int(checkpoint.get("total_chunks") or 0) != 10:
        raise ValueError("attempt is not a completed 10-chapter checkpoint")
    if hashlib.sha256(raw_source.encode("utf-8")).hexdigest() != manifest.get("source_hash"):
        raise ValueError("raw source hash does not match manifest")
    if not isinstance(inbox, list) or any(item.get("status") != "pending" for item in inbox):
        raise ValueError("repair requires an all-pending proposal inbox")

    original_statuses = [item.get("status") for item in inbox]
    snippets_enriched = _enrich_cards(cards, raw_source)
    character_updates = 0
    event_updates = 0
    for proposal in inbox:
        for operation in proposal.get("operations") or []:
            entity_id = str(operation.get("entityId") or "")
            fields = operation.get("fields") if isinstance(operation.get("fields"), dict) else {}
            kind = operation.get("entityType")
            if kind == "character" and (card := _match_card(cards, entity_id, "character")):
                character_updates += int(_repair_character(fields, entity_id, card))
            elif kind == "timeline_event" and (card := _match_card(cards, entity_id, "event")):
                event_updates += int(_repair_event(fields, entity_id, card))

    active_branch_ids = {
        str(event.get("branchId") or event.get("branch_id") or "")
        for event in timeline.get("canonical_events") or []
        if event.get("branchId") or event.get("branch_id")
    }
    root_branch_id = str(timeline.get("root_branch_id") or "")
    old_branches = list(timeline.get("branches") or [])
    timeline["branches"] = [
        branch for branch in old_branches
        if str(branch.get("id") or "") in active_branch_ids
        or str(branch.get("id") or "") == root_branch_id
    ]

    reviewer_state = {
        "proposals": inbox,
        "inbox_proposals": inbox,
        "evidence_cards": cards,
        "project_structure_digest": _read_json(run_dir / "project_structure_digest.json"),
        "timeline_architecture": timeline,
        "reviewer_staged_projection_metrics": {
            "inputs_present": True,
            "chapter_count": len(
                (_read_json(run_dir / "staged_manuscript_projection.json").get("chapters") or [])
            ),
        },
    }
    reviewer_reports = {
        "quality": QualityReviewer().review(reviewer_state),
        "fact": FactReviewer().review(reviewer_state),
        "consistency": ConsistencyReviewer().review(reviewer_state),
    }
    old_warnings = [
        warning for warning in review.get("warnings", [])
        if not str(warning).startswith(("quality_reviewer:", "fact_reviewer:", "consistency_reviewer:"))
    ]
    review["warnings"] = old_warnings
    review["reviewer_reports"] = reviewer_reports
    review["status"] = "fail" if review.get("errors") else "warning" if old_warnings else "pass"

    if [item.get("status") for item in inbox] != original_statuses:
        raise RuntimeError("proposal status changed during repair")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_dir = run_dir / "repair_receipts" / timestamp
    targets = [inbox_path, evidence_path, timeline_path, review_path]
    before_hashes = {str(path.relative_to(project)): _sha256_file(path) for path in targets}
    result = {
        "contract": "W1CompletedAttemptRepair/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "attempt_id": run_dir.name,
        "apply": apply,
        "offline": True,
        "provider_calls": 0,
        "proposal_count": len(inbox),
        "proposal_status": "pending",
        "character_proposals_updated": character_updates,
        "event_proposals_updated": event_updates,
        "evidence_cards_with_snippets": snippets_enriched,
        "timeline_branches_removed": len(old_branches) - len(timeline["branches"]),
        "reviewer_findings": {
            name: len(report.get("findings") or []) for name, report in reviewer_reports.items()
        },
        "reviewer_finding_counts": {
            name: {
                check_name: sum(
                    1 for finding in report.get("findings") or []
                    if finding.get("check_name") == check_name
                )
                for check_name in sorted({
                    str(finding.get("check_name") or "unknown")
                    for finding in report.get("findings") or []
                })
            }
            for name, report in reviewer_reports.items()
        },
        "fact_finding_entities": [
            {
                "check_name": finding.get("check_name"),
                "entity_refs": finding.get("entity_refs", []),
            }
            for finding in reviewer_reports["fact"].get("findings") or []
        ],
        "before_hashes": before_hashes,
    }
    if not apply:
        return result

    receipt_dir.mkdir(parents=True, exist_ok=False)
    for path in targets:
        shutil.copy2(path, receipt_dir / path.name)
    _atomic_json(inbox_path, inbox)
    _atomic_json(evidence_path, cards)
    _atomic_json(timeline_path, timeline)
    _atomic_json(review_path, review)
    result["after_hashes"] = {str(path.relative_to(project)): _sha256_file(path) for path in targets}
    result["backup_dir"] = str(receipt_dir)
    _atomic_json(receipt_dir / "receipt.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(repair_attempt(args.project, args.run_dir, apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
