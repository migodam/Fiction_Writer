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

def needs_expansion(plan_json: Dict, user_text: str = "") -> bool:
    steps = plan_json.get("modification_plan", {}).get("steps", [])
    creative_keywords = ["出生", "背景", "故事", "起源", "birth", "background", "origin", "elaborate"]
    user_text_lower = user_text.lower()
    
    if any(k in user_text_lower for k in creative_keywords):
        return True

    for step in steps:
        field_updates = step.get("field_updates", {})
        strategy_keys = ["background_fill", "style", "also_fill_description_if_missing"]
        if any(k in field_updates for k in strategy_keys):
            return True
        if step.get("target", {}).get("by") == "query":
            return True
    return False
def expand_plan_with_core(plan_json: Dict, context_packet: Dict, client: OpenAIClient, language: str = "English") -> Tuple[Dict, str, Optional[str]]:
    """Returns (expanded_mod_plan, raw_output, error_msg)"""
    core_p = _get_prompt("core_planner_prompt", "You are a world architect.")
    prompt = f"""
    {core_p}
    Language: {language}
    Task: Stage B - Execution. Expand the strategic modification plan into a concrete version with FULL narrative content.

    Strategic Plan: {json.dumps(plan_json.get("modification_plan"))}
    Relevant Context: {json.dumps(context_packet)[:6000]}

    ## Output Format (REQUIRED)
    You must output ONLY JSON in this format:
    {{
      "scope": "...",
      "rationale": "...",
      "steps": [
        {{
          "op": "upsert",
          "entity_type": "...",
          "target": {{ "by": "...", "value": "..." }},
          "field_updates": {{ "background": "FULL STORY HERE", "traits": "..." }}
        }}
      ]
    }}
    """
    msg = [{"role": "system", "content": "You are the Execution Agent. Output strictly JSON containing a 'steps' array."}, {"role": "user", "content": prompt}]

    raw = ""
    try:
        raw = client.chat(msg)
        obj, err = safe_parse_json(raw)
        if obj:
            # G4/G5: Extract the plan if AI nested it inside 'modification_plan'
            actual_plan = obj.get("modification_plan", obj)
            return actual_plan, raw, None
        return plan_json.get("modification_plan", {}), raw, f"Expansion Parse Error: {err}"
    except Exception as e:
        return plan_json.get("modification_plan", {}), raw, f"Expansion Call Error: {str(e)}"

def resolve_query_targets(step: Dict, memory_data: Dict, intent_type: str = "query") -> List[Dict]:
    entity_type = step.get("entity_type")
    target = step.get("target", {})
    t_by = target.get("by", "")
    t_val = str(target.get("value", "")).lower()
    op = step.get("op", "upsert")
    
    if op == "upsert" and intent_type == "create" and t_by == "all":
        return []

    entities = memory_data.get(entity_type + "s", []) if not entity_type.endswith("s") else memory_data.get(entity_type, [])
    if not entities and entity_type == "character": entities = memory_data.get("characters", [])
    
    results = []
    if t_by == "all" or "all" in t_val:
        return [{"id": e.get("id"), "name": e.get("name")} for e in entities]
    
    if t_by == "query":
        for e in entities:
            match = False
            if "background is missing" in t_val or "empty background" in t_val:
                if not e.get("background") or e.get("background").strip() == "": match = True
            elif "description is missing" in t_val or "empty description" in t_val:
                if not e.get("description") or e.get("description").strip() == "": match = True
            if match:
                results.append({"id": e.get("id"), "name": e.get("name")})
    return results

