from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from sidecar.models import state as sidecar_state
from sidecar.prompts import w1_prompts
from sidecar.workflows import w1_import


def test_import_manifest_is_deterministic(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nA beginning.", encoding="utf-8")
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(source),
        "import_mode": "import_all",
        "prompt_profile": "balanced",
        "context": {"model": "deepseek-chat"},
    }
    chunks = [{"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": "A beginning."}]

    first = w1_import._build_import_manifest(state, source.read_text(encoding="utf-8"), [dict(chunks[0])])
    second = w1_import._build_import_manifest(state, source.read_text(encoding="utf-8"), [dict(chunks[0])])

    assert first["import_run_id"] == second["import_run_id"]
    assert first["source_hash"] == second["source_hash"]
    assert first["segments"][0]["id"] == second["segments"][0]["id"]


def test_import_manifest_keeps_lineage_as_compatibility_import_run_id(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nA beginning.", encoding="utf-8")
    manifest = w1_import._build_import_manifest(
        {
            "project_path": str(tmp_path),
            "source_file_path": str(source),
            "import_run_id": "lineage_stable",
            "lineage_id": "lineage_stable",
            "context": {},
        },
        source.read_text(encoding="utf-8"),
        [{"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": "A beginning."}],
    )

    assert manifest["import_run_id"] == "lineage_stable"
    assert manifest["lineage_id"] == "lineage_stable"


def test_recoverable_checkpoint_error_stops_before_chunk_processing():
    assert w1_import.route_by_mode({"status": "recoverable_error"}) == "recoverable_error"


def test_prompt_window_preserves_complete_normal_chapter(tmp_path):
    state = {"project_path": str(tmp_path), "prompt_profile": "deep", "context": {}}
    digest = {
        "content": '{"characters":[],"relationships":[]}',
        "estimated_tokens": 10,
        "counts": {},
    }
    content = "Chapter 1\n" + ("A complete scene.\n\n" * 100)

    windows = w1_import._build_prompt_windows(
        state,
        [{"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": content, "source_span": {"start": 0, "end": len(content)}}],
        digest,
    )

    assert len(windows) == 1
    assert windows[0]["split_reason"] == "complete_chapter"
    assert content in windows[0]["text"]
    assert "middle omitted by W1 prompt profile context budget" not in windows[0]["text"]


def test_prompt_window_splits_only_single_oversized_chapter_by_budget(tmp_path):
    state = {"project_path": str(tmp_path), "prompt_profile": "deep", "context": {}}
    digest = {
        "content": '{"characters":[],"relationships":[]}',
        "estimated_tokens": 10,
        "counts": {},
    }
    paragraph = "A" * 250_000
    content = "\n\n".join([paragraph, paragraph, paragraph, paragraph])

    windows = w1_import._build_prompt_windows(
        state,
        [{"chunk_id": 0, "chapter_hint": "Chapter Huge", "manuscript_content": content, "source_span": {"start": 0, "end": len(content)}}],
        digest,
    )

    assert len(windows) > 1
    assert {window["split_reason"] for window in windows} == {"single_oversized_chapter_paragraph_split"}
    assert all(window["estimated_tokens"] <= 256_000 for window in windows)
    assert sum(window["source_chars"] for window in windows) == len(content)


def test_split_prompt_windows_keep_exact_source_spans_for_each_part(tmp_path):
    paragraph = "A" * 250_000
    raw_source = "\n\n".join([paragraph, paragraph, paragraph, paragraph])
    state = {"project_path": str(tmp_path), "prompt_profile": "deep", "context": {}, "source_text": raw_source}
    digest = {"content": "{}", "estimated_tokens": 1, "counts": {}}
    span = sidecar_state.make_source_span(raw_source, 0, len(raw_source))

    windows = w1_import._build_prompt_windows(
        state,
        [{"chunk_id": 0, "chapter_hint": "Huge", "manuscript_content": raw_source, "source_span": span}],
        digest,
    )

    assert len(windows) > 1
    for window in windows:
        assert sidecar_state.reconstruct_source_span(window["source_span"], raw_source) == window["text"]


def test_prompt_window_packs_short_chapters_toward_256k_budget(tmp_path):
    state = {"project_path": str(tmp_path), "prompt_profile": "deep", "context": {}}
    digest = {
        "content": '{"characters":[],"relationships":[]}',
        "estimated_tokens": 10,
        "counts": {},
    }
    chunks = []
    for index in range(50):
        content = f"第{index + 1}章\n" + ("韩" * 4000)
        chunks.append({
            "chunk_id": index,
            "chapter_hint": f"第{index + 1}章",
            "manuscript_content": content,
            "source_span": {"start": index * len(content), "end": (index + 1) * len(content)},
        })

    windows = w1_import._build_prompt_windows(state, chunks, digest)

    assert len(windows) < 50
    assert len(windows[0]["chunk_ids"]) > 1
    assert windows[0]["split_reason"] == "packed_complete_chapters"
    assert windows[0]["estimated_tokens"] <= 256_000
    assert windows[0]["total_token_budget"] == 256_000
    assert windows[0]["source_budget_tokens"] > windows[0]["source_token_estimate"]
    assert windows[0]["fill_ratio"] >= 0.8

    refreshed = w1_import._refresh_prompt_window_text(
        {
            **state,
            "cross_validation": {
                "duplicate_events": [
                    {"event_ids": [f"event_{i}", f"event_{i + 1}"], "reason": "重复事件" * 200}
                    for i in range(20)
                ],
                "warnings": ["滚动校验摘要" * 200 for _ in range(20)],
            },
        },
        windows[0],
        digest,
    )

    assert refreshed["estimated_tokens"] <= 256_000


def test_previous_validation_summary_prefers_rolling_cross_validation(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "cross_validation": {
            "duplicate_events": [{"event_ids": ["a", "b"], "reason": "same beat"}],
            "missing_major_characters": [{"name_or_alias": "韩立", "confidence": 0.95}],
            "warnings": ["check protagonist group"],
        },
        "import_review_report": {"status": "pass"},
    }

    summary = w1_import._previous_validation_summary(state)

    assert "rolling_cross_validation" in summary
    assert "duplicate_events" in summary
    assert "韩立" in summary


def test_merge_cross_validation_artifacts_preserves_unique_bounded_items():
    existing = {
        "duplicate_events": [{"event_ids": ["a", "b"], "reason": "same beat"}],
        "warnings": ["old warning"],
    }
    incoming = {
        "duplicate_events": [
            {"event_ids": ["a", "b"], "reason": "same beat"},
            {"event_ids": ["c", "d"], "reason": "same departure"},
        ],
        "warnings": ["new warning"],
    }

    merged = w1_import._merge_cross_validation_artifacts(existing, incoming, "import_test")

    assert merged["import_run_id"] == "import_test"
    assert len(merged["duplicate_events"]) == 2
    assert merged["warnings"] == ["old warning", "new warning"]


def test_process_chunks_runs_packed_window_once_and_marks_all_covered_chunks(tmp_path, monkeypatch):
    async def fake_invoke_json_prompt(_llm, prompt_template, **_kwargs):
        if "W1 Import Character Compiler" in prompt_template:
            return {"existing_character_updates": [], "new_characters": []}
        if "W1 Import Timeline Scout" in prompt_template:
            return {"events": []}
        if "world extraction" in prompt_template:
            return {"world_mentions": []}
        if "relationship evidence" in prompt_template:
            return {"relationships": []}
        if "scene boundaries" in prompt_template:
            return {"chapter_hint": "", "scenes": []}
        return {}

    async def fake_cross_validation(_llm, state, *, window, digest, prompt_outputs, cross_validation, session_id=""):
        return {
            "import_run_id": state["import_run_id"],
            "duplicate_events": [{"event_ids": ["old", "new"], "reason": "same beat"}],
            "warnings": [f"validated {window['id']}"],
        }

    monkeypatch.setattr(w1_import, "_invoke_json_prompt", fake_invoke_json_prompt)
    monkeypatch.setattr(w1_import, "_run_cross_validation_for_window", fake_cross_validation)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())

    chunks = [
        {"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": "first", "content": "first"},
        {"chunk_id": 1, "chapter_hint": "Chapter 2", "manuscript_content": "second", "content": "second"},
        {"chunk_id": 2, "chapter_hint": "Chapter 3", "manuscript_content": "third", "content": "third"},
    ]
    digest = {"content": '{"characters":[]}', "estimated_tokens": 4, "counts": {}}
    windows = w1_import._build_prompt_windows(
        {
            "project_path": str(tmp_path),
            "import_run_id": "import_test",
            "prompt_profile": "deep",
            "context": {},
        },
        chunks,
        digest,
    )

    result = asyncio.run(w1_import.node_process_chunks({
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "novel.txt"),
        "checkpoint_path": str(tmp_path / "import_progress.json"),
        "import_run_id": "import_test",
        "prompt_profile": "deep",
        "context": {},
        "chunks": chunks,
        "prompt_windows": windows,
        "project_structure_digest": digest,
        "entity_registry": {"characters": {}, "events": {}, "world": {}},
        "chunk_extractions": [],
        "raw_relationships": [],
        "errors": [],
    }))

    assert [item["chunk_id"] for item in result["chunk_extractions"]] == [0, 1, 2]
    assert result["chunk_extractions"][1]["notes"] == ["Covered by packed prompt window anchored at chunk 0."]
    assert result["cross_validation"]["warnings"] == [f"validated {windows[0]['id']}"]


def test_build_manuscript_orders_chapters_by_source_chunk_id(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "import_mode": "import_all",
        "chunks": [
            {"chunk_id": 2, "chapter_hint": "Chapter 3", "manuscript_content": "third"},
            {"chunk_id": 0, "chapter_hint": "Chapter 1", "manuscript_content": "first"},
            {"chunk_id": 1, "chapter_hint": "Chapter 2", "manuscript_content": "second"},
        ],
        "chunk_extractions": [
            {"chunk_id": 2, "manuscript_content": "third"},
            {"chunk_id": 0, "manuscript_content": "first"},
            {"chunk_id": 1, "manuscript_content": "second"},
        ],
    }

    result = asyncio.run(w1_import.node_build_manuscript(state))

    assert [chapter["title"] for chapter in result["manuscript_chapters"]] == [
        "Chapter 1",
        "Chapter 2",
        "Chapter 3",
    ]
    assert [chapter["chunk_ids"] for chapter in result["manuscript_chapters"]] == [[0], [1], [2]]
    assert [chapter["orderIndex"] for chapter in result["manuscript_chapters"]] == [0, 1, 2]
    assert [chapter["manuscript_content"] for chapter in result["manuscript_chapters"]] == ["first", "second", "third"]


def test_build_manuscript_supervisor_falls_back_to_chunks_without_extractions(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "import_mode": "import_all",
        "chunks": [
            {"chunk_id": 2, "chapter_hint": "第三章", "manuscript_content": "第三章原文"},
            {"chunk_id": 0, "chapter_hint": "第一章", "manuscript_content": "第一章原文"},
            {"chunk_id": 1, "chapter_hint": "第二章", "manuscript_content": "第二章原文"},
        ],
        "chunk_extractions": [],
    }

    result = asyncio.run(w1_import.node_build_manuscript(state))

    chapters = result["manuscript_chapters"]
    assert [chapter["title"] for chapter in chapters] == ["第一章", "第二章", "第三章"]
    assert [chapter["chunk_ids"] for chapter in chapters] == [[0], [1], [2]]
    assert [chapter["orderIndex"] for chapter in chapters] == [0, 1, 2]
    assert [chapter["manuscript_content"] for chapter in chapters] == ["第一章原文", "第二章原文", "第三章原文"]


def test_build_manuscript_enriches_and_dedupes_duplicate_chapter_numbers(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "fanren.txt"),
        "source_language": "zh",
        "import_mode": "import_all",
        "chunks": [
            {"chunk_id": 10, "chapter_hint": "第十章", "manuscript_content": "第十章 韩立进入神手谷。"},
            {"chunk_id": 9, "chapter_hint": "第十章", "manuscript_content": "第十章 墨大夫传授口诀。"},
        ],
        "chunk_extractions": [
            {"chunk_id": 10, "manuscript_content": "第十章 韩立进入神手谷。"},
            {"chunk_id": 9, "manuscript_content": "第十章 墨大夫传授口诀。"},
        ],
    }

    result = asyncio.run(w1_import.node_build_manuscript(state))
    chapters = result["manuscript_chapters"]

    assert len(chapters) == 1
    assert chapters[0]["title"] == "第十章"
    assert chapters[0]["chunk_ids"] == [9, 10]
    assert "韩立进入神手谷" in chapters[0]["manuscript_content"]
    assert "墨大夫传授口诀" in chapters[0]["manuscript_content"]
    assert chapters[0]["summary"]
    assert chapters[0]["goal"]
    assert "Chunks: 9, 10" in chapters[0]["notes"]


def test_compact_character_card_removes_repeated_age_fragments():
    card = {
        "summary": "韩立23岁被墨大夫收为弟子；韩立23岁在神手谷修炼；韩立23岁初显谨慎性格",
        "background": "",
        "role_in_story": "",
        "physical_description": "",
        "speech_style": "",
        "arc_notes": "",
        "personality_traits": [],
        "open_questions": [],
    }

    compacted = w1_import._compact_character_card(card)

    assert compacted["summary"].count("23岁") == 1


