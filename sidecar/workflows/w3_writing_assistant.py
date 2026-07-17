"""W3 — Writing Assistant LangGraph workflow.

Supports two modes via state["hitl_mode"]:
  "direct_output"   → generates prose directly, no user choice required
  "three_options"   → generates 3 options, interrupts for user selection, then expands chosen

Graph is compiled with interrupt_before=["expand_selected"] so the
three_options path suspends at that node. Resume by calling the compiled
graph with Command(resume=<selected_option_index>).

Entry point:
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(initial_state, config)
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.types import Command
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from sidecar.models.state import WritingState
from sidecar.shared import s1_context_builder, s2_memory_writer
from sidecar.tools.analysis import character_tracker
from sidecar.runtime.checkpointer import aclose_checkpointer, close_checkpointer, create_sqlite_checkpointer


# ── Prompt import (lazy to avoid import-time errors if prompts not yet written) ──

def _get_prompts():
    from sidecar.prompts.w3_prompts import (
        W3_GENERATE_DIRECT,
        W3_GENERATE_OPTIONS,
        W3_EXPAND_SELECTED,
        W3_METADATA_STYLE_BLOCK,
    )
    return W3_GENERATE_DIRECT, W3_GENERATE_OPTIONS, W3_EXPAND_SELECTED, W3_METADATA_STYLE_BLOCK


# ── Constants ─────────────────────────────────────────────────────────────────

TARGET_LENGTH = 300   # words for direct_output
EXPAND_LENGTH = 500   # words for expand_selected


# ── Format helpers ────────────────────────────────────────────────────────────

def _format_character(char: Optional[dict]) -> str:
    if not char:
        return "(no POV character set)"
    name = char.get("name", "Unknown")
    summary = char.get("summary", "")
    traits = char.get("traits", "")
    return f"{name}: {summary}" + (f"\nTraits: {traits}" if traits else "")


def _format_todos(todos: list[dict]) -> str:
    if not todos:
        return "(none)"
    return "\n".join(
        f"- [{t.get('priority', 'medium').upper()}] {t.get('title', '')}"
        for t in todos[:5]
    )


def _format_events(events: list[dict]) -> str:
    if not events:
        return "(none)"
    return "\n".join(
        f"- {e.get('title', '')} ({e.get('time', '')})"
        for e in events[:8]
    )


def _format_scenes(scenes: list[dict]) -> str:
    if not scenes:
        return "(none)"
    return "\n".join(
        f"- {s.get('title', '')}: {s.get('summary', '')[:80]}"
        for s in scenes[:5]
    )


def _load_scene_content(project_path: str, scene_id: str, scene_meta: dict) -> str:
    """Return scene prose: prefer .md file, fall back to meta.content field."""
    prose_path = Path(project_path) / "writing" / "scenes" / f"{scene_id}.md"
    if prose_path.exists():
        return prose_path.read_text(encoding="utf-8")
    return scene_meta.get("content", "")


# ── Output parsers ────────────────────────────────────────────────────────────

def _parse_three_options(text: str) -> list[str]:
    """Parse OPTION 1/2/3 structured response into a list of up to 3 prose strings."""
    pattern = re.compile(
        r"OPTION\s+\d+:\s*[^\n]*\n[-]+\n(.*?)(?=OPTION\s+\d+:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    options = [m.strip() for m in pattern.findall(text) if m.strip()]
    if len(options) < 2:
        # Fallback: split on OPTION markers
        parts = re.split(r"OPTION\s+[123]:", text, flags=re.IGNORECASE)
        options = [p.strip() for p in parts if p.strip()]
    return options[:3] if options else [text]


def _parse_new_entities(text: str) -> list[dict]:
    """Extract NEW ENTITIES section from model output."""
    match = re.search(r"NEW ENTITIES:\s*\n((?:- .+\n?)+)", text, re.IGNORECASE)
    if not match:
        return []
    entities = []
    for line in match.group(1).split("\n"):
        line = line.strip().lstrip("- ")
        if not line:
            continue
        m = re.match(r"\[([^\]]+)\]\s+([^:]+):\s*(.*)", line)
        if m:
            entities.append({
                "entity_type": m.group(1).lower().strip(),
                "name": m.group(2).strip(),
                "description": m.group(3).strip(),
            })
    return entities


def _strip_entities_section(text: str) -> str:
    return re.sub(r"\n*NEW ENTITIES:\s*\n((?:- .+\n?)+)", "", text, flags=re.IGNORECASE).strip()


def _get_llm(state: WritingState) -> ChatOpenAI:
    ctx = state["context"]
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    base_url = ctx.get("endpoint", "https://api.deepseek.com/v1")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, max_tokens=4096)


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def node_build_context(state: WritingState) -> dict:
    project_path = state["project_path"]
    scene_id = state["scene_id"]

    scene_path = Path(project_path) / "writing" / "scenes" / f"{scene_id}.meta.json"
    scene: dict = {}
    if scene_path.exists():
        scene = json.loads(scene_path.read_text(encoding="utf-8"))

    anchor_ids: dict[str, str] = {}
    if scene.get("chapterId"):
        anchor_ids["chapter_id"] = scene["chapterId"]
    if scene.get("povCharacterId"):
        anchor_ids["character_id"] = scene["povCharacterId"]
        anchor_ids["pov_character_id"] = scene["povCharacterId"]

    ctx = await s1_context_builder.build_context(project_path, "writing", anchor_ids)
    # Preserve credentials injected by endpoint
    orig_ctx = state.get("context") or {}
    ctx["api_key"] = orig_ctx.get("api_key", "")
    ctx["model"] = orig_ctx.get("model", "deepseek-chat")
    ctx["endpoint"] = orig_ctx.get("endpoint", "https://api.deepseek.com/v1")
    ctx["scene"] = scene

    return {"context": dict(ctx), "progress": 0.1}


async def node_load_active_todos(state: WritingState) -> dict:
    todos: list[dict] = state["context"].get("active_todos", [])
    active = [t for t in todos if t.get("status") not in ("done", "dismissed")]
    return {"active_todos": active[:5], "progress": 0.2}


async def node_load_metadata_style(state: WritingState) -> dict:
    metadata_file_id = state.get("metadata_style")
    if not metadata_file_id:
        return {"metadata_chunks": [], "progress": 0.3}
    try:
        from sidecar.tools.rag import rag_search
        project_id = Path(state["project_path"]).name
        chunks = await rag_search(project_id, "writing style vocabulary pacing", top_k=5)
        return {
            "metadata_chunks": [
                c.get("content", "") if isinstance(c, dict) else str(c)
                for c in chunks
            ],
            "progress": 0.3,
        }
    except Exception:
        return {"metadata_chunks": [], "progress": 0.3}


async def node_generate_content(state: WritingState) -> dict:
    W3_GENERATE_DIRECT, W3_GENERATE_OPTIONS, _, W3_METADATA_STYLE_BLOCK = _get_prompts()

    ctx = state["context"]
    scene = ctx.get("scene", {})
    hitl_mode = state["hitl_mode"]

    # Style reference block
    metadata_style_block = ""
    if state.get("metadata_chunks"):
        style_text = "\n".join(state["metadata_chunks"][:3])
        metadata_style_block = W3_METADATA_STYLE_BLOCK.format(
            style_profile=style_text[:800],
            vocabulary_notes="(from selected reference material)",
        )

    pov_char = _format_character(ctx.get("anchored_character"))
    timeline_events = _format_events(ctx.get("timeline_events", []))
    scene_summaries = _format_scenes(ctx.get("scenes", []))
    active_todos = _format_todos(state.get("active_todos", []))
    scene_content = _load_scene_content(state["project_path"], state["scene_id"], scene)

    llm = _get_llm(state)

    if hitl_mode == "three_options":
        prompt = W3_GENERATE_OPTIONS.format(
            scene_id=state["scene_id"],
            task=state["task"],
            pov_character=pov_char,
            timeline_events=timeline_events,
            active_todos=active_todos,
            metadata_style_block=metadata_style_block,
            scene_content=scene_content[:3000] or "(empty scene — write an opening)",
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw: str = response.content if isinstance(response.content, str) else str(response.content)
        options = _parse_three_options(raw)
        return {"options": options, "progress": 0.6}
    else:
        prompt = W3_GENERATE_DIRECT.format(
            scene_id=state["scene_id"],
            task=state["task"],
            pov_character=pov_char,
            timeline_events=timeline_events,
            scene_summaries=scene_summaries,
            active_todos=active_todos,
            metadata_style_block=metadata_style_block,
            scene_content=scene_content[:3000] or "(empty scene — write an opening)",
            target_length=TARGET_LENGTH,
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        return {"output": _strip_entities_section(raw), "progress": 0.6}


async def node_expand_selected(state: WritingState) -> dict:
    _, _, W3_EXPAND_SELECTED, _ = _get_prompts()

    options = state.get("options", [])
    selected_idx = state.get("selected_option") or 0
    if selected_idx >= len(options):
        selected_idx = 0

    selected_text = options[selected_idx] if options else "(no option)"
    ctx = state["context"]
    scene = ctx.get("scene", {})
    scene_content = _load_scene_content(state["project_path"], state["scene_id"], scene)

    context_summary = (
        f"POV Character: {_format_character(ctx.get('anchored_character'))}\n"
        f"Timeline: {_format_events(ctx.get('timeline_events', []))}"
    )

    prompt = W3_EXPAND_SELECTED.format(
        selected_option_text=selected_text,
        scene_content=scene_content[:2000] or "(empty scene)",
        context_summary=context_summary,
        target_length=EXPAND_LENGTH,
    )

    llm = _get_llm(state)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw: str = response.content if isinstance(response.content, str) else str(response.content)
    return {"output": _strip_entities_section(raw), "progress": 0.85}


async def node_lightweight_consistency_check(state: WritingState) -> dict:
    """Silent consistency check — non-fatal, result not surfaced to user."""
    try:
        scene = state["context"].get("scene", {})
        char_id = scene.get("povCharacterId")
        if char_id:
            character_tracker(char_id, [scene])
    except Exception:
        pass
    return {"progress": 0.9}


async def node_extract_new_entities(state: WritingState) -> dict:
    output = state.get("output", "")
    new_entities = _parse_new_entities(output)
    return {"new_entities": new_entities, "progress": 0.95}


async def node_push_proposals(state: WritingState) -> dict:
    new_entities = state.get("new_entities", [])
    project_path = state["project_path"]
    proposals = list(state.get("proposals", []))

    for entity in new_entities:
        op = {
            "op_type": "create",
            "entity_type": entity.get("entity_type", "character"),
            "entity_id": None,
            "data": {
                "name": entity.get("name", ""),
                "description": entity.get("description", ""),
                "summary": entity.get("description", ""),
            },
            "source_workflow": "W3_writing_assistant",
            "confidence": 0.7,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, project_path)
            proposals.append(proposal)
        except Exception:
            pass

    return {"proposals": proposals, "progress": 1.0}


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_generate(state: WritingState) -> str:
    if state["hitl_mode"] == "three_options":
        return "expand_selected"
    return "lightweight_consistency_check"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(checkpointer: Any) -> Any:
    """Build and compile the W3 StateGraph with the supplied checkpointer.

    interrupt_before=["expand_selected"] means LangGraph will pause BEFORE
    executing expand_selected. The caller detects this via GraphInterrupt and
    stores the thread_id for later resumption.
    """
    builder: StateGraph = StateGraph(WritingState)

    builder.add_node("build_context", node_build_context)
    builder.add_node("load_active_todos", node_load_active_todos)
    builder.add_node("load_metadata_style", node_load_metadata_style)
    builder.add_node("generate_content", node_generate_content)
    builder.add_node("expand_selected", node_expand_selected)
    builder.add_node("lightweight_consistency_check", node_lightweight_consistency_check)
    builder.add_node("extract_new_entities", node_extract_new_entities)
    builder.add_node("push_proposals", node_push_proposals)

    builder.set_entry_point("build_context")
    builder.add_edge("build_context", "load_active_todos")
    builder.add_edge("load_active_todos", "load_metadata_style")
    builder.add_edge("load_metadata_style", "generate_content")

    builder.add_conditional_edges(
        "generate_content",
        route_after_generate,
        {
            "expand_selected": "expand_selected",
            "lightweight_consistency_check": "lightweight_consistency_check",
        },
    )

    builder.add_edge("expand_selected", "lightweight_consistency_check")
    builder.add_edge("lightweight_consistency_check", "extract_new_entities")
    builder.add_edge("extract_new_entities", "push_proposals")
    builder.add_edge("push_proposals", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["expand_selected"],
    )


_GRAPH_CACHE: dict[tuple[str, int], Any] = {}
_PROJECT_CHECKPOINTERS: dict[str, Any] = {}


def _canonical_project_path(project_path: str | Path) -> Path:
    return Path(project_path).expanduser().resolve()


def _project_checkpointer(project_path: Path) -> Any:
    project_key = str(project_path)
    if project_key not in _PROJECT_CHECKPOINTERS:
        database_path = project_path / "system" / "runtime" / "langgraph_checkpoints.db"
        database_path.parent.mkdir(parents=True, exist_ok=True)
        _PROJECT_CHECKPOINTERS[project_key] = create_sqlite_checkpointer(database_path)
    return _PROJECT_CHECKPOINTERS[project_key]


def close_project_checkpointer(project_path: str | Path) -> None:
    """Release the cached durable saver when a project runtime shuts down."""
    project_key = str(_canonical_project_path(project_path))
    for cache_key in [key for key in _GRAPH_CACHE if key[0] == project_key]:
        _GRAPH_CACHE.pop(cache_key)
    saver = _PROJECT_CHECKPOINTERS.pop(project_key, None)
    close_checkpointer(saver)


async def close_project_checkpointer_async(project_path: str | Path) -> None:
    project_key = str(_canonical_project_path(project_path))
    for cache_key in [key for key in _GRAPH_CACHE if key[0] == project_key]:
        _GRAPH_CACHE.pop(cache_key)
    await aclose_checkpointer(_PROJECT_CHECKPOINTERS.pop(project_key, None))


def get_graph(project_path: str | Path, *, checkpointer: Any | None = None) -> Any:
    canonical_path = _canonical_project_path(project_path)
    saver = checkpointer if checkpointer is not None else _project_checkpointer(canonical_path)
    cache_key = (str(canonical_path), id(saver))
    if cache_key not in _GRAPH_CACHE:
        _GRAPH_CACHE[cache_key] = build_graph(saver)
    return _GRAPH_CACHE[cache_key]


async def run(project_path: str, config: dict) -> dict:
    """Run W3 with a stable thread id supplied by the caller when resuming."""
    project_path = str(_canonical_project_path(project_path))
    initial_state: WritingState = {
        "project_path": project_path,
        "workflow_id": "W3",
        "scene_id": config.get("scene_id", ""),
        "task": config.get("task", "continue"),
        "context": config.get("context", {}),
        "active_todos": [],
        "metadata_style": config.get("metadata_file_id"),
        "metadata_chunks": [],
        "hitl_mode": config.get("hitl_mode", "direct_output"),
        "options": [],
        "selected_option": config.get("selected_option"),
        "output": "",
        "new_entities": [],
        "proposals": [],
        "progress": 0.0,
        "errors": [],
    }
    thread_id = config.get("thread_id", f"w3-{uuid.uuid4().hex[:8]}")
    invocation: WritingState | Command = (
        Command(resume=config["resume"])
        if "resume" in config
        else initial_state
    )
    result = await get_graph(project_path).ainvoke(
        invocation, {"configurable": {"thread_id": thread_id}}
    )
    return dict(result)
