import os
import json
import shutil
from typing import Dict, Any

class MemoryStore:
    def __init__(self, root_dir: str = "memory"):
        self.root_dir = root_dir
        self.global_dir = os.path.join(self.root_dir, "global")
        self.agents_dir = os.path.join(self.root_dir, "agents")

    def _read_file(self, path: str, default: str = "") -> str:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return default

    def _write_file(self, path: str, content: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def read_governance_md(self) -> str:
        return self._read_file(os.path.join(self.global_dir, "governance.md"))

    def read_outline_md(self) -> str:
        return self._read_file(os.path.join(self.global_dir, "outline.md"))

    def read_tasks_json(self, path: str) -> Dict[str, Any]:
        content = self._read_file(path, '{"open": [], "done": []}')
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"open": [], "done": []}

    def write_tasks_json(self, path: str, data: Dict[str, Any]):
        self._write_file(path, json.dumps(data, indent=2, ensure_ascii=False))

    def read_agent_md(self, agent_name: str) -> str:
        return self._read_file(os.path.join(self.agents_dir, f"{agent_name}.md"))

    def apply_global_change_with_backup(self, rel_path: str, content: str):
        full_path = os.path.join(self.root_dir, rel_path)
        if os.path.exists(full_path):
            shutil.copy2(full_path, full_path + ".bak")
        self._write_file(full_path, content)

    def apply_agent_memory_change(self, rel_path: str, content: str):
        full_path = os.path.join(self.root_dir, rel_path)
        self._write_file(full_path, content)
