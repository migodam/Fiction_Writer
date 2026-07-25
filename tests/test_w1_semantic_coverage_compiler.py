"""Regression coverage for the read-only W1 semantic coverage compiler."""
from __future__ import annotations

from copy import deepcopy

from sidecar.supervisor.semantic_coverage import compile_semantic_coverage


def _clean_input() -> dict:
    return {
        "contract_version": "w1-semantic-coverage/v1",
        "import_run_id": "run_clean",
        "lineage_id": "lineage_clean",
        "attempt_id": "attempt_clean",
        "source_manifest": {"sha256": "source-hash", "chapter_count": 1},
        "chunks": [{
            "chunk_id": "chunk_0",
            "chapter_ids": ["chapter_1"],
            "manuscript_preserved": True,
            "semantic_status": "semantic_complete",
            "domain_status": {
                "characters": "complete", "relationships": "complete", "world": "complete",
                "events": "complete", "scenes": "complete",
            },
            "failure_refs": [],
            "candidate_ids": ["char_han", "event_departure", "scene_1"],
        }],
        "candidates": [
            {
                "candidate_id": "char_han", "entity_type": "character", "name": "韩立",
                "fields": {"importance": "major", "background": "韩家村少年", "experience": ["入七玄门"]},
                "evidence_refs": [{"evidence_id": "ev_han", "source_span": {"chapter_id": "chapter_1"}}],
                "source_chunk_ids": ["chunk_0"], "confidence": 0.95,
            },
            {
                "candidate_id": "world_sect", "entity_type": "world_item", "name": "七玄门",
                "fields": {"entity_type": "organization", "target_folder_id": "world_folder_organizations"},
                "evidence_refs": [{"evidence_id": "ev_sect", "source_span": {"chapter_id": "chapter_1"}}],
                "source_chunk_ids": ["chunk_0"], "confidence": 0.9,
            },
            {
                "candidate_id": "scene_1", "entity_type": "scene", "name": "韩立踏入七玄门",
                "fields": {"chapter_id": "chapter_1", "linked_event_ids": ["event_departure"], "linked_character_ids": ["char_han"], "linked_world_item_ids": ["world_sect"]},
                "evidence_refs": [{"evidence_id": "ev_scene", "source_span": {"chapter_id": "chapter_1"}}],
                "source_chunk_ids": ["chunk_0"], "confidence": 0.9,
            },
            {
                "candidate_id": "event_departure", "entity_type": "timeline_event", "name": "韩立赴七玄门",
                "fields": {"linked_scene_ids": ["scene_1"], "participant_character_ids": ["char_han"], "location_ids": ["world_sect"]},
                "evidence_refs": [{"evidence_id": "ev_event", "source_span": {"chapter_id": "chapter_1"}}],
                "source_chunk_ids": ["chunk_0"], "confidence": 0.9,
            },
            {
                "candidate_id": "rel_family", "entity_type": "relationship", "name": "韩立与韩铸",
                "fields": {"source_id": "char_han", "target_id": "char_han_2", "type": "亲属关系", "evidence_refs": ["ev_rel"]},
                "evidence_refs": [{"evidence_id": "ev_rel", "source_span": {"chapter_id": "chapter_1"}}],
                "source_chunk_ids": ["chunk_0"], "confidence": 0.9,
            },
            {
                "candidate_id": "char_han_2", "entity_type": "character", "name": "韩铸",
                "fields": {"importance": "supporting"},
                "evidence_refs": [{"evidence_id": "ev_han_2", "source_span": {"chapter_id": "chapter_1"}}],
                "source_chunk_ids": ["chunk_0"], "confidence": 0.8,
            },
        ],
        "entity_merge_decisions": [],
        "organizer_output": {},
        "timeline_architecture": {},
        "manuscript_projection": {"chapters": [{"id": "chapter_1"}]},
        "existing_project_digest": {},
        "profile": "balanced",
    }


def _codes(report: dict, key: str) -> set[str]:
    return {item["code"] for item in report[key]}


def test_clean_case_passes_and_never_mutates_input():
    payload = _clean_input()
    before = deepcopy(payload)

    report = compile_semantic_coverage(payload)

    assert report["verdict"] == "pass"
    assert report["blocking_findings"] == []
    assert payload == before
    assert report["input_hash"] == compile_semantic_coverage(deepcopy(payload))["input_hash"]


def test_failed_or_manuscript_only_chunk_blocks_and_coverage_is_reported():
    payload = _clean_input()
    payload["chunks"][0]["semantic_status"] = "failed"
    payload["chunks"][0]["domain_status"]["events"] = "failed"
    payload["chunks"][0]["failure_refs"] = ["chunk_0_failures.json"]

    report = compile_semantic_coverage(payload)

    assert report["verdict"] == "blocked"
    assert {"chunk_not_semantically_complete", "chunk_domain_failed"} <= _codes(report, "blocking_findings")
    event_coverage = next(item for item in report["coverage"] if item["domain"] == "events")
    assert event_coverage["failed"] == 1


