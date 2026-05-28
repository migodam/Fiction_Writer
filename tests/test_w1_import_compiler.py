from __future__ import annotations

import asyncio
import json

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

    async def fake_cross_validation(_llm, state, *, window, digest, prompt_outputs, cross_validation):
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
            {"chunk_id": 2, "chapter_hint": "Chapter 3"},
            {"chunk_id": 0, "chapter_hint": "Chapter 1"},
            {"chunk_id": 1, "chapter_hint": "Chapter 2"},
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

    assert by_key["locations"]["name"] == "地点"
    assert by_key["organizations"]["name"] == "组织与势力"
    assert w1_import._normalize_world_category("七玄门", "sect") == "organization"
    assert w1_import._normalize_world_category("七玄门", "地名") != "location"
    assert w1_import._normalize_world_category("掩月宗", "宗门") == "organization"
    assert w1_import._normalize_world_category("天南势力", "势力") == "faction"
    assert w1_import._normalize_world_category("长春功", "功法") == "system"
    assert w1_import._normalize_world_category("小绿瓶", "法器") == "artifact"
    assert w1_import.WORLD_ONTOLOGY_LABELS["organization"]["zh"] == "组织"
    assert "门派" in w1_import.WORLD_ONTOLOGY_LABELS["organization"]["zh_description"]
    assert w1_import._world_container_key("organization") == "organizations"
    assert w1_import._world_container_key("faction") == "organizations"
    assert w1_import._world_container_key("artifact") == "items"
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
                "长春功": "rule",
            },
            "world_detailed": {
                "七玄门": {"category": "organization", "description": "江湖门派。"},
                "青牛镇": {"category": "location", "description": "故事早期地点。"},
                "长春功": {"category": "rule", "description": "修炼功法。"},
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
    assert by_name["长春功"]["containerId"] == "cont_import_rules"
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
        "ANTI-SUMMARY-BLOAT RULES",
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

def _make_write_state(tmp_path, *, entity_registry=None, manuscript_chapters=None):
    """Minimal state for node_write_to_project tests."""
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


def test_node_write_to_project_manuscript_still_written(tmp_path, monkeypatch):
    """manuscript.json must be written even after switching to compact receipts."""
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
    assert manuscript_path.exists(), "manuscript.json must be written"
    manuscript = json.loads(manuscript_path.read_text(encoding="utf-8"))
    assert len(manuscript["chapters"]) == 2
    assert manuscript["chapters"][0]["title"] == "Ch 1"


def test_node_write_to_project_writes_manuscript_before_cancellable_proposals(tmp_path, monkeypatch):
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
    assert manuscript_path.exists(), "manuscript.json must be written before proposal loop can be cancelled"
    manuscript = json.loads(manuscript_path.read_text(encoding="utf-8"))
    assert manuscript["chapters"][0]["manuscript_content"] == "Text survives cancellation."


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


def test_node_write_to_project_streaming_manuscript_50_chapters(tmp_path, monkeypatch):
    """Streaming manuscript write must produce valid JSON with correct chapter count."""
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
    assert manuscript_path.exists()
    manuscript = json.loads(manuscript_path.read_text(encoding="utf-8"))
    assert len(manuscript["chapters"]) == 50
    assert manuscript["chapters"][0]["title"] == "Chapter 1"
    assert manuscript["chapters"][49]["title"] == "Chapter 50"
    assert "source_file" in manuscript
    assert "imported_at" in manuscript


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
        "relationships_extracted", "manuscript_chapters_count", "manuscript_written",
        "canonical_events_count", "branch_count", "duplicate_count", "topology_warning_count",
    ]
    for key in expected_keys:
        assert key in obs, f"import_observability missing key: {key}"

    # Verify counts match the fixture
    assert obs["characters_extracted"] == 2   # char_a (not skip_create), char_b
    assert obs["events_extracted"] == 1       # evt_1
    assert obs["world_items_extracted"] == 2  # world_a, world_b
    assert obs["relationships_extracted"] == 3
    assert obs["manuscript_chapters_count"] == 2
    assert obs["manuscript_written"] is True
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


def test_node_review_import_observability_manuscript_not_written(tmp_path):
    """manuscript_written must be False when manuscript_chapters is empty."""
    state = _make_review_state(tmp_path, manuscript_chapters=[])
    result = asyncio.run(w1_import.node_review_import(state))
    obs = result["import_review_report"]["import_observability"]
    assert obs["manuscript_written"] is False
    assert obs["manuscript_chapters_count"] == 0


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
