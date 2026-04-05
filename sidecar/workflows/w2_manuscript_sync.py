"""W2 — Manuscript Sync LangGraph workflow.

Three modes:
  "post_import"    → write manuscript.json chapters into writing/chapters/ directory
  "draft_only"     → store raw draft text to writing/draft.md
  "single_chapter" → extract entities from chapter, diff with project data, generate proposals

Entry point:
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(initial_state, config)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from sidecar.models.state import ManuscriptSyncState
from sidecar.shared import s1_context_builder, s2_memory_writer, s4_proposal_queue
from sidecar.prompts.w2_prompts import W2_EXTRACT_FROM_CHAPTER


# ── LLM helper ─────────────────────────────────────────────────────────────────

def _get_llm(state: ManuscriptSyncState) -> ChatOpenAI:
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    base_url = ctx.get("endpoint", "https://api.deepseek.com/v1")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, max_tokens=4096)


# ── Mode router ─────────────────────────────────────────────────────────────────

def route_by_mode(state: ManuscriptSyncState) -> str:
    return state["mode"]


# ── Nodes ───────────────────────────────────────────────────────────────────────

async def node_write_manuscript_from_import(state: ManuscriptSyncState) -> dict:
    """post_import mode: read manuscript.json, write chapter files into writing/chapters/."""
    project_path = Path(state["project_path"])
    manuscript_path = project_path / "manuscript.json"

    if not manuscript_path.exists():
        return {"status": "error", "errors": ["manuscript.json not found"], "progress": 1.0}

    with open(manuscript_path, "r", encoding="utf-8") as f:
        manuscript = json.load(f)

    chapters = manuscript.get("chapters", [])
    chapters_dir = project_path / "writing" / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    for chapter in chapters:
        chapter_id = chapter.get("chapter_id", f"chap_{uuid.uuid4().hex[:8]}")
        title = chapter.get("title", "Untitled Chapter")
        content = chapter.get("manuscript_content", "")

        chapter_data = {
            "id": chapter_id,
            "title": title,
            "summary": "",
            "goal": "",
            "notes": "",
            "sceneIds": [],
            "orderIndex": chapters.index(chapter),
            "status": "draft",
        }

        chapter_file = chapters_dir / f"{chapter_id}.json"
        with open(chapter_file, "w", encoding="utf-8") as f:
            json.dump(chapter_data, f, ensure_ascii=False, indent=2)

        # Write scene content file
        scenes_dir = project_path / "writing" / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        scene_id = f"scene_{uuid.uuid4().hex[:8]}"
        scene_content_file = scenes_dir / f"{scene_id}.md"
        with open(scene_content_file, "w", encoding="utf-8") as f:
            f.write(content)

        scene_meta = {
            "id": scene_id,
            "chapterId": chapter_id,
            "title": f"{title} — content",
            "summary": "",
            "content": "",
            "orderIndex": 0,
            "povCharacterId": None,
            "linkedCharacterIds": [],
            "linkedEventIds": [],
            "linkedWorldItemIds": [],
            "status": "draft",
        }
        scene_meta_file = scenes_dir / f"{scene_id}.meta.json"
        with open(scene_meta_file, "w", encoding="utf-8") as f:
            json.dump(scene_meta, f, ensure_ascii=False, indent=2)

        # Update chapter's sceneIds
        chapter_data["sceneIds"] = [scene_id]
        with open(chapter_file, "w", encoding="utf-8") as f:
            json.dump(chapter_data, f, ensure_ascii=False, indent=2)

    return {"status": "done", "progress": 1.0}


async def node_store_draft(state: ManuscriptSyncState) -> dict:
    """draft_only mode: write raw draft text to writing/draft.md."""
    project_path = Path(state["project_path"])
    writing_dir = project_path / "writing"
    writing_dir.mkdir(parents=True, exist_ok=True)

    draft_path = writing_dir / "draft.md"
    # If target_chapter_id is provided, it contains draft content
    draft_content = state.get("draft_content", "")
    if draft_content:
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(draft_content)

    return {"status": "done", "progress": 1.0}


async def node_load_chapter_content(state: ManuscriptSyncState) -> dict:
    """single_chapter mode: load chapter + scene content for extraction."""
    project_path = Path(state["project_path"])
    chapter_id = state.get("target_chapter_id")

    if not chapter_id:
        return {"status": "error", "errors": ["no target_chapter_id provided"]}

    chapter_file = project_path / "writing" / "chapters" / f"{chapter_id}.json"
    if not chapter_file.exists():
        return {"status": "error", "errors": [f"chapter {chapter_id} not found"]}

    with open(chapter_file, "r", encoding="utf-8") as f:
        chapter_data = json.load(f)

    # Combine all scene content
    combined_text = []
    for scene_id in chapter_data.get("sceneIds", []):
        scene_md = project_path / "writing" / "scenes" / f"{scene_id}.md"
        if scene_md.exists():
            with open(scene_md, "r", encoding="utf-8") as f:
                combined_text.append(f.read())

    chapter_content = "\n\n".join(combined_text)
    return {"chapter_content": chapter_content, "chapter_data": chapter_data, "progress": 0.2}


async def node_extract_entities_from_chapter(state: ManuscriptSyncState) -> dict:
    """single_chapter mode: call Claude to extract entities from chapter."""
    project_path = Path(state["project_path"])

    # Load project context for summary
    ctx = await s1_context_builder.build_context(
        str(project_path), "consistency",
        {"chapter_id": state.get("target_chapter_id", "")},
    )

    characters_summary = json.dumps(
        [{"id": c.get("id"), "name": c.get("name"), "summary": c.get("summary", "")}
         for c in ctx.get("characters", [])],
        ensure_ascii=False, indent=2,
    )

    timeline_events_summary = json.dumps(
        [{"id": e.get("id"), "title": e.get("title"), "summary": e.get("summary", "")}
         for e in ctx.get("timeline_events", [])[:20]],
        ensure_ascii=False, indent=2,
    )

    world_entries_summary = json.dumps(
        [{"id": w.get("id"), "title": w.get("title"), "category": w.get("category", "")}
         for w in ctx.get("world_entries", [])[:20]],
        ensure_ascii=False, indent=2,
    )

    chapter_content = state.get("chapter_content", "")
    if not chapter_content:
        return {"extracted_entities": [], "errors": ["empty chapter content"]}

    prompt = W2_EXTRACT_FROM_CHAPTER.format(
        characters_summary=characters_summary[:3000],
        timeline_events_summary=timeline_events_summary[:2000],
        world_entries_summary=world_entries_summary[:2000],
        chapter_content=chapter_content[:8000],
    )

    try:
        llm = _get_llm(state)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content if isinstance(response.content, str) else str(response.content)

        # Strip markdown code fences if present
        if raw.strip().startswith("```"):
            raw = raw.strip()
            for fence in ("```json", "```"):
                if raw.startswith(fence):
                    raw = raw[len(fence):]
                if raw.endswith("```"):
                    raw = raw[:-3]
            raw = raw.strip()

        extracted = json.loads(raw)
        return {"extracted_entities": extracted, "progress": 0.6}
    except Exception as e:
        return {"extracted_entities": [], "errors": [f"entity extraction failed: {e}"], "progress": 0.6}


async def node_diff_with_project_data(state: ManuscriptSyncState) -> dict:
    """single_chapter mode: compare extracted entities against project data."""
    extracted = state.get("extracted_entities", {})
    diff_items: list[dict] = []

    # Check character conflicts
    for char in extracted.get("characters_found", []):
        conflict = char.get("conflicts_with_project")
        if conflict:
            diff_items.append({
                "type": "conflict",
                "entity_type": "character",
                "entity_id": char.get("matched_canonical_id"),
                "field": "attributes",
                "current_value": None,
                "extracted_value": char.get("attributes_mentioned", {}),
                "ambiguous": True,
                "description": conflict,
            })
        elif not char.get("matched_canonical_id"):
            diff_items.append({
                "type": "create",
                "entity_type": "character",
                "entity_id": None,
                "field": None,
                "current_value": None,
                "extracted_value": {"name": char.get("name_in_text", "")},
                "ambiguous": False,
                "description": f"New character: {char.get('name_in_text', '')}",
            })

    # Check event conflicts
    for event in extracted.get("events_found", []):
        conflict = event.get("conflicts_with_project")
        if conflict:
            diff_items.append({
                "type": "conflict",
                "entity_type": "event",
                "entity_id": event.get("matched_event_id"),
                "field": "details",
                "current_value": None,
                "extracted_value": {"title": event.get("title", ""), "characters": event.get("character_names", [])},
                "ambiguous": True,
                "description": conflict,
            })
        elif not event.get("matched_event_id"):
            diff_items.append({
                "type": "create",
                "entity_type": "event",
                "entity_id": None,
                "field": None,
                "current_value": None,
                "extracted_value": {"title": event.get("title", ""), "characters": event.get("character_names", [])},
                "ambiguous": False,
                "description": f"New event: {event.get('title', '')}",
            })

    # Check world mentions
    for wm in extracted.get("world_mentions", []):
        if not wm.get("matched_entry_id"):
            diff_items.append({
                "type": "create",
                "entity_type": "world_item",
                "entity_id": None,
                "field": None,
                "current_value": None,
                "extracted_value": {"name": wm.get("name", ""), "category": wm.get("category", "")},
                "ambiguous": False,
                "description": f"New world entry: {wm.get('name', '')}",
            })

    return {"diff": diff_items, "progress": 0.75}


async def node_generate_proposals(state: ManuscriptSyncState) -> dict:
    """single_chapter mode: create proposals for each diff."""
    diff_items = state.get("diff", [])
    project_path = state["project_path"]
    proposals: list[dict] = []

    for item in diff_items:
        confidence = 0.6 if item.get("ambiguous") else 0.75
        op = {
            "op_type": item["type"],
            "entity_type": item["entity_type"],
            "entity_id": item.get("entity_id"),
            "data": item.get("extracted_value", {}),
            "source_workflow": "W2_manuscript_sync",
            "confidence": confidence,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, project_path)
            proposals.append(proposal)
        except Exception:
            pass

    return {"proposals": proposals, "progress": 0.9}


async def node_push_to_inbox(state: ManuscriptSyncState) -> dict:
    """single_chapter mode: push proposals to inbox."""
    project_path = state["project_path"]
    proposals = state.get("proposals", [])

    for proposal in proposals:
        try:
            await s4_proposal_queue.push_to_inbox(proposal, project_path)
        except Exception:
            pass

    return {"status": "done", "progress": 1.0}


# ── Graph builder ───────────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Build and compile the W2 StateGraph."""
    builder: StateGraph = StateGraph(ManuscriptSyncState)

    # Add all nodes
    builder.add_node("write_manuscript_from_import_result", node_write_manuscript_from_import)
    builder.add_node("store_draft", node_store_draft)
    builder.add_node("load_chapter_content", node_load_chapter_content)
    builder.add_node("extract_entities_from_chapter", node_extract_entities_from_chapter)
    builder.add_node("diff_with_project_data", node_diff_with_project_data)
    builder.add_node("generate_proposals", node_generate_proposals)
    builder.add_node("push_to_inbox", node_push_to_inbox)

    # Conditional entry: route_by_mode → one of three sub-paths
    builder.set_conditional_entry_point(
        route_by_mode,
        {
            "post_import": "write_manuscript_from_import_result",
            "draft_only": "store_draft",
            "single_chapter": "load_chapter_content",
        },
    )

    # post_import path
    builder.add_edge("write_manuscript_from_import_result", END)

    # draft_only path
    builder.add_edge("store_draft", END)

    # single_chapter path
    builder.add_edge("load_chapter_content", "extract_entities_from_chapter")
    builder.add_edge("extract_entities_from_chapter", "diff_with_project_data")
    builder.add_edge("diff_with_project_data", "generate_proposals")
    builder.add_edge("generate_proposals", "push_to_inbox")
    builder.add_edge("push_to_inbox", END)

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
    state: ManuscriptSyncState = {
        "project_path": project_path,
        "workflow_id": config.get("workflow_id", "W2"),
        "mode": config.get("mode", "single_chapter"),
        "target_chapter_id": config.get("target_chapter_id"),
        "extracted_entities": [],
        "diff": [],
        "proposals": [],
        "progress": 0.0,
        "errors": [],
        "status": "running",
    }
    thread_id = config.get("thread_id", f"w2-{uuid.uuid4().hex[:8]}")
    compiled = get_graph()
    return await compiled.ainvoke(state, {"configurable": {"thread_id": thread_id}})