def test_world_entity_candidates_are_routed_out_of_character_registry():
    registry = {
        "characters": {
            "char_sect": {
                "canonical_name": "七玄门",
                "summary": "江湖门派。",
                "confidence": 0.91,
            },
            "char_mo": {
                "canonical_name": "墨大夫",
                "summary": "神手谷医生。",
                "confidence": 0.91,
            },
        },
        "events": {
            "event_1": {
                "character_ids": ["char_sect", "char_mo"],
                "character_names": ["七玄门", "墨大夫"],
            }
        },
        "world": {},
        "world_detailed": {},
    }

    removed = w1_import._remove_world_entities_from_character_registry(registry)

    assert removed == {"char_sect": "七玄门"}
    assert "char_sect" not in registry["characters"]
    assert "char_mo" in registry["characters"]
    assert registry["world"]["七玄门"] == "organization"
    assert registry["world_detailed"]["七玄门"]["container_hint"] == "organizations"
    assert registry["events"]["event_1"]["character_ids"] == ["char_mo"]
    assert registry["events"]["event_1"]["character_names"] == ["墨大夫"]


def test_seed_character_from_relationship_evidence_skips_world_entities():
    registry = {"characters": {}, "world": {}, "world_detailed": {}}

    seeded = w1_import._seed_character_from_name(
        registry,
        "墨大夫",
        3,
        "zh",
        role_hint="师徒关系证据",
        confidence=0.8,
    )
    skipped = w1_import._seed_character_from_name(
        registry,
        "七玄门",
        3,
        "zh",
        role_hint="门派组织",
        confidence=0.8,
    )

    assert seeded is not None
    assert seeded["canonical_name"] == "墨大夫"
    assert skipped is None
    assert len(registry["characters"]) == 1


def test_default_world_container_specs_are_semantic_and_localized():
    specs = w1_import._default_world_container_specs("zh")
    by_key = {spec["importCategoryKey"]: spec for spec in specs}

    assert by_key["locations"]["name"] == "地理位置"
    assert by_key["organizations"]["name"] == "门派组织"
    assert w1_import._normalize_world_category("七玄门", "sect") == "organization"
    assert w1_import._normalize_world_category("七玄门", "地名") != "location"
    assert w1_import._normalize_world_category("掩月宗", "宗门") == "organization"
    assert w1_import._normalize_world_category("天南势力", "势力") == "faction"
    assert w1_import._normalize_world_category("长春功", "功法") == "cultivation_method"
    assert w1_import._normalize_world_category("七绝堂", "") == "location"
    assert w1_import._normalize_world_category("供奉堂", "organization") == "location"
    assert w1_import._normalize_world_category("小绿瓶", "法器") == "artifact"
    assert w1_import.WORLD_ONTOLOGY_LABELS["organization"]["zh"] == "组织"
    assert "门派" in w1_import.WORLD_ONTOLOGY_LABELS["organization"]["zh_description"]
    assert w1_import._world_container_key("organization") == "organizations"
    assert w1_import._world_container_key("faction") == "organizations"
    assert w1_import._world_container_key("artifact") == "items"
    assert w1_import._world_container_key("cultivation_method") == "cultivation_methods"
    assert w1_import._world_container_key("system") == "rules"


def test_project_structure_digest_includes_existing_project_context(tmp_path):
    chars = tmp_path / "entities" / "characters"
    chars.mkdir(parents=True)
    (chars / "char_lin.json").write_text(
        '{"id":"char_lin","name":"Lin","summary":"Existing hero","tagIds":["tag_core"],"importImportance":"core"}',
        encoding="utf-8",
    )
    world = tmp_path / "entities" / "world"
    world.mkdir(parents=True)
    (world / "containers.json").write_text('[{"id":"cont_lore","name":"Lore","type":"notebook"}]', encoding="utf-8")
    (world / "world_city.json").write_text('{"id":"world_city","name":"Capital","description":"Central city"}', encoding="utf-8")
    timeline = tmp_path / "entities" / "timeline"
    timeline.mkdir(parents=True)
    (timeline / "branches.json").write_text('[{"id":"branch_main","name":"Main"}]', encoding="utf-8")
    (tmp_path / "entities" / "relationships.json").write_text(
        '[{"id":"rel_1","sourceId":"char_lin","targetId":"char_mei","type":"ally"}]',
        encoding="utf-8",
    )
    system = tmp_path / "system"
    system.mkdir()
    (system / "issues.json").write_text('[{"severity":"HIGH"}]', encoding="utf-8")
    (system / "inbox.json").write_text('[{"status":"pending","riskLevel":"medium"}]', encoding="utf-8")

    digest = w1_import._build_project_structure_digest({"project_path": str(tmp_path)}, "import_test")

    assert digest["counts"]["characters"] == 1
    assert digest["counts"]["world_containers"] == 1
    assert digest["counts"]["world_items"] == 1
    assert '"proposal_risk_summary"' in digest["content"]
    assert '"Lin"' in digest["content"]


def test_parse_json_response_repairs_common_model_drift():
    raw = """```json
    {
      "existing_character_updates": [],
      "new_characters": [
        {"canonical_name": "Lin", "aliases": ["Forest"],}
      ],
    }
    ```"""

    parsed = w1_import._parse_json_response(raw)

    assert parsed["new_characters"][0]["canonical_name"] == "Lin"


def test_character_card_proposals_stay_slim_by_default(tmp_path, monkeypatch):
    captured_ops: list[dict] = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {
            "id": f"proposal_{op['entity_id']}",
            "confidence": op["confidence"],
        }

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    (tmp_path / "novel.txt").write_text("Chapter 1\nA young cultivator appears.", encoding="utf-8")
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "novel.txt"),
        "import_run_id": "import_test",
        "entity_registry": {
            "characters": {
                "char_lin": {
                    "canonical_name": "Lin",
                    "aliases": [],
                    "summary": "A young cultivator appears.",
                    "background": "Overly detailed background from a stale cache.",
                    "personality_traits": ["careful"],
                    "goals": ["become immortal"],
                    "fears": ["failure"],
                    "secrets": ["hidden bloodline"],
                    "speech_style": "formal",
                    "arc_notes": "will rise",
                    "notes": ["[chunk 1] first appears"],
                    "open_questions": ["Is Lin the protagonist?"],
                    "confidence": 0.8,
                    "importance": "supporting",
                    "tag_ids": [],
                }
            },
            "events": {},
        },
        "manuscript_chapters": [],
        "relationships": [],
        "character_tags": [],
        "timeline_branches": [],
        "world_settings": {},
        "world_containers": [],
        "chunk_extractions": [],
        "import_review_report": {},
        "proposals": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_write_to_project(state))

    # node_write_to_project now returns compact receipts (no 'operations' key).
    # Verify the receipt is present and is compact.
    char_receipts = [r for r in result["proposals"] if r.get("entity_type") == "character"]
    assert len(char_receipts) == 1
    assert "id" in char_receipts[0]
    assert "operations" not in char_receipts[0]

    # The op passed to propose_write must strip deep fields (goals/fears/secrets).
    char_ops = [op for op in captured_ops if op.get("entity_type") == "character"]
    assert len(char_ops) == 1
    data = char_ops[0]["data"]
    assert data.get("goals", []) == []
    assert data.get("fears", []) == []
    assert data.get("secrets", []) == []


