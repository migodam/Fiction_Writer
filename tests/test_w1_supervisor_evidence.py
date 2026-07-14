"""Regression coverage for supervisor evidence, validation, and review metrics."""
from __future__ import annotations

import asyncio
import hashlib
import json

from sidecar.models.state import PROFILE_CONFIGS, make_source_span
from sidecar.supervisor.policy import _merge_window_result, run_supervisor_policy
from sidecar.workflows import w1_import


def _source_span(start: int, end: int) -> dict:
    return {
        "raw_source_hash": "fixture-source-hash",
        "absolute_start": start,
        "absolute_end": end,
        "substring_hash": f"fixture-substring-{start}-{end}",
    }


def _supervisor_state(tmp_path, window: dict) -> dict:
    return {
        "project_path": str(tmp_path),
        "import_run_id": "supervisor_evidence_test",
        "source_file_path": str(tmp_path / "fixture.txt"),
        "prompt_profile": "balanced",
        "profile_config": PROFILE_CONFIGS["balanced"],
        "import_mode": "import_all",
        "source_language": "en",
        "context": {},
        "chunks": [{"chunk_id": 0, "content": "fixture", "source_span": _source_span(10, 20)}],
        "import_run_manifest": {"source_hash": "fixture-source-hash", "import_run_id": "supervisor_evidence_test"},
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "prompt_windows": [window],
        "window_metrics": {},
        "cross_validation": {},
        "gate_failures": [],
        "supervisor_decisions": [],
        "supervisor_log": [],
        "minor_repair_log": [],
        "supervisor_iteration": 0,
        "max_supervisor_iterations": 1,
        "use_supervisor": True,
        "errors": [],
    }


def test_merge_window_result_merges_cross_validation_with_shared_helper():
    state = {
        "import_run_id": "cv_run",
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "cross_validation": {
            "duplicate_events": [{"event_ids": ["event_a", "event_b"], "reason": "same beat"}],
            "warnings": ["existing warning"],
        },
    }
    result = {
        "cross_validation": {
            "duplicate_events": [
                {"event_ids": ["event_a", "event_b"], "reason": "same beat"},
                {"event_ids": ["event_c", "event_d"], "reason": "same departure"},
            ],
            "warnings": ["existing warning", "new warning"],
        },
    }

    merged = _merge_window_result(state, result)

    assert merged["cross_validation"]["duplicate_events"] == [
        {"event_ids": ["event_a", "event_b"], "reason": "same beat"},
        {"event_ids": ["event_c", "event_d"], "reason": "same departure"},
    ]
    assert merged["cross_validation"]["warnings"] == ["existing warning", "new warning"]


def test_supervisor_persists_evidence_cards_and_window_based_entity_refs(tmp_path):
    source_text = "Hero reaches harbor."
    span = make_source_span(source_text, 0, len(source_text))
    window = {
        "id": "pwin_0",
        "chunk_ids": [0],
        "chapter_range": "Chapter 1",
        "source_span": span,
    }
    state = _supervisor_state(tmp_path, window)
    state["source_text"] = source_text
    state["import_run_manifest"]["segments"] = [{"id": "seg_0", "chunk_id": 0, "source_span": span}]
    extracted_registry = {
        "characters": {"char_hero": {"canonical_id": "char_hero", "canonical_name": "Hero"}},
        "events": {"event_arrival": {"event_id": "event_arrival", "title": "Arrival"}},
        "world": {"Harbor": "location"},
        "world_detailed": {"Harbor": {"id": "world_harbor", "name": "Harbor", "category": "location"}},
    }
    raw_relationship = {
        "source_character_name": "Hero",
        "target_character_name": "Guide",
        "type": "alliance",
        "description": "The guide escorts Hero.",
    }

    async def passthrough(state, *args):
        return {"entity_registry": state.get("entity_registry", {}), "raw_relationships": state.get("raw_relationships", [])}

    async def extract(_state, _window_id):
        return {
            "entity_registry": extracted_registry,
            "raw_relationships": [raw_relationship],
            "window_metrics": {"pwin_0": {"window_id": "pwin_0", "chapter_count": 1, "char_count_extracted": 2, "event_count_extracted": 2, "failed_prompts": [], "gate_passed": True, "rerun_count": 0, "missing_majors": [], "missing_majors_count": 0}},
        }

    async def cross_validate(_state, _window_id):
        return {"cross_validation": {"warnings": ["window checked"]}}

    async def segment(_state):
        return {"prompt_windows": [window]}

    async def qa_review(_state):
        return {"gate_failures": [], "import_review_report": {}}

    async def proposal_write(_state):
        return {"proposals": [], "import_review_report": {}}

    tools = {
        "segment_manifest": segment,
        "extract_window": extract,
        "cross_validate_window": cross_validate,
        "rerun_window": extract,
        "reduce_entities": passthrough,
        "minor_repair": passthrough,
        "architect_timeline": passthrough,
        "qa_review": qa_review,
        "proposal_write": proposal_write,
    }

    result = asyncio.run(run_supervisor_policy(state, tools))

    evidence_path = tmp_path / "system" / "imports" / "supervisor_evidence_test" / "evidence_cards.json"
    cards = json.loads(evidence_path.read_text(encoding="utf-8"))
    hero = result["entity_registry"]["characters"]["char_hero"]
    hero_card = next(card for card in cards if card["entity_id"] == "char_hero")

    assert hero["evidence_refs"] == [hero_card["card_id"]]
    assert hero_card["source_prompt_window_id"] == "pwin_0"
    assert hero_card["source_span"] == window["source_span"]
    assert result["cross_validation"]["warnings"] == ["window checked"]


