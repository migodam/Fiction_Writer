import json
import os
import re
from typing import Dict, Any, Optional, Tuple, List
from src.ai.openai_client import OpenAIClient
from src.ai.context_builder import build_context_packet

def _get_prompt(key: str, default: str) -> str:
    path = "config/prompts.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get(key, default)
    return default

def safe_parse_json(raw: str) -> Tuple[Optional[Dict], Optional[str]]:
    if not raw:
        return None, "Empty input"
    text = re.sub(r"```json\s*", "", raw)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    start_idx = -1
    for i, char in enumerate(text):
        if char in '{[':
            start_idx = i
            break
    if start_idx == -1:
        return None, "No JSON structure found"
    end_char = '}' if text[start_idx] == '{' else ']'
    end_idx = text.rfind(end_char)
    if end_idx == -1 or end_idx < start_idx:
        return None, f"Incomplete JSON"
    json_str = text[start_idx : end_idx + 1]
    try:
        return json.loads(json_str), None
    except json.JSONDecodeError as e:
        return None, f"JSON Error: {str(e)}"

def validate_planner_output(obj: Dict) -> Tuple[bool, List[str], Dict]:
    required_keys = ["classification", "user_output", "modification_plan", "memory_change_proposals", "questions_for_user"]
    missing = [k for k in required_keys if k not in obj]
    defaults = {
        "user_output": {"content_markdown": "", "what_will_change": [], "what_will_not_change": []},
        "classification": {"request_type": "meta", "update_target": "neither", "needs_project_update": False, "needs_memory_update": False, "confidence": 0.0},
        "modification_plan": {"scope": "mixed", "rationale": "", "constraints": [], "steps": []},
        "memory_change_proposals": {"global": [], "agents": []},
        "questions_for_user": []
    }
    normalized = obj.copy()
    for k, default_val in defaults.items():
        if k not in normalized or not isinstance(normalized[k], type(default_val)):
            normalized[k] = default_val
    ok = len(normalized.get("modification_plan", {}).get("steps", [])) > 0
    return ok, missing, normalized

def needs_expansion(plan_json: Dict) -> bool:
    steps = plan_json.get("modification_plan", {}).get("steps", [])
    for step in steps:
        field_updates = step.get("field_updates", {})
        # If any field value looks like a strategy/instruction rather than content
        strategy_keys = ["background_fill", "style", "also_fill_description_if_missing"]
        if any(k in field_updates for k in strategy_keys):
            return True
        # Or if it's a query that needs expansion into concrete text
        if step.get("target", {}).get("by") == "query":
            return True
    return False

def expand_plan_with_core(plan_json: Dict, context_packet: Dict, client: OpenAIClient, language: str = "English") -> Tuple[Dict, Optional[str]]:
    core_p = _get_prompt("core_planner_prompt", "You are a world architect.")
    steps = plan_json.get("modification_plan", {}).get("steps", [])
    
    # Build a targeted summary of entities mentioned in steps
    targets_summary = []
    # Simplified extraction for expansion stage
    prompt = f"""
    {core_p}
    Language: {language}
    
    Task: Stage B - Execution. 
    Expand the following strategic modification plan into CONCRETE text fields.
    Strategic Plan: {json.dumps(plan_json.get("modification_plan"))}
    
    Relevant Context: {json.dumps(context_packet)[:6000]}
    
    Rules:
    - Replace strategic fields (like 'background_fill') with ACTUAL narrative text.
    - If it's a query, provide concrete field updates for the targets identified in context.
    - Output the EXACT same modification_plan JSON structure, but with 'field_updates' containing real content.
    - Output ONLY JSON.
    """
    msg = [{"role": "system", "content": "You are the Execution Agent. Output strictly JSON."}, {"role": "user", "content": prompt}]
    try:
        raw = client.chat(msg)
        obj, err = safe_parse_json(raw)
        if obj:
            return obj, None
        return plan_json["modification_plan"], f"Expansion Parse Error: {err}"
    except Exception as e:
        return plan_json["modification_plan"], f"Expansion Call Error: {str(e)}"

