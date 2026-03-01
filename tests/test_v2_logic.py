import pytest
import os
import json
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_v2_updates.json"

@pytest.fixture
def memory():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    yield mem
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_apply_updates_nonzero_counts(memory):
    updates = {
        "timeline_events": {
            "upsert": [{"title": "Event 1", "time": "100"}]
        },
        "characters": {
            "upsert": [{"name": "New Guy"}]
        }
    }
    summary = memory.apply_project_updates(updates)
    assert "+1" in summary
    assert "characters (candidates): +1" in summary
    assert len(memory.data["characters"]) == 1
    assert memory.data["characters"][0]["status"] == "candidate"

def test_character_confirm_flow(memory):
    char = memory.add_character("Hero", "...", "", "", "")
    char["status"] = "candidate"
    memory.save()
    
    memory.confirm_character(char["id"])
    assert memory.data["characters"][0]["status"] == "active"

def test_setting_pages_dynamic_fields(memory):
    page = memory.create_setting_page("Lore", "custom")
    item = {
        "id": "item-1", "name": "Sword", "content": "Sharp", 
        "fields": {"material": "glass", "weight": "light"}
    }
    updates = {
        "setting_pages": {
            "upsert_items": [item]
        }
    }
    # Manually associate page_id for the test as Core Agent would
    item["page_id"] = page["id"]
    memory.apply_project_updates(updates)
    
    assert memory.data["setting_pages"][0]["items"][0]["fields"]["material"] == "glass"

def test_no_garbage_symbols_in_summary(memory):
    summary = memory.apply_project_updates({})
    # Check for the common '鉁' mojibake or other non-ascii if possible
    assert "鉁" not in summary
    assert "馃" not in summary
