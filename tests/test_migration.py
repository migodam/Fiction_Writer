import pytest
import os
import json
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_migration.json"

@pytest.fixture
def bad_data():
    # Construct a legacy JSON with 'name' instead of 'title'
    data = {
        "setting_pages": [
            {
                "name": "Legacy Page",
                "items": [{"name": "Item 1"}]
            },
            {
                "title": "Modern Page",
                "items": []
            }
        ]
    }
    with open(TEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    yield TEST_FILE
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_setting_page_migration(bad_data):
    memory = ProjectMemory(file_path=bad_data)
    # The load() inside init should have called normalize_data()
    
    pages = memory.data["setting_pages"]
    assert pages[0]["title"] == "Legacy Page"
    assert "id" in pages[0]
    assert "created_at" in pages[0]
    assert pages[1]["title"] == "Modern Page"

def test_empty_memory_initialization():
    memory = ProjectMemory(file_path="data/new_project.json")
    assert isinstance(memory.data["setting_pages"], list)
    if os.path.exists("data/new_project.json"):
        os.remove("data/new_project.json")
