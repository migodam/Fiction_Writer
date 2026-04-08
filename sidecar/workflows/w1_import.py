"""W1 — Import Workflow LangGraph.

Serial chunk pipeline that processes a novel file, extracting characters, events,
and world-building elements into a structured project with a rolling Entity Registry.

Supports resume via checkpoint (import_progress.json) and per-chunk error recovery.

Entry point:
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(initial_state, config)
"""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from sidecar.models.state import ImportState, ManuscriptChapter
from sidecar.shared import s2_memory_writer, s3_chunk_manager, s4_proposal_queue
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w1_prompts import (
    W1_EXTRACT_CHARACTERS,
    W1_EXTRACT_CHARACTERS_DEEP,
    W1_EXTRACT_EVENTS,
    W1_EXTRACT_EVENTS_DEEP,
    W1_EXTRACT_RELATIONSHIPS_CHUNK,
    W1_EXTRACT_SCENE_SUMMARIES,
    W1_EXTRACT_WORLD_DEEP,
    W1_EXTRACT_WORLD,
    W1_SYNTHESIZE_RELATIONSHIPS,
    W1_CLASSIFY_CHARACTER_TAGS,
    W1_INFER_WORLD_SETTINGS,
)
# Deep extraction prompts (import_all only) — added in Step 3
_HAS_DEEP_PROMPTS = True


# ── Alias resolver ──────────────────────────────────────────────────────────────

def _alias_resolver(name: str, registry: dict) -> str | None:
    """Fuzzy-match a name against all canonical names and aliases in the registry.

    Returns canonical_id if similarity >= 0.85, else None.
    """
    normalized = re.sub(r"[^\w]", "", name).lower()
    best_id: str | None = None
    best_score: float = 0.0

    for cid, entry in registry.get("characters", {}).items():
        # Check canonical name
        canonical_norm = re.sub(r"[^\w]", "", entry.get("canonical_name", "")).lower()
        score = difflib.SequenceMatcher(None, normalized, canonical_norm).ratio()
        if score > best_score:
            best_score = score
            best_id = cid

        # Check all aliases
        for alias in entry.get("aliases", []):
            alias_norm = re.sub(r"[^\w]", "", alias).lower()
            score = difflib.SequenceMatcher(None, normalized, alias_norm).ratio()
            if score > best_score:
                best_score = score
                best_id = cid

    if best_score >= 0.85 and best_id:
        return best_id
    return None


def _registry_summary(registry: dict, max_chars: int = 3000) -> str:
    """Build a human-readable summary of the entity registry for prompts.

    Capped at max_chars to prevent prompt bloat on large registries.
    """
    lines: list[str] = []
    for cid, entry in registry.get("characters", {}).items():
        aliases = ", ".join(entry.get("aliases", [])[:3])  # limit aliases
        lines.append(
            f"- [{cid}] {entry.get('canonical_name', 'Unknown')}"
            f" (aliases: {aliases})"
        )
    if not lines:
        return "(empty — no characters identified yet)"
    summary = "\n".join(lines)
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "\n...(truncated)"
    return summary


def _world_summary(registry: dict) -> str:
    """Build a summary of known world entries."""
    world = registry.get("world", {})
    if not world:
        return "(no world entries yet)"
    return "\n".join(f"- {name}: {cat}" for name, cat in world.items())


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, stripping code fences."""
    text = raw.strip()
    if text.startswith("```"):
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()
    return json.loads(text)


async def _invoke_json_prompt(llm: ChatOpenAI, prompt_template: str, **kwargs: Any) -> dict:
    """Render a prompt template, invoke the LLM, and parse the JSON response."""
    prompt = prompt_template.format(**kwargs)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content if isinstance(response.content, str) else str(response.content)
    return _parse_json_response(raw)


def _append_unique_strings(target: list[str], values: list[Any]) -> None:
    """Append unique non-empty string values, preserving order."""
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


def _merge_text_field(existing: str, incoming: Any) -> str:
    """Merge a short text field without duplicating identical lines."""
    if not isinstance(incoming, str):
        return existing
    cleaned = incoming.strip()
    if not cleaned:
        return existing
    existing_lines = [line.strip() for line in existing.splitlines() if line.strip()]
    if cleaned in existing_lines:
        return existing
    if not existing_lines:
        return cleaned
    return f"{existing.rstrip()}\n{cleaned}"


def _resolve_character_id(reference: Any, registry: dict) -> str | None:
    """Resolve a canonical id, canonical name, or alias into a character id."""
    if not isinstance(reference, str):
        return None
    cleaned = reference.strip()
    if not cleaned:
        return None
    if cleaned in registry.get("characters", {}):
        return cleaned

    normalized = re.sub(r"[^\w]", "", cleaned).lower()
    for cid, entry in registry.get("characters", {}).items():
        candidates = [entry.get("canonical_name", ""), *entry.get("aliases", [])]
        for candidate in candidates:
            if re.sub(r"[^\w]", "", candidate).lower() == normalized:
                return cid

    return _alias_resolver(cleaned, registry)


def _resolve_character_ids(values: list[Any], registry: dict) -> list[str]:
    """Resolve a list of ids or names to canonical character ids."""
    resolved: list[str] = []
    for value in values:
        cid = _resolve_character_id(value, registry)
        if cid and cid not in resolved:
            resolved.append(cid)
    return resolved


def _slugify(value: str) -> str:
    """Generate a filesystem-safe slug fragment."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "item"


def _stable_generated_id(prefix: str, label: str, used_ids: set[str]) -> str:
    """Generate a stable-ish unique id from a human label."""
    base = f"{prefix}_{_slugify(label)}"
    candidate = base
    counter = 2
    while candidate in used_ids:
        candidate = f"{base}_{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def _tag_color(index: int) -> str:
    """Return a deterministic fallback color for generated tags."""
    palette = [
        "#f59e0b",
        "#38bdf8",
        "#22c55e",
        "#ef4444",
        "#a855f7",
        "#14b8a6",
        "#f97316",
        "#64748b",
    ]
    return palette[index % len(palette)]


# ── LLM helper ──────────────────────────────────────────────────────────────────

def _get_llm(state: ImportState) -> ChatOpenAI:
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    base_url = ctx.get("endpoint", "https://api.deepseek.com/v1")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, max_tokens=4096)


# ── Graph nodes ─────────────────────────────────────────────────────────────────

async def node_validate_file(state: ImportState) -> dict:
    """Validate source file exists and acquire workflow lock."""
    project_path = state["project_path"]
    source_path = state["source_file_path"]
    errors: list[str] = list(state.get("errors", []))

    path = Path(source_path)
    if not path.exists():
        return {"status": "error", "errors": [f"File not found: {source_path}"]}

    if not path.is_file():
        return {"status": "error", "errors": [f"Not a file: {source_path}"]}

    # Check readable extension
    ext = path.suffix.lower()
    if ext not in (".txt", ".md", ".text", ".markdown"):
        errors.append(f"Warning: unusual file extension '{ext}', attempting to read as plain text")

    try:
        await acquire_lock(project_path, "W1")
    except WorkflowBusyError as e:
        return {"status": "error", "errors": [str(e)]}

    return {
        "workflow_id": "W1",
        "checkpoint_path": str(Path(project_path) / "import_progress.json"),
        "errors": errors,
        "progress": 0.02,
    }