def run_pipeline(user_text: str, ui_choice: str, workbench_state: Dict[str, Any], project_memory: Any, store: Any, client: OpenAIClient, routing: Dict[str, Any]) -> Dict[str, Any]:
    ctx_packet = build_context_packet(routing=routing, project_memory=project_memory.data, global_memory_paths={}, agent_memory_paths={}, store=store)
    context_brief = ctx_packet
    # ... summarizer logic would go here ...

    planner_p = _get_prompt("core_planner_prompt", "You are the Core Planner.")
    planner_prompt = f"{planner_p}\nUser Request: {user_text}\nContext: {json.dumps(context_brief)[:10000]}\nOutput strictly JSON."
    plan_msg = [{"role": "system", "content": planner_p}, {"role": "user", "content": planner_prompt}]
    
    pipeline_errors = []
    diagnostics = {"expansion_ran": False}
    
    try:
        planner_raw = client.chat(plan_msg)
        plan_obj, parse_err = safe_parse_json(planner_raw)
        if parse_err:
            pipeline_errors.append({"stage": "core_planner_parse", "error": parse_err})
            _, _, plan_json = validate_planner_output({})
        else:
            _, missing, plan_json = validate_planner_output(plan_obj)
            diagnostics["planner_missing_keys"] = missing
    except Exception as e:
        pipeline_errors.append({"stage": "core_planner_call", "error": str(e)})
        _, _, plan_json = validate_planner_output({})

    # Stage B: Expansion
    if routing.get("needs_project_update") and needs_expansion(plan_json):
        diagnostics["expansion_ran"] = True
        expanded_mod_plan, exp_err = expand_plan_with_core(plan_json, context_brief, client)
        if exp_err:
            pipeline_errors.append({"stage": "expansion", "error": exp_err})
        else:
            plan_json["modification_plan"] = expanded_mod_plan

    pm_updates = {}
    mod_plan = plan_json.get("modification_plan", {})
    if routing.get("needs_project_update") and mod_plan.get("steps"):
        pm_p = _get_prompt("project_manager_prompt", "You are the Project Manager.")
        # Enhance PM prompt with expansion rules
        pm_prompt = f"""
        {pm_p}
        Task: Map the Modification Plan to project_updates JSON.
        Plan: {json.dumps(mod_plan)}
        Context: {json.dumps(context_brief)[:8000]}
        
        Special Mapping Rules:
        1. QUERY EXPANSION: If target.by is 'query' (e.g. 'background is missing'), find matching characters in Context and generate individual upserts.
        2. SETTING BACKGROUND: If entity_type is 'setting_page' and has 'background' or 'content' updates, map them to an item named 'Background' inside that page.
        
        Output Schema: {{ "project_updates": {{ "characters": {{ "upsert": [] }}, "setting_pages": {{ "upsert_items": [] }} }} }}
        """
        try:
            pm_raw = client.chat([{"role": "system", "content": pm_p}, {"role": "user", "content": pm_prompt}])
            pm_obj, pm_err = safe_parse_json(pm_raw)
            if pm_obj:
                pm_updates = pm_obj.get("project_updates", pm_obj)
                # Client-side query expansion fallback if LLM missed it
                # (Ideally the LLM handles it given the prompt above)
            else:
                pipeline_errors.append({"stage": "pm_parse", "error": pm_err})
        except Exception as e:
            pipeline_errors.append({"stage": "pm_call", "error": str(e)})

    update_counts = {}
    if pm_updates:
        update_counts = project_memory.apply_project_updates(pm_updates)

    return {
        "context_stats": ctx_packet["limits"],
        "core_summary": plan_json.get("user_output", {}),
        "pm_counts": update_counts,
        "project_updates": pm_updates,
        "errors": pipeline_errors,
        "diagnostics": diagnostics
    }
