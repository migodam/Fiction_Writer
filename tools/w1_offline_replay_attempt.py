#!/usr/bin/env python3
"""Replay one saved W1 supervisor attempt without provider access.

The tool rebuilds only the deterministic reviewer/proposal state from durable
artifacts.  It never imports a provider client, never accepts canonical data,
and only writes a new pending proposal package after every contract check and
semantic gate passes.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sidecar.supervisor.semantic_coverage import compile_semantic_coverage
from sidecar.workflows import w1_import


TOOL_VERSION = "w1-offline-attempt-replay/v1"
_DOMAIN_LABELS = {
    "characters": "character",
    "events": "event",
    "world": "world",
    "relationships": "relationship",
    "scenes": "scene",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _relative(project: Path, path: Path) -> str:
    return path.resolve().relative_to(project.resolve()).as_posix()


def _attempt_paths(project: Path, attempt_dir: Path) -> tuple[Path, Path]:
    project = project.expanduser().resolve()
    attempt_dir = attempt_dir.expanduser().resolve()
    imports_root = project / "system" / "imports"
    try:
        relative = attempt_dir.relative_to(imports_root)
    except ValueError as exc:
        raise ValueError("attempt directory must be inside project/system/imports") from exc
    parts = relative.parts
    if len(parts) != 3 or parts[1] != "attempts":
        raise ValueError("attempt directory must use system/imports/<lineage>/attempts/<attempt>")
    return project, imports_root / parts[0]


def _validate_usage_ledger(ledger: Any) -> list[str]:
    if not isinstance(ledger, dict):
        return ["usage_ledger_not_object"]
    errors: list[str] = []
    for key in ("actual_calls", "actual_input_tokens", "actual_output_tokens", "actual_total_tokens", "cost_usd"):
        value = ledger.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            errors.append(f"usage_ledger_invalid_{key}")
    if not str(ledger.get("model") or "").strip():
        errors.append("usage_ledger_missing_model")
    return errors


def _validate_segments(manifest: dict[str, Any], source_text: str, *, expected_chapters: int) -> list[str]:
    errors: list[str] = []
    source_hash = _sha256_text(source_text)
    if source_hash != str(manifest.get("source_hash") or ""):
        errors.append("source_hash_mismatch")
    segments = manifest.get("segments")
    if not isinstance(segments, list) or len(segments) != expected_chapters:
        return [*errors, f"segment_count_not_{expected_chapters}"]
    ordered = sorted((item for item in segments if isinstance(item, dict)), key=lambda item: int(item.get("chunk_id", -1)))
    if [item.get("chunk_id") for item in ordered] != list(range(expected_chapters)):
        errors.append("segment_chunk_ids_not_contiguous")
        return errors
    previous_end = 0
    for index, segment in enumerate(ordered):
        span = segment.get("source_span")
        if not isinstance(span, dict):
            errors.append(f"segment_{index}_missing_source_span")
            continue
        try:
            start, end = int(span["absolute_start"]), int(span["absolute_end"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"segment_{index}_invalid_source_span")
            continue
        if start != previous_end or end <= start or end > len(source_text):
            errors.append(f"segment_{index}_non_continuous_source_span")
        substring = source_text[start:end] if 0 <= start <= end <= len(source_text) else ""
        if span.get("raw_source_hash") != source_hash or span.get("substring_hash") != _sha256_text(substring):
            errors.append(f"segment_{index}_source_span_hash_mismatch")
        previous_end = end
    if previous_end != len(source_text):
        errors.append("segments_do_not_cover_source")
    return errors


def _build_supervisor_receipts(manifest: dict[str, Any], metrics: Any) -> tuple[list[dict[str, Any]], list[str]]:
    receipts: list[dict[str, Any]] = []
    missing: list[str] = []
    if not isinstance(metrics, dict):
        return receipts, ["window_metrics_missing"]
    for window in manifest.get("prompt_windows", []) or []:
        if not isinstance(window, dict):
            continue
        window_id = str(window.get("id") or "")
        metric = metrics.get(window_id)
        if not isinstance(metric, dict):
            missing.append(f"window_metric_missing:{window_id}")
            continue
        failed = {str(value).split(":", 1)[0].strip() for value in metric.get("failed_prompts", []) if str(value).strip()}
        completed = {str(value).strip() for value in metric.get("completed_domains", []) if str(value).strip()}
        gate_passed = metric.get("gate_passed") is True
        if not completed:
            missing.append(f"window_domain_completion_receipt_missing:{window_id}")

        def status(label: str) -> str:
            if label in failed:
                return "failed"
            if gate_passed and label in completed:
                return "complete"
            return "unknown"

        for chunk_id in window.get("chunk_ids", []) or []:
            receipts.append({
                "chunk_id": chunk_id,
                "window_id": window_id,
                "domain_status": {domain: status(label) for domain, label in _DOMAIN_LABELS.items()},
                "completion_evidence": {
                    "contract": "w1-supervisor-window-receipt/v1",
                    "window_gate_passed": gate_passed,
                    "failed_prompts": sorted(failed),
                    "completed_domains": sorted(completed),
                },
            })
    return receipts, missing


def _evidence_by_kind(cards: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [card for card in cards if isinstance(card, dict) and card.get("kind") == kind and isinstance(card.get("raw"), dict)]


def _append_unique(target: list[Any], values: list[Any]) -> list[Any]:
    result = list(target)
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _rebuild_state(
    project: Path, lineage_dir: Path, attempt_dir: Path, manifest: dict[str, Any], source_text: str,
    cards: list[dict[str, Any]], timeline: dict[str, Any], organizer: dict[str, Any], metrics: Any,
    replay_attempt_id: str,
) -> tuple[dict[str, Any], list[str]]:
    segments = sorted(manifest["segments"], key=lambda item: int(item["chunk_id"]))
    chunks: list[dict[str, Any]] = []
    manuscript_chapters: list[dict[str, Any]] = []
    for segment in segments:
        chunk_id = int(segment["chunk_id"])
        chapter_id = f"chap_replay_{chunk_id + 1:02d}"
        span = dict(segment["source_span"])
        body = source_text[int(span["absolute_start"]):int(span["absolute_end"])]
        chunks.append({"chunk_id": chunk_id, "chapter_ids": [chapter_id], "source_span": span})
        manuscript_chapters.append({
            "chapter_id": chapter_id,
            "scene_id": f"scene_replay_{chunk_id + 1:02d}",
            "title": str(segment.get("title") or f"Chapter {chunk_id + 1}"),
            "chunk_ids": [chunk_id],
            "source_span": span,
            "manuscript_content": body,
            "summary": str(segment.get("title") or ""),
        })

    characters: dict[str, dict[str, Any]] = {}
    for card in _evidence_by_kind(cards, "character"):
        raw = dict(card["raw"])
        entity_id = str(raw.get("canonical_id") or card.get("entity_id") or (card.get("candidate_ids") or [""])[0])
        if not entity_id:
            continue
        entry = characters.setdefault(entity_id, raw)
        entry["evidence_refs"] = _append_unique(list(entry.get("evidence_refs") or []), [str(card.get("id") or card.get("card_id") or "")])
        entry["source_chunk_ids"] = _append_unique(list(entry.get("source_chunk_ids") or []), [card.get("source_chunk_id")])
        entry.setdefault("source_span", card.get("source_span"))

    events: dict[str, dict[str, Any]] = {
        str(event.get("event_id") or event.get("id")): dict(event)
        for event in timeline.get("canonical_events", []) or []
        if isinstance(event, dict) and (event.get("event_id") or event.get("id"))
    }
    for card in _evidence_by_kind(cards, "event"):
        raw = card["raw"]
        entity_id = str(raw.get("event_id") or card.get("entity_id") or "")
        if entity_id not in events:
            continue
        event = events[entity_id]
        event["evidence_refs"] = _append_unique(list(event.get("evidence_refs") or []), [str(card.get("id") or card.get("card_id") or "")])
        event.setdefault("source_span", card.get("source_span"))
        event.setdefault("source_chunk_id", card.get("source_chunk_id"))

    world: dict[str, str] = {}
    world_detailed: dict[str, dict[str, Any]] = {}
    world_cards = _evidence_by_kind(cards, "world")
    for item in organizer.get("world_items", []) or []:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or item.get("id") or "")
        name = str(item.get("name") or "")
        if not entity_id or not name:
            continue
        detail = dict(item)
        for card in world_cards:
            raw = card["raw"]
            if entity_id in {str(raw.get("entity_id") or ""), str(card.get("entity_id") or "")} or name == str(raw.get("name") or ""):
                detail["evidence_refs"] = _append_unique(list(detail.get("evidence_refs") or []), [str(card.get("id") or card.get("card_id") or "")])
                detail.setdefault("source_span", card.get("source_span"))
                detail.setdefault("source_chunk_id", card.get("source_chunk_id"))
        world[name] = str(detail.get("category") or "concept")
        world_detailed[entity_id] = detail

    relationships: list[dict[str, Any]] = []
    for card in _evidence_by_kind(cards, "relationship"):
        raw = dict(card["raw"])
        relationship_id = str(raw.get("id") or card.get("entity_id") or card.get("id") or "")
        if not relationship_id:
            continue
        raw["id"] = relationship_id
        raw["sourceId"] = raw.get("sourceId") or raw.get("source_candidate_id")
        raw["targetId"] = raw.get("targetId") or raw.get("target_candidate_id")
        raw["evidence_refs"] = _append_unique(list(raw.get("evidence_refs") or []), [str(card.get("id") or card.get("card_id") or "")])
        raw.setdefault("source_span", card.get("source_span"))
        raw.setdefault("source_chunk_id", card.get("source_chunk_id"))
        relationships.append(raw)

    receipts, receipt_missing = _build_supervisor_receipts(manifest, metrics)
    replay_manifest = {
        **manifest,
        "attempt_id": replay_attempt_id,
        "lineage_id": str(manifest["lineage_id"]),
        "import_run_id": str(manifest["lineage_id"]),
        "chapter_count": len(chunks),
        "replayed_from_attempt_id": str(manifest["attempt_id"]),
        "offline_replay": True,
    }
    state = {
        "project_path": str(project), "workflow_id": "W1_offline_replay", "import_run_id": str(manifest["lineage_id"]),
        "lineage_id": str(manifest["lineage_id"]), "source_file_path": str(manifest["source_file_path"]),
        "source_text": source_text, "source_language": "zh", "use_supervisor": True,
        "context": {"use_supervisor": True, "offline_replay": True}, "prompt_profile": str(manifest.get("prompt_profile") or "balanced"),
        "import_run_manifest": replay_manifest, "chunks": chunks, "chunk_extractions": [],
        "supervisor_semantic_receipts": receipts, "entity_registry": {
            "characters": characters, "events": events, "world": world, "world_detailed": world_detailed,
        },
        "relationships": relationships, "evidence_cards": cards, "manuscript_chapters": manuscript_chapters,
        "timeline_architecture": timeline, "timeline_branches": list(timeline.get("branches") or []),
        "world_containers": list(organizer.get("world_containers") or []), "organizer_output": organizer,
        "reducer_artifact": {}, "character_tags": [], "world_settings": {}, "errors": [], "project_structure_digest": {},
    }
    return state, receipt_missing


def _validate_and_load(project: Path, attempt_dir: Path, expected_chapters: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    project, lineage_dir = _attempt_paths(project, attempt_dir)
    required = {
        "manifest": attempt_dir / "manifest.json", "evidence_cards": attempt_dir / "evidence_cards.json",
        "timeline": attempt_dir / "timeline_architecture.json", "usage_ledger": attempt_dir / "usage_ledger.json",
        "organizer": lineage_dir / "organizer_output.json", "window_metrics": lineage_dir / "window_metrics.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        return None, {"status": "blocked", "missing": [f"artifact_missing:{name}" for name in missing], "provider_calls": 0}
    manifest = _read_json(required["manifest"])
    if not isinstance(manifest, dict):
        return None, {"status": "blocked", "missing": ["manifest_not_object"], "provider_calls": 0}
    identity_errors: list[str] = []
    if str(manifest.get("attempt_id") or "") != attempt_dir.name:
        identity_errors.append("attempt_identity_mismatch")
    if str(manifest.get("lineage_id") or "") != lineage_dir.name:
        identity_errors.append("lineage_identity_mismatch")
    source_path = Path(str(manifest.get("source_file_path") or "")).expanduser()
    if not source_path.is_file():
        identity_errors.append("source_file_missing")
        source_text = ""
    else:
        source_text = source_path.read_text(encoding="utf-8")
    if source_text:
        identity_errors.extend(_validate_segments(manifest, source_text, expected_chapters=expected_chapters))
    identity_errors.extend(_validate_usage_ledger(_read_json(required["usage_ledger"])))
    if identity_errors:
        return None, {"status": "blocked", "missing": sorted(set(identity_errors)), "provider_calls": 0}
    cards = _read_json(required["evidence_cards"])
    timeline = _read_json(required["timeline"])
    organizer = _read_json(required["organizer"])
    metrics = _read_json(required["window_metrics"])
    if not isinstance(cards, list) or not isinstance(timeline, dict) or not isinstance(organizer, dict):
        return None, {"status": "blocked", "missing": ["replay_artifact_shape_invalid"], "provider_calls": 0}
    return {
        "project": project, "lineage_dir": lineage_dir, "attempt_dir": attempt_dir, "manifest": manifest,
        "source_text": source_text, "cards": cards, "timeline": timeline, "organizer": organizer, "metrics": metrics,
        "usage_ledger": _read_json(required["usage_ledger"]),
    }, {}


def replay_attempt(project: Path, attempt_dir: Path, *, apply: bool = False, expected_chapters: int = 10) -> dict[str, Any]:
    loaded, failure = _validate_and_load(project, attempt_dir, expected_chapters)
    if loaded is None:
        return {"contract": TOOL_VERSION, "apply": apply, **failure}
    replay_attempt_id = f"replay_{uuid.uuid4().hex[:12]}"
    state, receipt_missing = _rebuild_state(
        loaded["project"], loaded["lineage_dir"], loaded["attempt_dir"], loaded["manifest"], loaded["source_text"],
        loaded["cards"], loaded["timeline"], loaded["organizer"], loaded["metrics"], replay_attempt_id,
    )
    linked = w1_import._link_scene_events_from_provenance(state)
    state = {**state, **linked}
    payload, migration_status = w1_import._semantic_coverage_input(state)
    semantic = dict(compile_semantic_coverage(payload))
    base = {
        "contract": TOOL_VERSION, "apply": apply, "offline": True, "provider_calls": 0,
        "source_attempt_id": loaded["manifest"]["attempt_id"], "replay_attempt_id": replay_attempt_id,
        "lineage_id": loaded["manifest"]["lineage_id"], "expected_chapters": expected_chapters,
        "migration_status": migration_status, "receipt_missing": receipt_missing,
        "semantic_verdict": semantic["verdict"], "semantic_blocking_codes": [item["code"] for item in semantic["blocking_findings"]],
        "usage": {key: loaded["usage_ledger"].get(key) for key in ("actual_calls", "actual_total_tokens", "cost_usd", "model")},
    }
    if not apply:
        return {
            **base,
            "status": "dry_run"
            if not receipt_missing and semantic["verdict"] != "blocked"
            else "blocked",
        }

    replay_dir = loaded["lineage_dir"] / "attempts" / replay_attempt_id
    receipt_dir = replay_dir / "offline_replay_receipts"
    inbox_path = loaded["project"] / "system" / "inbox.json"
    replay_dir.mkdir(parents=True, exist_ok=False)
    receipt_dir.mkdir(parents=True, exist_ok=False)
    backups: list[dict[str, str]] = []
    for path in [loaded["attempt_dir"] / "manifest.json", loaded["attempt_dir"] / "evidence_cards.json", loaded["attempt_dir"] / "timeline_architecture.json", loaded["attempt_dir"] / "usage_ledger.json", inbox_path]:
        if path.is_file():
            target = receipt_dir / path.name
            shutil.copy2(path, target)
            backups.append({"source": _relative(loaded["project"], path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    receipt = {**base, "backup": backups, "receipt_path": _relative(loaded["project"], receipt_dir / "receipt.json")}
    _atomic_json(receipt_dir / "receipt.json", {**receipt, "phase": "prepared"})

    if receipt_missing or semantic["verdict"] == "blocked":
        result = {**receipt, "status": "blocked", "phase": "blocked"}
        _atomic_json(receipt_dir / "receipt.json", result)
        return result

    reviewed = asyncio.run(w1_import.node_review_import(state))
    written = asyncio.run(w1_import.node_write_to_project({**state, **reviewed}))
    result = {
        **receipt, "status": "applied" if written.get("status") != "blocked" else "blocked",
        "phase": "completed" if written.get("status") != "blocked" else "blocked",
        "proposal_receipt_count": len(written.get("proposals") or []),
        "review_status": (written.get("import_review_report") or {}).get("status"),
        "replay_attempt_dir": _relative(loaded["project"], replay_dir),
    }
    _atomic_json(receipt_dir / "receipt.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("attempt_dir", type=Path)
    parser.add_argument("--apply", action="store_true", help="create a backed-up pending replay package; default is no-write dry-run")
    parser.add_argument("--expected-chapters", type=int, default=10)
    args = parser.parse_args()
    result = replay_attempt(args.project, args.attempt_dir, apply=args.apply, expected_chapters=args.expected_chapters)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"dry_run", "applied"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
