#!/usr/bin/env python3
"""Reconcile links and safe World semantics in an accepted legacy W1 project.

The tool is deliberately offline and conservative.  It derives only links that
can be justified by source spans, evidence spans, or an exact entity-name
reference.  It never calls a provider, never accepts proposals, and keeps
ambiguous classification decisions in a review report instead of guessing.

Usage::

    python tools/w1_reconcile_accepted_semantics.py /path/to/project
    python tools/w1_reconcile_accepted_semantics.py /path/to/project --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sidecar.supervisor.pipeline_tools import repair_import_artifacts
from sidecar.supervisor.semantic_review import (
    assess_world_candidate,
    character_identity_index,
)


TOOL_VERSION = "w1-accepted-semantics-reconcile/v1"
DEFAULT_IMPORT_CONTAINERS = {
    "locations": "cont_import_locations",
    "organizations": "cont_import_organizations",
    "items": "cont_import_items",
    "cultivation_methods": "cont_import_cultivation_methods",
    "rules": "cont_import_rules",
    "culture": "cont_import_culture",
}
SKIP_WORLD_FILES = {"containers.json", "categories.json", "maps.json", "settings.json"}
_CULTIVATION_TOKENS = ("功法", "口诀", "法诀", "心法", "术法", "法术", "武学", "神功")
_ORGANIZATION_TOKENS = ("门", "宗", "派", "会", "盟", "帮", "堂")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json(value)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
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


def _relative(project: Path, path: Path) -> str:
    return path.relative_to(project).as_posix()


def _ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _union(existing: Any, additions: Iterable[str]) -> list[str]:
    values = _ids(existing)
    for item in additions:
        item = str(item)
        if item and item not in values:
            values.append(item)
    return values


def _span(value: dict[str, Any]) -> tuple[int, int] | None:
    raw = value.get("sourceSpan") or value.get("source_span")
    if not isinstance(raw, dict):
        return None
    start = raw.get("absolute_start", raw.get("start"))
    end = raw.get("absolute_end", raw.get("end"))
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        return None
    return start, end


def _overlap(left: tuple[int, int], right: tuple[int, int]) -> int:
    return max(0, min(left[1], right[1]) - max(left[0], right[0]))


def _strong_span_match(source: tuple[int, int], target: tuple[int, int]) -> bool:
    """Return true only for containment or a high-overlap legacy equivalence."""
    if target[0] <= source[0] and source[1] <= target[1]:
        return True
    overlap = _overlap(source, target)
    return overlap > 0 and overlap / (source[1] - source[0]) >= 0.85


def _all_json_files(directory: Path, *, skip: set[str] | None = None) -> list[Path]:
    return sorted(path for path in directory.glob("*.json") if path.name not in (skip or set()))


def _load_records(project: Path) -> tuple[dict[Path, Any], dict[str, dict[str, Any]]]:
    paths: list[Path] = []
    paths += _all_json_files(project / "entities" / "characters")
    paths += _all_json_files(project / "entities" / "timeline", skip={"branches.json"})
    paths += _all_json_files(project / "entities" / "world", skip=SKIP_WORLD_FILES)
    paths += sorted((project / "writing" / "scenes").glob("*.meta.json"))
    loaded = {path: _read_json(path) for path in paths}
    records: dict[str, dict[str, Any]] = {"characters": {}, "events": {}, "world": {}, "scenes": {}}
    for path, payload in loaded.items():
        if not isinstance(payload, dict) or not payload.get("id"):
            continue
        record_id = str(payload["id"])
        if "/characters/" in path.as_posix():
            records["characters"][record_id] = deepcopy(payload)
        elif "/timeline/" in path.as_posix():
            records["events"][record_id] = deepcopy(payload)
        elif "/world/" in path.as_posix():
            records["world"][record_id] = deepcopy(payload)
        elif path.name.endswith(".meta.json"):
            records["scenes"][record_id] = deepcopy(payload)
    return loaded, records


def _evidence_spans(project: Path, records: dict[str, dict[str, Any]]) -> dict[str, list[tuple[int, int]]]:
    """Map canonical IDs to trusted evidence spans from all local W1 runs."""
    result: dict[str, list[tuple[int, int]]] = {}
    known = {record_id for group in records.values() for record_id in group}
    for cards_path in sorted((project / "system" / "imports").glob("**/evidence_cards.json")):
        try:
            cards = _read_json(cards_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(cards, list):
            continue
        for card in cards:
            if not isinstance(card, dict):
                continue
            candidate_ids = [str(item) for item in card.get("candidate_ids") or []]
            candidate_ids += [str(card.get(key) or "") for key in ("entity_id", "entityId")]
            raw = card.get("raw") if isinstance(card.get("raw"), dict) else {}
            candidate_ids += [str(raw.get(key) or "") for key in ("canonical_id", "event_id", "id")]
            span = _span({"source_span": card.get("source_span")})
            if not span:
                continue
            for candidate_id in candidate_ids:
                if candidate_id in known:
                    result.setdefault(candidate_id, []).append(span)
    return {key: sorted(set(value)) for key, value in result.items()}


def _container_ids(project: Path) -> dict[str, str]:
    path = project / "entities" / "world" / "containers.json"
    values = _read_json(path) if path.is_file() else []
    by_key = dict(DEFAULT_IMPORT_CONTAINERS)
    if not isinstance(values, list):
        return by_key
    for container in values:
        if not isinstance(container, dict):
            continue
        container_id = str(container.get("id") or "")
        key = str(container.get("importCategoryKey") or "")
        if container_id and key:
            by_key[key] = container_id
    return by_key


def _world_reclassification(item: dict[str, Any], containers: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return a high-confidence folder move, or an explicit review item."""
    name = str(item.get("name") or "").strip()
    description = str(item.get("description") or "")
    category = str(item.get("category") or item.get("type") or "")
    name_is_method = any(token in name for token in _CULTIVATION_TOKENS) or name.endswith(("功", "劲"))
    description_explicitly_calls_method = any(
        phrase in description for phrase in ("一套功法", "一门功法", "修炼口诀", "修炼法诀", "武学功法")
    )
    if name_is_method or description_explicitly_calls_method:
        return ({"category": "cultivation_method", "type": "cultivation_method", "containerId": containers["cultivation_methods"]}, None)
    if name.endswith("会") and any(token in description for token in ("机构", "议事", "长老", "决策")):
        return ({"category": "organization", "type": "organization", "containerId": containers["organizations"]}, None)
    if name.endswith("堂") and any(token in description for token in ("分堂", "门内", "机构", "弟子")):
        return ({"category": "organization", "type": "organization", "containerId": containers["organizations"]}, None)
    if category in {"organization", "faction", "location", "cultivation_method", "rule", "system", "item", "artifact", "culture", "concept"}:
        return None, None
    return None, {"itemId": item.get("id"), "name": name, "reason": "unsupported_or_low_confidence_category", "currentCategory": category}