def test_final_evidence_cards_are_claim_local_hash_checked_and_cover_five_characters_and_events(tmp_path):
    source_text = (
        "韩立在村口遇见墨大夫。墨大夫带韩立前往七玄门。"
        "厉飞雨在演武场挑战韩立。张铁陪韩立进入山门。王绝楚宣读入门规矩。"
    )
    source_path = tmp_path / "real_shape.txt"
    source_path.write_text(source_text, encoding="utf-8")
    valid_span = make_source_span(source_text, 0, len(source_text))
    stale_span = {**valid_span, "raw_source_hash": "stale", "substring_hash": "stale"}
    window = {"id": "pwin_valid", "chunk_ids": [0], "source_span": valid_span}
    state = {
        **_supervisor_state(tmp_path, window),
        "source_file_path": str(source_path),
        "source_text": source_text,
        "import_run_manifest": {"segments": [{"id": "seg_0", "chunk_id": 0, "source_span": valid_span}]},
        "prompt_windows": [window, {"id": "pwin_stale", "chunk_ids": [0], "source_span": stale_span}],
        "timeline_branches": [{"id": "branch_import_main", "name": "主线", "mode": "root"}],
        "timeline_architecture": {"canonical_events": [], "discarded_duplicates": [], "warnings": []},
        "reducer_artifact": {}, "relationships": [], "character_tags": [], "world_settings": {},
        "world_containers": [], "manuscript_chapters": [],
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
    }
    names = ["韩立", "墨大夫", "厉飞雨", "张铁", "王绝楚"]
    sentences = [part + "。" for part in source_text.split("。") if part]
    for index, name in enumerate(names):
        state["entity_registry"]["characters"][f"char_{index}"] = {
            "canonical_name": name, "aliases": [name], "summary": sentences[index], "first_seen_chunk": 0,
        }
        state["entity_registry"]["events"][f"event_{index}"] = {
            "event_id": f"event_{index}", "title": sentences[index][:-1], "description": sentences[index],
            "chunk_id": 0, "branchId": "branch_import_main", "orderIndex": index,
            "locationIds": [], "participantCharacterIds": [f"char_{index}"], "linkedSceneIds": [],
            "linkedWorldItemIds": [], "tags": ["导入"],
        }

    reviewed = asyncio.run(w1_import.node_review_import(state))
    cards = reviewed["evidence_cards"]
    assert len(cards) == 10
    assert {card["entity_id"] for card in cards} == {*(f"char_{i}" for i in range(5)), *(f"event_{i}" for i in range(5))}
    assert all(card["snippets"] and len(card["snippets"][0]) < len(source_text) for card in cards)
    assert all(card["source_segment_id"] == "seg_0" for card in cards)
    for card in cards:
        span = card["source_span"]
        excerpt = source_text[span["absolute_start"]:span["absolute_end"]]
        assert span["raw_source_hash"] == hashlib.sha256(source_text.encode()).hexdigest()
        assert span["substring_hash"] == hashlib.sha256(excerpt.encode()).hexdigest()
    fact_findings = reviewed["import_review_report"]["reviewer_reports"]["fact"]["findings"]
    assert not [finding for finding in fact_findings if finding["check_name"] in {"evidence_entity_mismatch", "evidence_unusable"}]


