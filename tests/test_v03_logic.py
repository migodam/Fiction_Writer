import pytest
import os
import json
from src.ai.context_builder import build_context_packet
from src.core.persistence import ProjectMemory

class DummyStore:
    def read_governance_md(self): return "gov"
    def read_outline_md(self): return "outline"
    def read_tasks_json(self, path): return {"open": [], "done": []}

def test_context_builder_budget_truncation():
    routing = {"intent_type": "edit"}
    project_memory = {
        "canon_facts": [{"content": "x" * 15000}], # Force overflow
        "characters": [],
        "timeline_events": [],
        "setting_pages": []
    }
    
    packet = build_context_packet(routing, project_memory, {}, {}, DummyStore())
    
    assert packet["limits"]["truncated"] == True
    assert packet["limits"]["used_chars"] <= 12000
    assert "truncated" in packet["limits"]["overflow_summary"]

def test_apply_project_updates_counts():
    mem = ProjectMemory(file_path="data/test_v03_updates.json")
    diff = {
        "characters": {"upsert": [{"name": "Smoke Char"}], "delete": []},
        "timeline_events": {"upsert": [{"title": "Smoke Event"}], "delete": []}
    }
    counts = mem.apply_project_updates(diff)
    assert counts["characters_created"] == 1
    assert counts["timeline_upserted"] == 1
    
    # Cleanup
    if os.path.exists("data/test_v03_updates.json"):
        os.remove("data/test_v03_updates.json")
