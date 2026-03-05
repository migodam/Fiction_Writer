import json
from typing import Dict, Any, List

def _serialize_and_check(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

def build_context_packet(routing: Dict[str, Any], project_memory: Dict[str, Any], global_memory_paths: Dict[str, str], agent_memory_paths: Dict[str, str], store) -> Dict[str, Any]:
    # G1: Robustness check for None store
    packet = {
        "request_summary": routing.get("intent_type", "unknown"),
        "governance_extract": store.read_governance_md() if store else "",
        "outline_extract": store.read_outline_md() if store else "",
        "tasks_extract": store.read_tasks_json(global_memory_paths.get("roadmap_tasks", "memory/global/roadmap_tasks.json")) if store else {},
        "project_snapshot_compact": {},
        "limits": {
            "char_budget": 12000,
            "used_chars": 0,
            "truncated": False,
            "overflow_summary": None
        }
    }

    # G7: Check if project memory is large enough to warrant compaction/truncation notification
    full_snapshot_size = len(_serialize_and_check(project_memory))
    
    compact = {}
    intent = routing.get("intent_type", "query")
    
    # If the database is larger than ~50% of the budget, we compact/truncate
    if full_snapshot_size > 6000:
        packet["limits"]["truncated"] = True
        packet["limits"]["overflow_summary"] = f"Truncated: Project memory ({full_snapshot_size} chars) exceeds safety threshold. Only active/recent entities included."
        
        # Smart Compaction
        compact["canon_facts"] = project_memory.get("canon_facts", [])[:5]
        compact["characters"] = project_memory.get("characters", [])[:10]
        compact["timeline_events"] = project_memory.get("timeline_events", [])[-10:]
        compact["setting_pages"] = project_memory.get("setting_pages", [])[:5]
    else:
        # Include everything if it fits
        compact = project_memory

    packet["project_snapshot_compact"] = compact

    # Measure and truncate
    serialized = _serialize_and_check(packet)
    used_chars = len(serialized)
    
    if used_chars > packet["limits"]["char_budget"]:
        packet["limits"]["truncated"] = True
        packet["limits"]["overflow_summary"] = "Context exceeded 12000 chars. Project snapshot and tasks were truncated."
        # Truncate things to fit
        packet["project_snapshot_compact"] = {"note": "Truncated to fit limits."}
        packet["tasks_extract"] = {"note": "Truncated to fit limits."}
        # Recalculate
        packet["limits"]["used_chars"] = len(_serialize_and_check(packet))
    else:
        packet["limits"]["used_chars"] = used_chars

    return packet
