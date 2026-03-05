import json
import os
from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.orchestrator import run_pipeline
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input

# Setup - Empty Project
MEM_FILE = "data/sim_steampunk.json"
if os.path.exists(MEM_FILE): os.remove(MEM_FILE)
memory = ProjectMemory(file_path=MEM_FILE)
store = MemoryStore()
with open("tests/api_key.txt", "r") as f:
    client = OpenAIClient(api_key=f.read().strip(), model="gpt-4o-mini")

def run_sim():
    user_text = "给我一个现代蒸汽朋克故事"
    print(f"\n[SIM] User Request: {user_text}")
    
    # 1. Routing
    routing = route_user_input(user_text, {}, {}, client)
    print(f"[SIM] Routing: intent={routing.get('intent_type')}, sections={routing.get('needs_sections')}")
    
    # 2. Pipeline
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    # 3. Analysis
    print(f"[SIM] Applied Updates: {res['pm_counts']}")
    
    memory.load()
    print(f"[SIM] Worldscaffold Results:")
    print(f" -> Characters: {len(memory.data['characters'])}")
    print(f" -> Events: {len(memory.data['timeline_events'])}")
    print(f" -> Setting Pages: {len(memory.data['setting_pages'])}")
    
    if sum(res['pm_counts'].values()) == 0:
        print(f"[SIM] FAILURE: Project remains empty.")
        print(f"Diagnostics: {res['diagnostics'].get('failure_explanation')}")

if __name__ == "__main__":
    run_sim()
