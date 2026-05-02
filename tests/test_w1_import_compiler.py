from __future__ import annotations

import asyncio

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
    async def fake_propose_write(op, _project_path):
        return {
            "id": f"proposal_{op['entity_id']}",
            "operations": [{"entityType": op["entity_type"], "fields": op["data"]}],
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
    character_proposal = result["proposals"][0]
    data = character_proposal["operations"][0]["fields"] if "fields" in character_proposal["operations"][0] else None

    assert data is None or data.get("goals", []) == []
    assert data is None or data.get("fears", []) == []
    assert data is None or data.get("secrets", []) == []


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
    assert result["timeline_architecture"]["density_policy"]["max_events_per_branch"] == 24
