#!/usr/bin/env python3
"""Read-only semantic quality audit for accepted W1 project directories.

The audit deliberately reports findings instead of repairing data.  This makes
it safe to run against a user's canonical project or a copied benchmark.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    entity_type: str | None = None
    entity_id: str | None = None
    path: str | None = None
    details: dict[str, Any] | None = None


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _records(root: Path, relative: str, singular: str) -> list[tuple[Path, dict[str, Any]]]:
    directory = root / relative
    result: list[tuple[Path, dict[str, Any]]] = []
    if not directory.is_dir():
        return result
    index_files = {
        "branches.json", "containers.json", "categories.json", "settings.json",
        "maps.json", "character-tags.json", "relationships.json",
    }
    for path in sorted(directory.glob("*.json")):
        if path.name in index_files or (path.name.endswith(".meta.json") and relative != "writing/scenes"):
            continue
        value = _json(path, None)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and item.get("id"):
                result.append((path, item))
    return result


def _ids(value: Any) -> Iterable[str]:
    if isinstance(value, list):
        return (str(item) for item in value if item)
    return (str(value),) if value else ()


def _norm(value: Any) -> str:
    return re.sub(r"[\s·・]", "", str(value or "")).casefold()


def _finding(findings: list[Finding], code: str, severity: str, message: str, *, path: Path | None = None, entity_type: str | None = None, entity_id: str | None = None, details: dict[str, Any] | None = None) -> None:
    findings.append(Finding(code, severity, message, entity_type, entity_id, str(path) if path else None, details))


def audit_project(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    findings: list[Finding] = []
    if not root.is_dir():
        _finding(findings, "project_missing", "error", f"Project does not exist: {root}")
        return _result(root, findings, {})

    characters = _records(root, "entities/characters", "character")
    events = _records(root, "entities/timeline", "event")
    scenes = _records(root, "writing/scenes", "scene")
    worlds = _records(root, "entities/world", "world_item")
    containers_path = root / "entities/world/containers.json"
    containers_value = _json(containers_path, [])
    containers = [(containers_path, item) for item in (containers_value if isinstance(containers_value, list) else []) if isinstance(item, dict) and item.get("id")]
    branches_value = _json(root / "entities/timeline/branches.json", [])
    branches = {
        str(item.get("id"))
        for item in (branches_value if isinstance(branches_value, list) else [])
        if isinstance(item, dict) and item.get("id")
    }
    characters_by_id = {item["id"]: item for _, item in characters}
    events_by_id = {item["id"]: item for _, item in events}
    scenes_by_id = {item["id"]: item for _, item in scenes}
    worlds_by_id = {item["id"]: item for _, item in worlds}
    containers_by_id = {item["id"]: item for _, item in containers}

    # A world item containing a known character name plus a role/title is a
    # cross-module candidate, not an organization.  This catches 王六 and OCR
    # variants such as 王6 without attempting a mutation.
    character_names = [(cid, _norm(item.get("name"))) for cid, item in characters_by_id.items() if item.get("name")]
    title_words = ("门主", "堂主", "护法", "长老", "弟子", "师兄", "师姐", "掌门", "教主", "首领")
    for path, item in worlds:
        name = _norm(item.get("name"))
        for cid, character_name in character_names:
            if character_name and character_name in name and name != character_name and any(word in name for word in title_words):
                _finding(findings, "world_person_title_contamination", "error", f"World item {item.get('name')} combines character {characters_by_id[cid].get('name')} with a person title/role", path=path, entity_type="world_item", entity_id=item["id"], details={"characterId": cid, "characterName": characters_by_id[cid].get("name")})
                break

    org_words = ("门", "宗", "帮", "派", "教", "会", "盟", "堂")
    place_words = ("山", "峰", "谷", "镇", "城", "村", "院", "阁", "楼", "崖", "洞", "关", "门")
    cultivation_words = ("功", "诀", "术", "法", "经", "劲", "境", "丹")
    for path, item in worlds:
        container = containers_by_id.get(item.get("containerId") or item.get("parentId"), {})
        container_name = str(container.get("name") or "")
        category = str(item.get("category") or item.get("type") or "")
        name = str(item.get("name") or "")
        if ("组织" in container_name or category in {"organization", "faction"}) and any(token in name for token in place_words) and not any(token in name for token in org_words):
            _finding(findings, "world_location_in_organization", "error", f"Location-like world item {name} is placed in organization container {container_name}", path=path, entity_type="world_item", entity_id=item["id"])
        if ("功法" in container_name or "修炼" in container_name) and category in {"organization", "location"} and not any(token in name for token in cultivation_words):
            _finding(findings, "world_malformed_cultivation_placement", "error", f"Non-cultivation item {name} is placed in cultivation container {container_name}", path=path, entity_type="world_item", entity_id=item["id"])
        if category in {"organization", "faction"} and any(token in name for token in place_words) and "堂" not in name and "门" not in name:
            _finding(findings, "world_category_location_mismatch", "error", f"Organization category conflicts with location-like name {name}", path=path, entity_type="world_item", entity_id=item["id"])

    refs: list[tuple[str, str, dict[str, Any], Path, str, str]] = []
    for path, item in characters:
        refs += [("character", item["id"], item, path, field, target) for field, target in (("linkedEventIds", "event"), ("linkedSceneIds", "scene"), ("linkedWorldItemIds", "world_item")) for _ in [0] for _id in _ids(item.get(field)) for target in [_id]]
    for path, item in events:
        refs += [("event", item["id"], item, path, field, target) for field, target_kind in (("participantCharacterIds", "character"), ("linkedSceneIds", "scene"), ("linkedWorldItemIds", "world_item"), ("locationIds", "world_item")) for target in _ids(item.get(field))]
    for path, item in scenes:
        refs += [("scene", item["id"], item, path, field, target) for field, target_kind in (("linkedCharacterIds", "character"), ("linkedEventIds", "event"), ("linkedWorldItemIds", "world_item")) for target in _ids(item.get(field))]
    for path, item in worlds:
        refs += [("world_item", item["id"], item, path, field, target) for field, target_kind in (("linkedCharacterIds", "character"), ("linkedEventIds", "event"), ("linkedSceneIds", "scene")) for target in _ids(item.get(field))]
    lookup = {"character": characters_by_id, "event": events_by_id, "scene": scenes_by_id, "world_item": worlds_by_id}
    for source_type, source_id, _, path, field, target in refs:
        target_kind = {"participantCharacterIds": "character", "linkedCharacterIds": "character", "linkedEventIds": "event", "linkedSceneIds": "scene", "linkedWorldItemIds": "world_item", "locationIds": "world_item"}[field]
        if target not in lookup[target_kind]:
            _finding(findings, "broken_reference", "error", f"{source_type} {source_id} field {field} references missing {target_kind} {target}", path=path, entity_type=source_type, entity_id=source_id, details={"field": field, "targetId": target})

    empty_events = 0
    for path, item in events:
        if not list(_ids(item.get("linkedSceneIds"))) and not list(_ids(item.get("linkedWorldItemIds"))) and not list(_ids(item.get("locationIds"))):
            empty_events += 1
            _finding(findings, "event_without_scene_or_world_link", "warning", f"Event {item.get('title') or item['id']} has no scene or world/location link", path=path, entity_type="event", entity_id=item["id"])
    empty_scenes = 0
    for path, item in scenes:
        if not list(_ids(item.get("linkedEventIds"))) and not list(_ids(item.get("linkedWorldItemIds"))):
            empty_scenes += 1
            _finding(findings, "scene_without_event_or_world_link", "warning", f"Scene {item.get('title') or item['id']} has no event or world link", path=path, entity_type="scene", entity_id=item["id"])

    for path, item in worlds:
        container_id = item.get("containerId") or item.get("parentId")
        if container_id and container_id not in containers_by_id:
            _finding(findings, "broken_container_reference", "error", f"World item {item.get('name')} references missing container {container_id}", path=path, entity_type="world_item", entity_id=item["id"])
    for path, item in containers:
        parent_id = item.get("parentId")
        if parent_id and parent_id not in containers_by_id:
            _finding(findings, "broken_folder_reference", "error", f"Folder {item.get('name')} references missing parent {parent_id}", path=path, entity_type="world_container", entity_id=item["id"])
    summary = {"characters": len(characters), "events": len(events), "scenes": len(scenes), "worldItems": len(worlds), "worldContainers": len(containers), "eventsWithoutLinks": empty_events, "scenesWithoutLinks": empty_scenes, "branchesKnown": len(branches)}
    return _result(root, findings, summary)


def _result(root: Path, findings: list[Finding], summary: dict[str, Any]) -> dict[str, Any]:
    return {"project": str(root), "readOnly": True, "summary": summary, "thresholds": {"errors": 0}, "findings": [asdict(item) for item in findings], "counts": {"error": sum(item.severity == "error" for item in findings), "warning": sum(item.severity == "warning" for item in findings)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit accepted W1 project semantics without modifying data")
    parser.add_argument("project", type=Path)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args(argv)
    result = audit_project(args.project)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"W1 Semantic Quality Audit: {result['project']}")
        print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
        for finding in result["findings"]:
            print(f"[{finding['severity'].upper()}] {finding['code']}: {finding['message']}")
    return 1 if args.fail_on_threshold and result["counts"]["error"] > result["thresholds"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
