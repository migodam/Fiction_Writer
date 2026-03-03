import json
from typing import Dict, Any, List

def _serialize_and_check(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

def build_context_packet(routing: Dict[str, Any], project_memory: Dict[str, Any], global_memory_paths: Dict[str, str], agent_memory_paths: Dict[str, str], store) -> Dict[str, Any]:
    packet = {
        "request_summary": routing.get("intent_type", "unknown"),
        "governance_extract": store.read_governance_md(),
        "outline_extract": store.read_outline_md(),
        "tasks_extract": store.read_tasks_json(global_memory_paths.get("roadmap_tasks", "memory/global/roadmap_tasks.json")),
        "project_snapshot_compact": {},
        "limits": {
            "char_budget": 12000,
            "used_chars": 0,
            "truncated": False,
            "overflow_summary": None
        }
    }

    # Build compact snapshot based on routing intent
    # If edit/query, extract neighborhood. If create, extract top N.
    # For simplicity in MVP, we just include all or slice top items.
    
    compact = {}
    intent = routing.get("intent_type", "query")
    if intent in ["create", "edit", "query"]:
        compact["canon_facts"] = project_memory.get("canon_facts", [])[:5]
        compact["characters"] = project_memory.get("characters", [])[:5]
        compact["timeline_events"] = project_memory.get("timeline_events", [])[-5:]
        compact["setting_pages"] = project_memory.get("setting_pages", [])[:3]

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
