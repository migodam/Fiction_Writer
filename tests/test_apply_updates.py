import pytest
import os
import json
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_regression_updates.json"

@pytest.fixture
def memory():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    # Add a character with empty background
    mem.add_character(name="TestHero", description="A brave knight", traits="brave", goals="save world", secrets="none")
    mem.data["characters"][0]["background"] = ""
    mem.save()
    yield mem
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_character_background_edit_merge(memory):
    # Mock project_updates from PM
    updates = {
        "characters": {
            "upsert": [
                {
                    "name": "TestHero",
                    "fields": {
                        "background": "Born in a small village."
                    }
                }
            ]
        }
    }
    
    stats = memory.apply_project_updates(updates)
    
    assert stats["characters_updated"] == 1
    assert memory.data["characters"][0]["name"] == "TestHero"
    assert memory.data["characters"][0]["description"] == "A brave knight" # Should be preserved
    assert memory.data["characters"][0]["background"] == "Born in a small village."