def test_character_proposals_serialize_final_flash_experience_for_acceptance(tmp_path, monkeypatch):
    captured_ops: list[dict] = []

    async def capture_proposal(op, _project_path):
        captured_ops.append(op)
        return {"id": f"proposal_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture_proposal)
    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_han_li": {
                    "canonical_name": "韩立",
                    "background": "十岁农家少年，被三叔带入七玄门考验。",
                    "experience": [
                        "爬崖测试差一点通过，但表现突出被留为记名弟子",
                        {"chapter": "第四章", "fact": "被墨大夫选为炼药童子", "evidence": "evc_han_li"},
                    ],
                    "experiences": ["爬崖测试差一点通过，但表现突出被留为记名弟子"],
                    "profile_field_evidence": {"experience": ["evc_han_li"]},
                    "notes": ["[window pwin_final] 被墨大夫选为炼药童子"],
                    "evidence_refs": ["evc_han_li"],
                    "confidence": 1.0,
                    "importance": "core",
                    "tag_ids": [],
                },
                "char_mo_daifu": {
                    "canonical_name": "墨大夫",
                    "background": "七玄门供奉，收韩立和张铁为记名弟子。",
                    "experiences": ["曾救过门主王陆性命", "住处为神手谷，专事炼药"],
                    "profile_field_evidence": {"experience": ["evc_mo_daifu"]},
                    "notes": ["[window pwin_final] 曾救过门主王陆性命"],
                    "evidence_refs": ["evc_mo_daifu"],
                    "confidence": 0.95,
                    "importance": "major",
                    "tag_ids": [],
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    character_data = {
        op["data"]["name"]: op["data"]
        for op in captured_ops
        if op.get("entity_type") == "character"
    }
    han_li = character_data["韩立"]
    mo_daifu = character_data["墨大夫"]

    # This is the accepted frontend Character.experience contract: typed rows,
    # not the extractor's experience/experiences string aliases.
    assert han_li["experience"] == [
        {"id": "char_han_li_experience_1", "chapter": "", "fact": "爬崖测试差一点通过，但表现突出被留为记名弟子"},
        {"id": "char_han_li_experience_2", "chapter": "第四章", "fact": "被墨大夫选为炼药童子", "evidence": "evc_han_li"},
    ]
    assert mo_daifu["experience"] == [
        {"id": "char_mo_daifu_experience_1", "chapter": "", "fact": "曾救过门主王陆性命"},
        {"id": "char_mo_daifu_experience_2", "chapter": "", "fact": "住处为神手谷，专事炼药"},
    ]
    assert han_li["profile_field_evidence"] == {"experience": ["evc_han_li"]}
    assert mo_daifu["profile_field_evidence"] == {"experience": ["evc_mo_daifu"]}
    for data in character_data.values():
        assert "experiences" not in data
        assert all(set(row).issuperset({"id", "chapter", "fact"}) for row in data["experience"])


def test_character_proposals_backfill_latest_live_smoke_profiles_from_evidenced_window_notes(tmp_path, monkeypatch):
    captured_ops: list[dict] = []
    source_span = {
        "raw_source_hash": "7b78ecafbc0cb16e3f0f9e853273aa63e562ee6c03b7e2264535b5666503a84f",
        "absolute_start": 9,
        "absolute_end": 74,
        "substring_hash": "bdddc251e501701943da7213130d7d11c73b4d8f494eff28bb5ad7007beedfd2",
    }

    async def capture_proposal(op, _project_path):
        captured_ops.append(op)
        return {"id": f"proposal_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture_proposal)
    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_de7b4872": {
                    "canonical_name": "韩立",
                    "aliases": ["二愣子", "韩立", "韩悝"],
                    "summary": "十岁农家少年，皮肤黝黑，外表不起眼但早熟聪明，向往外面世界",
                    "background": "给妹妹摘浆果，体现疼爱家人",
                    "personality_traits": ["早熟", "聪明", "坚忍"],
                    "role_in_story": "故事主角，通过考验进入七玄门",
                    "notes": [
                        "[window pwin_a97f52c6853e] 被村里人叫'二愣子'，但实际不愣。",
                        "[window pwin_a97f52c6853e] 给妹妹摘浆果，体现疼爱家人。",
                    ],
                    "evidence_refs": ["evc_6ac5183598fb"],
                    "source_span": source_span,
                    "profile_field_evidence": {"background": ["evc_6ac5183598fb", source_span]},
                    "confidence": 0.95,
                    "importance": "core",
                    "tag_ids": [],
                },
                "char_569a1ea1": {
                    "canonical_name": "墨大夫",
                    "aliases": ["墨老", "墨大夫"],
                    "summary": "七玄门供奉，医术高超，传授韩立无名口诀，态度神秘狂热",
                    "background": "",
                    "personality_traits": ["面无表情", "狂热", "深藏不露"],
                    "role_in_story": "韩立的师父，传授口诀",
                    "notes": [
                        "[window pwin_1baadfe3095f] 墨大夫对无名口诀极为重视，显示出异乎寻常的狂热",
                        "Open question: 墨大夫的真实目的？为什么需要这种口诀修炼者？",
                    ],
                    "evidence_refs": ["evc_3e4149a1b364"],
                    "source_span": {**source_span, "absolute_start": 10355, "absolute_end": 10423, "substring_hash": "ab4a0f2fbd4716f2b6e4ce8ad3fb86e812bc31198f59147948952b5b363f0b17"},
                    "confidence": 0.95,
                    "importance": "major",
                    "tag_ids": [],
                },
                "char_sparse": {
                    "canonical_name": "稀疏配角",
                    "summary": "性格古怪的路人",
                    "background": "",
                    "personality_traits": ["冷漠"],
                    "notes": ["[window pwin_sparse] 性格冷漠，给人难以亲近的感觉。"],
                    "evidence_refs": ["evc_sparse"],
                    "source_span": source_span,
                    "confidence": 0.7,
                    "importance": "supporting",
                    "tag_ids": [],
                },
                "char_9c418035": {
                    "canonical_name": "张铁",
                    "summary": "韩立密友，修炼象甲功，承受巨大痛苦",
                    "background": "韩立的朋友和同门",
                    "personality_traits": ["意志坚强", "憨厚"],
                    "notes": [
                        "[window pwin_493dd0969609] 在无名口诀上毫无进展",
                        "[window pwin_493dd0969609] 被墨大夫允诺另传心法",
                    ],
                    "evidence_refs": ["evc_67317f8af15e", "evc_b188c2a1b3d9"],
                    "source_span": {
                        **source_span,
                        "absolute_start": 9115,
                        "absolute_end": 9205,
                        "substring_hash": "38d88ec98b23dbb54d68a3aa00d692cc6aefb6ec7aab821bd39b9c76a7efb175",
                    },
                    "profile_field_evidence": {"background": ["evc_67317f8af15e", source_span]},
                    "confidence": 0.95,
                    "importance": "supporting",
                    "groupKey": "Supporting Cast",
                    "tag_ids": [],
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    character_data = {
        op["data"]["name"]: op["data"]
        for op in captured_ops
        if op.get("entity_type") == "character"
    }
    han_li = character_data["韩立"]
    mo_daifu = character_data["墨大夫"]
    sparse = character_data["稀疏配角"]
    zhang_tie = character_data["张铁"]

    assert han_li["experience"] == [{
        "id": "char_de7b4872_experience_1",
        "chapter": "",
        "fact": "给妹妹摘浆果",
        "evidence": "evc_6ac5183598fb",
    }]
    assert mo_daifu["experience"] == [{
        "id": "char_569a1ea1_experience_1",
        "chapter": "",
        "fact": "墨大夫对无名口诀极为重视",
        "evidence": "evc_3e4149a1b364",
    }]
    assert mo_daifu["background"] == "七玄门供奉"
    assert "狂热" not in mo_daifu["background"]
    for data, evidence_ref in ((han_li, "evc_6ac5183598fb"), (mo_daifu, "evc_3e4149a1b364")):
        assert data["experience"]
        assert all(set(row).issuperset({"id", "chapter", "fact", "evidence"}) for row in data["experience"])
        assert all(row["evidence"] == evidence_ref for row in data["experience"])
        assert evidence_ref in data["profile_field_evidence"]["experience"]
        assert data["sourceSpan"]["substring_hash"] in {
            proof["substring_hash"]
            for proof in data["profile_field_evidence"].get("experience", [])
            if isinstance(proof, dict)
        }
    assert sparse["experience"] == []
    assert sparse["background"] == ""
    assert zhang_tie["experience"] == [
        {
            "id": "char_9c418035_experience_1",
            "chapter": "",
            "fact": "在无名口诀上毫无进展",
            "evidence": "evc_67317f8af15e",
        },
        {
            "id": "char_9c418035_experience_2",
            "chapter": "",
            "fact": "被墨大夫允诺另传心法",
            "evidence": "evc_67317f8af15e",
        },
    ]
    assert zhang_tie["background"] == "韩立的朋友和同门"
    assert zhang_tie["profile_field_evidence"]["experience"] == [
        "evc_67317f8af15e",
        zhang_tie["sourceSpan"],
    ]


def test_character_experience_note_fallback_has_stable_ids_and_a_small_cap():
    source_span = {
        "raw_source_hash": "source_hash",
        "absolute_start": 10,
        "absolute_end": 20,
        "substring_hash": "substring_hash",
    }
    experience, background, profile_field_evidence = w1_import._backfill_character_profile_at_write_boundary(
        "char_major",
        {
            "canonical_name": "主角",
            "importance": "core",
            "summary": "农家少年",
            "notes": [
                "[window pwin_1] 参加入门测试。",
                "[window pwin_1] 进入宗门。",
                "[window pwin_1] 成为记名弟子。",
                "[window pwin_1] 学习基础口诀。",
            ],
            "evidence_refs": ["evc_major"],
            "source_span": source_span,
        },
    )

    assert experience == [
        {"id": "char_major_experience_1", "chapter": "", "fact": "参加入门测试。", "evidence": "evc_major"},
        {"id": "char_major_experience_2", "chapter": "", "fact": "进入宗门。", "evidence": "evc_major"},
        {"id": "char_major_experience_3", "chapter": "", "fact": "成为记名弟子。", "evidence": "evc_major"},
    ]
    assert background == "农家少年"
    assert profile_field_evidence["experience"] == ["evc_major", source_span]
    assert w1_import._action_or_state_note("[window pwin_1] 性格冷漠，给人难以亲近的感觉。") == ""
    assert w1_import._action_or_state_note("[chunk 1] 抵达七玄门。") == "抵达七玄门。"


def test_character_evidence_card_restores_profile_provenance_and_supported_fields():
    source_span = {
        "raw_source_hash": "source_hash",
        "absolute_start": 0,
        "absolute_end": 100,
        "substring_hash": "substring_hash",
    }
    entry = w1_import._attach_character_evidence_card(
        {
            "canonical_name": "三叔",
            "importance": "supporting",
            "summary": "韩立的亲三叔，七玄门外门弟子，经营春香酒楼",
            "notes": ["[chunk 1] 准时到达青牛镇并带韩立进入七玄门。"],
        },
        "char_uncle",
        [{
            "id": "evc_uncle",
            "kind": "character",
            "candidate_ids": ["char_uncle"],
            "source_span": source_span,
        }],
    )

    experience, background, profile_field_evidence = w1_import._backfill_character_profile_at_write_boundary(
        "char_uncle", entry,
    )
    assert background == "韩立的亲三叔"
    assert experience == [{
        "id": "char_uncle_experience_1",
        "chapter": "",
        "fact": "准时到达青牛镇并带韩立进入七玄门。",
        "evidence": "evc_uncle",
    }]
    assert entry["evidence_refs"] == ["evc_uncle"]
    assert entry["source_span"] == source_span
    assert profile_field_evidence["background"] == ["evc_uncle", source_span]
    assert profile_field_evidence["experience"] == ["evc_uncle", source_span]


def test_character_card_compaction_caps_long_running_import_fields():
    entry = {
        "summary": "\n".join(f"第{i}章新增经历，韩立继续成长并面对新的压力。" for i in range(20)),
        "background": "\n".join(f"背景补充 {i}，用于证明不应无限追加。" for i in range(12)),
        "role_in_story": "主角\n主角\n承担修炼线、瓶子线、墨大夫威胁线的核心视角。",
        "physical_description": "普通农家少年。\n普通农家少年。",
        "speech_style": "谨慎少言。\n谨慎少言。",
        "arc_notes": "\n".join(f"arc note {i}" for i in range(20)),
        "personality_traits": [f"谨慎但会在复杂压力下观察局势变化 {i}" for i in range(30)],
        "open_questions": [f"问题 {i}" for i in range(10)],
        "goals": ["become immortal"],
        "fears": ["failure"],
        "secrets": ["hidden bloodline"],
    }

    compacted = w1_import._compact_character_card(entry)

    assert len(compacted["summary"]) <= 180
    assert len(compacted["background"]) <= 160
    assert len(compacted["role_in_story"]) <= 120
    assert len(compacted["arc_notes"]) <= 140
    assert len(compacted["personality_traits"]) == 10
    assert all(len(trait) <= 24 for trait in compacted["personality_traits"])
    assert len(compacted["open_questions"]) == 4
    assert compacted["goals"] == []
    assert compacted["fears"] == []
    assert compacted["secrets"] == []


def test_write_to_project_preserves_chapter_content_and_world_container_routing(tmp_path, monkeypatch):
    proposals = []

    async def fake_propose_write(op, _project_path):
        proposal = {
            "id": f"proposal_{op['entity_id']}",
            "operations": [{"entityType": op["entity_type"], "fields": op["data"]}],
            "depends_on": op.get("depends_on", []),
            "confidence": op["confidence"],
        }
        proposals.append(proposal)
        return proposal

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    (tmp_path / "凡人修仙传_前50章.txt").write_text("第一章正文\n第二章正文", encoding="utf-8")
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "凡人修仙传_前50章.txt"),
        "import_run_id": "import_quality",
        "source_language": "zh",
        "entity_registry": {
            "characters": {},
            "events": {},
            "world": {
                "七玄门": "organization",
                "青牛镇": "location",
                "长春功": "功法",
            },
            "world_detailed": {
                "七玄门": {"category": "organization", "description": "江湖门派。"},
                "青牛镇": {"category": "location", "description": "故事早期地点。"},
                "长春功": {"category": "功法", "description": "修炼功法。"},
            },
        },
        "manuscript_chapters": [
            {"chapter_id": "chap_2", "title": "第二章", "orderIndex": 1, "chunk_ids": [1], "manuscript_content": "第二章正文"},
            {"chapter_id": "chap_1", "title": "第一章", "orderIndex": 0, "chunk_ids": [0], "manuscript_content": "第一章正文"},
        ],
        "relationships": [],
        "character_tags": [],
        "timeline_branches": [],
        "world_settings": {},
        "world_containers": w1_import._default_world_container_specs("zh"),
        "chunk_extractions": [],
        "import_review_report": {},
        "proposals": [],
        "errors": [],
    }

    asyncio.run(w1_import.node_write_to_project(state))
    world_items = [
        proposal["operations"][0]["fields"]
        for proposal in proposals
        if proposal["operations"][0]["entityType"] == "world_item"
    ]
    chapters = [
        proposal["operations"][0]["fields"]
        for proposal in proposals
        if proposal["operations"][0]["entityType"] == "chapter"
    ]

    by_name = {item["name"]: item for item in world_items}
    assert by_name["七玄门"]["category"] == "organization"
    assert by_name["七玄门"]["containerId"] == "cont_import_organizations"
    assert by_name["青牛镇"]["containerId"] == "cont_import_locations"
    assert by_name["长春功"]["containerId"] == "cont_import_cultivation_methods"
    assert [chapter["title"] for chapter in chapters] == ["第一章", "第二章"]
    assert [chapter["content"] for chapter in chapters] == ["第一章正文", "第二章正文"]
    assert chapters[0]["manuscriptContent"] == "第一章正文"


