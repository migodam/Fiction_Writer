import json
import os
from typing import Dict, Any
from src.ai.openai_client import OpenAIClient

def _load_routing_prompt():
    path = "config/prompts.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("routing_prompt")
    return None

def route_user_input(user_text: str, workbench_state: Dict[str, Any], memory_meta: Dict[str, Any], client: OpenAIClient) -> Dict[str, Any]:
    custom_p = _load_routing_prompt()
    base_p = custom_p if custom_p else "You are a routing agent."
    
    prompt = f"""
    {base_p}
    
    Analyze the user's request: "{user_text}"
    
    Determine if this is an edit, create, query, or memory_change.
    Special Rules: 
    1. If the user is asking to add or change a character's background, traits, or description, set intent_type="edit", needs_project_update=true, and needs_sections=["characters"].
    2. If the user is adding details to a location, building, or setting object (e.g., "In the Church..."), set intent_type="edit", needs_project_update=true, and needs_sections=["settings"].
    3. If user says "添加事件" or "出生", set needs_sections=["timeline"].
    
    Output JSON schema:
    {{
      "intent_type": "create|edit|query|memory_change",
      "scope": "string|null",
      "target_entities": ["string"],
      "ambiguous_update": true|false,
      "needs_project_update": true|false,
      "needs_global_rule_update": true|false,
      "needs_sections": ["governance", "outline", "characters", "timeline", "settings"],
      "target_agents": ["core_planner", "project_manager"]
    }}
    """
    messages = [{"role": "system", "content": "You are a routing agent. Output ONLY valid JSON."}, 
                {"role": "user", "content": prompt}]
    
    try:
        response = client.chat(messages)
        clean = response.strip().replace("```json", "").replace("```", "")
        result = json.loads(clean)
    except Exception as e:
        # Fallback routing
        result = {
            "intent_type": "query",
            "ambiguous_update": False,
            "needs_project_update": False,
            "needs_global_rule_update": False,
            "needs_sections": [],
            "target_agents": ["core_planner"]
        }

    # Post-processing for creation/initialization
    if result.get("intent_type") == "create" and not result.get("needs_sections"):
        result["needs_sections"] = ["characters", "timeline", "settings"]
        result["needs_project_update"] = True
        result["target_agents"] = ["core_planner", "project_manager"]
    
    return result
