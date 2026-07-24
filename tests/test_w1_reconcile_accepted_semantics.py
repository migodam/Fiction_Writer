"""Tests for the offline repair of accepted legacy W1 project data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.w1_reconcile_accepted_semantics import reconcile_project


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _span(start: int, end: int) -> dict[str, int]:
    return {"absolute_start": start, "absolute_end": end}


def _fixture(root: Path) -> dict[str, Path]:
    character = root / "entities/characters/char_wang.json"
    title_world = root / "entities/world/world_title.json"
    cultivation_world = root / "entities/world/world_method.json"
    ambiguous_world = root / "entities/world/world_council.json"
    event = root / "entities/timeline/event_1.json"
    scene = root / "writing/scenes/scene_1.meta.json"
    _write(character, {"id": "char_wang", "name": "王六", "aliases": [], "evidenceRefs": []})
    _write(title_world, {
        "id": "world_title", "name": "正门主王六", "category": "organization", "type": "organization",
        "containerId": "cont_org", "linkedEventIds": [], "linkedSceneIds": [], "linkedCharacterIds": [],
    })
    _write(cultivation_world, {
        "id": "world_method", "name": "无名口诀", "description": "一套修炼口诀", "category": "system", "type": "system",
        "containerId": "cont_rules", "linkedEventIds": [], "linkedSceneIds": [], "linkedCharacterIds": [],
    })
    _write(ambiguous_world, {
        "id": "world_council", "name": "长老会", "description": "待人工确认", "category": "rule", "type": "rule",
        "containerId": "cont_rules", "linkedEventIds": [], "linkedSceneIds": [], "linkedCharacterIds": [],
    })
    _write(event, {
        "id": "event_1", "title": "学习无名口诀", "summary": "王六传授无名口诀", "sourceSpan": _span(10, 20),
        "linkedSceneIds": [], "linkedWorldItemIds": [], "locationIds": [],
    })
    _write(scene, {
        "id": "scene_1", "title": "第一章", "summary": "王六学习无名口诀", "sourceSpan": _span(0, 100),
        "linkedEventIds": [], "linkedWorldItemIds": [],
    })
    _write(root / "entities/world/containers.json", [
        {"id": "cont_org", "importCategoryKey": "organizations"},
        {"id": "cont_rules", "importCategoryKey": "rules"},
        {"id": "cont_cultivation", "importCategoryKey": "cultivation_methods"},
    ])
    _write(root / "system/imports/legacy/evidence_cards.json", [
        {"candidate_ids": ["world_method"], "source_span": _span(10, 20)},
    ])
    return {"character": character, "title_world": title_world, "cultivation_world": cultivation_world, "ambiguous_world": ambiguous_world, "event": event, "scene": scene}


def test_dry_run_does_not_mutate_the_accepted_project(tmp_path: Path):
    paths = _fixture(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    report = reconcile_project(tmp_path)

    assert report["status"] == "dry_run"
    assert report["plannedMutations"]
    assert {name: path.read_bytes() for name, path in paths.items()} == before
    assert not (tmp_path / "system/migrations").exists()


def test_apply_rebuilds_inverse_links_relocates_title_person_and_is_idempotent(tmp_path: Path):
    paths = _fixture(tmp_path)

    report = reconcile_project(tmp_path, apply=True)

    assert report["status"] == "applied"
    assert not paths["title_world"].exists()
    character = json.loads(paths["character"].read_text(encoding="utf-8"))
    assert "正门主王六" in character["aliases"]
    assert character["role"] == "正门主"
    world = json.loads(paths["cultivation_world"].read_text(encoding="utf-8"))
    assert world["category"] == "cultivation_method"
    assert world["containerId"] == "cont_cultivation"
    assert world["folderId"] == "cont_cultivation"
    event = json.loads(paths["event"].read_text(encoding="utf-8"))
    scene = json.loads(paths["scene"].read_text(encoding="utf-8"))
    assert event["linkedSceneIds"] == ["scene_1"]
    assert scene["linkedEventIds"] == ["event_1"]
    assert event["linkedWorldItemIds"] == ["world_method"]
    assert scene["linkedWorldItemIds"] == ["world_method"]
    assert world["linkedEventIds"] == ["event_1"]
    assert world["linkedSceneIds"] == ["scene_1"]
    ambiguous = json.loads(paths["ambiguous_world"].read_text(encoding="utf-8"))
    assert ambiguous["category"] == "rule"
    assert any(item.get("itemId") == "world_council" for item in report["quarantine"])
    migration = tmp_path / report["migrationRoot"]
    receipt = json.loads((migration / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["phase"] == "completed"
    assert receipt["backedUp"]
    assert (migration / "backup/entities/world/world_title.json").is_file()

    content_hash = hashlib.sha256(paths["character"].read_bytes()).hexdigest()
    second = reconcile_project(tmp_path, apply=True)
    assert second["status"] == "noop"
    assert hashlib.sha256(paths["character"].read_bytes()).hexdigest() == content_hash
