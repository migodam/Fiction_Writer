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


def test_prompt_profile_bounds_chunk_content():
    state = {"prompt_profile": "fast", "context": {}}
    content = "A" * 80_000

    bounded = w1_import._bounded_chunk_content(state, content)

    assert len(bounded) < len(content)
    assert "middle omitted by W1 prompt profile context budget" in bounded


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
