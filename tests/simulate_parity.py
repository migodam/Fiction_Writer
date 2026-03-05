import json
import os
import shutil
from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.orchestrator import run_pipeline
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input

# Setup
TEST_MEM = "data/sim_parity_check.json"
if os.path.exists(TEST_MEM): os.remove(TEST_MEM)
memory = ProjectMemory(file_path=TEST_MEM)
# Add a dummy event to delete later
memory.add_timeline_event("Event to Delete", "2026", "None", "Will be removed")
memory.add_character("Old Character", "Desc", "Traits", "Goals", "Secrets")
memory.save()

store = MemoryStore()
with open("tests/api_key.txt", "r") as f:
    client = OpenAIClient(api_key=f.read().strip(), model="gpt-4o-mini")

def test_deletion_and_parity():
    print("\n--- SIMULATION: DELETION AND PARITY ---")
    
    # 1. Test Deletion
    user_text = "Delete the event 'Event to Delete' and remove the character 'Old Character'. Also create a new character named 'New Hero' with background 'Born in fire'."
    print(f"User: {user_text}")
    
    routing = route_user_input(user_text, {}, {}, client)
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    print(f"Applied: {res['pm_counts']}")
    
    memory.load()
    
    # CHECK JSON PARITY
    event_exists = any(e['title'] == "Event to Delete" for e in memory.data['timeline_events'])
    char_exists = any(c['name'] == "Old Character" for c in memory.data['characters'])
    new_char = next((c for c in memory.data['characters'] if c['name'] == "New Hero"), None)
    
    print(f"Event Deleted? {not event_exists}")
    print(f"Old Char Deleted? {not char_exists}")
    
    if new_char:
        print(f"New Char 'background' field: '{new_char.get('background')}'")
        print(f"New Char 'description' field (Synced?): '{new_char.get('description')}'")
        print(f"New Char UI Metadata (is_new_update): {new_char.get('ui_metadata', {}).get('is_new_update')}")
    else:
        print("FAILURE: New Char not found.")

    # CHECK INTEGRITY
    assert not event_exists
    assert not char_exists
    assert new_char
    assert new_char.get('background') == "Born in fire" or "fire" in str(new_char.get('background'))
    assert new_char.get('description') == new_char.get('background')
    
    print("\n✅ SIMULATION PARITY CHECK PASSED.")

if __name__ == "__main__":
    test_deletion_and_parity()