def test_import_test18_han_li_alias_duplicate_is_blocking_and_evidence_backed_merge_is_not():
    payload = _clean_input()
    payload["candidates"].append({
        "candidate_id": "char_fool", "entity_type": "character", "name": "二愣子（韩立）",
        "fields": {"importance": "major", "aliases": ["二愣子"]},
        "evidence_refs": [{"evidence_id": "ev_alias", "source_span": {"chapter_id": "chapter_1"}}],
        "source_chunk_ids": ["chunk_0"], "confidence": 0.94,
    })

    report = compile_semantic_coverage(payload)

    assert "character_alias_collision" in _codes(report, "blocking_findings")
    merge = report["character_merge_report"]["merge_candidates"][0]
    assert {"char_han", "char_fool"} <= set(merge["candidate_ids"])


def test_event_action_cannot_be_promoted_to_long_term_relationship():
    payload = _clean_input()
    relationship = next(item for item in payload["candidates"] if item["entity_type"] == "relationship")
    relationship["fields"]["type"] = "选拔"

    report = compile_semantic_coverage(payload)

    assert "relationship_event_action" in _codes(report, "blocking_findings")
    assert report["relationship_report"]["dispositions"][0]["disposition"] == "event_participation"


def test_long_term_relationship_can_cite_an_action_as_evidence():
    payload = _clean_input()
    relationship = next(item for item in payload["candidates"] if item["entity_type"] == "relationship")
    relationship["fields"]["type"] = "政治关系"
    relationship["fields"]["source_label"] = "上下级"
    relationship["fields"]["description"] = "王护法向岳堂主恭敬行礼，以此证明上下级关系。"

    report = compile_semantic_coverage(payload)

    assert "relationship_event_action" not in _codes(report, "blocking_findings")
    assert report["relationship_report"]["dispositions"][0]["disposition"] == "long_term_relationship"


def test_quarantined_relationship_remains_a_blocking_repair():
    payload = _clean_input()
    payload["relationship_quarantines"] = [{
        "relationship_id": "rel_unknown", "type": "陌生称谓", "reason": "unknown_type_or_missing_evidence_or_endpoint",
        "evidence": [],
    }]

    report = compile_semantic_coverage(payload)

    assert "relationship_quarantined" in _codes(report, "blocking_findings")


def test_world_role_contamination_blocks_and_ambiguous_hall_warns():
    payload = _clean_input()
    payload["candidates"].extend([
        {
            "candidate_id": "world_inner", "entity_type": "world_item", "name": "内门",
            "fields": {"entity_type": "rule", "target_folder_id": "world_folder_cultivation"},
            "evidence_refs": [{"evidence_id": "ev_inner", "source_span": {"chapter_id": "chapter_1"}}],
            "source_chunk_ids": ["chunk_0"], "confidence": 0.9,
        },
        {
            "candidate_id": "world_hall", "entity_type": "world_item", "name": "七绝堂",
            "fields": {"entity_type": "location", "target_folder_id": "world_folder_locations"},
            "evidence_refs": [{"evidence_id": "ev_hall", "source_span": {"chapter_id": "chapter_1"}}],
            "source_chunk_ids": ["chunk_0"], "confidence": 0.65,
        },
    ])

    report = compile_semantic_coverage(payload)

    assert "world_role_or_rank_contamination" in _codes(report, "blocking_findings")
    assert "world_ambiguous_institution" in _codes(report, "warnings")
    hall = next(item for item in report["world_routing_report"]["decisions"] if item["entity_id"] == "world_hall")
    assert hall["action"] == "hold"


def test_generic_scene_and_missing_event_linkage_block_but_missing_optional_scene_link_is_warning():
    payload = _clean_input()
    scene = next(item for item in payload["candidates"] if item["candidate_id"] == "scene_1")
    event = next(item for item in payload["candidates"] if item["candidate_id"] == "event_departure")
    scene["name"] = "章节正文"
    scene["fields"]["linked_event_ids"] = []
    event["fields"]["linked_scene_ids"] = []

    report = compile_semantic_coverage(payload)

    assert {"scene_generic_title", "event_missing_scene_link"} <= _codes(report, "blocking_findings")
    assert "scene_missing_event_link" in _codes(report, "warnings")


def test_scene_event_world_linkage_rejects_unknown_world_target():
    payload = _clean_input()
    event = next(item for item in payload["candidates"] if item["candidate_id"] == "event_departure")
    event["fields"]["linked_world_item_ids"] = ["world_missing"]

    report = compile_semantic_coverage(payload)

    assert "event_world_link_missing_target" in _codes(report, "blocking_findings")


def test_major_character_background_stays_blocked_when_evidence_cannot_support_it():
    payload = _clean_input()
    character = next(item for item in payload["candidates"] if item["candidate_id"] == "char_han")
    character["fields"]["background"] = ""

    report = compile_semantic_coverage(payload)

    assert "major_character_missing_background" in _codes(report, "blocking_findings")


def test_input_hash_is_order_independent_and_finds_missing_major_character_evidence():
    payload = _clean_input()
    payload["candidates"][0]["evidence_refs"] = []
    reversed_payload = deepcopy(payload)
    reversed_payload["candidates"] = list(reversed(reversed_payload["candidates"]))

    first = compile_semantic_coverage(payload)
    second = compile_semantic_coverage(reversed_payload)

    assert first["input_hash"] == second["input_hash"]
    assert "major_character_missing_evidence" in _codes(first, "blocking_findings")
