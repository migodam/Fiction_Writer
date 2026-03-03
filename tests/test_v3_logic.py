import pytest
import os
import json
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_v3_logic.json"

@pytest.fixture
def memory():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    # 1. Setup 3 characters, 2 with missing background
    mem.add_character("Hero A", "Desc", "traits", "goals", "secrets")
    mem.data["characters"][0]["background"] = "Existing background"
    mem.add_character("Hero B", "Desc", "traits", "goals", "secrets")
    mem.data["characters"][1]["background"] = ""
    mem.add_character("Hero C", "Desc", "traits", "goals", "secrets")
    # background missing entirely for C
    
    # 2. Setup a setting page
    mem.create_setting_page("The Glass Guild")
    
    mem.save()
    yield mem
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_apply_project_updates_field_merge_counts(memory):
    # Mock an expanded PM update JSON
    updates = {
        "characters": {
            "upsert": [
                {
                    "name": "Hero B",
                    "fields": {"background": "New Background for B"}
                },
                {
                    "name": "Hero C",
                    "fields": {"background": "New Background for C"}
                }
            ]
        },
        "setting_pages": {
            "upsert_items": [
                {
                    "page_id": memory.data["setting_pages"][0]["id"],
                    "name": "Background",
                    "content": "Lore about the guild."
                }
            ]
        }
    }
    
    stats = memory.apply_project_updates(updates)
    
    assert stats["characters_updated"] == 2
    assert stats["setting_items_created"] == 1
    
    # Verify B
    char_b = next(c for c in memory.data["characters"] if c["name"] == "Hero B")
    assert char_b["background"] == "New Background for B"
    assert char_b["description"] == "Desc" # preserved
    
    # Verify Setting Item
    guild_page = memory.data["setting_pages"][0]
    assert len(guild_page["items"]) == 1
    assert guild_page["items"][0]["name"] == "Background"
    assert guild_page["items"][0]["content"] == "Lore about the guild."
