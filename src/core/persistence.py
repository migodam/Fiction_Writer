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
                self.normalize_data()
            except Exception as e:
                print(f"Error loading JSON: {e}")

    def normalize_data(self):
        """
        Ensures all data adheres to the expected schema. 
        Fixes missing titles, missing IDs, etc.
        """
        changed = False
        notes = []

        # Normalize setting_pages
        if not isinstance(self.data.get("setting_pages"), list):
            self.data["setting_pages"] = []
            changed = True

        for i, page in enumerate(self.data["setting_pages"]):
            # Fix ID
            if "id" not in page:
                page["id"] = str(uuid.uuid4())
                changed = True
            
            # Fix Title (Back-compat for 'name')
            if "title" not in page:
                if "name" in page:
                    page["title"] = page["name"]
                    notes.append(f"Migrated page[{i}].name -> title")
                else:
                    page["title"] = "Untitled"
                    notes.append(f"Filled missing title for page[{i}]")
                changed = True
            
            # Fix Items
            if "items" not in page or not isinstance(page["items"], list):
                page["items"] = []
                changed = True
            
            for item in page["items"]:
                if "id" not in item:
                    item["id"] = str(uuid.uuid4())
                    changed = True
                if "fields" not in item or not isinstance(item["fields"], dict):
                    item["fields"] = {}
                    changed = True

            # Fix Timestamps
            if "created_at" not in page:
                page["created_at"] = datetime.now().isoformat()
                changed = True
            if changed and "updated_at" not in page:
                page["updated_at"] = datetime.now().isoformat()

        if changed:
            self.save()
            print(f"Normalization complete: {notes}")

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

    # --- CRUD Methods ---
    def apply_project_updates(self, updates: Dict[str, Any]) -> Dict[str, int]:
        self.create_backup()
        res = {
            "timeline_upserted": 0,
            "characters_created": 0,
            "relationships_created": 0,
            "setting_items_created": 0
        }

        # Characters
        char_upserts = updates.get("characters", {}).get("upsert", [])
        for char in char_upserts:
            if "id" not in char: char["id"] = str(uuid.uuid4())
            char["status"] = char.get("status", "candidate")
            existing = next((c for c in self.data["characters"] if c["id"] == char["id"]), None)
            if existing: existing.update(char)
            else:
                self.data["characters"].append(char)
                res["characters_created"] += 1

        # Timeline
        tl_upserts = updates.get("timeline_events", {}).get("upsert", [])
        for ev in tl_upserts:
            if "id" not in ev: ev["id"] = str(uuid.uuid4())
            existing = next((e for e in self.data["timeline_events"] if e["id"] == ev["id"]), None)
            if existing: existing.update(ev)
            else:
                self.data["timeline_events"].append(ev)
                res["timeline_upserted"] += 1

        # Relationships
        rel_upserts = updates.get("relationships", {}).get("upsert", [])
        for rel in rel_upserts:
            if "id" not in rel: rel["id"] = str(uuid.uuid4())
            existing = next((r for r in self.data["relationships"] if r["id"] == rel["id"]), None)
            if existing: existing.update(rel)
            else:
                self.data["relationships"].append(rel)
                res["relationships_created"] += 1

        # Setting Pages & Items
        sp_updates = updates.get("setting_pages", {})
        for p_upd in sp_updates.get("upsert_pages", []):
            if "id" not in p_upd: p_upd["id"] = str(uuid.uuid4())
            existing_p = next((p for p in self.data["setting_pages"] if p["id"] == p_upd["id"]), None)
            if existing_p: existing_p.update(p_upd)
            else:
                p_upd["items"] = p_upd.get("items", [])
                self.data["setting_pages"].append(p_upd)

        for i_upd in sp_updates.get("upsert_items", []):
            if "id" not in i_upd: i_upd["id"] = str(uuid.uuid4())
            pid = i_upd.get("page_id")
            page = next((p for p in self.data["setting_pages"] if p["id"] == pid), None)
            if page:
                existing_item = next((it for it in page["items"] if it["id"] == i_upd["id"]), None)
                if existing_item: existing_item.update(i_upd)
                else:
                    page["items"].append(i_upd)
                    res["setting_items_created"] += 1

        self.save()
        return res

    def create_setting_page(self, title: str):
        page = {"id": str(uuid.uuid4()), "title": title, "items": [], "created_at": datetime.now().isoformat()}
        self.data["setting_pages"].append(page)
        self.save()
        return page

    def delete_setting_page(self, page_id: str):
        self.data["setting_pages"] = [p for p in self.data["setting_pages"] if p["id"] != page_id]
        self.save()

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
            "traits": traits, "goals": goals, "secrets": secrets, "status": "candidate",
            "created_at": datetime.now().isoformat()
        }
        self.data["characters"].append(char)
        self.save()
        return char
