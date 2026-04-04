"""S1 — ProjectContext Builder

Builds a precisely scoped context object for any workflow.
Never loads more than the task needs — always titles-first.

Actual project paths (overriding langgraph.md idealised paths):
  characters:     entities/characters/{id}.json
  timeline events: entities/timeline/{id}.json
  chapters:       writing/chapters/{id}.json
  scenes:         writing/scenes/{id}.meta.json
  world (SQLite): project.db  →  SELECT id,title,category,summary FROM world_entries
  todos:          project.json → .todos[]
  proposals:      system/inbox.json
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

import aiosqlite
import aiofiles


# ── Context profiles ──────────────────────────────────────────────────────────

CONTEXT_PROFILES: dict[str, list[str]] = {
    "writing": [
        "pov_character_full",
        "scene_summaries_same_chapter",
        "related_timeline_events",
        "active_todos_top5",
    ],
    "consistency": [
        "all_character_summaries",
        "timeline_skeleton",
        "world_entry_titles",
    ],
    "simulation": [
        "full_character_motivations",
        "full_timeline",
        "world_rules",
    ],
    "import": [],
    "beta_reader": [
        "chapter_content",
        "persona_profile",
    ],
}


# ── ProjectContext structure ───────────────────────────────────────────────────

class ProjectContext(dict):
    """A plain dict subclass — keeps typing flexible while remaining JSON-serialisable."""


# ── Public API ────────────────────────────────────────────────────────────────

async def build_context(
    project_path: str,
    profile: str,
    anchor_ids: dict[str, str],
) -> ProjectContext:
    """Build a context object scoped to the given profile.

    anchor_ids examples:
      {"character_id": "char_001"}
      {"chapter_id": "ch_003", "scene_id": "scene_007"}
    """
    root = pathlib.Path(project_path)
    keys = CONTEXT_PROFILES.get(profile, [])
    ctx: ProjectContext = ProjectContext()

    # Always include entity registry summary (lightweight)
    ctx["entity_registry"] = await _load_entity_registry(root)

    for key in keys:
        if key == "all_character_summaries":
            ctx["characters"] = await _load_character_summaries(root)

        elif key == "pov_character_full":
            char_id = anchor_ids.get("character_id") or anchor_ids.get("pov_character_id")
            if char_id:
                ctx["anchored_character"] = await _load_character_full(root, char_id)
            ctx.setdefault("characters", await _load_character_summaries(root))

        elif key == "full_character_motivations":
            summaries = await _load_character_summaries(root)
            ctx["characters"] = summaries

        elif key == "scene_summaries_same_chapter":
            chapter_id = anchor_ids.get("chapter_id")
            ctx["scenes"] = await _load_scene_summaries(root, chapter_id)

        elif key == "chapter_content":
            chapter_id = anchor_ids.get("chapter_id")
            if chapter_id:
                ctx["anchored_chapter"] = await _load_chapter_full(root, chapter_id)

        elif key == "related_timeline_events":
            ctx["timeline_events"] = await _load_timeline_summaries(root)

        elif key == "timeline_skeleton":
            ctx["timeline_events"] = await _load_timeline_summaries(root)

        elif key == "full_timeline":
            ctx["timeline_events"] = await _load_timeline_summaries(root)

        elif key == "world_entry_titles":
            ctx["world_entries"] = await _load_world_titles(root)

        elif key == "world_rules":
            ctx["world_entries"] = await _load_world_titles(root)

        elif key == "active_todos_top5":
            ctx["active_todos"] = await _load_active_todos(root, limit=5)

        elif key == "persona_profile":
            persona_id = anchor_ids.get("persona_id")
            if persona_id:
                ctx["persona"] = await _load_persona(root, persona_id)

    # Always load active todos unless already loaded
    ctx.setdefault("active_todos", await _load_active_todos(root, limit=20))

    return ctx


# ── Loaders ───────────────────────────────────────────────────────────────────

async def _read_json(path: pathlib.Path) -> Any:
    if not path.exists():
        return None
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return json.loads(await f.read())


async def _load_entity_registry(root: pathlib.Path) -> dict:
    project = await _read_json(root / "project.json") or {}
    return project.get("entityRegistry", {})


async def _load_character_summaries(root: pathlib.Path) -> list[dict]:
    chars_dir = root / "entities" / "characters"
    if not chars_dir.exists():
        return []
    summaries = []
    for f in sorted(chars_dir.glob("*.json")):
        data = await _read_json(f) or {}
        summaries.append({
            "id": data.get("id"),
            "name": data.get("name"),
            "summary": data.get("summary"),
            "aliases": data.get("aliases", []),
            "statusFlags": data.get("statusFlags", {}),
        })
    return summaries


async def _load_character_full(root: pathlib.Path, character_id: str) -> dict | None:
    path = root / "entities" / "characters" / f"{character_id}.json"
    return await _read_json(path)


async def _load_scene_summaries(
    root: pathlib.Path, chapter_id: str | None
) -> list[dict]:
    scenes_dir = root / "writing" / "scenes"
    if not scenes_dir.exists():
        return []
    summaries = []
    for f in sorted(scenes_dir.glob("*.meta.json")):
        data = await _read_json(f) or {}
        if chapter_id and data.get("chapterId") != chapter_id:
            continue
        summaries.append({
            "id": data.get("id"),
            "title": data.get("title"),
            "summary": data.get("summary"),
            "chapterId": data.get("chapterId"),
            "orderIndex": data.get("orderIndex"),
            "status": data.get("status"),
        })
    return summaries


async def _load_chapter_full(root: pathlib.Path, chapter_id: str) -> dict | None:
    path = root / "writing" / "chapters" / f"{chapter_id}.json"
    return await _read_json(path)


async def _load_timeline_summaries(root: pathlib.Path) -> list[dict]:
    events_dir = root / "entities" / "timeline"
    if not events_dir.exists():
        return []
    summaries = []
    for f in sorted(events_dir.glob("*.json")):
        if f.name == "branches.json":
            continue
        data = await _read_json(f) or {}
        summaries.append({
            "id": data.get("id"),
            "title": data.get("title"),
            "time": data.get("time"),
            "branchId": data.get("branchId"),
            "orderIndex": data.get("orderIndex"),
        })
    return summaries


async def _load_world_titles(root: pathlib.Path) -> list[dict]:
    """Titles-first from SQLite: SELECT id, title, category, summary."""
    db_path = root / "project.db"
    if not db_path.exists():
        return []
    try:
        async with aiosqlite.connect(str(db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, title, category, summary FROM world_entries"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception:
        return []


async def _load_active_todos(root: pathlib.Path, limit: int = 20) -> list[dict]:
    project = await _read_json(root / "project.json") or {}
    todos = project.get("todos", [])
    active = [t for t in todos if t.get("status") not in ("done", "archived")]
    return active[:limit]


async def _load_persona(root: pathlib.Path, persona_id: str) -> dict | None:
    personas_path = root / "system" / "beta-personas.json"
    personas = await _read_json(personas_path) or []
    return next((p for p in personas if p.get("id") == persona_id), None)
