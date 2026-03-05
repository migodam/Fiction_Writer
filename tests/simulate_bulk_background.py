import json
import os
import shutil
from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.orchestrator import run_pipeline
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input

# Setup
shutil.copy2("tests/fixtures/golden_project.json", "data/sim_bulk_bg.json")
memory = ProjectMemory(file_path="data/sim_bulk_bg.json")
store = MemoryStore()
with open("tests/api_key.txt", "r") as f:
    client = OpenAIClient(api_key=f.read().strip(), model="gpt-4o-mini")

def run_sim():
    user_text = "给所有人物创作一个background"
    print(f"\n[SIM] User Request: {user_text}")
    
    # 1. Routing
    routing = route_user_input(user_text, {}, {}, client)
    print(f"[SIM] Routing: intent={routing.get('intent_type')}, sections={routing.get('needs_sections')}")
    
    # 2. Pipeline
    res = run_pipeline(user_text, "Project Updates", {}, memory, store, client, routing)
    
    # 3. Analysis
    print(f"[SIM] Applied Updates: {res['pm_counts']}")
    print(f"[SIM] Expansion Ran: {res['diagnostics']['expansion_stage_ran']}")
    
    if res['pm_counts'].get('characters_updated', 0) > 0:
        memory.load()
        for c in memory.data['characters']:
            print(f" -> Character: {c['name']} | Background Length: {len(c.get('background', ''))}")
    else:
        print(f"[SIM] FAILURE: No updates applied.")
        print(f"--- DEBUG DATA ---")
        print(f"Stage B Raw: {res['diagnostics'].get('core_planner_raw_b')}")
        print(f"Expanded Plan: {json.dumps(res['diagnostics'].get('expanded_plan'), indent=2, ensure_ascii=False)}")
        print(f"PM Raw: {res['diagnostics'].get('pm_raw')}")
        print(f"Failure Analysis: {res['diagnostics'].get('failure_explanation')}")

if __name__ == "__main__":
    run_sim()