def test_timeline_architect_dedupes_and_fills_required_fields(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_test",
        "entity_registry": {
            "events": {
                "event_a": {
                    "title": "Hero enters the city",
                    "description": "The hero reaches the capital.",
                    "character_ids": ["char_hero"],
                    "location_hint": "Capital",
                    "temporal_hint": "Chapter 1",
                    "confidence": 0.91,
                    "chunk_id": 0,
                },
                "event_b": {
                    "title": "Hero enters the city",
                    "description": "The hero reaches the capital.",
                    "character_ids": ["char_hero"],
                    "location_hint": "Capital",
                    "temporal_hint": "Chapter 1",
                    "confidence": 0.88,
                    "chunk_id": 0,
                },
            },
            "character_id_map": {"char_hero": "char_existing_hero"},
        },
        "timeline_branches": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    events = result["entity_registry"]["events"]

    assert list(events) == ["event_a"]
    event = events["event_a"]
    assert event["branchId"] == "branch_import_main"
    assert event["orderIndex"] == 0
    assert event["participantCharacterIds"] == ["char_existing_hero"]
    assert event["linkedSceneIds"] == []
    assert event["tags"] == ["imported"]
    assert result["timeline_architecture"]["discarded_duplicates"][0]["event_id"] == "event_b"


def test_timeline_architect_merges_near_duplicate_chinese_titles(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_near_dup_titles",
        "entity_registry": {
            "events": {
                "event_a": {
                    "title": "王护法接走韩立前往七玄门",
                    "description": "王护法带韩立离村前往七玄门。",
                    "character_ids": ["char_han"],
                    "temporal_hint": "第一章",
                    "confidence": 0.92,
                    "importanceScore": 90,
                    "chunk_id": 0,
                },
                "event_b": {
                    "title": "王护法接韩立前往七玄门",
                    "description": "王护法接韩立去七玄门。",
                    "character_ids": ["char_han"],
                    "temporal_hint": "第二章",
                    "confidence": 0.91,
                    "importanceScore": 88,
                    "chunk_id": 1,
                },
            },
            "character_id_map": {"char_han": "char_han"},
        },
        "timeline_branches": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    events = result["entity_registry"]["events"]
    discarded = result["timeline_architecture"]["discarded_duplicates"]

    assert list(events) == ["event_a"]
    assert any(item.get("event_id") == "event_b" and item.get("reason") == "high-confidence duplicate title" for item in discarded)


def test_timeline_architect_prunes_imported_branches_without_canonical_events(tmp_path):
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_prune_empty_branch",
        "entity_registry": {
            "events": {
                "event_main": {
                    "title": "韩立参加七玄门选拔",
                    "description": "韩立离开家乡，参加七玄门弟子选拔。",
                    "character_ids": ["char_han"],
                    "temporal_hint": "第一章",
                    "confidence": 0.95,
                    "importanceScore": 95,
                    "chunk_id": 0,
                },
            },
            "character_id_map": {"char_han": "char_han"},
        },
        "timeline_branches": [
            {"id": "branch_unused", "name": "未使用支线", "mode": "forked"},
        ],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    branch_ids = {branch["id"] for branch in result["timeline_architecture"]["branches"]}
    active_ids = {event["branchId"] for event in result["timeline_architecture"]["canonical_events"]}
    assert "branch_unused" not in branch_ids
    assert branch_ids - {result["timeline_architecture"]["root_branch_id"]} <= active_ids


def test_timeline_architect_creates_semantic_branches_for_dense_import(tmp_path):
    events = {}
    for idx in range(8):
        events[f"event_{idx}"] = {
            "title": f"Sect conflict escalates {idx}",
            "description": "The sect alliance faces an enemy ambush.",
            "character_ids": ["char_hero"],
            "location_hint": "Cloud Sect",
            "temporal_hint": f"Chapter {idx + 1}",
            "chunk_position": "middle",
            "stakes": "sect power shift",
            "confidence": 0.92,
            "chunk_id": idx,
        }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_test_dense",
        "entity_registry": {"events": events, "character_id_map": {"char_hero": "char_existing_hero"}},
        "timeline_branches": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    branches = result["timeline_branches"]
    assigned_branch_ids = {event["branchId"] for event in result["entity_registry"]["events"].values()}

    assert len(branches) > 1
    assert assigned_branch_ids != {"branch_import_main"}
    assert result["timeline_architecture"]["density_policy"]["max_events_per_branch"] == 36


def test_timeline_ontology_coerces_illegal_event_class_and_sets_lane_hints():
    event, warnings = w1_import._normalize_timeline_event_ontology({
        "title": "七玄门冲突升级",
        "description": "七玄门内部势力冲突改变韩立处境。",
        "eventClass": "major_turning_point",
        "importanceScore": 82,
        "confidence": 0.91,
        "location_hint": "七玄门",
    })

    assert event["eventClass"] == "canonical_event"
    assert event["timelineClass"] == "canonical_event"
    assert event["arcRole"] == "faction"
    assert event["timelineLaneHint"] == "Faction / Organization"
    assert event["deterministicLaneHints"]["factionOrOrganization"] is True
    assert warnings


def test_timeline_architect_promotes_minimum_density_for_long_import(tmp_path):
    events = {}
    for idx in range(50):
        events[f"chapter_{idx}"] = {
            "title": f"第{idx + 1}章转折",
            "description": "章节证据显示主线处境发生变化。",
            "eventClass": "scene_beat",
            "timelineClass": "scene_beat",
            "arcId": "protagonist_origin" if idx < 10 else "cultivation_progress",
            "chapterRange": {"start": f"第{idx + 1}章", "end": f"第{idx + 1}章"},
            "importanceScore": 72,
            "character_ids": ["char_han"],
            "location_hint": "神手谷" if idx >= 10 else "山边小村",
            "temporal_hint": f"第{idx + 1}章",
            "confidence": 0.9,
            "chunk_id": idx,
        }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_long_density",
        "chunks": [{"chunk_id": idx} for idx in range(50)],
        "profile_config": {"event_density": "chapter_level"},
        "entity_registry": {"events": events, "character_id_map": {"char_han": "char_existing_han"}},
        "timeline_branches": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    canonical_events = list(result["entity_registry"]["events"].values())
    lane_hints = {event.get("timelineLaneHint") for event in canonical_events}

    assert len(canonical_events) > 3
    assert len(canonical_events) >= result["timeline_architecture"]["density_policy"]["minimum_canonical_events"]
    assert "Training / Power Progression" in lane_hints or any("Training" in hint for hint in lane_hints)
    assert any("promoted to canonical_event" in warning for warning in result["timeline_architecture"]["warnings"])


def test_timeline_architect_merges_han_li_origin_variants_and_demotes_scene_beats(tmp_path):
    variants = [
        ("event_offer_a", "三叔提议韩立参加七玄门考验", "三叔建议韩立参加一个月后的七玄门考验。", "canonical_event", 92),
        ("event_offer_b", "三叔提议韩立参加七玄门测试", "韩胖子说服韩父同意韩立参加七玄门测试。", "canonical_event", 89),
        ("event_offer_c", "三叔提议送韩立入七玄门", "三叔提议带韩立参加内门弟子考验。", "canonical_event", 88),
        ("event_leave_a", "韩立离家前往七玄门", "韩立告别父母，随三叔离开村子。", "canonical_event", 91),
        ("event_leave_b", "韩立随三叔离家", "韩立乘马车离开家乡前往青牛镇。", "canonical_event", 86),
        ("event_join", "韩立加入七玄门", "韩立通过安排正式进入七玄门。", "canonical_event", 82),
        ("event_mo", "墨大夫收徒", "墨大夫将韩立收为弟子。", "canonical_event", 84),
        ("event_training", "韩立每日练功", "韩立重复练习口诀。", "scene_beat", 35),
    ]
    events = {}
    for idx, (event_id, title, description, timeline_class, score) in enumerate(variants):
        events[event_id] = {
            "title": title,
            "description": description,
            "eventClass": "journey_departure" if "离家" in title else "inciting_choice",
            "timelineClass": timeline_class,
            "arcId": "protagonist_origin",
            "timelineLaneHint": "Family Origin",
            "dedupeKey": "",
            "chapterRange": {"start": "第一章", "end": "第一章"},
            "importanceScore": score,
            "character_ids": ["char_han", "char_uncle"],
            "location_hint": "山边小村",
            "temporal_hint": "第一章",
            "confidence": 0.95,
            "chunk_id": idx,
        }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_han_li_variants",
        "entity_registry": {"events": events},
        "timeline_branches": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    canonical_titles = {event["title"] for event in result["entity_registry"]["events"].values()}
    discarded = result["timeline_architecture"]["discarded_duplicates"]

    assert len(canonical_titles) == 4
    assert "韩立每日练功" not in canonical_titles
    assert any(item.get("merged_into") == "event_offer_a" for item in discarded)
    assert any(item.get("merged_into") == "event_leave_a" for item in discarded)
    assert any(item.get("timelineClass") == "scene_beat" and item.get("event_id") == "event_training" for item in discarded)
    assert all(event["branchId"] == "branch_import_main" for event in result["entity_registry"]["events"].values())


def test_timeline_architect_distributes_dense_lanes_and_enforces_branch_budget(tmp_path):
    events = {}
    for idx in range(40):
        events[f"mentor_{idx}"] = {
            "title": f"墨大夫威胁升级 {idx}",
            "description": "墨大夫对韩立施压，推动师徒威胁线升级。",
            "timelineClass": "canonical_event",
            "eventClass": "confrontation",
            "arcId": "mentor_control",
            "timelineLaneHint": "Mentor Threat",
            "chapterRange": {"start": f"第{idx + 1}章", "end": f"第{idx + 1}章"},
            "importanceScore": 72,
            "character_ids": ["char_han", "char_mo"],
            "location_hint": "神手谷",
            "temporal_hint": f"第{idx + 1}章",
            "confidence": 0.91,
            "chunk_id": idx,
        }
    for idx in range(8):
        events[f"sect_{idx}"] = {
            "title": f"七玄门冲突 {idx}",
            "description": "七玄门内部势力冲突影响韩立处境。",
            "timelineClass": "canonical_event",
            "eventClass": "faction_move",
            "arcId": "sect_conflict",
            "timelineLaneHint": "Sect Conflict",
            "chapterRange": {"start": f"第{idx + 1}章", "end": f"第{idx + 1}章"},
            "importanceScore": 74,
            "character_ids": ["char_han"],
            "location_hint": "七玄门",
            "temporal_hint": f"第{idx + 1}章",
            "confidence": 0.91,
            "chunk_id": idx + 40,
        }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "import_dense_lanes",
        "entity_registry": {"events": events},
        "timeline_branches": [],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_architect_timeline(state))
    canonical_events = list(result["entity_registry"]["events"].values())
    branch_counts = {}
    for event in canonical_events:
        branch_counts[event["branchId"]] = branch_counts.get(event["branchId"], 0) + 1

    assert len(branch_counts) >= 2
    assert max(branch_counts.values()) <= result["timeline_architecture"]["density_policy"]["max_events_per_branch"]
    assert any(item.get("reason", "").startswith("branch event budget overflow") for item in result["timeline_architecture"]["scene_beats"])
    assert all("laneId" in branch and "rankStart" in branch and "rankEnd" in branch for branch in result["timeline_architecture"]["branches"])


def test_character_prompt_preserves_identity_group_and_card_contract():
    prompt = w1_prompts.W1_EXTRACT_CHARACTERS_DEEP

    required_terms = [
        "Project Digest Input Placeholders",
        "{{project_digest}}",
        "story_function",
        "protagonist",
        "mentor",
        "antagonist",
        "ally",
        "groupKey",
        "main_characters",
        "mentors_antagonists",
        "allies_family",
        "minor_characters",
        "alias_reconciliation_rationale",
        "OUTPUT RULES",
        "Do NOT translate",
        "existing_character_updates",
        "new_characters",
        "{source_language_label}",
        "{language_policy}",
    ]

    for term in required_terms:
        assert term in prompt


def test_all_five_deep_prompts_contain_language_policy_variables():
    prompts = {
        "W1_EXTRACT_CHARACTERS_DEEP": w1_prompts.W1_EXTRACT_CHARACTERS_DEEP,
        "W1_EXTRACT_EVENTS_DEEP": w1_prompts.W1_EXTRACT_EVENTS_DEEP,
        "W1_EXTRACT_WORLD_DEEP": w1_prompts.W1_EXTRACT_WORLD_DEEP,
        "W1_EXTRACT_RELATIONSHIPS_CHUNK": w1_prompts.W1_EXTRACT_RELATIONSHIPS_CHUNK,
        "W1_EXTRACT_SCENE_SUMMARIES": w1_prompts.W1_EXTRACT_SCENE_SUMMARIES,
    }

    for name, prompt in prompts.items():
        assert "{source_language_label}" in prompt, f"{name} missing {{source_language_label}}"
        assert "{language_policy}" in prompt, f"{name} missing {{language_policy}}"


def test_event_prompt_preserves_timeline_topology_contract():
    prompt = w1_prompts.W1_EXTRACT_EVENTS_DEEP

    required_terms = [
        "CANONICAL VS SCENE-BEAT DECISION",
        "eventClass",
        "timelineClass",
        "arcId",
        "timelineLaneHint",
        "causalPredecessorHints",
        "forkMergeHint",
        "dedupeKey",
        "chapterRange",
        "importanceScore",
        "mergeCandidateTitles",
        "canonical_event",
        "scene_beat",
    ]

    for term in required_terms:
        assert term in prompt


def test_relationship_and_scene_prompts_support_cross_validation():
    relationship_prompt = w1_prompts.W1_EXTRACT_RELATIONSHIPS_CHUNK
    scene_prompt = w1_prompts.W1_EXTRACT_SCENE_SUMMARIES

    for term in ["topologyRole", "aliasEvidence", "contradictionHint"]:
        assert term in relationship_prompt

    for term in [
        "canonicalEventRefs",
        "sceneBeatRefs",
        "timelineLaneHint",
        "arcId",
        "chapterRange",
    ]:
        assert term in scene_prompt


def test_cross_validation_prompt_and_artifact_contract_are_stable():
    prompt = w1_prompts.W1_CROSS_VALIDATE_IMPORT
    annotations = sidecar_state.CrossValidationArtifact.__annotations__

    required_fields = [
        "duplicate_characters",
        "duplicate_events",
        "missing_major_characters",
        "suspicious_groups",
        "contradictory_aliases",
        "event_merge_recommendations",
    ]

    for field in required_fields:
        assert field in prompt
        assert field in annotations

    assert "cross_validation" in sidecar_state.ImportState.__annotations__


# ── node_write_to_project compact receipts and manuscript ─────────────────────


def test_existing_project_snapshot_reads_canonical_character_tag_path(tmp_path):
    tags_path = tmp_path / "entities" / "character-tags.json"
    tags_path.parent.mkdir(parents=True)
    tags_path.write_text('[{"id":"tag_existing","name":"Existing"}]', encoding="utf-8")

    snapshot = w1_import._load_existing_project_snapshot(tmp_path)

    assert snapshot["character_tags"] == [{"id": "tag_existing", "name": "Existing"}]
    assert w1_import._proposal_graph_existing_ids(snapshot)["character_tag"] == {"tag_existing"}

def _make_write_state(tmp_path, *, entity_registry=None, manuscript_chapters=None):
    """Minimal state for node_write_to_project tests."""
    (tmp_path / "novel.txt").write_text("Chapter 1\nFixture source text.", encoding="utf-8")
    return {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "novel.txt"),
        "import_run_id": "import_compact",
        "source_language": "en",
        "entity_registry": entity_registry or {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "manuscript_chapters": manuscript_chapters or [],
        "relationships": [],
        "character_tags": [],
        "timeline_branches": [],
        "world_settings": {},
        "world_containers": [],
        "chunk_extractions": [],
        "import_review_report": {},
        "proposals": [],
        "errors": [],
    }


def test_node_write_to_project_returns_compact_receipts(tmp_path, monkeypatch):
    """proposals returned by node_write_to_project must be compact receipts, not full proposal dicts."""
    async def fake_propose_write(op, _project_path):
        return {
            "id": f"p_{op['entity_id']}",
            "operations": [{"entityType": op["entity_type"]}],
            "confidence": op["confidence"],
        }

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_a": {"canonical_name": "Alice", "confidence": 0.8, "importance": "core", "aliases": [], "tag_ids": []},
                "char_b": {"canonical_name": "Bob", "confidence": 0.7, "importance": "minor", "aliases": [], "tag_ids": []},
            },
            "events": {
                "ev_1": {"title": "A battle", "description": "Clash", "confidence": 0.8, "branchId": "branch_main", "orderIndex": 1},
            },
            "world": {"Rivendell": "location"},
            "world_detailed": {"Rivendell": {"category": "location", "description": "An elf city."}},
        },
    )

    result = asyncio.run(w1_import.node_write_to_project(state))
    receipts = result["proposals"]

    # All receipts must be compact (id, entity_type present; no operations key)
    assert len(receipts) > 0
    for receipt in receipts:
        assert "id" in receipt, f"receipt missing 'id': {receipt}"
        assert "entity_type" in receipt, f"receipt missing 'entity_type': {receipt}"
        assert "operations" not in receipt, f"receipt must not contain 'operations': {receipt}"

    entity_types = {r["entity_type"] for r in receipts}
    assert "character" in entity_types
    assert "timeline_event" in entity_types
    assert "world_item" in entity_types