def test_final_evidence_rebuild_recovers_latest_smoke_ids_from_stale_window_spans(tmp_path):
    """Final IDs must retain verified evidence after dedupe strips raw window hashes."""
    source_text = (
        "老张叔是村里唯一识字的读书人，曾为城里有钱人当伴读书童。"
        "张铁憨厚勤快，和韩立一起被墨大夫收为记名弟子。"
        "墨大夫是七玄门供奉，传授韩立无名口诀。"
        "舞岩有副门主的姻亲关系，被直接保送七绝堂。"
        "张均、吴铭瑞把过关之人带到本堂去。"
        "王6门主曾被墨大夫救下性命。\n"
        "墨大夫说：你二人从即日起便是我的记名弟子。\n"
        "从今天起，你就是我的亲传弟子了。张铁改学另一种心法。\n"
        "韩立在树丛中发现一个细颈圆形的绿色金属小瓶。"
        "韩立终于冲关成功，练成了这套无名口诀的第一层。"
    )
    chapter_ends = [source_text.index("\n") + 1]
    chapter_ends.append(source_text.index("\n", chapter_ends[0]) + 1)
    chapter_ends.append(len(source_text))
    chapter_starts = [0, *chapter_ends[:-1]]
    manifest_segments = [
        {
            "id": f"seg_{index}",
            "chunk_id": index,
            "source_span": make_source_span(source_text, start, end),
        }
        for index, (start, end) in enumerate(zip(chapter_starts, chapter_ends))
    ]
    stale_span = {"raw_source_hash": "stale", "absolute_start": 0, "absolute_end": 1, "substring_hash": "stale"}
    windows = [
        {"id": "pwin_base", "chunk_ids": [0], "chapter_range": "第一章", "source_span": stale_span},
        {"id": "pwin_middle", "chunk_ids": [1], "chapter_range": "第二章", "source_span": stale_span},
        {"id": "pwin_late", "chunk_ids": [2], "chapter_range": "第三章", "source_span": stale_span},
    ]
    character_specs = {
        "char_4164f0ba": ("老张叔", "村里唯一识字的读书人，曾为城里有钱人当伴读书童", "pwin_base"),
        "char_c6c870c0": ("张铁", "与韩立一起被墨大夫收为记名弟子", "pwin_base"),
        "char_0ce896f2": ("墨大夫", "七玄门供奉，传授韩立无名口诀", "pwin_base"),
        "char_0a7ef8f8": ("舞岩", "有副门主的姻亲关系，被直接保送七绝堂", "pwin_base"),
        "char_c4d00eee": ("张均", "七玄门内门弟子，负责带领新弟子", "pwin_base"),
        "char_c7ed8370": ("吴铭瑞", "七玄门内门弟子，负责带领新弟子", "pwin_base"),
        "char_41854421": ("王6", "七玄门正门主，曾被墨大夫所救", "pwin_base"),
    }
    event_specs = {
        "event_4c66790e": ("韩立被墨大夫收为记名弟子", "墨大夫收韩立和张铁为记名弟子", "第一章"),
        "event_3fa00f29": ("韩立通过测试成为亲传弟子", "墨大夫收韩立为亲传弟子，张铁改学另一种心法", "第二章"),
        "event_ab06693f": ("韩立发现神秘小瓶", "韩立在树丛中发现绿色金属小瓶", "第三章"),
        "event_2ed9f858": ("韩立练成无名口诀第一层", "韩立冲关成功，练成无名口诀第一层", "第三章"),
    }
    state = {
        **_supervisor_state(tmp_path, windows[0]),
        "source_text": source_text,
        "prompt_windows": windows,
        "import_run_manifest": {"segments": manifest_segments},
        "timeline_branches": [{"id": "branch_import_main", "name": "主线", "mode": "root"}],
        "timeline_architecture": {"canonical_events": [], "discarded_duplicates": [], "warnings": []},
        "reducer_artifact": {},
        "relationships": [],
        "character_tags": [],
        "world_settings": {},
        "world_containers": [],
        "manuscript_chapters": [],
        "entity_registry": {
            "characters": {
                entity_id: {
                    "canonical_name": name,
                    "summary": summary,
                    "notes": [f"[window {window_id}] {summary}"],
                }
                for entity_id, (name, summary, window_id) in character_specs.items()
            },
            "events": {
                entity_id: {
                    "event_id": entity_id,
                    "title": title,
                    "description": description,
                    "time": chapter,
                    "branchId": "branch_import_main",
                    "orderIndex": index,
                    "locationIds": [],
                    "participantCharacterIds": [],
                    "linkedSceneIds": [],
                    "linkedWorldItemIds": [],
                    "tags": ["导入"],
                }
                for index, (entity_id, (title, description, chapter)) in enumerate(event_specs.items())
            },
            "world": {},
            "world_detailed": {},
        },
    }

    reviewed = asyncio.run(w1_import.node_review_import(state))
    final_ids = set(character_specs) | set(event_specs)
    cards = [card for card in reviewed["evidence_cards"] if card["entity_id"] in final_ids]
    assert {card["entity_id"] for card in cards} == final_ids
    for card in cards:
        span = card["source_span"]
        excerpt = source_text[span["absolute_start"]:span["absolute_end"]]
        assert span["raw_source_hash"] == hashlib.sha256(source_text.encode()).hexdigest()
        assert span["substring_hash"] == hashlib.sha256(excerpt.encode()).hexdigest()
        assert card["snippets"] and card["snippets"][0] in source_text

    fact_findings = reviewed["import_review_report"]["reviewer_reports"]["fact"]["findings"]
    assert not [
        finding for finding in fact_findings
        if finding["check_name"] in {"evidence_missing", "evidence_entity_mismatch", "evidence_unusable"}
        and set(finding["entity_refs"]) & final_ids
    ]


