"""Regression coverage for W1 semantic review and cross-module relocation."""
from __future__ import annotations

import asyncio

from sidecar.supervisor.organizer import organize_project_content
from sidecar.supervisor.pipeline_tools import repair_import_artifacts
from sidecar.supervisor.semantic_review import (
    normalize_candidate_name,
    parse_person_title_expression,
)


def _input(**overrides):
    value = {
        "characters": {}, "events": [], "relationships": [],
        "world_candidates": {}, "manuscript_notes": [],
        "timeline_architecture": {}, "project_digest": {}, "source_language": "zh",
    }
    value.update(overrides)
    return value


def test_normalizes_ocr_digits_and_extracts_title_plus_name():
    assert normalize_candidate_name("王6") == "王六"
    assert parse_person_title_expression("正门主王6") == ("正门主", "王六")
    assert parse_person_title_expression("王大门主") == ("大门主", "王")


def test_organizer_quarantines_unknown_and_ambiguous_world_candidates():
    output = organize_project_content(_input(world_candidates={
        "正门": {"category": "organization", "confidence": 0.95},
        "主网六": {"category": "organization", "confidence": 0.20},
        "供奉堂": {"category": "organization", "confidence": 0.75},
        "七玄门": {"category": "organization", "confidence": 0.95},
        "长老会": {"category": "organization", "confidence": 0.95, "description": "七玄门长老组成的议事机构"},
    }))

    items = {item["name"]: item for item in output["world_items"]}
    quarantined = {item["raw_name"]: item for item in output["quarantine_items"]}
    assert items["七玄门"]["container_key"] == "organizations"
    assert items["长老会"]["container_key"] == "organizations"
    assert quarantined["正门"]["status"] == "quarantined"
    assert quarantined["主网六"]["status"] == "quarantined"
    assert quarantined["供奉堂"]["status"] == "quarantined"


def test_organizer_creates_deterministic_relocation_for_title_name_alias():
    output = organize_project_content(_input(
        characters={"char_wang": {"name": "王六", "aliases": ["王6"]}},
        world_candidates={"正门主王六": {"id": "world_wang", "category": "organization", "confidence": 0.91, "evidence_refs": ["ev_1"]}},
    ))

    assert output["world_items"] == []
    assert output["excluded_items"][0]["reason"] == "person_title_mixed"
    plan = output["relocation_plans"][0]
    assert plan["target_entity_id"] == "char_wang"
    assert plan["field_merge_plan"]["aliases"] == ["正门主王六"]
    assert plan["field_merge_plan"]["role"] == "正门主"
    assert plan["deterministic"] is True


def test_relocation_repair_is_idempotent_and_preserves_character_evidence():
    state = {
        "entity_registry": {
            "characters": {"char_wang": {"name": "王六", "aliases": ["王6"], "evidence_refs": ["old"]}},
            "world": {"正门主王六": "organization"},
            "world_detailed": {"world_wang": {"entity_id": "world_wang", "name": "正门主王六", "category": "organization", "evidence_refs": ["ev_1"]}},
        },
        "minor_repair_log": [], "supervisor_log": [],
    }
    plan = {
        "plan_id": "relocate_wang", "source_candidate_id": "world_wang",
        "source_kind": "world_item", "target_kind": "character", "target_entity_id": "char_wang",
        "field_merge_plan": {"aliases": ["正门主王六", "王六"], "role": "正门主", "evidence_refs": ["ev_1"]},
        "status": "approved", "deterministic": True,
    }
    action = {"action_type": "relocate", "target_entity_ids": ["world_wang"], "description": "move", "deterministic": True, "proposed_operations": [{"op": "relocate_world_item", "relocation_plan": plan}]}

    result = asyncio.run(repair_import_artifacts(state, [action]))
    again = asyncio.run(repair_import_artifacts(result, [action]))
    character = again["entity_registry"]["characters"]["char_wang"]
    assert "world_wang" not in again["entity_registry"]["world_detailed"]
    assert "正门主王六" not in again["entity_registry"]["world"]
    assert character["aliases"].count("正门主王六") == 1
    assert character["role"] == "正门主"
    assert character["evidence_refs"] == ["old", "ev_1"]
    assert again["applied_relocation_plan_ids"] == ["relocate_wang"]


def test_unsafe_relocation_stays_quarantined():
    state = {"entity_registry": {"characters": {}, "world": {}, "world_detailed": {"w": {"entity_id": "w", "name": "主网六"}}}}
    plan = {"plan_id": "unsafe", "source_candidate_id": "w", "target_kind": "character", "target_entity_id": "missing", "status": "approved", "deterministic": True}
    action = {"action_type": "relocate", "target_entity_ids": ["w"], "description": "unsafe", "deterministic": True, "proposed_operations": [{"relocation_plan": plan}]}
    result = asyncio.run(repair_import_artifacts(state, [action]))
    assert "w" in result["entity_registry"]["world_detailed"]
    assert result["quarantine_candidates"][0]["candidate_id"] == "w"


def test_organizer_holds_relation_bearing_appellation_for_human_review():
    output = organize_project_content(_input(world_candidates={
        "续弦夫人": {"id": "world_spouse", "category": "concept", "confidence": 0.7},
    }))

    assert output["world_items"] == []
    assert output["quarantine_items"][0]["reason_codes"] == ["person_or_relationship_phrase"]


def test_organizer_quarantines_kinship_appellation_instead_of_routing_it_as_organization():
    output = organize_project_content(_input(world_candidates={
        "韩父": {"id": "world_han_father", "category": "organization", "confidence": 0.98},
    }))

    assert output["world_items"] == []
    assert output["quarantine_items"][0]["raw_name"] == "韩父"
    assert output["quarantine_items"][0]["reason_codes"] == ["person_or_relationship_phrase"]


def test_organizer_routes_described_branch_hall_as_a_location():
    output = organize_project_content(_input(world_candidates={
        "七玄门分堂": {"id": "world_branch", "category": "location", "confidence": 0.7, "description": "各个堂口占据彩霞山大小山峰。"},
    }))

    assert output["quarantine_items"] == []
    assert output["world_items"][0]["container_key"] == "locations"