def test_proposal_staging_preserves_recovery_checkpoint_until_acceptance(tmp_path, monkeypatch):
    async def fake_propose_write(op, _project_path):
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    checkpoint_path = tmp_path / "system" / "imports" / "lineage" / "attempts" / "attempt" / "checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text('{"status":"recoverable"}', encoding="utf-8")
    state = _make_write_state(tmp_path)
    state["checkpoint_path"] = str(checkpoint_path)

    asyncio.run(w1_import.node_write_to_project(state))

    assert checkpoint_path.read_text(encoding="utf-8") == '{"status":"recoverable"}'
    assert (tmp_path / "system" / "imports" / "import_compact" / "proposal_write_receipts.json").exists()


def test_matched_character_merge_writes_an_accepted_update_proposal(tmp_path, monkeypatch):
    operations: list[dict] = []

    async def capture_proposal(operation, _project_path):
        operations.append(operation)
        return {"id": f"p_{operation['entity_id']}", "status": "pending", "confidence": operation["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture_proposal)
    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "import_alice": {
                    "canonical_name": "Alice", "skip_create": True,
                    "existing_project_id": "char_existing", "confidence": 0.91,
                    "entity_merge_decision": {
                        "contract": "EntityMergeDecision/v1",
                        "fields": {
                            "aliases": {"value": ["Alicia"]}, "background": {"value": "New history"},
                            "experience": {"value": ["survived siege"]}, "traits": {"value": ["brave"]},
                            "notes": {"value": ["evidence note"]}, "confidence": {"value": 0.91},
                        },
                        "conflicts": [{"field": "background", "resolution": "preserve_and_append"}],
                    },
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    merge = next(operation for operation in operations if operation["entity_id"] == "char_existing")
    assert merge["op_type"] == "update"
    assert merge["data"]["aliases"] == ["Alicia"]
    assert merge["data"]["experience"] == ["survived siege"]
    assert merge["data"]["traits"] == ["brave"]
    assert merge["diagnostics"]["semantic_conflicts"]


def test_node_write_to_project_normalizes_event_branch_to_imported_root(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {},
            "events": {
                "event_stale": {
                    "title": "Stale branch event",
                    "description": "Timeline architect left branch_main on the event.",
                    "confidence": 0.8,
                    "branchId": "branch_main",
                    "orderIndex": 1,
                },
            },
            "world": {},
            "world_detailed": {},
        },
    )
    state["timeline_branches"] = [{
        "id": "branch_item",
        "name": "韩立修仙之路",
        "mode": "root",
        "sortOrder": 0,
    }]

    asyncio.run(w1_import.node_write_to_project(state))

    event_op = next(op for op in captured_ops if op["entity_type"] == "timeline_event")
    assert event_op["data"]["branchId"] == "branch_item"
    assert event_op["depends_on"] == ["branch_item"]


def test_node_write_to_project_uses_timeline_architect_event_ids_for_character_links(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_han": {
                    "canonical_name": "韩立", "confidence": 0.9,
                    "importance": "core", "aliases": [], "tag_ids": [],
                },
            },
            # These are already the canonical Timeline Architect results. The
            # writer must not perform another fuzzy-title dedupe pass.
            "events": {
                "event_disciple_confirmed": {
                    "title": "韩立被确认为墨大夫亲传弟子",
                    "description": "身份得到确认。",
                    "confidence": 0.9,
                    "branchId": "branch_main",
                    "orderIndex": 0,
                    "character_ids": ["char_han"],
                },
                "event_disciple_became": {
                    "title": "韩立成为墨大夫亲传弟子",
                    "description": "关系进入新的阶段。",
                    "confidence": 0.9,
                    "branchId": "branch_main",
                    "orderIndex": 1,
                    "character_ids": ["char_han"],
                },
            },
            "world": {},
            "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    emitted_event_ids = {
        op["entity_id"] for op in captured_ops if op["entity_type"] == "timeline_event"
    }
    character = next(op for op in captured_ops if op["entity_type"] == "character")
    assert emitted_event_ids == {"event_disciple_confirmed", "event_disciple_became"}
    assert set(character["data"]["linkedEventIds"]) == emitted_event_ids


def test_node_write_to_project_dedupes_duplicate_character_names_before_proposals(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_han_a": {"canonical_name": "韩立", "confidence": 0.8, "importance": "core", "aliases": ["二愣子"], "tag_ids": []},
                "char_han_b": {"canonical_name": "韩立", "confidence": 0.9, "importance": "core", "aliases": ["韩立"], "tag_ids": []},
            },
            "events": {
                "event_1": {
                    "title": "韩立离家",
                    "description": "韩立踏上旅途。",
                    "confidence": 0.9,
                    "branchId": "branch_main",
                    "orderIndex": 0,
                    "character_ids": ["char_han_a", "char_han_b"],
                },
            },
            "world": {},
            "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    character_ops = [op for op in captured_ops if op["entity_type"] == "character"]
    assert len(character_ops) == 1
    assert character_ops[0]["data"]["name"] == "韩立"
    event_op = next(op for op in captured_ops if op["entity_type"] == "timeline_event")
    assert event_op["data"]["participantCharacterIds"] == ["char_han_a"]


def test_node_infer_world_settings_preserves_existing_timeline_architect_branches(monkeypatch):
    async def fake_invoke_json_prompt(*_args, **_kwargs):
        return {
            "world_settings": {"projectType": "xianxia"},
            "suggested_world_containers": [],
            "inferred_timeline_branches": [
                {"id": "branch_world_settings", "name": "World Settings Branch", "mode": "root"},
            ],
        }

    monkeypatch.setattr(w1_import, "_HAS_DEEP_PROMPTS", True)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())
    monkeypatch.setattr(w1_import, "_invoke_json_prompt", fake_invoke_json_prompt)

    state = {
        "source_language": "zh",
        "manuscript_chapters": [{"manuscript_content": "第一章 韩立离家。"}],
        "chunk_extractions": [],
        "timeline_branches": [
            {"id": "branch_main", "name": "主线", "mode": "root"},
            {"id": "branch_training", "name": "修炼支线", "mode": "forked", "parentBranchId": "branch_main"},
        ],
        "errors": [],
        "progress": 0.9,
    }

    result = asyncio.run(w1_import.node_infer_world_settings(state))

    assert [branch["id"] for branch in result["timeline_branches"]] == ["branch_main", "branch_training"]


def test_node_write_to_project_stages_manuscript_before_acceptance(tmp_path, monkeypatch):
    """Pre-acceptance W1 manuscript output must remain staged."""
    import json

    async def fake_propose_write(op, _project_path):
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[
            {"chapter_id": "chap_1", "title": "Ch 1", "orderIndex": 0, "chunk_ids": [0], "manuscript_content": "Text of chapter one."},
            {"chapter_id": "chap_2", "title": "Ch 2", "orderIndex": 1, "chunk_ids": [1], "manuscript_content": "Text of chapter two."},
        ],
    )

    asyncio.run(w1_import.node_write_to_project(state))

    manuscript_path = tmp_path / "manuscript.json"
    assert not manuscript_path.exists(), "W1 must not write canonical manuscript.json before acceptance"
    staged_path = tmp_path / "system" / "imports" / "import_compact" / "staged_manuscript_projection.json"
    manuscript = json.loads(staged_path.read_text(encoding="utf-8"))
    assert len(manuscript["chapters"]) == 2
    assert manuscript["chapters"][0]["title"] == "Ch 1"


def test_staged_manuscript_projection_uses_project_local_raw_source_evidence(tmp_path, monkeypatch):
    """Acceptance must read an immutable raw-source copy within the import run."""
    async def fake_propose_write(op, _project_path):
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    original = tmp_path / "external-source.txt"
    original_bytes = "Chapter 1\nEvidence stays byte-for-byte identical.\n".encode("utf-8")
    original.write_bytes(original_bytes)
    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[
            {"chapter_id": "chap_evidence", "title": "Chapter 1", "orderIndex": 0, "chunk_ids": [0], "manuscript_content": "Evidence stays byte-for-byte identical."},
        ],
    )
    state["source_file_path"] = str(original)
    state["source_text"] = original_bytes.decode("utf-8")
    content = state["manuscript_chapters"][0]["manuscript_content"]
    start = state["source_text"].index(content)
    state["manuscript_chapters"][0]["source_span"] = sidecar_state.make_source_span(state["source_text"], start, start + len(content))

    asyncio.run(w1_import.node_write_to_project(state))

    run_dir = tmp_path / "system" / "imports" / "import_compact"
    evidence_path = run_dir / "raw_source.txt"
    projection = json.loads((run_dir / "staged_manuscript_projection.json").read_text(encoding="utf-8"))

    assert evidence_path.read_bytes() == original_bytes
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == hashlib.sha256(original_bytes).hexdigest()
    assert projection["source_file_path"] == str(evidence_path)
    assert projection["source_file_path"] != str(original)
    assert projection["chapters"][0]["source_span"]["raw_source_hash"] == hashlib.sha256(original_bytes).hexdigest()

    original.write_bytes(b"Changed source must not overwrite recorded evidence.")
    with pytest.raises(ValueError, match="immutable"):
        w1_import._stage_raw_source_evidence(state)
    assert evidence_path.read_bytes() == original_bytes


def test_staged_manuscript_projection_hard_fails_when_raw_source_is_missing(tmp_path, monkeypatch):
    """A projection without readable raw evidence must never be staged for acceptance."""
    async def fake_propose_write(_op, _project_path):
        raise AssertionError("raw source validation must fail before proposal writes")

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    state = _make_write_state(tmp_path, manuscript_chapters=[])
    (tmp_path / "novel.txt").unlink()

    with pytest.raises(FileNotFoundError):
        asyncio.run(w1_import.node_write_to_project(state))

    assert not (tmp_path / "system" / "imports" / "import_compact" / "staged_manuscript_projection.json").exists()


def test_sort_manuscript_chapters_handles_mixed_chinese_and_arabic_titles():
    chapters = [
        {"title": "第七章", "manuscript_content": "7"},
        {"title": "第三章", "manuscript_content": "3"},
        {"title": "第十章", "manuscript_content": "10"},
        {"title": "Chapter 5", "manuscript_content": "5"},
    ]
    ordered = w1_import._sort_manuscript_chapters(chapters)
    assert [chapter["title"] for chapter in ordered] == ["第三章", "Chapter 5", "第七章", "第十章"]


def test_chunk_sort_key_extracts_numeric_suffixes():
    chunks = [{"chunk_id": "chunk_10"}, {"chunk_id": "chunk_2"}, {"chunk_id": "chunk_1"}]
    ordered = sorted(chunks, key=lambda chunk: w1_import._chunk_sort_key(chunk["chunk_id"]))
    assert [chunk["chunk_id"] for chunk in ordered] == ["chunk_1", "chunk_2", "chunk_10"]


