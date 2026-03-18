from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .project_repository import list_prompt_templates, migrate_project


def load_prompt_registry(root_path: str | Path) -> List[Dict]:
    migrate_project(root_path)
    return list_prompt_templates(root_path)


def get_prompt_template(root_path: str | Path, template_id: str) -> Optional[Dict]:
    templates = load_prompt_registry(root_path)
    return next((template for template in templates if template.get("id") == template_id), None)
