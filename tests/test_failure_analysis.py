import pytest
from src.ai.orchestrator import explain_failure

def test_explain_failure_invalid_participants():
    memory_data = {
        "characters": [{"id": "uuid-1", "name": "Lorian"}]
    }
    routing = {"needs_project_update": True, "needs_sections": ["timeline"]}
    plan_json = {
        "modification_plan": {
            "steps": [
                {
                    "entity_type": "timeline_event",
                    "field_updates": {"participants": ["1", "Unknown"]}
                }
            ]
        }
    }
    
    explanation, reasons = explain_failure(
        user_text="Add event",
        routing=routing,
        plan_json=plan_json,
        pm_json=None,
        memory_data=memory_data,
        metrics={},
        client=None # Should not be called for rule-based
    )
    
    assert "Invalid participant references" in reasons
    assert "Participants ['1', 'Unknown'] not found" in explanation

def test_explain_failure_missing_fields():
    memory_data = {"characters": []}
    routing = {"needs_project_update": True, "needs_sections": ["timeline"]}
    plan_json = {
        "modification_plan": {
            "steps": [
                {
                    "entity_type": "timeline_event",
                    "field_updates": {"title": ""} # Missing 'time'
                }
            ]
        }
    }
    
    explanation, reasons = explain_failure(
        user_text="Add event",
        routing=routing,
        plan_json=plan_json,
        pm_json=None,
        memory_data=memory_data,
        metrics={},
        client=None
    )
    
    assert "Missing required fields" in reasons
    assert "time" in explanation