async def node_load_or_init_checkpoint(state: ImportState) -> dict:
    """Load existing checkpoint if resuming, or init empty state."""
    checkpoint_path = Path(state.get("checkpoint_path", ""))

    empty_registry = {"characters": {}, "events": {}, "world": {}}

    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            return {
                "entity_registry": checkpoint.get("entity_registry", empty_registry),
                "chunk_extractions": checkpoint.get("chunk_extractions", []),
                "progress": len(checkpoint.get("completed_chunk_ids", [])) / max(checkpoint.get("total_chunks", 1), 1),
            }
        except Exception:
            pass  # Corrupt checkpoint — start fresh

    return {
        "entity_registry": empty_registry,
        "chunk_extractions": [],
        "progress": 0.05,
    }


async def node_split_chunks(state: ImportState) -> dict:
    """Read source file and split into chunks using S3."""
    source_path = state["source_file_path"]
    errors: list[str] = list(state.get("errors", []))

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        try:
            with open(source_path, "r", encoding="gbk") as f:
                text = f.read()
        except Exception as e:
            return {"status": "error", "errors": [f"Cannot read file: {e}"]}

    # Try chapter strategy first
    config = s3_chunk_manager.ChunkConfig(strategy="chapter", chunk_size=500_000, overlap=50_000)
    chunks = s3_chunk_manager.chunk_text(text, config)

    # Fallback to paragraph if no chapter headings detected and text is large
    if len(chunks) == 1 and len(text) > 500_000:
        config = s3_chunk_manager.ChunkConfig(strategy="paragraph", chunk_size=500_000, overlap=50_000)
        chunks = s3_chunk_manager.chunk_text(text, config)

    # Ensure chunk_id and manuscript_content on each chunk
    for i, chunk in enumerate(chunks):
        chunk["manuscript_content"] = chunk.get("content", "")
        chunk["chunk_id"] = i

    return {
        "chunks": chunks,
        "progress": 0.1,
    }


