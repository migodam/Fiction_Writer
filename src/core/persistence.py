import json
import os
import uuid
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional

class ProjectMemory:
    def __init__(self, file_path: str = "data/narrative_lab_memory.json"):
        self.file_path = file_path
        self.backup_path = file_path + ".backup"
        self.data = {
            "project_info": {"name": "Untitled Project", "style": "Modern"},
            "canon_facts": [],
            "chat_history": [],
            "chapters": [],
            "timeline_events": [],
            "setting_pages": [],
            "characters": [],
            "relationships": []
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
        temp_path = self.file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        os.replace(temp_path, self.file_path)

    def create_backup(self):
        if os.path.exists(self.file_path):
            shutil.copy2(self.file_path, self.backup_path)

    def undo_last_apply(self) -> bool:
        if os.path.exists(self.backup_path):
            shutil.copy2(self.backup_path, self.file_path)
            self.load()
            return True
        return False

    # --- Unified Update API v2 ---
    def apply_project_updates(self, updates: Dict[str, Any]) -> str:
        self.create_backup()
        stats = {
            "timeline": {"add": 0, "upd": 0},
            "characters": {"new": 0},
            "pages": {"add": 0},
            "items": {"add": 0}
        }

        # 1. Timeline
        tl_upserts = updates.get("timeline_events", {}).get("upsert", [])
        for ev in tl_upserts:
            existing = next((e for e in self.data["timeline_events"] if e["id"] == ev.get("id")), None)
            if existing:
                existing.update(ev)
                stats["timeline"]["upd"] += 1
            else:
                if "id" not in ev: ev["id"] = str(uuid.uuid4())
                self.data["timeline_events"].append(ev)
                stats["timeline"]["add"] += 1

        # 2. Characters (Always Candidates)
        char_upserts = updates.get("characters", {}).get("upsert", [])
        for char in char_upserts:
            existing = next((c for c in self.data["characters"] if c["id"] == char.get("id")), None)
            if not existing:
                char["status"] = "candidate"
                if "id" not in char: char["id"] = str(uuid.uuid4())
                self.data["characters"].append(char)
                stats["characters"]["new"] += 1
            else:
                existing.update(char)

        # 3. Setting Pages (OneNote Style)
        sp_updates = updates.get("setting_pages", {})
        # Handle Upsert Pages
        for p_upd in sp_updates.get("upsert_pages", []):
            existing_p = next((p for p in self.data["setting_pages"] if p["id"] == p_upd.get("id")), None)
            if existing_p:
                existing_p.update(p_upd)
            else:
                if "id" not in p_upd: p_upd["id"] = str(uuid.uuid4())
                if "items" not in p_upd: p_upd["items"] = []
                self.data["setting_pages"].append(p_upd)
                stats["pages"]["add"] += 1
        
        # Handle Upsert Items into Pages
        for i_upd in sp_updates.get("upsert_items", []):
            target_page_id = i_upd.get("page_id")
            page = next((p for p in self.data["setting_pages"] if p["id"] == target_page_id), None)
            if page:
                existing_item = next((it for i, it in enumerate(page["items"]) if it["id"] == i_upd.get("id")), None)
                if existing_item:
                    existing_item.update(i_upd)
                else:
                    if "id" not in i_upd: i_upd["id"] = str(uuid.uuid4())
                    page["items"].append(i_upd)
                    stats["items"]["add"] += 1

        self.save()
        
        return (f"Applied updates:\n"
                f"- timeline_events: +{stats['timeline']['add']} / ~{stats['timeline']['upd']}\n"
                f"- characters (candidates): +{stats['characters']['new']}\n"
                f"- settings pages: +{stats['pages']['add']}\n"
                f"- settings items: +{stats['items']['add']}")

    def confirm_character(self, char_id: str):
        for char in self.data["characters"]:
            if char["id"] == char_id:
                char["status"] = "active"
                self.save()
                return True
        return False

    def delete_character(self, char_id: str):
        self.data["characters"] = [c for c in self.data["characters"] if c["id"] != char_id]
        self.save()

    def add_character(self, name: str, description: str, traits: str, goals: str, secrets: str):
        char = {
            "id": str(uuid.uuid4()), "name": name, "description": description, 
            "traits": traits, "goals": goals, "secrets": secrets, "created_at": datetime.now().isoformat(),
            "status": "candidate"
        }
        self.data["characters"].append(char)
        self.save()
        return char

    def create_setting_page(self, title: str, category: str, content: str = ""):
        page = {
            "id": str(uuid.uuid4()), "title": title, "category": category, "items": [],
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

    def delete_timeline_event(self, event_id: str):
        self.data["timeline_events"] = [e for e in self.data["timeline_events"] if e["id"] != event_id]
        self.save()

    def add_fact(self, content: str, category: str, provenance: str = "user"):
        fact = {"id": str(uuid.uuid4()), "content": content, "category": category, "provenance": provenance, "timestamp": datetime.now().isoformat()}
        self.data["canon_facts"].append(fact)
        self.save()
        return fact

    def add_assistant_chat_msg(self, role: str, content: str, provenance: str = "user"):
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), "provenance": provenance}
        self.data["chat_history"].append(msg)
        self.save()
        return msg
