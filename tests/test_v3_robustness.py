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
TEST_PROJECT = "data/test_robustness_project.json"

@pytest.fixture
def memory():
    # Setup test file
    shutil.copy2(GOLDEN_FIXTURE, TEST_PROJECT)
    mem = ProjectMemory(file_path=TEST_PROJECT)
    yield mem
    # Cleanup
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

def test_baseline_incremental_updates(memory, store, client):
    """G5: Incremental edits work without damaging others."""
    # Intent: Update Lorian's goal
    user_text = "Lorian's new goal is to rebuild Silverhall."
    routing = route_user_input(user_text, {}, {}, client)
    
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    if res["pm_counts"].get("characters_updated", 0) < 1:
        print("\n--- DIAGNOSTICS ---")
        print(f"PM Raw: {res['diagnostics'].get('pm_raw')}")
        print(f"Failure Analysis: {res['diagnostics'].get('failure_explanation')}")
        print(f"Project Memory: {json.dumps(memory.data['characters'], indent=2)}")

    # Verify Apply
    assert res["pm_counts"].get("characters_updated", 0) >= 1
    
    # Reload and verify persistence
    memory.load()
    lorian = next(c for c in memory.data["characters"] if c["name"] == "Lorian Sunlight")
    assert "rebuild silverhall" in lorian["goals"].lower()
    assert lorian["traits"] == "Brave, Melancholic" # Integrity check

def test_add_timeline_event_with_valid_participants(memory, store, client):
    """G3: Referential integrity (participants)."""
    # Intent: Add a birth event for Malakor
    user_text = "Add a timeline event: Malakor the Void was born in the abyss 100 years ago."
    routing = route_user_input(user_text, {}, {}, client)
    
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    if res["pm_counts"].get("timeline_upserted", 0) < 1:
        print("\n--- DIAGNOSTICS ---")
        print(f"PM Raw: {res['diagnostics'].get('pm_raw')}")
        print(f"Failure Analysis: {res['diagnostics'].get('failure_explanation')}")

    assert res["pm_counts"].get("timeline_upserted", 0) >= 1
    
    # Verify participant resolution
    memory.load()
    event = next(e for e in memory.data["timeline_events"] if "born" in e["title"].lower() or "born" in e["summary"].lower() or "born" in str(e))
    # It should resolve to the ID char-villain-002
    assert "char-villain-002" in event["participants"] or "Malakor the Void" in event["participants"]

def test_setting_page_item_creation(memory, store, client):
    """G4: Setting Notebook model stable."""
    # Intent: Add a 'Sacrificial Bowl' to the Church
    user_text = "In the Sunken Church, there is a Sacrificial Bowl on the altar."
    routing = route_user_input(user_text, {}, {}, client)
    
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    if res["pm_counts"].get("setting_items_created", 0) < 1:
        print("\n--- DIAGNOSTICS ---")
        print(f"PM Raw: {res['diagnostics'].get('pm_raw')}")
        print(f"Failure Analysis: {res['diagnostics'].get('failure_explanation')}")

    assert res["pm_counts"].get("setting_items_created", 0) >= 1
    
    memory.load()
    church = next(p for p in memory.data["setting_pages"] if p["title"] == "The Sunken Church")
    assert any("Bowl" in it["name"] for it in church["items"])