async def _legacy_node_process_chunks(state: ImportState) -> dict:
    """Serial loop: extract characters/events/world from each chunk, update registry, checkpoint."""
    chunks = state.get("chunks", [])
    registry = dict(state.get("entity_registry", {"characters": {}, "events": {}, "world": {}}))
    # Deep-copy nested dicts to avoid mutating frozen state
    registry = {
        "characters": {k: dict(v) for k, v in registry.get("characters", {}).items()},
        "events": {k: dict(v) for k, v in registry.get("events", {}).items()},
        "world": dict(registry.get("world", {})),
    }
    extractions: list[dict] = list(state.get("chunk_extractions", []))
    errors: list[str] = list(state.get("errors", []))
    project_path = state["project_path"]
    checkpoint_path = state.get("checkpoint_path", "")

    # Determine which chunks are already done
    completed_ids: set[int] = {e.get("chunk_id", -1) for e in extractions}
    total = len(chunks)

    llm = _get_llm(state)

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", 0)
        if chunk_id in completed_ids:
            continue

        chunk_content = chunk.get("content", "")

        try:
            # 1. Extract characters
            char_prompt = W1_EXTRACT_CHARACTERS.format(
                chunk_id=chunk_id,
                total_chunks=total,
                entity_registry_summary=_registry_summary(registry),
                chunk_content=chunk_content[:8000],
            )
            char_response = await llm.ainvoke([HumanMessage(content=char_prompt)])
            char_data = _parse_json_response(char_response.content)

            # Process existing character updates
            for update in char_data.get("existing_character_updates", []):
                cid = update.get("canonical_id")
                if cid and cid in registry.get("characters", {}):
                    entry = registry["characters"][cid]
                    for alias in update.get("new_aliases", []):
                        if alias and alias not in entry.get("aliases", []):
                            entry.setdefault("aliases", []).append(alias)
                    for note in update.get("new_notes", []):
                        if note:
                            entry.setdefault("notes", []).append(
                                f"[chunk {chunk_id}] {note}"
                            )

            # Process new characters — resolve aliases first
            new_chars: list[dict] = []
            alias_updates: list[dict] = []
            for nc in char_data.get("new_characters", []):
                name = nc.get("canonical_name", "")
                matched_id = _alias_resolver(name, registry)
                if matched_id:
                    # Existing character — append alias + notes
                    entry = registry["characters"][matched_id]
                    for alias in nc.get("aliases", []):
                        if alias and alias not in entry.get("aliases", []):
                            entry.setdefault("aliases", []).append(alias)
                    for note in nc.get("notes", []):
                        if note:
                            entry.setdefault("notes", []).append(
                                f"[chunk {chunk_id}] {note}"
                            )
                    alias_updates.append({
                        "canonical_id": matched_id,
                        "new_alias": name,
                        "note": f"Seen as '{name}' in chunk {chunk_id}",
                    })
                else:
                    # New character
                    char_id = f"char_{uuid.uuid4().hex[:8]}"
                    registry["characters"][char_id] = {
                        "canonical_id": char_id,
                        "canonical_name": name,
                        "aliases": nc.get("aliases", []),
                        "first_seen_chunk": chunk_id,
                        "notes": [f"[chunk {chunk_id}] {n}" for n in nc.get("notes", [])],
                        "confidence": nc.get("confidence", 0.7),
                    }
                    new_chars.append(registry["characters"][char_id])

            # 2. Extract events
            event_prompt = W1_EXTRACT_EVENTS.format(
                chunk_id=chunk_id,
                total_chunks=total,
                entity_registry_summary=_registry_summary(registry),
                chunk_content=chunk_content[:8000],
            )
            event_response = await llm.ainvoke([HumanMessage(content=event_prompt)])
            event_data = _parse_json_response(event_response.content)

            events: list[dict] = []
            for ev in event_data.get("events", []):
                event_id = f"event_{uuid.uuid4().hex[:8]}"
                registry["events"][event_id] = {
                    "event_id": event_id,
                    "title": ev.get("title", ""),
                    "description": ev.get("description", ""),
                    "character_ids": ev.get("character_ids", []),
                    "location_hint": ev.get("location_hint"),
                    "temporal_hint": ev.get("temporal_hint"),
                    "chunk_position": ev.get("chunk_position", ""),
                    "confidence": ev.get("confidence", 0.7),
                    "chunk_id": chunk_id,
                }
                events.append(registry["events"][event_id])

            # 3. Extract world mentions
            world_prompt = W1_EXTRACT_WORLD.format(
                chunk_id=chunk_id,
                total_chunks=total,
                known_world_entries=_world_summary(registry),
                chunk_content=chunk_content[:8000],
            )
            world_response = await llm.ainvoke([HumanMessage(content=world_prompt)])
            world_data = _parse_json_response(world_response.content)

            world_mentions: list[str] = []
            for wm in world_data.get("world_mentions", []):
                name = wm.get("name", "")
                category = wm.get("category", "concept")
                if name and name not in registry.get("world", {}):
                    registry["world"][name] = category
                world_mentions.append(name)

            # Build extraction record
            extraction: dict = {
                "chunk_id": chunk_id,
                "new_characters": new_chars,
                "updated_aliases": alias_updates,
                "events": events,
                "world_mentions": world_mentions,
                "manuscript_content": chunk.get("manuscript_content", chunk_content),
                "notes": [],
            }
            extractions.append(extraction)

        except Exception as e:
            errors.append(f"Chunk {chunk_id} failed: {str(e)}")
            # Still add a minimal extraction so we can preserve manuscript content
            extractions.append({
                "chunk_id": chunk_id,
                "new_characters": [],
                "updated_aliases": [],
                "events": [],
                "world_mentions": [],
                "manuscript_content": chunk.get("manuscript_content", chunk_content),
                "notes": [f"Extraction failed: {str(e)}"],
            })

        # Save checkpoint after EVERY chunk
        completed = len([e for e in extractions if e.get("chunk_id") is not None])
        try:
            checkpoint = {
                "project_path": project_path,
                "source_file_path": state["source_file_path"],
                "total_chunks": total,
                "completed_chunk_ids": [e["chunk_id"] for e in extractions],
                "entity_registry": registry,
                "chunk_extractions": extractions,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        except Exception as e:
            errors.append(f"Checkpoint save failed after chunk {chunk_id}: {str(e)}")

    progress = 0.1 + (0.7 * (completed / max(total, 1)))
    return {
        "entity_registry": registry,
        "chunk_extractions": extractions,
        "errors": errors,
        "progress": progress,
    }


async def node_resolve_low_confidence(state: ImportState) -> dict:
    """Flag characters with confidence < 0.6 for user review."""
    registry = dict(state.get("entity_registry", {}))
    registry["characters"] = {k: dict(v) for k, v in registry.get("characters", {}).items()}

    for cid, entry in registry.get("characters", {}).items():
        if float(entry.get("confidence", 1.0)) < 0.6:
            entry.setdefault("notes", []).append(
                "[LOW CONFIDENCE — needs review]"
            )

    return {"entity_registry": registry, "progress": 0.82}


async def node_build_manuscript(state: ImportState) -> dict:
    """Group chunks into ManuscriptChapter list.

    For import_content_only: builds directly from raw chunks (no extractions available).
    For import_all: builds from chunk_extractions (manuscript_content field).
    """
    import_mode = state.get("import_mode", "import_all")
    chunks = state.get("chunks", [])

    if import_mode == "import_content_only":
        # Fast path: group raw chunks by chapter_hint
        chapter_map: dict[str, list[dict]] = {}
        chapter_order: list[str] = []

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", 0)
            hint = chunk.get("chapter_hint") or f"Chapter {len(chapter_order) + 1}"
            if hint not in chapter_map:
                chapter_map[hint] = []
                chapter_order.append(hint)
            chapter_map[hint].append(chunk)

        manuscript_chapters: list[dict] = []
        for hint in chapter_order:
            chapter_chunks = chapter_map[hint]
            content = "\n\n".join(
                c.get("content", c.get("manuscript_content", "")) for c in chapter_chunks
            )
            manuscript_chapters.append({
                "chapter_id": f"chap_{uuid.uuid4().hex[:8]}",
                "title": hint,
                "chunk_ids": [c["chunk_id"] for c in chapter_chunks],
                "manuscript_content": content,
            })

        return {"manuscript_chapters": manuscript_chapters, "progress": 0.88}

    # import_all path: build from chunk_extractions
    extractions = state.get("chunk_extractions", [])
    chunk_map2 = {c.get("chunk_id", i): c for i, c in enumerate(chunks)}
    chapter_map2: dict[str, list[dict]] = {}
    chapter_order2: list[str] = []

    for extraction in extractions:
        chunk_id = extraction.get("chunk_id", 0)
        chunk_data = chunk_map2.get(chunk_id, {})
        hint = chunk_data.get("chapter_hint") or f"Chapter {len(chapter_order2) + 1}"
        if hint not in chapter_map2:
            chapter_map2[hint] = []
            chapter_order2.append(hint)
        chapter_map2[hint].append(extraction)

    manuscript_chapters2: list[dict] = []
    for hint in chapter_order2:
        chapter_extractions = chapter_map2[hint]
        content = "\n\n".join(
            e.get("manuscript_content", "") for e in chapter_extractions
        )
        manuscript_chapters2.append({
            "chapter_id": f"chap_{uuid.uuid4().hex[:8]}",
            "title": hint,
            "chunk_ids": [e["chunk_id"] for e in chapter_extractions],
            "manuscript_content": content,
        })

    return {"manuscript_chapters": manuscript_chapters2, "progress": 0.88}


async def node_generate_import_todos(state: ImportState) -> dict:
    """Create TodoItem proposals for unresolved entities and open questions."""
    extractions = state.get("chunk_extractions", [])
    registry = state.get("entity_registry", {})
    project_path = state["project_path"]
    proposals: list[dict] = list(state.get("proposals", []))
    errors: list[str] = list(state.get("errors", []))

    # Scan notes for open questions
    todo_texts: list[str] = []
    for extraction in extractions:
        for note in extraction.get("notes", []):
            if any(kw in note.lower() for kw in ("?", "unclear", "unresolved", "ambiguous")):
                todo_texts.append(note)

    # Flag low-confidence characters
    for cid, entry in registry.get("characters", {}).items():
        if float(entry.get("confidence", 1.0)) < 0.6:
            todo_texts.append(
                f"Character '{entry.get('canonical_name', cid)}' has low confidence — review identity"
            )

    for text in todo_texts:
        todo_id = f"todo_{uuid.uuid4().hex[:8]}"
        todo = {
            "id": todo_id,
            "title": text[:100],
            "description": text,
            "status": "pending",
            "priority": "medium",
            "source": "W1_import",
        }
        try:
            op = {
                "op_type": "create",
                "entity_type": "todo_item",
                "entity_id": todo_id,
                "data": todo,
                "source_workflow": "W1_import",
                "confidence": 0.75,
                "auto_apply": False,
                "depends_on": [],
            }
            proposal = await s2_memory_writer.propose_write(op, project_path)
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to create todo: {str(e)}")

    return {"proposals": proposals, "errors": errors, "progress": 0.92}


async def node_write_to_project(state: ImportState) -> dict:
    """Write entities to project, push proposals, write manuscript.json, trigger W2 post_import."""
    project_path = Path(state["project_path"])
    registry = state.get("entity_registry", {})
    manuscript_chapters = state.get("manuscript_chapters", [])
    relationships = state.get("relationships", [])
    character_tags = state.get("character_tags", [])
    world_settings = state.get("world_settings", {})
    timeline_branches = state.get("timeline_branches", [])
    world_containers = state.get("world_containers", [])
    proposals: list[dict] = list(state.get("proposals", []))
    errors: list[str] = list(state.get("errors", []))

    character_event_links: dict[str, list[str]] = {}
    for event_id, event in registry.get("events", {}).items():
        for cid in event.get("character_ids", []):
            character_event_links.setdefault(cid, [])
            if event_id not in character_event_links[cid]:
                character_event_links[cid].append(event_id)

    # Write character proposals
    for cid, entry in registry.get("characters", {}).items():
        op = {
            "op_type": "create",
            "entity_type": "character",
            "entity_id": cid,
            "data": {
                "id": cid,
                "name": entry.get("canonical_name", ""),
                "aliases": entry.get("aliases", []),
                "summary": entry.get("summary", "") or " ".join(entry.get("notes", [])[:2]),
                "background": entry.get("background", ""),
                "traits": entry.get("personality_traits", []),
                "goals": entry.get("goals", []),
                "fears": entry.get("fears", []),
                "secrets": entry.get("secrets", []),
                "speechStyle": entry.get("speech_style", ""),
                "arc": entry.get("arc_notes", ""),
                "tagIds": entry.get("tag_ids", []),
                "linkedEventIds": character_event_links.get(cid, []),
                "roleInStory": entry.get("role_in_story", ""),
                "physicalDescription": entry.get("physical_description", ""),
                "notes": entry.get("notes", []),
                "importConfidence": entry.get("confidence", 0.7),
                "importImportance": entry.get("importance", ""),
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose character {cid}: {str(e)}")

    # Write event proposals
    for eid, entry in registry.get("events", {}).items():
        op = {
            "op_type": "create",
            "entity_type": "timeline_event",
            "entity_id": eid,
            "data": {
                "id": eid,
                "title": entry.get("title", ""),
                "summary": entry.get("description", ""),
                "participantCharacterIds": entry.get("character_ids", []),
                "time": entry.get("temporal_hint", ""),
                "importConfidence": entry.get("confidence", 0.7),
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose event {eid}: {str(e)}")

    # Write world item proposals
    world_detailed = registry.get("world_detailed", {})
    for name, category in registry.get("world", {}).items():
        wid = f"world_{uuid.uuid4().hex[:8]}"
        detail = world_detailed.get(name, {})
        op = {
            "op_type": "create",
            "entity_type": "world_item",
            "entity_id": wid,
            "data": {
                "id": wid,
                "name": name,
                "category": detail.get("category", category),
                "description": detail.get("description", ""),
                "attributes": detail.get("attributes", []),
            },
            "source_workflow": "W1_import",
            "confidence": 0.70,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose world entry '{name}': {str(e)}")

    # Write relationship proposals
    for relationship in relationships:
        rel_id = relationship.get("id") or f"rel_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "relationship",
            "entity_id": rel_id,
            "data": {**relationship, "id": rel_id},
            "source_workflow": "W1_import",
            "confidence": float(relationship.get("importConfidence", 0.75)),
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose relationship {rel_id}: {str(e)}")

    # Write character tag proposals
    for tag in character_tags:
        tag_id = tag.get("id") or f"tag_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "character_tag",
            "entity_id": tag_id,
            "data": {**tag, "id": tag_id},
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose character tag {tag_id}: {str(e)}")

    # Write world settings proposal
    if world_settings:
        op = {
            "op_type": "update",
            "entity_type": "world_settings",
            "entity_id": "world_settings",
            "data": world_settings,
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose world settings: {str(e)}")

    # Write timeline branch proposals
    for branch in timeline_branches:
        branch_id = branch.get("id") or f"branch_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "timeline_branch",
            "entity_id": branch_id,
            "data": {**branch, "id": branch_id},
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose timeline branch {branch_id}: {str(e)}")

    # Write world container proposals
    for container in world_containers:
        container_id = container.get("id") or f"cont_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "world_container",
            "entity_id": container_id,
            "data": {**container, "id": container_id},
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose world container {container_id}: {str(e)}")

    # Push all proposals to inbox
    for proposal in proposals:
        try:
            await s4_proposal_queue.push_to_inbox(proposal, str(project_path))
        except Exception:
            pass

    # Write manuscript.json directly (verbatim source text, not AI-generated)
    manuscript_data = {
        "chapters": manuscript_chapters,
        "source_file": state["source_file_path"],
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    manuscript_path = project_path / "manuscript.json"
    with open(manuscript_path, "w", encoding="utf-8") as f:
        json.dump(manuscript_data, f, ensure_ascii=False, indent=2)

    # Delete checkpoint on success
    checkpoint_path = state.get("checkpoint_path", "")
    if checkpoint_path:
        try:
            Path(checkpoint_path).unlink(missing_ok=True)
        except Exception:
            pass

    # Trigger W2 in post_import mode (in-process, NOT via HTTP)
    try:
        from sidecar.workflows.w2_manuscript_sync import get_graph as get_w2_graph

        w2_initial = {
            "project_path": str(project_path),
            "workflow_id": f"W2-post-{state.get('workflow_id', 'W1')}",
            "mode": "post_import",
            "target_chapter_id": None,
            "extracted_entities": [],
            "diff": [],
            "proposals": [],
            "progress": 0.0,
            "errors": [],
            "status": "running",
        }
        w2_graph = get_w2_graph()
        await w2_graph.ainvoke(
            w2_initial,
            {"configurable": {"thread_id": f"w2-post-{state.get('workflow_id', 'W1')}"}},
        )
    except Exception as e:
        errors.append(f"W2 post_import trigger failed: {str(e)}")

    # Release workflow lock
    try:
        await release_lock(str(project_path))
    except Exception:
        pass

    return {
        "proposals": proposals,
        "errors": errors,
        "status": "done",
        "progress": 1.0,
    }


# ── Routing ──────────────────────────────────────────────────────────────────────

def route_by_mode(state: ImportState) -> str:
    """Conditional edge after split_chunks: content_only skips AI processing."""
    mode = state.get("import_mode", "import_all")
    if mode == "import_content_only":
        return "build_manuscript"
    return "process_chunks"


def route_after_build(state: ImportState) -> str:
    """Conditional edge after build_manuscript: content_only skips synthesis nodes."""
    mode = state.get("import_mode", "import_all")
    if mode == "import_content_only":
        return "generate_import_todos"
    return "synthesize_relationships"


# ── Synthesis node stubs (populated by Codex in Steps 3–5) ───────────────────

async def node_synthesize_relationships(state: ImportState) -> dict:
    """Post-chunk: consolidate raw relationship candidates into final relationships."""
    if not _HAS_DEEP_PROMPTS:
        return {"relationships": [], "progress": state.get("progress", 0.87)}

    raw_relationships = state.get("raw_relationships", [])
    if not raw_relationships:
        return {"relationships": [], "progress": 0.87}

    errors: list[str] = list(state.get("errors", []))
    registry = state.get("entity_registry", {})
    llm = _get_llm(state)

    registry_payload = {
        "characters": [
            {
                "canonical_id": cid,
                "canonical_name": entry.get("canonical_name", ""),
                "aliases": entry.get("aliases", []),
            }
            for cid, entry in registry.get("characters", {}).items()
        ]
    }

    try:
        result = await _invoke_json_prompt(
            llm,
            W1_SYNTHESIZE_RELATIONSHIPS,
            entity_registry_json=json.dumps(registry_payload, ensure_ascii=False, indent=2),
            relationship_candidates_json=json.dumps(raw_relationships, ensure_ascii=False, indent=2),
        )
    except Exception as e:
        errors.append(f"Relationship synthesis failed: {str(e)}")
        return {"relationships": [], "errors": errors, "progress": 0.87}

    relationships: list[dict] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for rel in result.get("relationships", []):
        source_id = _resolve_character_id(rel.get("source_id"), registry)
        target_id = _resolve_character_id(rel.get("target_id"), registry)
        if not source_id or not target_id or source_id == target_id:
            continue

        evidence = rel.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        evidence_list = [item.strip() for item in evidence if isinstance(item, str) and item.strip()]
        if len(evidence_list) < 1:
            continue

        directionality = str(rel.get("directionality", "bidirectional")).strip() or "bidirectional"
        key_ids: tuple[str, str]
        if directionality == "bidirectional":
            key_ids = tuple(sorted((source_id, target_id)))
        else:
            key_ids = (source_id, target_id)
        key = (
            key_ids,
            str(rel.get("type", "")).strip().lower(),
            str(rel.get("category", "")).strip().lower(),
            directionality,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)

        relationships.append({
            "id": rel.get("id") or f"rel_{uuid.uuid4().hex[:8]}",
            "sourceId": source_id,
            "targetId": target_id,
            "type": str(rel.get("type", "")).strip() or "relationship",
            "description": str(rel.get("description", "")).strip(),
            "strength": rel.get("strength"),
            "category": str(rel.get("category", "other")).strip() or "other",
            "directionality": directionality,
            "status": str(rel.get("status", "unknown")).strip() or "unknown",
            "sourceNotes": "\n".join(evidence_list),
            "importConfidence": float(rel.get("confidence", 0.75)),
        })

    return {"relationships": relationships, "errors": errors, "progress": 0.87}


async def node_classify_character_tags(state: ImportState) -> dict:
    """Post-chunk: classify imported characters into editorial tag groups."""
    if not _HAS_DEEP_PROMPTS:
        return {"character_tags": [], "progress": state.get("progress", 0.89)}

    registry = dict(state.get("entity_registry", {}))
    registry["characters"] = {k: dict(v) for k, v in registry.get("characters", {}).items()}
    errors: list[str] = list(state.get("errors", []))

    if not registry.get("characters"):
        return {"character_tags": [], "entity_registry": registry, "progress": 0.89}

    characters_payload = []
    for cid, entry in registry.get("characters", {}).items():
        characters_payload.append({
            "character_id": cid,
            "name": entry.get("canonical_name", ""),
            "aliases": entry.get("aliases", []),
            "summary": entry.get("summary", ""),
            "background": entry.get("background", ""),
            "role_in_story": entry.get("role_in_story", ""),
            "traits": entry.get("personality_traits", []),
            "goals": entry.get("goals", []),
            "fears": entry.get("fears", []),
            "secrets": entry.get("secrets", []),
            "arc_notes": entry.get("arc_notes", ""),
            "importance": entry.get("importance", ""),
        })
        registry["characters"][cid].setdefault("tag_ids", [])
        registry["characters"][cid]["tag_ids"] = []

    llm = _get_llm(state)
    try:
        result = await _invoke_json_prompt(
            llm,
            W1_CLASSIFY_CHARACTER_TAGS,
            characters_json=json.dumps(characters_payload, ensure_ascii=False, indent=2),
        )
    except Exception as e:
        errors.append(f"Character tag classification failed: {str(e)}")
        return {"character_tags": [], "entity_registry": registry, "errors": errors, "progress": 0.89}

    used_tag_ids: set[str] = set()
    character_tags: list[dict] = []
    for index, tag in enumerate(result.get("tags", [])):
        name = str(tag.get("name", "")).strip()
        if not name:
            continue

        character_ids = _resolve_character_ids(
            list(tag.get("character_ids", [])) + list(tag.get("character_names", [])),
            registry,
        )
        if not character_ids:
            continue

        tag_id = tag.get("id") or _stable_generated_id("tag", name, used_tag_ids)
        used_tag_ids.add(tag_id)
        color = str(tag.get("color", "")).strip() or _tag_color(index)
        tag_entry = {
            "id": tag_id,
            "name": name,
            "color": color,
            "description": str(tag.get("description", "")).strip(),
            "characterIds": character_ids,
        }
        character_tags.append(tag_entry)
        for cid in character_ids:
            registry["characters"][cid].setdefault("tag_ids", [])
            if tag_id not in registry["characters"][cid]["tag_ids"]:
                registry["characters"][cid]["tag_ids"].append(tag_id)

    for update in result.get("character_importance_updates", []):
        cid = update.get("character_id") or _resolve_character_id(update.get("character_name"), registry)
        if not cid or cid not in registry["characters"]:
            continue
        importance = str(update.get("importance", "")).strip()
        if importance:
            registry["characters"][cid]["importance"] = importance

    return {
        "character_tags": character_tags,
        "entity_registry": registry,
        "errors": errors,
        "progress": 0.89,
    }


async def node_infer_world_settings(state: ImportState) -> dict:
    """Post-chunk: infer world settings plus suggested branches and containers."""
    if not _HAS_DEEP_PROMPTS:
        return {"world_settings": {}, "timeline_branches": [], "world_containers": [], "progress": state.get("progress", 0.91)}

    errors: list[str] = list(state.get("errors", []))
    manuscript_chapters = state.get("manuscript_chapters", [])
    chunk_extractions = state.get("chunk_extractions", [])

    text_sample = "\n\n".join(chapter.get("manuscript_content", "") for chapter in manuscript_chapters).strip()
    if not text_sample:
        text_sample = "\n\n".join(extraction.get("manuscript_content", "") for extraction in chunk_extractions).strip()
    text_sample = text_sample[:24000]
    if not text_sample:
        return {"world_settings": {}, "timeline_branches": [], "world_containers": [], "errors": errors, "progress": 0.91}

    llm = _get_llm(state)
    try:
        result = await _invoke_json_prompt(
            llm,
            W1_INFER_WORLD_SETTINGS,
            text_sample=text_sample,
        )
    except Exception as e:
        errors.append(f"World settings inference failed: {str(e)}")
        return {"world_settings": {}, "timeline_branches": [], "world_containers": [], "errors": errors, "progress": 0.91}

    settings_raw = result.get("world_settings", {})
    world_settings = {
        "projectType": str(settings_raw.get("projectType", "")).strip(),
        "narrativePacing": str(settings_raw.get("narrativePacing", "")).strip(),
        "languageStyle": str(settings_raw.get("languageStyle", "")).strip(),
        "narrativePerspective": str(settings_raw.get("narrativePerspective", "")).strip(),
        "lengthStrategy": str(settings_raw.get("lengthStrategy", "")).strip(),
        "worldRulesSummary": str(settings_raw.get("worldRulesSummary", "")).strip(),
    }

    allowed_container_types = {"notebook", "graph", "timeline", "map"}
    world_containers: list[dict] = []
    used_container_ids: set[str] = set()
    for index, container in enumerate(result.get("suggested_world_containers", [])):
        name = str(container.get("name", "")).strip()
        if not name:
            continue
        container_type = str(container.get("type", "notebook")).strip().lower() or "notebook"
        if container_type not in allowed_container_types:
            container_type = "notebook"
        world_containers.append({
            "id": container.get("id") or _stable_generated_id("cont", name, used_container_ids),
            "name": name,
            "type": container_type,
            "isDefault": bool(container.get("is_default", container.get("isDefault", False))),
            "sortOrder": index,
            "description": str(container.get("description", "")).strip(),
        })

    raw_branches = result.get("inferred_timeline_branches", [])
    timeline_branches: list[dict] = []
    used_branch_ids: set[str] = set()
    branch_name_to_id: dict[str, str] = {}
    for index, branch in enumerate(raw_branches):
        name = str(branch.get("name", "")).strip()
        if not name:
            continue
        branch_id = branch.get("id") or _stable_generated_id("branch", name, used_branch_ids)
        mode = str(branch.get("mode", "independent")).strip().lower() or "independent"
        if mode not in {"root", "forked", "independent"}:
            mode = "independent"
        if index == 0 and mode != "root":
            mode = "root"
        branch_name_to_id[name.lower()] = branch_id
        timeline_branches.append({
            "id": branch_id,
            "name": name,
            "description": str(branch.get("description", "")).strip(),
            "parentBranchId": None,
            "forkEventId": None,
            "mergeEventId": None,
            "color": str(branch.get("color", "")).strip() or _tag_color(index),
            "sortOrder": index,
            "collapsed": False,
            "mode": mode,
            "startAnchor": None,
            "endAnchor": None,
            "endMode": "open",
            "mergeTargetBranchId": None,
        })

    for branch, raw_branch in zip(timeline_branches, raw_branches):
        parent_name = str(raw_branch.get("parent_branch_name", "")).strip().lower()
        if parent_name and parent_name in branch_name_to_id:
            branch["parentBranchId"] = branch_name_to_id[parent_name]
        elif branch.get("mode") == "forked" and timeline_branches:
            branch["parentBranchId"] = timeline_branches[0]["id"]

    return {
        "world_settings": world_settings,
        "timeline_branches": timeline_branches,
        "world_containers": world_containers,
        "errors": errors,
        "progress": 0.91,
    }


# ── Graph builder ───────────────────────────────────────────────────────────────

async def node_process_chunks(state: ImportState) -> dict:
    """Serial loop: run deep per-chunk extraction, update registry, and checkpoint."""
    chunks = [dict(chunk) for chunk in state.get("chunks", [])]
    registry_seed = dict(state.get("entity_registry", {"characters": {}, "events": {}, "world": {}}))
    registry = {
        "characters": {k: dict(v) for k, v in registry_seed.get("characters", {}).items()},
        "events": {k: dict(v) for k, v in registry_seed.get("events", {}).items()},
        "world": dict(registry_seed.get("world", {})),
    }
    extractions: list[dict] = list(state.get("chunk_extractions", []))
    raw_relationships: list[dict] = list(state.get("raw_relationships", []))
    errors: list[str] = list(state.get("errors", []))
    project_path = state["project_path"]
    checkpoint_path = state.get("checkpoint_path", "")
    completed_ids: set[int] = {e.get("chunk_id", -1) for e in extractions}
    total = len(chunks)
    completed = len(completed_ids)

    llm = _get_llm(state)
    chunk_index_by_id = {chunk.get("chunk_id", i): i for i, chunk in enumerate(chunks)}

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", 0)
        if chunk_id in completed_ids:
            continue

        chunk_content = chunk.get("content", "")
        chunk_notes: list[str] = []
        chunk_raw_relationships: list[dict] = []
        world_mentions_detailed: list[dict] = []
        scenes: list[dict] = []
        new_chars: list[dict] = []
        alias_updates: list[dict] = []
        events: list[dict] = []
        world_mentions: list[str] = []

        registry_summary = _registry_summary(registry)
        scene_hint = chunk.get("chapter_hint") or ""

        try:
            results = await asyncio.gather(
                _invoke_json_prompt(
                    llm,
                    W1_EXTRACT_CHARACTERS_DEEP,
                    chunk_content=chunk_content,
                    chunk_id=chunk_id,
                    total_chunks=total,
                    entity_registry_summary=registry_summary,
                ),
                _invoke_json_prompt(
                    llm,
                    W1_EXTRACT_EVENTS_DEEP,
                    chunk_content=chunk_content,
                    chunk_id=chunk_id,
                    total_chunks=total,
                    entity_registry_summary=registry_summary,
                ),
                _invoke_json_prompt(
                    llm,
                    W1_EXTRACT_WORLD_DEEP,
                    chunk_content=chunk_content,
                    chunk_id=chunk_id,
                    total_chunks=total,
                    entity_registry_summary=registry_summary,
                ),
                _invoke_json_prompt(
                    llm,
                    W1_EXTRACT_RELATIONSHIPS_CHUNK,
                    chunk_content=chunk_content,
                    chunk_id=chunk_id,
                    total_chunks=total,
                    entity_registry_summary=registry_summary,
                ),
                _invoke_json_prompt(
                    llm,
                    W1_EXTRACT_SCENE_SUMMARIES,
                    chunk_content=chunk_content,
                    chunk_id=chunk_id,
                    total_chunks=total,
                    entity_registry_summary=registry_summary,
                    chapter_hint=scene_hint,
                ),
                return_exceptions=True,
            )

            def _coerce_result(index: int, label: str) -> dict:
                result = results[index]
                if isinstance(result, Exception):
                    chunk_notes.append(f"{label} extraction failed: {result}")
                    errors.append(f"Chunk {chunk_id} {label} extraction failed: {result}")
                    return {}
                return result

            char_data = _coerce_result(0, "character")
            event_data = _coerce_result(1, "event")
            world_data = _coerce_result(2, "world")
            relationship_data = _coerce_result(3, "relationship")
            scene_data = _coerce_result(4, "scene")

            for update in char_data.get("existing_character_updates", []):
                cid = update.get("canonical_id") or _resolve_character_id(update.get("canonical_name"), registry)
                if not cid or cid not in registry.get("characters", {}):
                    continue

                entry = registry["characters"][cid]
                entry.setdefault("aliases", [])
                entry.setdefault("notes", [])
                entry.setdefault("personality_traits", [])
                entry.setdefault("goals", [])
                entry.setdefault("fears", [])
                entry.setdefault("secrets", [])
                entry.setdefault("tag_ids", [])

                new_aliases = update.get("new_aliases", [])
                _append_unique_strings(entry["aliases"], new_aliases)
                for alias in new_aliases:
                    if isinstance(alias, str) and alias.strip():
                        alias_updates.append({
                            "canonical_id": cid,
                            "new_alias": alias.strip(),
                            "note": f"Seen in chunk {chunk_id}",
                        })

                for note in update.get("new_notes", []):
                    if isinstance(note, str) and note.strip():
                        formatted_note = f"[chunk {chunk_id}] {note.strip()}"
                        if formatted_note not in entry["notes"]:
                            entry["notes"].append(formatted_note)

                entry["summary"] = _merge_text_field(entry.get("summary", ""), update.get("summary_update", ""))
                entry["background"] = _merge_text_field(entry.get("background", ""), update.get("background_update", ""))
                entry["role_in_story"] = _merge_text_field(entry.get("role_in_story", ""), update.get("role_in_story_update", ""))
                entry["physical_description"] = _merge_text_field(entry.get("physical_description", ""), update.get("physical_description_update", ""))
                entry["speech_style"] = _merge_text_field(entry.get("speech_style", ""), update.get("speech_style_update", ""))
                entry["arc_notes"] = _merge_text_field(entry.get("arc_notes", ""), update.get("arc_notes_update", ""))
                _append_unique_strings(entry["personality_traits"], update.get("new_personality_traits", []))
                _append_unique_strings(entry["goals"], update.get("new_goals", []))
                _append_unique_strings(entry["fears"], update.get("new_fears", []))
                _append_unique_strings(entry["secrets"], update.get("new_secrets", []))
                if isinstance(update.get("importance_update"), str) and update["importance_update"].strip():
                    entry["importance"] = update["importance_update"].strip()
                entry["confidence"] = max(float(entry.get("confidence", 0.7)), float(update.get("confidence", 0.7)))

            for nc in char_data.get("new_characters", []):
                name = str(nc.get("canonical_name", "")).strip()
                if not name:
                    continue

                matched_id = _resolve_character_id(name, registry)
                if matched_id:
                    entry = registry["characters"][matched_id]
                    entry.setdefault("aliases", [])
                    entry.setdefault("notes", [])
                    entry.setdefault("personality_traits", [])
                    entry.setdefault("goals", [])
                    entry.setdefault("fears", [])
                    entry.setdefault("secrets", [])
                    entry.setdefault("tag_ids", [])

                    if name != entry.get("canonical_name", "") and name not in entry["aliases"]:
                        entry["aliases"].append(name)
                        alias_updates.append({
                            "canonical_id": matched_id,
                            "new_alias": name,
                            "note": f"Seen as '{name}' in chunk {chunk_id}",
                        })

                    existing_aliases = set(entry["aliases"])
                    new_aliases = [alias for alias in nc.get("aliases", []) if isinstance(alias, str)]
                    _append_unique_strings(entry["aliases"], new_aliases)
                    for alias in new_aliases:
                        alias_clean = alias.strip()
                        if alias_clean and alias_clean not in existing_aliases:
                            alias_updates.append({
                                "canonical_id": matched_id,
                                "new_alias": alias_clean,
                                "note": f"Seen in chunk {chunk_id}",
                            })

                    for note in nc.get("notes", []):
                        if isinstance(note, str) and note.strip():
                            formatted_note = f"[chunk {chunk_id}] {note.strip()}"
                            if formatted_note not in entry["notes"]:
                                entry["notes"].append(formatted_note)

                    entry["summary"] = _merge_text_field(entry.get("summary", ""), nc.get("summary", ""))
                    entry["background"] = _merge_text_field(entry.get("background", ""), nc.get("background", ""))
                    entry["role_in_story"] = _merge_text_field(entry.get("role_in_story", ""), nc.get("role_in_story", ""))
                    entry["physical_description"] = _merge_text_field(entry.get("physical_description", ""), nc.get("physical_description", ""))
                    entry["speech_style"] = _merge_text_field(entry.get("speech_style", ""), nc.get("speech_style", ""))
                    entry["arc_notes"] = _merge_text_field(entry.get("arc_notes", ""), nc.get("arc_notes", ""))
                    _append_unique_strings(entry["personality_traits"], nc.get("personality_traits", []))
                    _append_unique_strings(entry["goals"], nc.get("goals", []))
                    _append_unique_strings(entry["fears"], nc.get("fears", []))
                    _append_unique_strings(entry["secrets"], nc.get("secrets", []))
                    if isinstance(nc.get("importance"), str) and nc["importance"].strip():
                        entry["importance"] = nc["importance"].strip()
                    entry["confidence"] = max(float(entry.get("confidence", 0.7)), float(nc.get("confidence", 0.7)))
                    continue

                char_id = f"char_{uuid.uuid4().hex[:8]}"
                aliases: list[str] = []
                _append_unique_strings(aliases, nc.get("aliases", []))
                registry["characters"][char_id] = {
                    "canonical_id": char_id,
                    "canonical_name": name,
                    "aliases": aliases,
                    "first_seen_chunk": chunk_id,
                    "notes": [f"[chunk {chunk_id}] {note.strip()}" for note in nc.get("notes", []) if isinstance(note, str) and note.strip()],
                    "confidence": float(nc.get("confidence", 0.7)),
                    "summary": str(nc.get("summary", "")).strip(),
                    "background": str(nc.get("background", "")).strip(),
                    "role_in_story": str(nc.get("role_in_story", "")).strip(),
                    "physical_description": str(nc.get("physical_description", "")).strip(),
                    "personality_traits": [trait.strip() for trait in nc.get("personality_traits", []) if isinstance(trait, str) and trait.strip()],
                    "goals": [goal.strip() for goal in nc.get("goals", []) if isinstance(goal, str) and goal.strip()],
                    "fears": [fear.strip() for fear in nc.get("fears", []) if isinstance(fear, str) and fear.strip()],
                    "secrets": [secret.strip() for secret in nc.get("secrets", []) if isinstance(secret, str) and secret.strip()],
                    "speech_style": str(nc.get("speech_style", "")).strip(),
                    "arc_notes": str(nc.get("arc_notes", "")).strip(),
                    "importance": str(nc.get("importance", "")).strip(),
                    "tag_ids": [],
                }
                new_chars.append(registry["characters"][char_id])

            for ev in event_data.get("events", []):
                event_id = f"event_{uuid.uuid4().hex[:8]}"
                character_refs = list(ev.get("character_ids", [])) + list(ev.get("character_names", []))
                resolved_character_ids = _resolve_character_ids(character_refs, registry)
                registry["events"][event_id] = {
                    "event_id": event_id,
                    "title": str(ev.get("title", "")).strip(),
                    "description": str(ev.get("description", "")).strip(),
                    "character_ids": resolved_character_ids,
                    "location_hint": str(ev.get("location_hint", "")).strip() or None,
                    "temporal_hint": str(ev.get("temporal_hint", "")).strip() or None,
                    "chunk_position": str(ev.get("chunk_position", "")).strip(),
                    "stakes": str(ev.get("stakes", "")).strip(),
                    "confidence": float(ev.get("confidence", 0.7)),
                    "chunk_id": chunk_id,
                }
                events.append(registry["events"][event_id])

            for wm in world_data.get("world_mentions", []):
                name = str(wm.get("name", "")).strip()
                if not name:
                    continue
                category = str(wm.get("category", "concept")).strip() or "concept"
                description = str(wm.get("description", "")).strip()
                if name not in registry.get("world", {}):
                    registry["world"][name] = category
                # Also store full detail in world_detailed for description passthrough
                if "world_detailed" not in registry:
                    registry["world_detailed"] = {}
                if name not in registry["world_detailed"]:
                    registry["world_detailed"][name] = {
                        "name": name,
                        "category": category,
                        "description": description,
                        "container_hint": str(wm.get("container_hint", "")).strip(),
                        "attributes": wm.get("attributes", []),
                        "confidence": float(wm.get("confidence", 0.7)),
                    }
                elif description and not registry["world_detailed"][name].get("description"):
                    registry["world_detailed"][name]["description"] = description
                world_mentions.append(name)
                world_mentions_detailed.append({
                    "name": name,
                    "category": category,
                    "description": description,
                    "container_hint": str(wm.get("container_hint", "")).strip(),
                    "attributes": wm.get("attributes", []),
                    "confidence": float(wm.get("confidence", 0.7)),
                })

            for rel in relationship_data.get("relationships", []):
                source_name = str(
                    rel.get("source_character_name")
                    or rel.get("source_name")
                    or rel.get("source", "")
                ).strip()
                target_name = str(
                    rel.get("target_character_name")
                    or rel.get("target_name")
                    or rel.get("target", "")
                ).strip()
                if not source_name or not target_name:
                    continue

                evidence = rel.get("evidence", [])
                if isinstance(evidence, str):
                    evidence = [evidence]

                candidate = {
                    "chunk_id": chunk_id,
                    "source_character_name": source_name,
                    "target_character_name": target_name,
                    "source_candidate_id": _resolve_character_id(source_name, registry),
                    "target_candidate_id": _resolve_character_id(target_name, registry),
                    "type": str(rel.get("type", "")).strip(),
                    "description": str(rel.get("description", "")).strip(),
                    "category": str(rel.get("category", "other")).strip() or "other",
                    "directionality": str(rel.get("directionality", "bidirectional")).strip() or "bidirectional",
                    "status": str(rel.get("status", "unknown")).strip() or "unknown",
                    "evidence": [item.strip() for item in evidence if isinstance(item, str) and item.strip()],
                    "confidence": float(rel.get("confidence", 0.7)),
                }
                raw_relationships.append(candidate)
                chunk_raw_relationships.append(candidate)

            chapter_hint = str(scene_data.get("chapter_hint", "")).strip() or scene_hint
            if chapter_hint:
                chunk_index = chunk_index_by_id.get(chunk_id)
                if chunk_index is not None and not chunks[chunk_index].get("chapter_hint"):
                    chunks[chunk_index]["chapter_hint"] = chapter_hint

            for scene in scene_data.get("scenes", []):
                character_ids = _resolve_character_ids(scene.get("character_names", []), registry)
                scenes.append({
                    "title": str(scene.get("title", "")).strip(),
                    "summary": str(scene.get("summary", "")).strip(),
                    "location_hint": str(scene.get("location_hint", "")).strip(),
                    "time_hint": str(scene.get("time_hint", "")).strip(),
                    "character_names": [name.strip() for name in scene.get("character_names", []) if isinstance(name, str) and name.strip()],
                    "character_ids": character_ids,
                    "purpose": str(scene.get("purpose", "")).strip(),
                    "confidence": float(scene.get("confidence", 0.7)),
                })

            extractions.append({
                "chunk_id": chunk_id,
                "new_characters": new_chars,
                "updated_aliases": alias_updates,
                "events": events,
                "world_mentions": world_mentions,
                "world_mentions_detailed": world_mentions_detailed,
                "raw_relationships": chunk_raw_relationships,
                "scenes": scenes,
                "chapter_hint": chapter_hint,
                "manuscript_content": chunk.get("manuscript_content", chunk_content),
                "notes": chunk_notes,
            })

        except Exception as e:
            errors.append(f"Chunk {chunk_id} failed: {str(e)}")
            extractions.append({
                "chunk_id": chunk_id,
                "new_characters": [],
                "updated_aliases": [],
                "events": [],
                "world_mentions": [],
                "world_mentions_detailed": [],
                "raw_relationships": [],
                "scenes": [],
                "chapter_hint": chunk.get("chapter_hint"),
                "manuscript_content": chunk.get("manuscript_content", chunk_content),
                "notes": [f"Extraction failed: {str(e)}"],
            })

        completed = len([e for e in extractions if e.get("chunk_id") is not None])
        try:
            checkpoint = {
                "project_path": project_path,
                "source_file_path": state["source_file_path"],
                "total_chunks": total,
                "completed_chunk_ids": [e["chunk_id"] for e in extractions],
                "entity_registry": registry,
                "chunk_extractions": extractions,
                "raw_relationships": raw_relationships,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        except Exception as e:
            errors.append(f"Checkpoint save failed after chunk {chunk_id}: {str(e)}")

    progress = 0.1 + (0.7 * (completed / max(total, 1)))
    return {
        "chunks": chunks,
        "entity_registry": registry,
        "chunk_extractions": extractions,
        "raw_relationships": raw_relationships,
        "errors": errors,
        "progress": progress,
    }


def build_graph() -> Any:
    """Build and compile the W1 Import StateGraph (dual-mode).

    content_only path: validate → checkpoint → split → build_manuscript → todos → write
    import_all path:   validate → checkpoint → split → process_chunks → resolve →
                       build_manuscript → synthesize_relationships → classify_tags →
                       infer_world_settings → todos → write
    """
    builder: StateGraph = StateGraph(ImportState)

    # Shared nodes
    builder.add_node("validate_file", node_validate_file)
    builder.add_node("load_or_init_checkpoint", node_load_or_init_checkpoint)
    builder.add_node("split_chunks", node_split_chunks)
    builder.add_node("build_manuscript", node_build_manuscript)
    builder.add_node("generate_import_todos", node_generate_import_todos)
    builder.add_node("write_to_project", node_write_to_project)

    # import_all-only nodes
    builder.add_node("process_chunks", node_process_chunks)
    builder.add_node("resolve_low_confidence", node_resolve_low_confidence)
    builder.add_node("synthesize_relationships", node_synthesize_relationships)
    builder.add_node("classify_character_tags", node_classify_character_tags)
    builder.add_node("infer_world_settings", node_infer_world_settings)

    # Shared spine
    builder.set_entry_point("validate_file")
    builder.add_edge("validate_file", "load_or_init_checkpoint")
    builder.add_edge("load_or_init_checkpoint", "split_chunks")

    # Branch: content_only → build_manuscript; import_all → process_chunks
    builder.add_conditional_edges(
        "split_chunks",
        route_by_mode,
        {
            "build_manuscript": "build_manuscript",
            "process_chunks": "process_chunks",
        },
    )

    # import_all path: process → resolve → build_manuscript
    builder.add_edge("process_chunks", "resolve_low_confidence")
    builder.add_edge("resolve_low_confidence", "build_manuscript")

    # After build_manuscript: branch again
    # content_only → generate_import_todos; import_all → synthesis chain
    builder.add_conditional_edges(
        "build_manuscript",
        route_after_build,
        {
            "generate_import_todos": "generate_import_todos",
            "synthesize_relationships": "synthesize_relationships",
        },
    )

    # Synthesis chain (import_all only)
    builder.add_edge("synthesize_relationships", "classify_character_tags")
    builder.add_edge("classify_character_tags", "infer_world_settings")
    builder.add_edge("infer_world_settings", "generate_import_todos")

    builder.add_edge("generate_import_todos", "write_to_project")
    builder.add_edge("write_to_project", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# Module-level singleton
_graph: Any = None


def get_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run(project_path: str, config: dict) -> dict:
    """Convenience entry point — creates state from config and runs graph."""
    import_mode = config.get("import_mode", "import_all")
    state: ImportState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "import_mode": import_mode,
        "context": config.get("context", {}),
        "chunks": [],
        "entity_registry": {},
        "chunk_extractions": [],
        "raw_relationships": [],
        "relationships": [],
        "character_tags": [],
        "world_settings": {},
        "timeline_branches": [],
        "world_containers": [],
        "manuscript_chapters": [],
        "proposals": [],
        "checkpoint_path": str(Path(project_path) / "import_progress.json"),
        "progress": 0.0,
        "errors": [],
        "status": "running",
    }
    thread_id = config.get("thread_id", f"w1-{uuid.uuid4().hex[:8]}")
    compiled = get_graph()
    return await compiled.ainvoke(state, {"configurable": {"thread_id": thread_id}})