def explain_failure(user_text: str, routing: Dict, plan_json: Dict, pm_json: Dict, memory_data: Dict, metrics: Dict, client: OpenAIClient) -> Tuple[str, List[str]]:
    reasons = []
    evidence = []
    suggestions = []
    
    steps = plan_json.get("modification_plan", {}).get("steps", [])
    existing_char_ids = {str(c.get("id")) for c in memory_data.get("characters", [])}
    existing_char_names = {str(c.get("name")) for c in memory_data.get("characters", [])}

    # --- STEP 0: PM Output Check ---
    if not pm_json:
        reasons.append("PM Output Empty/Invalid")
        evidence.append("Project Manager failed to produce a valid update JSON.")
        suggestions.append("Check the Project Manager prompt or try a simpler request.")
    elif not any(pm_json.get(k, {}).get("upsert") for k in ["characters", "timeline_events", "relationships", "setting_pages"]):
        reasons.append("PM Emitted No Updates")
        evidence.append("PM produced a valid JSON structure, but all 'upsert' lists are empty.")
        suggestions.append("The PM couldn't map the plan to specific data changes. Try specifying names.")

    # --- STEP 1: Reference Integrity ---
    for step in steps:
        if step.get("entity_type") == "timeline_event":
            participants = step.get("field_updates", {}).get("participants", [])
            if isinstance(participants, list) and len(participants) > 0:
                broken_refs = [p for p in participants if str(p) not in existing_char_ids and str(p) not in existing_char_names]
                if broken_refs:
                    reasons.append("Invalid Participant References")
                    evidence.append(f"Participants {broken_refs} do not exist. AI used placeholders instead of real IDs/Names.")
                    suggestions.append(f"Refer to characters by their exact names: {list(existing_char_names)[:3]}")

    # --- STEP 2: Selector Check ---
    for step in steps:
        t_by = step.get("target", {}).get("by")
        if t_by and t_by not in ["id", "name", "query", "all"]:
            reasons.append("Unsupported Target Selector")
            evidence.append(f"Entity {step.get('entity_type')} used unsupported 'target.by={t_by}'.")
            suggestions.append("Try using 'name' matching in your request.")

    # --- STEP 3: Schema Check ---
    if pm_json and sum(metrics.values() if isinstance(metrics, dict) else [0]) == 0:
        known_keys = {"characters", "timeline_events", "relationships", "setting_pages"}
        found_keys = set(pm_json.keys())
        weird_keys = found_keys - known_keys
        if weird_keys:
            reasons.append("Schema Key Mismatch")
            evidence.append(f"PM used non-standard keys: {weird_keys}. Persistence expects: {known_keys}")
            suggestions.append("Review the Project Manager Prompt in Prompt Manager.")

    if not reasons:
        explanation = "### 🚩 Pipeline Logic Gap\nNo obvious rules were violated, but updates didn't apply. AI may have struggled to map the plan to the data model."
        explanation += "\n\n**Action:** Try a more explicit prompt or check if the target exists."
    else:
        explanation = "### 🚩 Failure Diagnosis (Evidence-Based)\n" + "\n".join([f"- **{r}**: {e}" for r, e in zip(reasons, evidence)])
        explanation += "\n\n**Actionable Suggestions:**\n" + "\n".join([f"{i+1}. {s}" for i, s in enumerate(suggestions)])

    return explanation, reasons

