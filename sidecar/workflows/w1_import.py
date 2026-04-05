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

from sidecar.models.state import ImportState, ChunkExtraction, ManuscriptChapter
from sidecar.shared import s2_memory_writer, s3_chunk_manager, s4_proposal_queue
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w1_prompts import (
    W1_EXTRACT_CHARACTERS,
    W1_EXTRACT_EVENTS,
    W1_EXTRACT_WORLD,
)


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


def _registry_summary(registry: dict) -> str:
    """Build a human-readable summary of the entity registry for prompts."""
    lines: list[str] = []
    for cid, entry in registry.get("characters", {}).items():
        aliases = ", ".join(entry.get("aliases", []))
        lines.append(
            f"- [{cid}] {entry.get('canonical_name', 'Unknown')}"
            f" (aliases: {aliases})"
            f" [first seen chunk {entry.get('first_seen_chunk', '?')}]"
        )
    if not lines:
        return "(empty — no characters identified yet)"
    return "\n".join(lines)


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


async def node_process_chunks(state: ImportState) -> dict:
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
    """Group chunk extractions by chapter_hint into ManuscriptChapter list."""
    extractions = state.get("chunk_extractions", [])
    chunks = state.get("chunks", [])

    # Build a map of chunk_id → chunk for chapter_hint lookup
    chunk_map = {c.get("chunk_id", i): c for i, c in enumerate(chunks)}

    # Group by chapter_hint
    chapter_map: dict[str, list[dict]] = {}
    chapter_order: list[str] = []

    for extraction in extractions:
        chunk_id = extraction.get("chunk_id", 0)
        chunk_data = chunk_map.get(chunk_id, {})
        hint = chunk_data.get("chapter_hint") or f"Chapter {len(chapter_order) + 1}"

        if hint not in chapter_map:
            chapter_map[hint] = []
            chapter_order.append(hint)
        chapter_map[hint].append(extraction)

    manuscript_chapters: list[dict] = []
    for hint in chapter_order:
        chapter_extractions = chapter_map[hint]
        content = "\n\n".join(
            e.get("manuscript_content", "") for e in chapter_extractions
        )
        manuscript_chapters.append({
            "chapter_id": f"chap_{uuid.uuid4().hex[:8]}",
            "title": hint,
            "chunk_ids": [e["chunk_id"] for e in chapter_extractions],
            "manuscript_content": content,
        })

    return {
        "manuscript_chapters": manuscript_chapters,
        "progress": 0.88,
    }


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
    proposals: list[dict] = list(state.get("proposals", []))
    errors: list[str] = list(state.get("errors", []))

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
                "summary": " ".join(entry.get("notes", [])[:2]),
                "background": "",
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
    for name, category in registry.get("world", {}).items():
        wid = f"world_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "world_item",
            "entity_id": wid,
            "data": {
                "id": wid,
                "name": name,
                "category": category,
                "description": "",
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


# ── Graph builder ───────────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Build and compile the W1 Import StateGraph."""
    builder: StateGraph = StateGraph(ImportState)

    builder.add_node("validate_file", node_validate_file)
    builder.add_node("load_or_init_checkpoint", node_load_or_init_checkpoint)
    builder.add_node("split_chunks", node_split_chunks)
    builder.add_node("process_chunks", node_process_chunks)
    builder.add_node("resolve_low_confidence", node_resolve_low_confidence)
    builder.add_node("build_manuscript", node_build_manuscript)
    builder.add_node("generate_import_todos", node_generate_import_todos)
    builder.add_node("write_to_project", node_write_to_project)

    builder.set_entry_point("validate_file")
    builder.add_edge("validate_file", "load_or_init_checkpoint")
    builder.add_edge("load_or_init_checkpoint", "split_chunks")
    builder.add_edge("split_chunks", "process_chunks")
    builder.add_edge("process_chunks", "resolve_low_confidence")
    builder.add_edge("resolve_low_confidence", "build_manuscript")
    builder.add_edge("build_manuscript", "generate_import_todos")
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
    state: ImportState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "chunks": [],
        "entity_registry": {},
        "chunk_extractions": [],
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
