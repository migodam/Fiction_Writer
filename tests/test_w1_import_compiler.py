from __future__ import annotations

import asyncio

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


def test_prompt_profile_bounds_chunk_content():
    state = {"prompt_profile": "fast", "context": {}}
    content = "A" * 80_000

    bounded = w1_import._bounded_chunk_content(state, content)

    assert len(bounded) < len(content)
    assert "middle omitted by W1 prompt profile context budget" in bounded


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
    ]

    for term in required_terms:
        assert term in prompt


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
