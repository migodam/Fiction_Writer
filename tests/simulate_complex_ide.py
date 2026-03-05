import json
import os
from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.orchestrator import run_pipeline
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input

# Setup - Empty Project
MEM_FILE = "data/sim_complex_ide.json"
if os.path.exists(MEM_FILE): os.remove(MEM_FILE)
memory = ProjectMemory(file_path=MEM_FILE)
store = MemoryStore()
with open("tests/api_key.txt", "r") as f:
    client = OpenAIClient(api_key=f.read().strip(), model="gpt-4o-mini")

def test_complex_scenario():
    print("\n--- Phase 1: Clarification Trigger ---")
    user_text_1 = "Create a new character."
    routing_1 = route_user_input(user_text_1, {}, {}, client)
    res_1 = run_pipeline(user_text_1, "Chat", {}, memory, store, client, routing_1)
    
    # We expect questions_for_user to be populated
    q_len = len(res_1.get("core_summary", {}).get("questions_for_user", []))
    print(f"Questions asked by AI: {q_len}")
    if q_len == 0:
        print("WARNING: AI did not ask for clarification!")
        print(f"Core Summary: {res_1.get('core_summary')}")

    print("\n--- Phase 2: Create Character with Tags & Aliases ---")
    user_text_2 = "Create a character named Arthur Pendragon. He is a king. Tags: leader, sword, royal. Aliases: Artie, The Once and Future King."
    routing_2 = route_user_input(user_text_2, {}, {}, client)
    res_2 = run_pipeline(user_text_2, "Project Updates", {}, memory, store, client, routing_2)
    print(f"Applied Updates: {res_2['pm_counts']}")
    
    memory.load()
    arthur = next((c for c in memory.data.get("characters", []) if c["name"] == "Arthur Pendragon"), None)
    if arthur:
        print(f"Character Created: {arthur['name']}")
        print(f"Tags parsed: {arthur.get('tags')}")
        print(f"Aliases parsed: {arthur.get('aliases')}")
    else:
        print("FAILURE: Character not created.")

    print("\n--- Phase 3: Create Outline Structure ---")
    user_text_3 = "Create a 3-chapter outline about Arthur pulling the sword from the stone."
    routing_3 = route_user_input(user_text_3, {}, {}, client)
    res_3 = run_pipeline(user_text_3, "Project Updates", {}, memory, store, client, routing_3)
    print(f"Applied Updates: {res_3['pm_counts']}")
    
    memory.load()
    outline = memory.data.get("outline", [])
    print(f"Outline Nodes Created: {len(outline)}")
    for node in outline:
        summary = node.get('summary') or ''
        print(f" -> {node.get('title')}: {summary[:30]}...")

if __name__ == "__main__":
    test_complex_scenario()
