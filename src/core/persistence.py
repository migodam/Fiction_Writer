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
            "chat_history": [],
            "chapters": [],
            "timeline_events": [],
            "setting_pages": [],
            "characters": [],
            "relationships": [],
            "map_settings": {"image_path": ""}
        }
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    for key in self.data.keys():
                        if key in loaded_data:
                            self.data[key] = loaded_data[key]
            except Exception as e:
                print(f"Error loading JSON: {e}")

    def save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        # Use a temporary file for safe writing
        temp_path = self.file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        os.replace(temp_path, self.file_path)

    # --- Unified Update API ---
    def apply_project_updates(self, updates: Dict[str, Any]) -> Dict[str, int]:
        """
        Applies a 'project_updates' JSON from the Core Agent.
        Returns counts of changes.
        """
        stats = {"upserted": 0, "deleted": 0}
        
        mapping = {
            "characters": "characters",
            "relationships": "relationships",
            "timeline_events": "timeline_events",
            "setting_pages": "setting_pages",
            "canon_facts": "canon_facts"
        }

        for agent_key, data_key in mapping.items():
            if agent_key not in updates:
                continue
            
            section = updates[agent_key]
            
            # 1. Handle Deletes
            if "delete" in section:
                original_count = len(self.data[data_key])
                self.data[data_key] = [item for item in self.data[data_key] if item.get("id") not in section["delete"]]
                stats["deleted"] += (original_count - len(self.data[data_key]))

            # 2. Handle Upserts
            if "upsert" in section:
                for item in section["upsert"]:
                    # Check if ID exists
                    existing_idx = -1
                    for i, existing in enumerate(self.data[data_key]):
                        if existing.get("id") == item.get("id"):
                            existing_idx = i
                            break
                    
                    if existing_idx >= 0:
                        # Update existing
                        self.data[data_key][existing_idx].update(item)
                        self.data[data_key][existing_idx]["updated_at"] = datetime.now().isoformat()
                    else:
                        # Create new
                        if "id" not in item:
                            item["id"] = str(uuid.uuid4())
                        item["created_at"] = datetime.now().isoformat()
                        self.data[data_key].append(item)
                    stats["upserted"] += 1
        
        self.save()
        return stats

    # --- Existing Helper Methods (Extended) ---
    def add_assistant_chat_msg(self, role: str, content: str, provenance: str = "user"):
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), "provenance": provenance}
        self.data["chat_history"].append(msg)
        self.save()
        return msg

    def create_setting_page(self, title: str, category: str, content: str = ""):
        page = {
            "id": str(uuid.uuid4()), "title": title, "category": category, "content_markdown": content,
            "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
        }
        self.data["setting_pages"].append(page)
        self.save()
        return page

    def add_timeline_event(self, title: str, time: str, participants: str, summary: str):
        event = {
            "id": str(uuid.uuid4()), "title": title, "time": time, 
            "participants": [p.strip() for p in participants.split(",") if p.strip()],
            "summary": summary, "created_at": datetime.now().isoformat()
        }
        self.data["timeline_events"].append(event)
        self.save()
        return event

    def add_character(self, name: str, description: str, traits: str, goals: str, secrets: str):
        char = {
            "id": str(uuid.uuid4()), "name": name, "description": description, 
            "traits": traits, "goals": goals, "secrets": secrets, "created_at": datetime.now().isoformat()
        }
        self.data["characters"].append(char)
        self.save()
        return char
    
    def add_fact(self, content: str, category: str, provenance: str = "user"):
        fact = {"id": str(uuid.uuid4()), "content": content, "category": category, "provenance": provenance, "timestamp": datetime.now().isoformat()}
        self.data["canon_facts"].append(fact)
        self.save()
        return fact
