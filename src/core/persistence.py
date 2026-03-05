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
            "outline": [],
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
        changed = False
        if "outline" not in self.data:
            self.data["outline"] = []
            changed = True

        for char in self.data.get("characters", []):
            if "tags" not in char: char["tags"] = []; changed = True
            if "aliases" not in char: char["aliases"] = []; changed = True
            if "background" not in char: char["background"] = ""; changed = True
            if "description" not in char: char["description"] = ""; changed = True

        if not isinstance(self.data.get("setting_pages"), list):
            self.data["setting_pages"] = []; changed = True

        for i, page in enumerate(self.data["setting_pages"]):
            if "id" not in page: page["id"] = str(uuid.uuid4()); changed = True
            if "title" not in page:
                page["title"] = page.get("name", "Untitled")
                changed = True
            if "items" not in page: page["items"] = []; changed = True
            for item in page["items"]:
                if "id" not in item: item["id"] = str(uuid.uuid4()); changed = True

        if changed: self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        temp_path = self.file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        os.replace(temp_path, self.file_path)

    def create_backup(self):
        if os.path.exists(self.file_path):
            shutil.copy2(self.file_path, self.backup_path)

    def apply_project_updates(self, updates: Dict[str, Any]) -> Dict[str, int]:
        self.create_backup()
        res = {
            "timeline_upserted": 0, "timeline_deleted": 0,
            "characters_created": 0, "characters_updated": 0, "characters_deleted": 0,
            "setting_items_created": 0, "setting_items_updated": 0, "outline_nodes_updated": 0
        }
        root = updates.get("project_updates", updates)

        # 1. Characters
        char_sec = root.get("characters", {})
        # Deletions
        for d_id in char_sec.get("delete", []):
            self.data["characters"] = [c for c in self.data["characters"] if c["id"] != d_id and c["name"] != d_id]
            res["characters_deleted"] += 1
        # Upserts
        for char_data in char_sec.get("upsert", []):
            tid = char_data.get("id") or char_data.get("id_or_name")
            tname = char_data.get("name") or char_data.get("id_or_name")
            existing = next((c for c in self.data["characters"] if c["id"] == tid or c["name"] == tname), None)
            
            if existing:
                fields = char_data.get("fields", {}) or {k:v for k,v in char_data.items() if k not in ["id","id_or_name","name"]}
                updated = False
                for k, v in fields.items():
                    if k in ["tags", "aliases"] and isinstance(v, list):
                        if k not in existing: existing[k] = []
                        for item in v:
                            if item not in existing[k]: existing[k].append(item); updated = True
                    elif v and v != "..." and existing.get(k) != v:
                        existing[k] = v
                        # Sync background/description
                        if k == "background": existing["description"] = v
                        if k == "description": existing["background"] = v
                        updated = True
                if updated:
                    existing["ui_metadata"] = {"is_new_update": True}
                    res["characters_updated"] += 1
            else:
                new_char = {"id": str(uuid.uuid4()), "name": tname or "Unknown", "status": "candidate", "created_at": datetime.now().isoformat(), "tags": [], "aliases": [], "ui_metadata": {"is_new_update": True}}
                fields = char_data.get("fields", {}) or {k:v for k,v in char_data.items() if k not in ["id","id_or_name","name"]}
                new_char.update(fields)
                # Sync
                if "background" in fields: new_char["description"] = fields["background"]
                elif "description" in fields: new_char["background"] = fields["description"]
                self.data["characters"].append(new_char)
                res["characters_created"] += 1

        # 2. Timeline
        tl_sec = root.get("timeline_events", {})
        for d_id in tl_sec.get("delete", []):
            self.data["timeline_events"] = [e for e in self.data["timeline_events"] if e["id"] != d_id and e["title"] != d_id]
            res["timeline_deleted"] += 1
        for ev in tl_sec.get("upsert", []):
            if "id" not in ev: ev["id"] = str(uuid.uuid4())
            existing = next((e for e in self.data["timeline_events"] if e["id"] == ev["id"] or e["title"] == ev.get("title")), None)
            if existing:
                actually_changed = any(existing.get(k) != v for k, v in ev.items() if k != "id")
                if actually_changed:
                    existing.update(ev)
                    existing["ui_metadata"] = {"is_new_update": True}
                    res["timeline_upserted"] += 1
            else:
                ev["ui_metadata"] = {"is_new_update": True}
                self.data["timeline_events"].append(ev)
                res["timeline_upserted"] += 1

        # 3. Outline
        out_sec = root.get("outline", {})
        for out_node in out_sec.get("upsert", []):
            if "id" not in out_node: out_node["id"] = str(uuid.uuid4())
            existing = next((o for o in self.data["outline"] if o["id"] == out_node["id"] or o.get("title") == out_node.get("title")), None)
            if existing:
                existing.update(out_node)
                existing["ui_metadata"] = {"is_new_update": True}
                res["outline_nodes_updated"] += 1
            else:
                out_node["ui_metadata"] = {"is_new_update": True}
                self.data["outline"].append(out_node)
                res["outline_nodes_updated"] += 1

        # 4. Settings
        sp_sec = root.get("setting_pages", {})
        for i_upd in sp_sec.get("upsert_items", []):
            pid = i_upd.get("page_id")
            page = next((p for p in self.data["setting_pages"] if p["id"] == pid or p["title"] == pid), None)
            if page:
                if "id" not in i_upd: i_upd["id"] = str(uuid.uuid4())
                existing_it = next((it for it in page["items"] if it["id"] == i_upd["id"] or it["name"] == i_upd.get("name")), None)
                if existing_it:
                    actually_changed = any(existing_it.get(k) != v for k,v in i_upd.items() if k != "id")
                    if actually_changed:
                        existing_it.update(i_upd)
                        existing_it["ui_metadata"] = {"is_new_update": True}
                        res["setting_items_updated"] += 1
                else:
                    i_upd["ui_metadata"] = {"is_new_update": True}
                    page["items"].append(i_upd)
                    res["setting_items_created"] += 1

        self.save()
        return res

    def clear_update_flag(self, entity_type: str, entity_id: str, parent_id: str = None):
        target = None
        if entity_type == "character":
            target = next((c for c in self.data["characters"] if c["id"] == entity_id), None)
        elif entity_type == "outline":
            target = next((o for o in self.data.get("outline", []) if o["id"] == entity_id), None)
        elif entity_type == "timeline_event":
            target = next((e for e in self.data["timeline_events"] if e["id"] == entity_id), None)
        elif entity_type == "setting_item" and parent_id:
            page = next((p for p in self.data["setting_pages"] if p["id"] == parent_id), None)
            if page: target = next((it for it in page["items"] if it["id"] == entity_id), None)

        if target and "ui_metadata" in target:
            target["ui_metadata"]["is_new_update"] = False
            self.save()
            return True
        return False

    def add_timeline_event(self, title, time, participants, summary):
        if isinstance(participants, str):
            participants = [p.strip() for p in participants.split(",") if p.strip()]
        ev = {"id": str(uuid.uuid4()), "title": title, "time": time, "participants": participants, "summary": summary, "created_at": datetime.now().isoformat()}
        self.data["timeline_events"].append(ev)
        self.save()
        return ev

    def delete_timeline_event(self, ev_id):
        self.data["timeline_events"] = [e for e in self.data["timeline_events"] if e["id"] != ev_id]
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

    def add_character(self, name, description, traits, goals, secrets):
        char = {"id": str(uuid.uuid4()), "name": name, "description": description, "background": description, "traits": traits, "goals": goals, "secrets": secrets, "status": "candidate", "created_at": datetime.now().isoformat(), "tags": [], "aliases": []}
        self.data["characters"].append(char)
        self.save()
        return char
