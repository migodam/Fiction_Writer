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
    Special Rule: If the user is asking to add or change a character's background, traits, or description (e.g., "添加人物background"), set intent_type="edit", needs_project_update=true, and needs_sections=["characters"].
    
    If specific names are present in the request, list them in a "target_entities" field; otherwise set a "scope" field to "all_characters" if it's a general character edit.
    
    Output JSON schema:
    {{
      "intent_type": "create|edit|query|memory_change",
      "scope": "string|null",
      "target_entities": ["string"],
      "ambiguous_update": true|false,
      "needs_project_update": true|false,
      "needs_global_rule_update": true|false,
      "needs_sections": ["governance", "outline", "characters", "timeline"],
      "target_agents": ["core_planner", "project_manager"]
    }}
    """
    messages = [{"role": "system", "content": "You are a routing agent. Output ONLY valid JSON."}, 
                {"role": "user", "content": prompt}]
    
    try:
        response = client.chat(messages)
        clean = response.strip().replace("```json", "").replace("```", "")
        return json.loads(clean)
    except Exception as e:
        # Fallback routing
        return {
            "intent_type": "query",
            "ambiguous_update": False,
            "needs_project_update": False,
            "needs_global_rule_update": False,
            "needs_sections": [],
            "target_agents": ["core_planner"]
        }