def run_pipeline(user_text: str, ui_choice: str, workbench_state: Dict[str, Any], project_memory: Any, store: Any, client: OpenAIClient, routing: Dict[str, Any]) -> Dict[str, Any]:
    planner_raw_a, planner_raw_b = "", ""
    pm_raw = "(Skipped: No project update needed according to router)"
    planner_err_a, planner_err_b = None, None
    expansion_ran = False
    pipeline_error_summary = None
    update_counts = {}
    pm_updates = {}
    
    _, _, plan_json = validate_planner_output({})
    ctx_packet = build_context_packet(routing=routing, project_memory=project_memory.data, global_memory_paths={}, agent_memory_paths={}, store=store)

    try:
        # Stage A: Strategy
        planner_p = _get_prompt("core_planner_prompt", "You are the Core Planner.")
        try:
            planner_raw_a = client.chat([{"role": "system", "content": planner_p}, {"role": "user", "content": f"{planner_p}\nReq: {user_text}\nCtx: {json.dumps(ctx_packet)[:8000]}"}])
            plan_obj, p_err = safe_parse_json(planner_raw_a)
            if p_err: 
                planner_err_a = p_err
                plan_json["user_output"]["content_markdown"] = "⚠️ Core Planner (Stage A) failed to produce valid JSON."
            else: 
                _, _, plan_json = validate_planner_output(plan_obj)
        except Exception as e: 
            planner_err_a = str(e)
            plan_json["user_output"]["content_markdown"] = f"⚠️ Stage A Call Error: {planner_err_a}"

        # SELF-HEALING & NAME RESOLUTION logic remains the same (removed in favor of Stage D resolution)

        # Stage B: Expansion
        if not planner_err_a and routing.get("needs_project_update") and needs_expansion(plan_json, user_text):
            expansion_ran = True
            expanded_plan, planner_raw_b, planner_err_b = expand_plan_with_core(plan_json, ctx_packet, client)
            if not planner_err_b:
                plan_json["modification_plan"] = expanded_plan
            else:
                plan_json["user_output"]["content_markdown"] += f"\n\n⚠️ Expansion failed: {planner_err_b}"

        # Stage C: PM Mapping
        mod_plan = plan_json.get("modification_plan", {})
        if not planner_err_a and not planner_err_b and routing.get("needs_project_update") and mod_plan.get("steps"):
            pm_raw = "(Failed to produce output)"
            for step in mod_plan["steps"]:
                if step.get("target", {}).get("by") in ["query", "all"]:
                    step["resolved_targets"] = resolve_query_targets(step, project_memory.data, intent_type=routing.get("intent_type"))
            
            pm_p = _get_prompt("project_manager_prompt", "You are the Project Manager.")
            pm_prompt = f"{pm_p}\nTask: Map to project_updates JSON.\nPlan: {json.dumps(mod_plan)}\nContext: {json.dumps(ctx_packet)[:8000]}"
            try:
                pm_raw = client.chat([{"role": "system", "content": pm_p}, {"role": "user", "content": pm_prompt}])
                pm_obj, pm_err = safe_parse_json(pm_raw)
                if pm_obj: 
                    pm_updates = pm_obj.get("project_updates", pm_obj)
                    if "project_updates" not in pm_obj and not any(k in pm_obj for k in ["characters", "timeline_events", "setting_pages"]):
                        pipeline_error_summary = "PM output missing project_updates key and known entities."
                else: pipeline_error_summary = f"PM Parse Error: {pm_err}"
            except Exception as e: pipeline_error_summary = f"PM Call Error: {str(e)}"
        elif not planner_err_a and routing.get("needs_project_update") and not mod_plan.get("steps"):
            pm_raw = "(Skipped: Modification plan has no steps)"

        # Stage D: Apply
        if pm_updates and not pipeline_error_summary:
            # G3: Final Name-to-ID Resolution before Apply
            char_name_map = {c.get("name"): c.get("id") for c in project_memory.data.get("characters", [])}
            
            # Resolve character updates
            for char_upd in pm_updates.get("characters", {}).get("upsert", []):
                val = char_upd.get("id_or_name")
                if val in char_name_map: char_upd["id"] = char_name_map[val]
            
            # Resolve timeline participants
            for tl_upd in pm_updates.get("timeline_events", {}).get("upsert", []):
                parts = tl_upd.get("participants", [])
                if isinstance(parts, list):
                    tl_upd["participants"] = [char_name_map.get(p, p) for p in parts]

            update_counts = project_memory.apply_project_updates(pm_updates)

        # Stage E: Failure Analysis
        total_applied = sum(update_counts.values()) if isinstance(update_counts, dict) else 0
        failure_explanation, failure_reasons = None, []
        if routing.get("needs_project_update") and total_applied == 0:
            failure_explanation, failure_reasons = explain_failure(user_text, routing, plan_json, pm_updates, project_memory.data, update_counts, client)

    finally:
        return {
            "context_stats": ctx_packet.get("limits", {}),
            "core_summary": plan_json.get("user_output", {}),
            "pm_counts": update_counts,
            "project_updates": pm_updates,
            "diagnostics": {
                "core_planner_raw_a": planner_raw_a,
                "core_planner_raw_b": planner_raw_b,
                "pm_raw": pm_raw,
                "expansion_stage_ran": expansion_ran,
                "pipeline_error_summary": pipeline_error_summary,
                "failure_explanation": failure_explanation,
                "failure_reasons": failure_reasons
            }
        }