def test_node_write_to_project_proposes_chapter_and_content_scene(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[
            {
                "chapter_id": "chap_3",
                "title": "第三章",
                "orderIndex": 2,
                "chunk_ids": ["chunk_3"],
                "manuscript_content": "韩立进入七绝堂，发现长春功残卷。",
            },
        ],
        entity_registry={"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
    )
    state["source_language"] = "zh"

    asyncio.run(w1_import.node_write_to_project(state))

    chapter_op = next(op for op in captured_ops if op["entity_type"] == "chapter")
    scene_op = next(op for op in captured_ops if op["entity_type"] == "scene")
    assert chapter_op["data"]["title"] == "第三章"
    assert chapter_op["data"]["summary"]
    assert chapter_op["data"]["goal"]
    assert scene_op["data"]["chapterId"] == "chap_3"
    assert scene_op["data"]["content"] == "韩立进入七绝堂，发现长春功残卷。"
    assert scene_op["depends_on"] == ["chap_3"]


def test_node_write_to_project_does_not_link_scene_and_event_from_shared_chunk_alone(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[{
            "chapter_id": "chap_1", "scene_id": "scene_1", "title": "第一章",
            "chunk_ids": [0], "manuscript_content": "正文",
        }],
        entity_registry={
            "characters": {},
            "events": {
                "event_1": {
                    "title": "入门测试", "description": "", "confidence": 0.9,
                    "branchId": "branch_main", "orderIndex": 0, "chunk_id": 0,
                },
            },
            "world": {}, "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    event_op = next(op for op in captured_ops if op["entity_type"] == "timeline_event")
    scene_op = next(op for op in captured_ops if op["entity_type"] == "scene")
    assert event_op["data"]["linkedSceneIds"] == []
    assert event_op["data"].get("sceneLinkEvidence", {}) == {}
    assert scene_op["data"]["linkedEventIds"] == []
    assert scene_op["data"].get("eventLinkEvidence", {}) == {}


def test_node_write_to_project_does_not_link_scene_event_without_durable_provenance(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[{
            "chapter_id": "chap_1", "scene_id": "scene_1", "title": "第一章",
            "manuscript_content": "正文",
        }],
        entity_registry={
            "characters": {},
            "events": {"event_1": {"title": "入门测试", "description": "", "confidence": 0.9, "branchId": "branch_main", "orderIndex": 0}},
            "world": {}, "world_detailed": {},
        },
    )

    asyncio.run(w1_import.node_write_to_project(state))

    event_op = next(op for op in captured_ops if op["entity_type"] == "timeline_event")
    scene_op = next(op for op in captured_ops if op["entity_type"] == "scene")
    assert event_op["data"]["linkedSceneIds"] == []
    assert scene_op["data"]["linkedEventIds"] == []


def test_scene_event_linking_uses_exact_span_not_shared_chunk_with_multiple_scenes():
    raw_hash = "source_hash"
    state = {
        "entity_registry": {"events": {"event_1": {
            "chunk_id": 0,
            "source_span": {"raw_source_hash": raw_hash, "absolute_start": 6, "absolute_end": 8},
        }}},
        "manuscript_chapters": [
            {"chapter_id": "chap_1", "scene_id": "scene_1", "chunk_ids": [0], "source_span": {"raw_source_hash": raw_hash, "absolute_start": 0, "absolute_end": 5}},
            {"chapter_id": "chap_2", "scene_id": "scene_2", "chunk_ids": [0], "source_span": {"raw_source_hash": raw_hash, "absolute_start": 5, "absolute_end": 10}},
        ],
    }

    linked = w1_import._link_scene_events_from_provenance(state)

    event = linked["entity_registry"]["events"]["event_1"]
    chapters = {chapter["scene_id"]: chapter for chapter in linked["manuscript_chapters"]}
    assert event["linkedSceneIds"] == ["scene_2"]
    assert event["sceneLinkEvidence"] == {"scene_2": "source_span_overlap"}
    assert chapters["scene_1"].get("linkedEventIds", []) == []
    assert chapters["scene_2"]["linkedEventIds"] == ["event_1"]


def test_node_write_to_project_world_containers_before_items_and_skips_people(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_zhang_er": {"canonical_name": "张二", "confidence": 0.8, "importance": "supporting", "aliases": [], "tag_ids": []},
            },
            "events": {},
            "world": {"七绝堂": "organization", "长春功": "功法", "张二": "person"},
            "world_detailed": {
                "七绝堂": {"category": "organization", "description": "宗门内的一处堂口。"},
                "长春功": {"category": "功法", "description": "基础功法。"},
                "张二": {"category": "person", "description": "门丁。"},
            },
        },
    )
    state["source_language"] = "zh"

    asyncio.run(w1_import.node_write_to_project(state))

    first_world_container = next(i for i, op in enumerate(captured_ops) if op["entity_type"] == "world_container")
    first_world_item = next(i for i, op in enumerate(captured_ops) if op["entity_type"] == "world_item")
    assert first_world_container < first_world_item
    world_items = [op["data"] for op in captured_ops if op["entity_type"] == "world_item"]
    assert {item["name"] for item in world_items} == {"七绝堂", "长春功"}
    assert next(item for item in world_items if item["name"] == "七绝堂")["category"] == "location"
    assert next(item for item in world_items if item["name"] == "长春功")["category"] == "cultivation_method"


def test_node_write_to_project_rebinds_stale_world_container_references(tmp_path, monkeypatch):
    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)
    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {},
            "events": {},
            "world": {"七玄门": "organization"},
            "world_detailed": {
                "七玄门": {
                    "category": "organization",
                    "containerId": "world_container_organizations",
                    "parentId": "world_container_organizations",
                },
            },
        },
    )
    state["world_containers"] = w1_import._default_world_container_specs("zh")
    asyncio.run(w1_import.node_write_to_project(state))

    container_ids = {
        op["entity_id"] for op in captured_ops if op["entity_type"] == "world_container"
    }
    item_op = next(op for op in captured_ops if op["entity_type"] == "world_item")
    assert item_op["data"]["containerId"] == "cont_import_organizations"
    assert item_op["data"]["parentId"] == "cont_import_organizations"
    assert set(item_op["depends_on"]).issubset(container_ids)


def test_node_write_to_project_stages_manuscript_before_cancellable_proposals(tmp_path, monkeypatch):
    async def cancelled_propose_write(_op, _project_path):
        raise asyncio.CancelledError()

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", cancelled_propose_write)

    state = _make_write_state(
        tmp_path,
        entity_registry={
            "characters": {
                "char_a": {"canonical_name": "Alice", "confidence": 0.8, "importance": "core", "aliases": [], "tag_ids": []},
            },
            "events": {},
            "world": {},
            "world_detailed": {},
        },
        manuscript_chapters=[
            {"chapter_id": "chap_1", "title": "Ch 1", "orderIndex": 0, "chunk_ids": [0], "manuscript_content": "Text survives cancellation."},
        ],
    )

    try:
        asyncio.run(w1_import.node_write_to_project(state))
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Expected cancellation to propagate")

    manuscript_path = tmp_path / "manuscript.json"
    assert not manuscript_path.exists(), "cancellation must not leave canonical manuscript content"
    staged_path = tmp_path / "system" / "imports" / "import_compact" / "staged_manuscript_projection.json"
    manuscript = json.loads(staged_path.read_text(encoding="utf-8"))
    assert manuscript["chapters"][0]["content"] == "Text survives cancellation."


def test_node_write_to_project_stages_manuscript_node_projection(tmp_path, monkeypatch):
    """Writing nodes and documents remain staged until proposal acceptance."""
    import json as _json

    proposal_call_count = {"n": 0}

    async def fake_propose_write(op, _project_path):
        proposal_call_count["n"] += 1
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[
            {
                "chapter_id": "chap_1",
                "title": "第一章",
                "orderIndex": 0,
                "chunk_ids": [0],
                "manuscript_content": "韩立踏上修仙之路，历经千辛万苦，终成大道。",
            },
            {
                "chapter_id": "chap_2",
                "title": "第二章",
                "orderIndex": 1,
                "chunk_ids": [1],
                "manuscript_content": "韩立进入七玄门，开始修炼长春功。",
            },
        ],
    )
    state["source_language"] = "zh"

    asyncio.run(w1_import.node_write_to_project(state))

    nodes_path = tmp_path / "writing" / "manuscript" / "nodes.json"
    assert not nodes_path.exists(), "W1 must not write canonical manuscript nodes"
    staged_path = tmp_path / "system" / "imports" / "import_compact" / "staged_manuscript_projection.json"
    nodes = _json.loads(staged_path.read_text(encoding="utf-8"))["nodes"]

    assert len(nodes) == 4
    chapter_nodes = [n for n in nodes if n["type"] == "chapter_outline"]
    scene_nodes = [n for n in nodes if n["type"] == "scene_outline"]
    assert len(chapter_nodes) == 2
    assert len(scene_nodes) == 2

    ch1_node = next(n for n in chapter_nodes if n["linkedChapterId"] == "chap_1")
    assert ch1_node["title"] == "第一章"
    assert ch1_node["parentId"] is None
    assert ch1_node["depth"] == 0
    assert ch1_node["orderIndex"] == 0

    sc1_node = next(n for n in scene_nodes if n["linkedChapterId"] == "chap_1")
    assert sc1_node["parentId"] == ch1_node["id"]
    assert sc1_node["depth"] == 1
    assert sc1_node["linkedSceneId"] is not None

    # CJK wordCount counts characters in U+4E00-U+9FFF range, not whitespace-split
    assert ch1_node["wordCount"] > 1, "CJK wordCount should use character count, not whitespace split"

    for sc_node in scene_nodes:
        md_path = tmp_path / "writing" / "manuscript" / f"{sc_node['id']}.md"
        assert not md_path.exists(), "scene markdown must not exist before acceptance"

    for node in nodes:
        assert "/" not in node["id"] and "\\" not in node["id"] and " " not in node["id"], \
            f"node id {node['id']!r} contains unsafe characters"


def test_synthesize_relationships_falls_back_to_evidence_candidates(tmp_path, monkeypatch):
    async def fake_invoke(*_args, **_kwargs):
        return {"relationships": []}

    monkeypatch.setattr(w1_import, "_invoke_json_prompt", fake_invoke)
    monkeypatch.setattr(w1_import, "_get_llm", lambda _state: object())

    state = {
        "project_path": str(tmp_path),
        "entity_registry": {
            "characters": {
                "char_han": {"canonical_name": "韩立", "aliases": []},
                "char_mo": {"canonical_name": "墨大夫", "aliases": []},
            }
        },
        "raw_relationships": [{
            "source_character_name": "韩立",
            "target_character_name": "墨大夫",
            "type": "师徒",
            "description": "墨大夫收韩立为徒。",
            "evidence": ["墨大夫收韩立为记名弟子"],
            "confidence": 0.9,
        }],
        "errors": [],
    }

    result = asyncio.run(w1_import.node_synthesize_relationships(state))
    relationships = result["relationships"]
    assert len(relationships) == 1
    assert relationships[0]["sourceId"] == "char_han"
    assert relationships[0]["targetId"] == "char_mo"
    assert "墨大夫收韩立" in relationships[0]["sourceNotes"]


# ── P1: node_build_manuscript supervisor fallback ─────────────────────────────

def test_node_build_manuscript_supervisor_fallback_empty_extractions(tmp_path):
    """Supervisor path: chunk_extractions=[] → falls back to _build_from_chunks."""
    chunks = [
        {"chunk_id": 0, "chapter_hint": "Chapter 1", "content": "Chapter one text."},
        {"chunk_id": 1, "chapter_hint": "Chapter 2", "content": "Chapter two text."},
    ]
    state = {
        "project_path": str(tmp_path),
        "import_mode": "import_all",
        "chunks": chunks,
        "chunk_extractions": [],
    }
    result = asyncio.run(w1_import.node_build_manuscript(state))
    chapters = result["manuscript_chapters"]
    assert len(chapters) == 2, f"Expected 2 chapters, got {len(chapters)}"
    titles = {c["title"] for c in chapters}
    assert "Chapter 1" in titles
    assert "Chapter 2" in titles
    assert all(c["manuscript_content"] for c in chapters), "All chapters must have non-empty content"


def test_node_build_manuscript_extractions_without_manuscript_content(tmp_path):
    """Part A fix: extractions missing manuscript_content fall back to chunk content."""
    chunks = [
        {"chunk_id": 0, "chapter_hint": "Chapter 1", "content": "Raw chunk text."},
    ]
    extractions = [
        {"chunk_id": 0},  # No manuscript_content key
    ]
    state = {
        "project_path": str(tmp_path),
        "import_mode": "import_all",
        "chunks": chunks,
        "chunk_extractions": extractions,
    }
    result = asyncio.run(w1_import.node_build_manuscript(state))
    chapters = result["manuscript_chapters"]
    assert len(chapters) >= 1
    assert "Raw chunk text." in chapters[0]["manuscript_content"], (
        "Should fall back to raw chunk content when extraction lacks manuscript_content"
    )


def test_node_build_manuscript_failsafe_when_extractions_produce_no_chapters(tmp_path):
    """Part B fix: extractions path with no matching chunk IDs → failsafe to chunks."""
    chunks = [
        {"chunk_id": 0, "chapter_hint": "Chapter 1", "content": "Fallback text."},
    ]
    extractions = [
        {"chunk_id": 99},  # chunk_id 99 doesn't exist in chunks → empty chapter list
    ]
    state = {
        "project_path": str(tmp_path),
        "import_mode": "import_all",
        "chunks": chunks,
        "chunk_extractions": extractions,
    }
    result = asyncio.run(w1_import.node_build_manuscript(state))
    chapters = result["manuscript_chapters"]
    assert len(chapters) >= 1, "Failsafe must produce chapters from chunks when extractions yield none"
    assert any("Fallback text." in c.get("manuscript_content", "") for c in chapters)


# ── P1: node_write_to_project progressive pop + streaming manuscript ──────────