def test_review_observability_is_explicitly_pre_proposal(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "review_phase_test",
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "relationships": [],
        "manuscript_chapters": [],
        "timeline_architecture": {},
        "timeline_branches": [],
        "reducer_artifact": {},
        "errors": [],
        "context": {},
        "source_language": "en",
        "character_tags": [],
    }

    report = asyncio.run(w1_import.node_review_import(state))["import_review_report"]
    observability = report["import_observability"]

    assert observability["observability_phase"] == "pre_proposal"
    assert observability["relationships_preproposal_count"] == 0
    assert observability["manuscript_chapters_preproposal_count"] == 0
    assert "relationships_extracted" not in observability
    assert "manuscript_written" not in observability


def test_final_reviewer_and_proposal_staging_share_bound_canonical_evidence(tmp_path, monkeypatch):
    """Final remaps must bind cards to the entities both review and proposal staging use."""
    source_text = "Hero arrives at the harbor and meets the guide."
    source_path = tmp_path / "fixture.txt"
    source_path.write_text(source_text, encoding="utf-8")
    span = make_source_span(source_text, 0, len(source_text))
    window = {"id": "pwin_0", "chunk_ids": [0], "source_span": span}
    state = {
        **_supervisor_state(tmp_path, window),
        "source_file_path": str(source_path),
        "source_text": source_text,
        "timeline_branches": [{"id": "branch_import_main", "mode": "root", "name": "Main Timeline"}],
        "timeline_architecture": {"canonical_events": [], "discarded_duplicates": [], "warnings": []},
        "reducer_artifact": {},
        "relationships": [],
        "character_tags": [],
        "world_settings": {},
        "world_containers": [],
        "manuscript_chapters": [],
        "entity_registry": {
            "characters": {
                "char_hero": {"canonical_name": "Hero", "summary": "Hero arrives at the harbor.", "first_seen_chunk": 0},
                "char_hero_duplicate": {"canonical_name": "Hero", "summary": "The guide meets Hero.", "first_seen_chunk": 0},
            },
            "events": {
                "event_arrival": {
                    "event_id": "event_arrival",
                    "title": "Hero arrives at the harbor",
                    "description": "Hero arrives at the harbor and meets the guide.",
                    "chunk_id": 0,
                    "character_ids": ["char_hero_duplicate"],
                    "participantCharacterIds": ["char_hero_duplicate"],
                    "branchId": "branch_import_main",
                    "orderIndex": 0,
                    "locationIds": [],
                    "linkedSceneIds": [],
                    "linkedWorldItemIds": [],
                    "tags": ["imported"],
                },
            },
            "world": {},
            "world_detailed": {},
        },
    }

    reviewed = asyncio.run(w1_import.node_review_import(state))
    reviewed_registry = reviewed["entity_registry"]
    cards = reviewed["evidence_cards"]
    card_ids = {card["card_id"] for card in cards}

    assert set(reviewed_registry["characters"]) == {"char_hero"}
    assert reviewed_registry["events"]["event_arrival"]["participantCharacterIds"] == ["char_hero"]
    assert reviewed_registry["characters"]["char_hero"]["evidence_refs"]
    assert reviewed_registry["events"]["event_arrival"]["evidence_refs"]
    assert set(reviewed_registry["characters"]["char_hero"]["evidence_refs"]) <= card_ids
    assert set(reviewed_registry["events"]["event_arrival"]["evidence_refs"]) <= card_ids
    assert all(card["source_span"] == span for card in cards)
    assert not [
        finding for finding in reviewed["import_review_report"]["reviewer_reports"]["fact"]["findings"]
        if finding["check_name"] == "evidence_missing"
    ]
    expected_character_refs = list(reviewed_registry["characters"]["char_hero"]["evidence_refs"])
    expected_event_refs = list(reviewed_registry["events"]["event_arrival"]["evidence_refs"])

    proposed_operations = []

    async def fake_propose_write(operation, _project_path):
        proposed_operations.append(operation)
        return {"id": f"proposal_{operation['entity_id']}", "status": "pending", "confidence": operation["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    asyncio.run(w1_import.node_write_to_project({**state, **reviewed}))

    staged = {operation["entity_type"]: operation["data"] for operation in proposed_operations if operation["entity_type"] in {"character", "timeline_event"}}
    assert staged["character"]["evidenceRefs"] == expected_character_refs
    assert staged["timeline_event"]["evidenceRefs"] == expected_event_refs
    assert staged["character"]["sourceSpan"] == span
    assert staged["timeline_event"]["sourceSpan"] == span
