from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ENTITY_PATHS = {
    "character": Path("data") / "characters",
    "chapter": Path("writing") / "chapters",
    "scene": Path("writing") / "scenes",
    "timeline_event": Path("data") / "timeline_events",
}


def project_reader(project_path: str, entity_type: str, entity_id: str | None = None) -> Any:
    if entity_type not in ENTITY_PATHS:
        raise ValueError(f"Unsupported entity type: {entity_type}")

    project_root = Path(project_path)
    base_path = project_root / ENTITY_PATHS[entity_type]

    if entity_id is None:
        if not base_path.exists():
            return []
        return sorted(item.name for item in base_path.iterdir())

    file_path = base_path / f"{entity_id}.json"
    with file_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def manuscript_reader(project_path: str, chapter_id: str | None = None) -> Any:
    chapters_dir = Path(project_path) / "writing" / "chapters"

    if chapter_id is not None:
        chapter_path = chapters_dir / f"{chapter_id}.md"
        return chapter_path.read_text(encoding="utf-8")

    chapters = []
    if not chapters_dir.exists():
        return chapters

    for chapter_path in sorted(path for path in chapters_dir.iterdir() if path.is_file()):
        chapters.append(
            {
                "chapter_id": chapter_path.stem,
                "content": chapter_path.read_text(encoding="utf-8"),
            }
        )
    return chapters


def chunk_reader(project_path: str, file_id: str, chunk_id: int | str | None = None) -> Any:
    chunk_path = Path(project_path) / "metadata" / file_id / "chunks.json"
    with chunk_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    chunks = data.get("chunks", data) if isinstance(data, dict) else data

    if chunk_id is None:
        return "\n\n".join(chunk.get("content", "") for chunk in chunks)

    for chunk in chunks:
        if str(chunk.get("chunk_id")) == str(chunk_id):
            return chunk

    raise KeyError(f"Chunk '{chunk_id}' not found for file '{file_id}'.")


def sqlite_query(db_path: str, query: str) -> list[dict]:
    if not query.lstrip().lower().startswith("select"):
        raise ValueError("sqlite_query only accepts SELECT statements.")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()
