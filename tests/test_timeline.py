import pytest
import os
from src.core.persistence import ProjectMemory

TEST_FILE = "data/test_memory_timeline.json"

@pytest.fixture
def memory():
    # Setup
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    mem = ProjectMemory(file_path=TEST_FILE)
    yield mem
    # Teardown
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

def test_timeline_crud(memory):
    # Create
    event = memory.add_timeline_event(
        title="The Burning of Glass Harbor",
        time="Year 182",
        participants="Lorian, The Glass Guild",
        summary="A tragic fire."
    )
    
    assert event["title"] == "The Burning of Glass Harbor"
    assert event["time"] == "Year 182"
    assert "Lorian" in event["participants"]
    assert len(memory.data["timeline_events"]) == 1
    
    # Update
    updated = memory.update_timeline_event(event["id"], {"summary": "A devastating fire."})
    assert updated["summary"] == "A devastating fire."
    assert memory.data["timeline_events"][0]["summary"] == "A devastating fire."
    
    # Reload from file to verify persistence
    memory2 = ProjectMemory(file_path=TEST_FILE)
    assert len(memory2.data["timeline_events"]) == 1
    
    # Delete
    memory.delete_timeline_event(event["id"])
    assert len(memory.data["timeline_events"]) == 0
