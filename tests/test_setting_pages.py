import pytest
import os
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_memory_settings.json"

@pytest.fixture
def memory():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    yield mem
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_setting_pages_crud(memory):
    # Create
    page = memory.create_setting_page(title="The Glass Guild", category="organization", content="Makers of fine glass.")
    assert page["title"] == "The Glass Guild"
    assert page["category"] == "organization"
    assert len(memory.data["setting_pages"]) == 1
    
    # Update
    updated = memory.update_setting_page(page["id"], {"title": "The Grand Glass Guild", "content_markdown": "Updated content."})
    assert updated["title"] == "The Grand Glass Guild"
    
    # Delete
    memory.delete_setting_page(page["id"])
    assert len(memory.data["setting_pages"]) == 0
