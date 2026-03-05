import pytest
import os
import json
import shutil
from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.orchestrator import run_pipeline
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input

GOLDEN_FIXTURE = "tests/fixtures/golden_project.json"
TEST_PROJECT = "data/test_advanced_project.json"

@pytest.fixture
def memory():
    shutil.copy2(GOLDEN_FIXTURE, TEST_PROJECT)
    mem = ProjectMemory(file_path=TEST_PROJECT)
    yield mem
    if os.path.exists(TEST_PROJECT):
        os.remove(TEST_PROJECT)

@pytest.fixture
def store():
    return MemoryStore()

@pytest.fixture
def client():
    with open("tests/api_key.txt", "r") as f:
        key = f.read().strip()
    return OpenAIClient(api_key=key, model="gpt-4o-mini")

def test_chinese_protagonist_resolution(memory, store, client):
    """G2/G3: Multi-lingual ambiguous entity resolution ('男主')."""
    # Intent: Add background for '男主' (Lorian Sunlight)
    user_text = "给男主添加一段背景：他曾是银厅的最后一名守卫。"
    routing = route_user_input(user_text, {}, {}, client)
    
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    # If the AI failed to resolve it, we want to know why from diagnostics
    if res["pm_counts"].get("characters_updated", 0) < 1:
        print(f"PM Raw: {res['diagnostics'].get('pm_raw')}")
        print(f"Failure: {res['diagnostics'].get('failure_explanation')}")

    assert res["pm_counts"].get("characters_updated", 0) >= 1
    
    memory.load()
    lorian = next(c for c in memory.data["characters"] if c["name"] == "Lorian Sunlight")
    assert lorian["id"] == "char-hero-001"

def test_failure_explainer_invalid_id(memory, store, client):
    """G6: Failure Explainer provides root cause for invalid IDs."""
    # We bypass the planner and mock a PM output with a bad ID
    bad_updates = {
        "project_updates": {
            "characters": {
                "upsert": [{"id_or_name": "non-existent-uuid", "fields": {"goals": "Win"}}]
            }
        }
    }
    
    # Call explain_failure directly
    from src.ai.orchestrator import explain_failure
    explanation, reasons = explain_failure(
        "Update unknown char",
        {"needs_project_update": True, "needs_sections": ["characters"]},
        {"modification_plan": {"steps": [{"entity_type": "character", "target": {"by": "id", "value": "non-existent-uuid"}}]}},
        bad_updates,
        memory.data,
        {"characters_updated": 0},
        client
    )
    
    assert "PM Emitted No Updates" in reasons or "Apply layer ignored updates" in reasons

def test_mass_entity_context_truncation(memory, store, client):
    """G7: Context packet truncation stability."""
    # 1. Fill memory with 50 characters to trigger truncation (threshold is 6000 chars)
    # 50 chars with some content will exceed 6000
    for i in range(50):
        memory.add_character(f"Extra Character {i}", "Role", "Very long traits and goals to fill space" * 5, "Goals", "Secrets")
    memory.save()
    
    user_text = "Who is Malakor?"
    routing = route_user_input(user_text, {}, {}, client)
    
    from src.ai.context_builder import build_context_packet
    ctx = build_context_packet(routing, memory.data, {}, {}, store)
    
    assert ctx["limits"]["truncated"] is True
    assert "Truncated" in ctx["limits"]["overflow_summary"]
