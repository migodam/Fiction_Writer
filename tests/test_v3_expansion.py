import pytest
import os
import json
from src.core.persistence import ProjectMemory
from src.ai.orchestrator import resolve_query_targets

TEST_FILE = "data/test_v3_expansion.json"

@pytest.fixture
def memory():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    # 1. Setup 3 characters, 2 with empty background
    mem.add_character("Char A", "Desc", "traits", "goals", "secrets")
    mem.data["characters"][0]["background"] = "Has background"
    mem.add_character("Char B", "Desc", "traits", "goals", "secrets")
    mem.data["characters"][1]["background"] = "" # Empty
    mem.add_character("Char C", "Desc", "traits", "goals", "secrets")
    # background missing for C
    mem.save()
    yield mem
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_resolve_query_targets(memory):
    step = {
        "entity_type": "character",
        "target": {"by": "query", "value": "background is missing"}
    }
    resolved = resolve_query_targets(step, memory.data)
    # Should find B and C
    names = [r["name"] for r in resolved]
    assert "Char B" in names
    assert "Char C" in names
    assert "Char A" not in names
    assert len(resolved) == 2

def test_apply_project_updates_robustness(memory):
    # Mock a PM output that includes upsert_items for a page
    page = memory.create_setting_page("The Guild")
    updates = {
        "project_updates": {
            "setting_pages": {
                "upsert_items": [
                    {
                        "page_id": page["id"],
                        "name": "Background",
                        "content": "New background text"
                    }
                ]
            }
        }
    }
    stats = memory.apply_project_updates(updates)
    assert stats["setting_items_created"] == 1
    assert memory.data["setting_pages"][0]["items"][0]["name"] == "Background"
