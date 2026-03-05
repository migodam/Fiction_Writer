import json
import os
import sys
from typing import List

from src.core.persistence import ProjectMemory
from src.core.memory_store import MemoryStore
from src.ai.orchestrator import run_pipeline
from src.ai.openai_client import OpenAIClient
from src.ai.router import route_user_input

# Setup - Empty Project
MEM_FILE = "data/sim_extreme_complex.json"
if os.path.exists(MEM_FILE):
    os.remove(MEM_FILE)
memory = ProjectMemory(file_path=MEM_FILE)
store = MemoryStore()

with open("tests/api_key.txt", "r") as f:
    key = f.read().strip()
    
# Primary client for the pipeline
client = OpenAIClient(api_key=key, model="gpt-4o") # Use 4o for better complex planning
# Simulator client to act as the human user
sim_client = OpenAIClient(api_key=key, model="gpt-4o-mini")

def simulate_user_answer(questions: List[str]) -> str:
    """Uses LLM to pretend to be a creative author answering the AI's clarifying questions."""
    prompt = f"""
    You are an imaginative author writing a modern steampunk novel. 
    Your AI assistant just asked you these questions to help build your world:
    {json.dumps(questions, ensure_ascii=False)}
    
    Provide creative, detailed answers. Give your characters cool names, outline a basic conflict, and describe a unique setting.
    Output ONLY your answer in Chinese, as if you are replying directly to the assistant. Do not add any preamble.
    """
    messages = [{"role": "system", "content": "You are a creative writer."}, {"role": "user", "content": prompt}]
    return sim_client.chat(messages).strip()

def run_extreme_simulation():
    print("\n" + "="*50)
    print("🚀 EXTREME SIMULATION START: Multi-Round & Major Refactor")
    print("="*50)

    # ---------------------------------------------------------
    # ROUND 1: Vague Request
    # ---------------------------------------------------------
    print("\n--- [ROUND 1] Vague Initialization ---")
    user_text_1 = "我想写一个关于现代蒸汽朋克的故事，帮我建个项目。"
    print(f"User: {user_text_1}")
    
    routing_1 = route_user_input(user_text_1, {}, {}, client)
    res_1 = run_pipeline(user_text_1, "Chat", {}, memory, store, client, routing_1)
    
    questions = res_1.get("core_summary", {}).get("questions_for_user", [])
    
    # If the AI decided to just create it anyway (due to the "create" router fallback), 
    # we still want to simulate a conversation.
    if not questions:
        print("AI didn't ask questions. Forcing a simulated follow-up.")
        simulated_answer = "主角叫艾伦，是一个机械臂发明家，在一个由巨型财阀控制的雾都里生存。他发现了一个能推翻财阀的古代图纸。"
    else:
        print(f"AI asked {len(questions)} questions:")
        for q in questions: print(f"  - {q}")
        
        print("\n⏳ Simulating Author's Response...")
        simulated_answer = simulate_user_answer(questions)
        
    print(f"Author (Simulated): {simulated_answer}")

    # ---------------------------------------------------------
    # ROUND 2: Detailed Creation
    # ---------------------------------------------------------
    print("\n--- [ROUND 2] Detailed Worldbuilding Execution ---")
    # We combine the intent with the answer to ensure the router catches the creation intent.
    user_text_2 = f"根据我刚才的设定帮我完整初始化这个项目（包括主角和反派人物、大纲、时间线、场景）。设定是：{simulated_answer}"
    routing_2 = route_user_input(user_text_2, {}, {}, client)
    
    print(f"Router identified intent: {routing_2.get('intent_type')} | sections: {routing_2.get('needs_sections')}")
    
    res_2 = run_pipeline(user_text_2, "Project Updates", {}, memory, store, client, routing_2)
    
    print("\n📊 ROUND 2 RESULTS:")
    print(f"Updates Applied: {res_2['pm_counts']}")
    
    memory.load()
    print(f"Characters: {len(memory.data['characters'])}")
    for c in memory.data['characters']:
        desc = c.get('description') or ''
        print(f"  - {c['name']} (Tags: {c.get('tags')}) -> {desc[:30]}...")
        
    print(f"Settings: {len(memory.data['setting_pages'])}")
    for s in memory.data['setting_pages']:
        print(f"  - {s['title']} ({len(s.get('items', []))} items)")
        
    print(f"Timeline Events: {len(memory.data['timeline_events'])}")
    for t in memory.data['timeline_events']:
        print(f"  - {t['title']} (Participants: {t.get('participants')})")
        
    print(f"Outline Nodes: {len(memory.data['outline'])}")
    for o in memory.data['outline']:
        print(f"  - {o.get('title')}")

    # ---------------------------------------------------------
    # ROUND 3: Major Refactor (The "大改" test)
    # ---------------------------------------------------------
    print("\n--- [ROUND 3] Major Refactor (Tone & History Shift) ---")
    user_text_3 = "大改：把故事基调变得非常黑暗。主角其实以前是个杀人不眨眼的财阀走狗，他失去记忆才以为自己是个普通发明家。更新他的背景和目标，并在时间线上添加他过去屠杀贫民窟的事件。"
    print(f"User: {user_text_3}")
    
    routing_3 = route_user_input(user_text_3, {}, {}, client)
    print(f"Router identified intent: {routing_3.get('intent_type')} | sections: {routing_3.get('needs_sections')}")
    
    res_3 = run_pipeline(user_text_3, "Project Updates", {}, memory, store, client, routing_3)
    
    print("\n📊 ROUND 3 RESULTS (Refactor):")
    print(f"Updates Applied: {res_3['pm_counts']}")
    
    memory.load()
    
    # Analyze the refactor results
    print("\n🔍 POST-REFACTOR ANALYSIS:")
    for c in memory.data['characters']:
        print(f"Character: {c['name']}")
        bg = c.get('background') or ''
        gl = c.get('goals') or ''
        print(f"  -> New Background: {bg[:100]}...")
        print(f"  -> New Goals: {gl[:100]}...")
        
    print("\nTimeline Events Check:")
    massacre_found = False
    for t in memory.data['timeline_events']:
        print(f"  - {t['time']}: {t['title']}")
        title = str(t.get('title', ''))
        summary = str(t.get('summary', ''))
        if "杀" in title or "杀" in summary or "贫民窟" in summary or "massacre" in title.lower() or "massacre" in summary.lower():
            massacre_found = True
            
    if massacre_found:
        print("✅ SUCCESS: Dark history event was successfully added to the timeline.")
    else:
        print("❌ FAILURE: The AI failed to add the requested historical event.")

    if sum(res_3['pm_counts'].values()) > 0:
        print("\n🎉 EXTREME SIMULATION COMPLETED SUCCESSFULLY.")
    else:
        print("\n⚠️ EXTREME SIMULATION ENCOUNTERED FAILURES.")
        if res_3.get('diagnostics', {}).get('failure_explanation'):
            print(res_3['diagnostics']['failure_explanation'])

if __name__ == "__main__":
    run_extreme_simulation()