def _referenced_names(record: dict[str, Any]) -> str:
    return "\n".join(str(record.get(key) or "") for key in ("title", "summary", "description", "notes"))


def _apply_semantic_relocation(records: dict[str, dict[str, Any]], evidence: dict[str, list[tuple[int, int]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Use the same relocation contract as the reviewer, only in memory."""
    character_index = character_identity_index(records["characters"])
    state = {
        "entity_registry": {
            "characters": deepcopy(records["characters"]),
            "world": {item.get("name"): item.get("category") for item in records["world"].values()},
            "world_detailed": deepcopy(records["world"]),
        },
        "minor_repair_log": [],
        "supervisor_log": [],
        "quarantine_candidates": [],
        "applied_relocation_plan_ids": [],
    }
    actions: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for item_id, item in records["world"].items():
        candidate = dict(item)
        candidate["source_spans"] = [{"absolute_start": start, "absolute_end": end} for start, end in evidence.get(item_id, [])]
        assessment = assess_world_candidate(
            candidate_id=item_id,
            raw_name=str(item.get("name") or item_id),
            candidate=candidate,
            character_index=character_index,
            category=str(item.get("category") or item.get("type") or ""),
            container_id=str(item.get("containerId") or "") or None,
        )
        plan = assessment.get("relocation_plan")
        if isinstance(plan, dict):
            actions.append({"action_type": "relocate", "target_entity_ids": [item_id], "proposed_operations": [{"op": "relocate_world_item", "relocation_plan": plan}]})
        elif assessment["ledger"]["status"] == "quarantined":
            quarantined.append({"itemId": item_id, "name": item.get("name"), "reasonCodes": assessment["ledger"]["reason_codes"], "decision": assessment["decision"]})
    if actions:
        import asyncio
        repaired = asyncio.run(repair_import_artifacts(state, actions))
        records["characters"].clear()
        records["characters"].update(repaired["entity_registry"]["characters"])
        records["world"].clear()
        records["world"].update(repaired["entity_registry"]["world_detailed"])
    return quarantined, actions


def _rebuild_links(records: dict[str, dict[str, Any]], evidence: dict[str, list[tuple[int, int]]]) -> dict[str, int]:
    events, scenes, worlds = records["events"], records["scenes"], records["world"]
    added = {"eventScene": 0, "eventWorld": 0, "sceneWorld": 0}
    scene_spans = {scene_id: _span(scene) for scene_id, scene in scenes.items()}
    event_spans = {event_id: _span(event) for event_id, event in events.items()}

    def attach(left: dict[str, Any], field: str, right_id: str, inverse: dict[str, Any], inverse_field: str, bucket: str) -> None:
        previous = _ids(left.get(field))
        left[field] = _union(previous, [right_id])
        inverse[inverse_field] = _union(inverse.get(inverse_field), [str(left["id"])])
        if right_id not in previous:
            added[bucket] += 1

    for event_id, event in events.items():
        source = event_spans[event_id]
        if source:
            matches = [(scene_id, scene_span) for scene_id, scene_span in scene_spans.items() if scene_span and _strong_span_match(source, scene_span)]
            if matches:
                # A boundary event can overlap two neighbouring scenes; retain only the best one.
                best_id = max(matches, key=lambda value: _overlap(source, value[1]))[0]
                attach(event, "linkedSceneIds", best_id, scenes[best_id], "linkedEventIds", "eventScene")

    for world_id, world in worlds.items():
        world_spans = evidence.get(world_id, [])
        name = str(world.get("name") or "").strip()
        safe_name = len(name) >= 2 and not name.endswith(("门主", "堂主", "师兄", "师姐"))
        for event_id, event in events.items():
            matches_span = any(event_spans[event_id] and _strong_span_match(span, event_spans[event_id]) for span in world_spans)
            exact_name = safe_name and name in _referenced_names(event)
            if matches_span or exact_name:
                attach(event, "linkedWorldItemIds", world_id, world, "linkedEventIds", "eventWorld")
                event["locationIds"] = _union(event.get("locationIds"), [world_id]) if world.get("category") == "location" else _ids(event.get("locationIds"))
        for scene_id, scene in scenes.items():
            matches_span = any(scene_spans[scene_id] and _strong_span_match(span, scene_spans[scene_id]) for span in world_spans)
            exact_name = safe_name and name in _referenced_names(scene)
            if matches_span or exact_name:
                attach(scene, "linkedWorldItemIds", world_id, world, "linkedSceneIds", "sceneWorld")
    return added


def _changes(loaded: dict[Path, Any], records: dict[str, dict[str, Any]]) -> dict[Path, Any | None]:
    """Return canonical writes; ``None`` means a relocated World file is deleted."""
    target: dict[Path, Any | None] = {}
    all_records = {record_id: record for group in records.values() for record_id, record in group.items()}
    for path, original in loaded.items():
        if not isinstance(original, dict):
            continue
        record_id = str(original.get("id") or "")
        if record_id not in all_records:
            if "/entities/world/" in path.as_posix():
                target[path] = None
            continue
        updated = all_records[record_id]
        if _canonical_json(original) != _canonical_json(updated):
            target[path] = updated
    return target


def reconcile_project(project: Path, *, apply: bool = False) -> dict[str, Any]:
    project = project.expanduser().resolve()
    required = [project / "entities", project / "writing" / "scenes", project / "entities" / "world"]
    if not project.is_dir() or any(not path.exists() for path in required):
        raise ValueError("project must contain entities/, entities/world/, and writing/scenes/")
    loaded, records = _load_records(project)
    evidence = _evidence_spans(project, records)
    containers = _container_ids(project)
    quarantined, relocation_actions = _apply_semantic_relocation(records, evidence)
    quarantined_ids = {str(item.get("itemId") or "") for item in quarantined}
    reclassifications: list[dict[str, Any]] = []
    for item_id, item in records["world"].items():
        item.setdefault("folderId", item.get("containerId"))
        update, review = _world_reclassification(item, containers)
        if review:
            quarantined.append(review)
        if update and item_id not in quarantined_ids:
            before = {key: item.get(key) for key in update}
            item.update(update)
            item["folderId"] = item["containerId"]
            if before != update:
                reclassifications.append({"itemId": item_id, "name": item.get("name"), "before": before, "after": update})
    link_counts = _rebuild_links(records, evidence)
    mutations = _changes(loaded, records)
    report = {
        "toolVersion": TOOL_VERSION,
        "project": str(project),
        "dryRun": not apply,
        "records": {key: len(value) for key, value in records.items()},
        "plannedMutations": [
            {"path": _relative(project, path), "operation": "delete" if value is None else "write"}
            for path, value in sorted(mutations.items())
        ],
        "linkAdditions": link_counts,
        "relocationPlansApplied": len(relocation_actions),
        "reclassifications": reclassifications,
        "quarantine": quarantined,
        "evidenceBoundEntities": len(evidence),
    }
    if not apply or not mutations:
        report["status"] = "dry_run" if not apply else "noop"
        return report

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    migration_root = project / "system" / "migrations" / "w1-accepted-semantics" / stamp
    backup_root = migration_root / "backup"
    backup_manifest: list[dict[str, str]] = []
    for path in sorted(mutations):
        relative = path.relative_to(project)
        backup_path = backup_root / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        backup_manifest.append({"path": relative.as_posix(), "sha256": _sha256(path.read_bytes())})
    receipt_path = migration_root / "receipt.json"
    prepared_receipt = {
        "toolVersion": TOOL_VERSION,
        "migrationId": stamp,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "phase": "prepared",
        "project": str(project),
        "backupRoot": _relative(project, backup_root),
        "backedUp": backup_manifest,
        "planned": report,
    }
    # The durable intent is written before the first canonical file changes.
    _atomic_write_json(receipt_path, prepared_receipt)
    for path, value in mutations.items():
        if value is None:
            path.unlink()
        else:
            _atomic_write_json(path, value)
    receipt = {
        "toolVersion": TOOL_VERSION,
        "migrationId": stamp,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "phase": "completed",
        "project": str(project),
        "backupRoot": _relative(project, backup_root),
        "backedUp": backup_manifest,
        "written": [
            {"path": _relative(project, path), "operation": "deleted" if value is None else "written", "sha256": _sha256(path.read_bytes()) if value is not None else None}
            for path, value in sorted(mutations.items())
        ],
        "report": report,
    }
    _atomic_write_json(receipt_path, receipt)
    _atomic_write_json(migration_root / "review.json", report)
    report.update({"status": "applied", "migrationRoot": _relative(project, migration_root)})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely reconcile accepted legacy W1 semantics without APIs")
    parser.add_argument("project", type=Path)
    parser.add_argument("--apply", action="store_true", help="write an auditable migration; otherwise only print a dry-run")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)
    try:
        report = reconcile_project(args.project, apply=args.apply)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"W1 accepted-project reconciliation: {report['status']}")
        print(json.dumps({key: report[key] for key in ("records", "plannedMutations", "linkAdditions", "relocationPlansApplied", "quarantine")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
