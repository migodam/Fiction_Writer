import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

class ProjectMemory:
    def __init__(self, file_path: str = "data/narrative_lab_memory.json"):
        self.file_path = file_path
        self.data = {
            "project_info": {"name": "Untitled Project", "style": "Modern"},
            "canon_facts": [],
            "clarifier_history": [],
            "chapters": [],
            "timeline_events": [],
            "setting_pages": []
        }
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    # Merge loaded data with defaults to ensure all keys exist
                    for key in self.data.keys():
                        if key in loaded_data:
                            self.data[key] = loaded_data[key]
            except Exception as e:
                print(f"Error loading JSON: {e}")

    def save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    # --- Canon Facts ---
    def add_fact(self, content: str, category: str, provenance: str = "user"):
        fact = {
            "id": str(uuid.uuid4()),
            "content": content,
            "category": category,
            "provenance": provenance,
            "version": 1,
            "timestamp": datetime.now().isoformat()
        }
        self.data["canon_facts"].append(fact)
        self.save()
        return fact

    # --- Timeline CRUD ---
    def add_timeline_event(self, title: str, time: str, participants: str, summary: str):
        event = {
            "id": str(uuid.uuid4()),
            "title": title,
            "time": time,
            "participants": [p.strip() for p in participants.split(",") if p.strip()],
            "summary": summary,
            "linked_fact_ids": [],
            "created_at": datetime.now().isoformat()
        }
        self.data["timeline_events"].append(event)
        self.save()
        return event

    def update_timeline_event(self, event_id: str, updates: Dict[str, Any]):
        for i, event in enumerate(self.data["timeline_events"]):
            if event["id"] == event_id:
                self.data["timeline_events"][i].update(updates)
                self.save()
                return self.data["timeline_events"][i]
        return None

    def delete_timeline_event(self, event_id: str):
        self.data["timeline_events"] = [e for e in self.data["timeline_events"] if e["id"] != event_id]
        self.save()

    # --- Setting Pages CRUD ---
    def create_setting_page(self, title: str, category: str, content: str = ""):
        page = {
            "id": str(uuid.uuid4()),
            "title": title,
            "category": category,
            "content_markdown": content,
            "linked_fact_ids": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": 1
        }
        self.data["setting_pages"].append(page)
        self.save()
        return page

    def update_setting_page(self, page_id: str, updates: Dict[str, Any]):
        for i, page in enumerate(self.data["setting_pages"]):
            if page["id"] == page_id:
                updates["updated_at"] = datetime.now().isoformat()
                self.data["setting_pages"][i].update(updates)
                self.save()
                return self.data["setting_pages"][i]
        return None

    def delete_setting_page(self, page_id: str):
        self.data["setting_pages"] = [p for p in self.data["setting_pages"] if p["id"] != page_id]
        self.save()

    # --- Chat History ---
    def add_chat_msg(self, role: str, content: str, provenance: str = "user"):
        self.data["clarifier_history"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "provenance": provenance
        })
        self.save()
