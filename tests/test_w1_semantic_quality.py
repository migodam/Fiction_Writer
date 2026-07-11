"""Synthetic semantic contracts for the W1 import compiler. No network/LLM calls."""
from sidecar.supervisor.organizer import organize_project_content
from sidecar.workflows.w1_import import (
    _entity_merge_decision,
    _normalize_character_tag,
    _relationship_dedupe_key,
    _relationship_ontology,
)


def _organizer_input(world_candidates):
    return {
        "characters": {"char_han": {"canonical_name": "韩立", "aliases": ["二愣子"]}},
        "events": [], "relationships": [], "world_candidates": world_candidates,
        "manuscript_notes": [], "timeline_architecture": {}, "project_digest": {}, "source_language": "zh",
    }


def test_han_li_merge_decision_preserves_field_evidence_and_conflicts():
    existing = {
        "id": "char_han", "aliases": ["二愣子"], "background": "韩家村少年。",
        "experience": [{"chapter": 1, "fact": "入七玄门"}], "personality_traits": ["谨慎"],
        "notes": ["既有笔记"], "physical_description": "相貌平常", "speech_style": "寡言",
        "arc_notes": "求仙起点", "importConfidence": 0.8,
    }
    incoming = {
        "canonical_name": "韩立", "aliases": ["二愣子", "小韩"], "background": "出身韩家村，拜入七玄门。",
        "experience": [{"chapter": 1, "fact": "入七玄门"}, {"chapter": 2, "fact": "得长春功"}],
        "personality_traits": ["谨慎", "坚韧"], "notes": ["新证据"], "physical_description": "相貌平常",
        "speech_style": "少言谨慎", "arc_notes": "踏上修仙路", "confidence": 0.92,
    }
    decision = _entity_merge_decision(existing, incoming, "import_han")
    assert decision["fields"]["aliases"]["value"] == ["二愣子", "小韩", "韩立"]
    assert len(decision["fields"]["experience"]["value"]) == 2
    assert "坚韧" in decision["fields"]["personality_traits"]["value"]
    assert decision["fields"]["confidence"]["value"] == 0.92
    assert {item["field"] for item in decision["conflicts"]} >= {"background", "speech_style", "arc_notes"}


def test_chinese_tag_normalization_translates_or_rejects_without_blank_name():
    translated, rejection = _normalize_character_tag({"name": "Protagonist"}, "zh")
    assert rejection is None and translated["name"] == "主角" and translated["sourceName"] == "Protagonist"
    rejected, rejection = _normalize_character_tag({"name": "Unmapped Editorial Label"}, "zh")
    assert rejected is None and rejection["reason"] == "unmapped_english_tag_for_chinese_source"


def test_relationship_ontology_preserves_direction_and_demotes_false_labels():
    mentor = _relationship_ontology({"type": "师徒", "category": "mentor_disciple"}, "zh")
    assert mentor["type"] == "师徒关系" and mentor["ontologyDirection"] == "directed"
    assert _relationship_dedupe_key("master", "student", mentor) != _relationship_dedupe_key("student", "master", mentor)
    alliance = _relationship_ontology({"type": "盟友", "category": "alliance"}, "zh")
    assert _relationship_dedupe_key("a", "b", alliance) == _relationship_dedupe_key("b", "a", alliance)
    assert _relationship_ontology({"type": "解惑", "category": "mentor_disciple"}, "zh") is None
    assert _relationship_ontology({"type": "冷冰冰的师兄", "category": "rivalry"}, "zh") is None


def test_world_routes_once_to_stable_notebook_targets_and_excludes_contamination():
    out = organize_project_content(_organizer_input({
        "七玄门": {"category": "location", "description": "修仙门派"},
        "神手谷": {"category": "organization", "description": "山谷"},
        "长春功": {"category": "concept", "description": "修炼功法"},
        "人物关系图": {"category": "concept"}, "记名弟子": {"category": "cultivation_method"},
    }))
    items = {item["name"]: item for item in out["world_items"]}
    assert items["七玄门"]["category"] == "organization"
    assert items["神手谷"]["category"] == "location"
    assert items["长春功"]["container_key"] == "cultivation_methods"
    assert all(item["containerId"] == f"world_container_{item['container_key']}" for item in items.values())
    assert {container["id"] for container in out["world_containers"]} == {item["containerId"] for item in items.values()}
    assert {item["name"] for item in out["excluded_items"]} >= {"人物关系图", "记名弟子"}