def test_node_write_to_project_characters_fully_popped(tmp_path, monkeypatch):
    """Characters dict must be empty after write — progressive pop releases each entry."""
    import json

    async def fake_propose_write(op, _project_path):
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    registry = {
        "characters": {
            "char_a": {"canonical_name": "Alice", "confidence": 0.8, "importance": "core"},
            "char_b": {"canonical_name": "Bob", "confidence": 0.7, "importance": "supporting"},
        },
        "events": {},
        "world": {},
        "world_detailed": {},
    }
    state = _make_write_state(tmp_path, entity_registry=registry)
    asyncio.run(w1_import.node_write_to_project(state))

    # After write, registry's characters dict must be empty (all entries popped)
    assert "characters" not in registry or not registry.get("characters"), (
        "entity_registry['characters'] must be fully consumed by the write loop"
    )


def test_node_write_to_project_stages_50_chapter_manuscript(tmp_path, monkeypatch):
    """Large pre-acceptance manuscript projection remains valid staged JSON."""
    import json

    async def fake_propose_write(op, _project_path):
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"]}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    chapters = [
        {
            "chapter_id": f"chap_{i}",
            "title": f"Chapter {i + 1}",
            "orderIndex": i,
            "chunk_ids": [i],
            "manuscript_content": f"Content of chapter {i + 1}.",
        }
        for i in range(50)
    ]
    state = _make_write_state(tmp_path, manuscript_chapters=chapters)
    asyncio.run(w1_import.node_write_to_project(state))

    manuscript_path = tmp_path / "manuscript.json"
    assert not manuscript_path.exists()
    staged_path = tmp_path / "system" / "imports" / "import_compact" / "staged_manuscript_projection.json"
    manuscript = json.loads(staged_path.read_text(encoding="utf-8"))
    assert len(manuscript["chapters"]) == 50
    assert manuscript["chapters"][0]["title"] == "Chapter 1"
    assert manuscript["chapters"][49]["title"] == "Chapter 50"
    assert manuscript["acceptance_required"] is True


def test_world_organizer_filters_module_contamination_and_sets_category_paths():
    """World Model organizer must not duplicate Timeline/Relationship modules."""
    assert w1_import._is_world_model_module_contamination("人物关系图", "graph")
    assert w1_import._is_world_model_module_contamination("事件时间线", "timeline")
    assert not w1_import._is_world_model_module_contamination("七玄门", "notebook")

    specs = w1_import._default_world_container_specs("zh")
    names = {spec["name"] for spec in specs}
    assert "人物关系图" not in names
    assert "事件时间线" not in names
    assert {"地理位置", "门派组织", "功法与术法", "修炼境界与制度"}.issubset(names)
    assert w1_import._world_category_path("cultivation_method", "长春功") == ["世界模型", "功法与术法"]
    assert w1_import._world_category_path("rule", "记名弟子") == ["世界模型", "修炼境界与制度"]


def test_world_taxonomy_keeps_roles_out_of_cultivation_methods():
    assert w1_import._normalize_world_category("记名弟子", "修炼体系") == "rule"
    assert w1_import._normalize_world_category("内门弟子", "cultivation") == "rule"
    assert w1_import._normalize_world_category("长春功", "功法") == "cultivation_method"
    assert w1_import._normalize_world_category("神手谷", "organization") == "location"
    assert w1_import._normalize_world_category("七玄门", "location") == "organization"


# ── Phase B: import_observability in node_review_import ──────────────────────

def _make_review_state(tmp_path, *, registry=None, manuscript_chapters=None,
                       timeline_architecture=None, timeline_branches=None,
                       relationships=None, reducer_artifact=None):
    """Minimal state for node_review_import tests."""
    default_registry = {
        "characters": {
            "char_a": {"canonical_name": "Alice", "confidence": 0.9, "skip_create": False},
            "char_b": {"canonical_name": "Bob", "confidence": 0.85},
        },
        "events": {
            "evt_1": {"title": "First event", "confidence": 0.8,
                      "branchId": "main", "orderIndex": 0, "locationIds": [],
                      "participantCharacterIds": [], "linkedSceneIds": [],
                      "linkedWorldItemIds": [], "tags": []},
        },
        "world": {},
        "world_detailed": {
            "world_a": {"name": "七玄门", "category": "organization", "confidence": 0.75},
            "world_b": {"name": "Cold Mountain", "category": "location", "confidence": 0.7},
        },
    }
    return {
        "project_path": str(tmp_path),
        "import_run_id": "obs_test",
        "entity_registry": registry or default_registry,
        "manuscript_chapters": manuscript_chapters if manuscript_chapters is not None else [
            {"chapter_id": "ch1", "title": "Chapter 1"},
            {"chapter_id": "ch2", "title": "Chapter 2"},
        ],
        "timeline_architecture": timeline_architecture or {
            "canonical_events": [{"title": "Main arc event"}],
            "discarded_duplicates": [{"event_id": "dup_1"}, {"event_id": "dup_2"}],
            "warnings": ["Topology warning A"],
        },
        "timeline_branches": timeline_branches or [
            {"id": "main"}, {"id": "branch_a"}
        ],
        "relationships": relationships or [{"id": "rel_1"}, {"id": "rel_2"}, {"id": "rel_3"}],
        "reducer_artifact": reducer_artifact or {"warnings": [], "duplicate_candidates": []},
        "errors": [],
        "context": {"model": "deepseek-chat"},
        "source_language": "en",
        "character_tags": [],
    }


def test_node_review_import_includes_observability_fields(tmp_path):
    """node_review_import must populate import_observability with counts from existing state."""
    state = _make_review_state(tmp_path)
    result = asyncio.run(w1_import.node_review_import(state))
    report = result["import_review_report"]

    assert "import_observability" in report, "import_observability key must be in review_report"
    obs = report["import_observability"]

    expected_keys = [
        "characters_extracted", "events_extracted", "world_items_extracted",
        "observability_phase", "relationships_preproposal_count", "manuscript_chapters_preproposal_count",
        "manuscript_staging_pending",
        "canonical_events_count", "branch_count", "duplicate_count", "topology_warning_count",
    ]
    for key in expected_keys:
        assert key in obs, f"import_observability missing key: {key}"

    # Verify counts match the fixture
    assert obs["characters_extracted"] == 2   # char_a (not skip_create), char_b
    assert obs["events_extracted"] == 1       # evt_1
    assert obs["world_items_extracted"] == 2  # world_a, world_b
    assert obs["observability_phase"] == "pre_proposal"
    assert obs["relationships_preproposal_count"] == 3
    assert obs["manuscript_chapters_preproposal_count"] == 2
    assert obs["manuscript_staging_pending"] is True
    assert obs["canonical_events_count"] == 1
    assert obs["branch_count"] == 2
    assert obs["duplicate_count"] == 2
    assert obs["topology_warning_count"] == 1


def test_node_review_import_observability_skips_skip_create_characters(tmp_path):
    """Characters with skip_create=True must not be counted in characters_extracted."""
    registry = {
        "characters": {
            "char_a": {"canonical_name": "Alice", "confidence": 0.9},
            "char_b": {"canonical_name": "Skip Me", "confidence": 0.9, "skip_create": True},
            "char_c": {"canonical_name": "Charlie", "confidence": 0.8},
        },
        "events": {},
        "world": {},
        "world_detailed": {},
    }
    state = _make_review_state(tmp_path, registry=registry)
    result = asyncio.run(w1_import.node_review_import(state))
    obs = result["import_review_report"]["import_observability"]
    assert obs["characters_extracted"] == 2, "skip_create characters must be excluded from count"


def test_node_review_import_observability_marks_empty_manuscript_as_preproposal(tmp_path):
    """An empty review snapshot must not claim the manuscript has been written."""
    state = _make_review_state(tmp_path, manuscript_chapters=[])
    result = asyncio.run(w1_import.node_review_import(state))
    obs = result["import_review_report"]["import_observability"]
    assert obs["observability_phase"] == "pre_proposal"
    assert obs["manuscript_chapters_preproposal_count"] == 0
    assert obs["manuscript_staging_pending"] is True


def test_node_review_import_runs_all_zero_cost_reviewers(tmp_path):
    state = _make_review_state(tmp_path)
    result = asyncio.run(w1_import.node_review_import(state))
    report = result["import_review_report"]

    assert set(report["reviewer_reports"]) == {"quality", "fact", "consistency"}
    for reviewer_report in report["reviewer_reports"].values():
        ledger = reviewer_report["token_cost_ledger"]
        assert ledger["live_model_calls"] is False
        assert ledger["full50_run"] is False


def test_attach_event_evidence_card_uses_candidate_id():
    entry = {"title": "韩立离家", "evidence_refs": []}
    source_span = {
        "raw_source_hash": "a" * 64,
        "absolute_start": 10,
        "absolute_end": 20,
        "substring_hash": "b" * 64,
    }
    cards = [{
        "id": "evc_event",
        "kind": "event",
        "candidate_ids": ["event_departure"],
        "source_span": source_span,
        "raw": {"event_id": "event_departure"},
    }]

    result = w1_import._attach_entity_evidence_card(
        entry, "event_departure", cards, kind="event",
    )

    assert result["evidence_refs"] == ["evc_event"]
    assert result["source_span"] == source_span


def test_import_observability_key_survives_proposal_write_merge():
    """proposal_write updates proposal_counts/safe_accept_ids/blocked_ids but must NOT
    remove import_observability from the review_report dict."""
    existing_report = {
        "import_run_id": "test",
        "status": "pass",
        "warnings": [],
        "errors": [],
        "import_observability": {
            "characters_extracted": 5,
            "events_extracted": 10,
            "manuscript_written": True,
        },
    }
    # Simulate what proposal_write does to the review_report (lines 3972-3977 in w1_import.py)
    existing_report["proposal_counts"] = {"character": 5, "timeline_event": 10}
    existing_report["safe_accept_ids"] = ["p1", "p2"]
    existing_report["blocked_ids"] = []
    existing_report["proposal_ids"] = ["p1", "p2", "p3"]

    # import_observability must still be present and unchanged
    assert "import_observability" in existing_report
    assert existing_report["import_observability"]["characters_extracted"] == 5
    assert existing_report["import_observability"]["manuscript_written"] is True


def test_world_category_arcid_does_not_create_item_branch(tmp_path):
    """arcId='item' (world category) must never produce branch_arc_item.

    Uses arcRole='background' (low importance) to avoid the protagonist/mainline
    short-circuit so the arc_id path in _timeline_lane_key is actually exercised.
    """
    import asyncio
    from sidecar.workflows import w1_import

    events = {}
    for i in range(10):
        events[f"ev_{i}"] = {
            "title": f"韩立修炼进阶 {i}",
            "description": "韩立突破功法瓶颈，实力提升。",
            "timelineClass": "canonical_event",
            "eventClass": "canonical_event",
            "arcId": "item",          # world category — should be ignored
            "arcRole": "background",  # avoids protagonist/mainline short-circuit
            "importanceScore": 50,    # below 65 threshold — also avoids short-circuit
            "character_ids": ["char_han"],
            "temporal_hint": f"第{i + 1}章",
            "confidence": 0.85,
            "chunk_id": i,
        }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_no_item_branch",
        "entity_registry": {"events": events},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    branch_ids = [b["id"] for b in result["timeline_branches"]]
    assert not any("item" in bid for bid in branch_ids), (
        f"branch_item was created from world category arcId: {branch_ids}"
    )


def test_source_order_fields_present_on_canonical_events(tmp_path):
    """node_architect_timeline must add sourceOrder, chapterNumber, sourceChunkIds to each event."""
    import asyncio
    from sidecar.workflows import w1_import

    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_source_fields",
        "entity_registry": {"events": {
            "ev_a": {
                "title": "韩立离家",
                "description": "韩立离开村庄。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "protagonist_origin",
                "arcRole": "protagonist",
                "importanceScore": 82,
                "chapterRange": {"start": "第一章", "end": "第一章"},
                "temporal_hint": "第一章",
                "character_ids": ["char_han"],
                "confidence": 0.88,
                "chunk_id": 0,
            },
        }},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    events = list(result["entity_registry"]["events"].values())
    assert len(events) == 1
    ev = events[0]
    assert "sourceOrder" in ev, "sourceOrder field missing"
    assert "chapterNumber" in ev, "chapterNumber field missing"
    assert "sourceChunkIds" in ev, "sourceChunkIds field missing"
    assert ev["sourceChunkIds"] == [0]
    assert ev["chapterNumber"] == 1


