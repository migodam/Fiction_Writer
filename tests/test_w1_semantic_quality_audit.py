from __future__ import annotations

import json

from tools import w1_semantic_quality_audit as audit


def write_json(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def make_project(tmp_path, *, contaminated=True, broken=False):
    write_json(tmp_path, "project.json", {"metadata": {"locale": "zh-CN"}})
    write_json(tmp_path, "entities/world/containers.json", [{"id": "orgs", "name": "门派组织", "type": "notebook"}, {"id": "places", "name": "地理位置", "type": "map"}, {"id": "cultivation", "name": "功法与术法", "type": "notebook"}])
    write_json(tmp_path, "entities/characters/c1.json", {"id": "c1", "name": "王六", "linkedEventIds": ["missing"] if broken else []})
    world = [{"id": "w1", "name": "青牛镇", "type": "location", "category": "location", "containerId": "places", "linkedEventIds": []}, {"id": "w2", "name": "无名口诀", "type": "cultivation_method", "category": "cultivation_method", "containerId": "cultivation"}]
    if contaminated:
        world.append({"id": "w3", "name": "正门主王六", "type": "organization", "category": "organization", "containerId": "orgs"})
    if broken:
        world.append({"id": "w4", "name": "坏容器", "type": "location", "category": "location", "containerId": "gone"})
    write_json(tmp_path, "entities/world/world.json", world)
    write_json(tmp_path, "entities/timeline/event_1.json", {"id": "e1", "title": "测试事件", "linkedSceneIds": [], "linkedWorldItemIds": [], "locationIds": []})
    write_json(tmp_path, "writing/scenes/scene_1.meta.json", {"id": "s1", "title": "测试场景", "linkedEventIds": [], "linkedWorldItemIds": []})
    return tmp_path


def test_detects_person_title_world_contamination(tmp_path):
    result = audit.audit_project(make_project(tmp_path))
    codes = {item["code"] for item in result["findings"]}
    assert "world_person_title_contamination" in codes
    assert result["readOnly"] is True


def test_clean_project_has_no_person_or_placement_errors(tmp_path):
    result = audit.audit_project(make_project(tmp_path, contaminated=False))
    assert result["counts"]["error"] == 0
    assert result["summary"]["branchesKnown"] == 0


def test_detects_location_name_in_organization_without_crashing(tmp_path):
    project = make_project(tmp_path, contaminated=False)
    write_json(
        project,
        "entities/world/world_location.json",
        {"id": "w_location", "name": "青牛镇", "type": "organization", "category": "organization", "containerId": "orgs"},
    )
    result = audit.audit_project(project)
    assert "world_category_location_mismatch" in {item["code"] for item in result["findings"]}


def test_detects_broken_refs_and_bad_container_without_mutation(tmp_path):
    project = make_project(tmp_path, broken=True)
    before = (project / "entities/world/world.json").read_text(encoding="utf-8")
    result = audit.audit_project(project)
    codes = {item["code"] for item in result["findings"]}
    assert {"broken_reference", "broken_container_reference"} <= codes
    assert (project / "entities/world/world.json").read_text(encoding="utf-8") == before


def test_cli_json_and_fail_on_threshold(tmp_path, capsys):
    code = audit.main([str(make_project(tmp_path)), "--format", "json", "--fail-on-threshold"])
    output = json.loads(capsys.readouterr().out)
    assert code == 1
    assert output["readOnly"] is True
    assert output["counts"]["error"] >= 1