def test_global_order_index_follows_source_chapter_order(tmp_path):
    """Events from later chapters must have higher globalOrderIndex than earlier chapters."""
    import asyncio
    from sidecar.workflows import w1_import

    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_global_order",
        "entity_registry": {"events": {
            "ev_ch3": {
                "title": "韩立突破",
                "description": "韩立功法突破。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "cultivation_progress",
                "arcRole": "power_progression",
                "importanceScore": 80,
                "chapterRange": {"start": "第三章", "end": "第三章"},
                "temporal_hint": "第三章",
                "character_ids": ["char_han"],
                "confidence": 0.88,
                "chunk_id": 2,
            },
            "ev_ch1": {
                "title": "韩立入学",
                "description": "韩立进入七玄门。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "sect_entry",
                "arcRole": "protagonist",
                "importanceScore": 85,
                "chapterRange": {"start": "第一章", "end": "第一章"},
                "temporal_hint": "第一章",
                "character_ids": ["char_han"],
                "confidence": 0.90,
                "chunk_id": 0,
            },
            "ev_ch2": {
                "title": "墨大夫收徒",
                "description": "墨大夫收韩立为徒。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "mentor_control",
                "arcRole": "antagonist",
                "importanceScore": 82,
                "chapterRange": {"start": "第二章", "end": "第二章"},
                "temporal_hint": "第二章",
                "character_ids": ["char_han", "char_mo"],
                "confidence": 0.87,
                "chunk_id": 1,
            },
        }},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    events = list(result["entity_registry"]["events"].values())
    assert len(events) == 3
    ordered = sorted(events, key=lambda e: e["globalOrderIndex"])
    chunk_order = [ev["chunk_id"] for ev in ordered]
    assert chunk_order == [0, 1, 2], (
        f"globalOrderIndex does not follow source chapter order. Got chunk order: {chunk_order}"
    )


def test_global_order_index_cross_branch_follows_source_order(tmp_path):
    """globalOrderIndex must follow source chapter order even when events are on different branches."""
    import asyncio
    from sidecar.workflows import w1_import

    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_cross_branch_order",
        "entity_registry": {"events": {
            "ev_training_ch5": {
                "title": "韩立突破五层",
                "description": "韩立达到新的修炼高度。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "cultivation_progress",
                "arcRole": "power_progression",
                "importanceScore": 81,
                "chapterRange": {"start": "第五章", "end": "第五章"},
                "temporal_hint": "第五章",
                "character_ids": ["char_han"],
                "confidence": 0.88,
                "chunk_id": 4,
            },
            "ev_training_ch4": {
                "title": "韩立突破四层",
                "description": "韩立再次突破修炼境界。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "cultivation_progress",
                "arcRole": "power_progression",
                "importanceScore": 82,
                "chapterRange": {"start": "第四章", "end": "第四章"},
                "temporal_hint": "第四章",
                "character_ids": ["char_han"],
                "confidence": 0.89,
                "chunk_id": 3,
            },
            "ev_main_ch3": {
                "title": "韩立突破三层",
                "description": "韩立突破修炼瓶颈到达三层。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "cultivation_progress",
                "arcRole": "power_progression",
                "importanceScore": 85,
                "chapterRange": {"start": "第三章", "end": "第三章"},
                "temporal_hint": "第三章",
                "character_ids": ["char_han"],
                "confidence": 0.90,
                "chunk_id": 2,
            },
            "ev_conflict_ch1": {
                "title": "敌人伏击背叛韩立",
                "description": "敌人设下伏击，背叛了韩立。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "faction_conflict",
                "arcRole": "antagonist",
                "importanceScore": 80,
                "chapterRange": {"start": "第一章", "end": "第一章"},
                "temporal_hint": "第一章",
                "character_ids": ["char_han"],
                "confidence": 0.87,
                "chunk_id": 0,
            },
            "ev_main_ch2": {
                "title": "韩立加入七玄门",
                "description": "韩立正式成为七玄门弟子。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "sect_entry",
                "arcRole": "protagonist",
                "importanceScore": 88,
                "chapterRange": {"start": "第二章", "end": "第二章"},
                "temporal_hint": "第二章",
                "character_ids": ["char_han"],
                "confidence": 0.91,
                "chunk_id": 1,
            },
        }},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    events = list(result["entity_registry"]["events"].values())
    assert len(events) == 5

    # Confirm events landed on at least 2 different branches
    branch_ids = {ev["branchId"] for ev in events}
    assert len(branch_ids) >= 2, f"Expected multi-branch, got: {branch_ids}"

    # globalOrderIndex must follow chunk_id (source chapter) order regardless of branch
    ordered = sorted(events, key=lambda e: e["globalOrderIndex"])
    chunk_order = [ev["chunk_id"] for ev in ordered]
    assert chunk_order == [0, 1, 2, 3, 4], (
        f"Cross-branch globalOrderIndex does not follow source order. Got chunk order: {chunk_order}"
    )


def test_wang_guard_title_variants_collapse_to_one_canonical_event(tmp_path):
    """Title variants '王护法接走韩立' and '七玄门王护法接走韩立' must merge to one event."""
    import asyncio
    from sidecar.workflows import w1_import

    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_wang_dedup",
        "entity_registry": {"events": {
            "ev_a": {
                "title": "王护法接走韩立",
                "description": "王护法奉命将韩立带走。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "sect_entry",
                "arcRole": "protagonist",
                "importanceScore": 78,
                "character_ids": ["char_wang", "char_han"],
                "chapterRange": {"start": "第五章", "end": "第五章"},
                "temporal_hint": "第五章",
                "confidence": 0.85,
                "chunk_id": 4,
            },
            "ev_b": {
                "title": "七玄门王护法接走韩立",
                "description": "七玄门的王护法将韩立带至门内。",
                "timelineClass": "canonical_event",
                "eventClass": "canonical_event",
                "arcId": "sect_entry",
                "arcRole": "protagonist",
                "importanceScore": 76,
                "character_ids": ["char_wang", "char_han"],
                "chapterRange": {"start": "第五章", "end": "第五章"},
                "temporal_hint": "第五章",
                "confidence": 0.83,
                "chunk_id": 4,
            },
        }},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    final_events = result["entity_registry"]["events"]
    assert len(final_events) == 1, (
        f"Expected 1 merged event, got {len(final_events)}: {list(final_events.keys())}"
    )


def test_branch_without_merge_event_has_endmode_open(tmp_path):
    """A side branch with no merge-hinted event must have endMode='open'."""
    import asyncio
    from sidecar.workflows import w1_import

    events = {}
    for i in range(3):
        events[f"side_{i}"] = {
            "title": f"墨大夫威胁 {i}",
            "description": "墨大夫对韩立施压。",
            "timelineClass": "canonical_event",
            "eventClass": "canonical_event",
            "arcId": "mentor_control",
            "arcRole": "antagonist",
            "importanceScore": 75,
            "character_ids": ["char_han", "char_mo"],
            "temporal_hint": f"第{i + 1}章",
            "confidence": 0.85,
            "chunk_id": i,
            "forkMergeHint": "root",
        }
    events["main_ev"] = {
        "title": "韩立进入七玄门",
        "description": "韩立正式成为七玄门弟子。",
        "timelineClass": "canonical_event",
        "eventClass": "canonical_event",
        "arcId": "sect_entry",
        "arcRole": "protagonist",
        "importanceScore": 88,
        "character_ids": ["char_han"],
        "temporal_hint": "第一章",
        "confidence": 0.91,
        "chunk_id": 0,
        "forkMergeHint": "root",
    }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_open_branch",
        "entity_registry": {"events": events},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    branches = {b["id"]: b for b in result["timeline_branches"]}
    mentor_branch = next(
        (b for bid, b in branches.items() if "mentor" in bid or "antagonist" in bid),
        None,
    )
    assert mentor_branch is not None, f"No mentor/antagonist branch found: {list(branches.keys())}"
    assert mentor_branch.get("endMode") == "open", (
        f"Expected endMode='open' but got '{mentor_branch.get('endMode')}'"
    )


def test_branch_with_merge_hint_event_has_endmode_merge(tmp_path):
    """A branch whose final event has forkMergeHint='merge' must set endMode='merge'."""
    import asyncio
    from sidecar.workflows import w1_import

    events = {
        "main_ev": {
            "title": "韩立进入七玄门",
            "description": "韩立成为七玄门弟子。",
            "timelineClass": "canonical_event",
            "eventClass": "canonical_event",
            "arcId": "sect_entry",
            "arcRole": "protagonist",
            "importanceScore": 88,
            "character_ids": ["char_han"],
            "temporal_hint": "第一章",
            "confidence": 0.91,
            "chunk_id": 0,
            "forkMergeHint": "root",
        },
        "mentor_start": {
            "title": "墨大夫收韩立为徒",
            "description": "墨大夫将韩立纳为弟子。",
            "timelineClass": "canonical_event",
            "eventClass": "canonical_event",
            "arcId": "mentor_control",
            "arcRole": "antagonist",
            "importanceScore": 76,
            "character_ids": ["char_han", "char_mo"],
            "temporal_hint": "第二章",
            "confidence": 0.86,
            "chunk_id": 1,
            "forkMergeHint": "root",
        },
        "mentor_mid": {
            "title": "墨大夫施压韩立",
            "description": "墨大夫对韩立继续施加威胁。",
            "timelineClass": "canonical_event",
            "eventClass": "canonical_event",
            "arcId": "mentor_control",
            "arcRole": "antagonist",
            "importanceScore": 74,
            "character_ids": ["char_han", "char_mo"],
            "temporal_hint": "第二章末",
            "confidence": 0.84,
            "chunk_id": 1,
            "forkMergeHint": "root",
        },
        "mentor_merge": {
            "title": "韩立脱离墨大夫控制",
            "description": "韩立终于摆脱墨大夫的威胁，重归主线。",
            "timelineClass": "canonical_event",
            "eventClass": "canonical_event",
            "arcId": "mentor_control",
            "arcRole": "antagonist",
            "importanceScore": 82,
            "character_ids": ["char_han", "char_mo"],
            "temporal_hint": "第三章",
            "confidence": 0.88,
            "chunk_id": 2,
            "forkMergeHint": "merge",
        },
    }
    state = {
        "project_path": str(tmp_path),
        "import_run_id": "test_merge_branch",
        "entity_registry": {"events": events},
        "timeline_branches": [],
        "errors": [],
    }
    result = asyncio.run(w1_import.node_architect_timeline(state))
    branches = {b["id"]: b for b in result["timeline_branches"]}
    mentor_branch = next(
        (b for bid, b in branches.items() if "mentor" in bid or "antagonist" in bid),
        None,
    )
    assert mentor_branch is not None, f"No mentor/antagonist branch: {list(branches.keys())}"
    assert mentor_branch.get("endMode") == "merge", (
        f"Expected endMode='merge' but got '{mentor_branch.get('endMode')}'"
    )
    assert mentor_branch.get("mergeEventId") is not None, "mergeEventId should be set"


# ── F-4: supervisor-path content chain integrity ──────────────────────────────

def test_supervisor_path_content_chain_integrity(tmp_path, monkeypatch):
    """chapter_proposals and scene_proposals must both carry the original manuscript_content."""
    KNOWN_TEXT = "韩立踏上修仙之路" * 20  # 180 chars of known CJK content

    captured_ops = []

    async def fake_propose_write(op, _project_path):
        captured_ops.append(op)
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[
            {
                "chapter_id": "chap_integrity_1",
                "title": "第一章",
                "orderIndex": 0,
                "chunk_ids": [0],
                "manuscript_content": KNOWN_TEXT,
            },
        ],
        entity_registry={"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
    )
    state["source_language"] = "zh"

    asyncio.run(w1_import.node_write_to_project(state))

    chapter_op = next(op for op in captured_ops if op["entity_type"] == "chapter")
    scene_op = next(op for op in captured_ops if op["entity_type"] == "scene")

    # Chapter proposal must carry the original manuscript_content
    assert chapter_op["data"]["content"] == KNOWN_TEXT, (
        f"chapter_op content mismatch: got {chapter_op['data']['content']!r}"
    )
    # Scene proposal must carry the original manuscript_content
    assert scene_op["data"]["content"] == KNOWN_TEXT, (
        f"scene_op content mismatch: got {scene_op['data']['content']!r}"
    )


# ── F-5: nodes.json includes source_span per node ─────────────────────────────

def test_staged_manuscript_nodes_include_source_span(tmp_path, monkeypatch):
    """The staged node projection keeps chapter source provenance."""

    async def fake_propose_write(op, _project_path):
        return {"id": f"p_{op['entity_id']}", "confidence": op["confidence"], "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", fake_propose_write)

    state = _make_write_state(
        tmp_path,
        manuscript_chapters=[
            {
                "chapter_id": "chap_span_test",
                "title": "第一章",
                "orderIndex": 0,
                "chunk_ids": [0],
                "manuscript_content": "韩立踏上修仙之路。",
                "source_span": {"start": 100, "end": 500},
            },
        ],
        entity_registry={"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
    )
    state["source_language"] = "zh"

    asyncio.run(w1_import.node_write_to_project(state))

    nodes_path = tmp_path / "writing" / "manuscript" / "nodes.json"
    assert not nodes_path.exists(), "nodes must not be canonical before acceptance"
    staged_path = tmp_path / "system" / "imports" / "import_compact" / "staged_manuscript_projection.json"
    nodes_json = json.loads(staged_path.read_text(encoding="utf-8"))["nodes"]

    # Find the chapter_outline node (type == "chapter_outline")
    chapter_nodes = [n for n in nodes_json if n.get("type") == "chapter_outline"]
    assert len(chapter_nodes) > 0, "Expected at least one chapter_outline node in nodes.json"

    chapter_node = chapter_nodes[0]
    assert "source_span" in chapter_node, (
        f"chapter_outline node missing source_span: {chapter_node}"
    )
    assert set(chapter_node["source_span"]) == {
        "raw_source_hash", "absolute_start", "absolute_end", "substring_hash",
    }
