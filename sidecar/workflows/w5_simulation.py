"""W5 — Simulation Engine Workflow.

Given a scenario variable (a change introduced into the story) and a set of affected
chapters, runs up to five simulation engines serially — only those in engines_selected.

Graph:
  acquire_lock → setup_scenario → load_affected_context → chunk_affected_chapters
      → [conditional serial] scenario_engine? → character_engine? → author_engine?
                                               → reader_engine? → logic_engine?
      → synthesize_results → generate_report → release_lock → END
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from sidecar.models.state import SimulationState, EngineOutput
from sidecar.shared import s1_context_builder, s3_chunk_manager
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w5_prompts import (
    W5_SCENARIO_ENGINE,
    W5_CHARACTER_ENGINE,
    W5_AUTHOR_ENGINE,
    W5_READER_ENGINE,
    W5_LOGIC_ENGINE,
)
from sidecar.tools.rag import rag_search
from sidecar.runtime.checkpointer import aclose_checkpointer, close_checkpointer, create_sqlite_checkpointer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_model(state: dict) -> ChatOpenAI:
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    base_url = ctx.get("endpoint", "https://api.deepseek.com/v1")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, max_tokens=4096)


def _parse_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return {}


def _selected(state: dict) -> list[str]:
    return [e.lower() for e in state.get("engines_selected", [])]


def _summarize_chars(ctx: dict) -> str:
    chars = ctx.get("characters", [])
    return json.dumps(
        [{"id": c.get("id"), "name": c.get("name"), "role": c.get("role")} for c in chars],
        ensure_ascii=False, indent=2,
    ) if chars else "[]"


def _summarize_timeline(ctx: dict) -> str:
    events = ctx.get("timeline_events", [])
    return json.dumps(
        [{"id": e.get("id"), "title": e.get("title"), "order": e.get("order")} for e in events],
        ensure_ascii=False, indent=2,
    ) if events else "[]"


def _summarize_world(ctx: dict) -> str:
    world = ctx.get("world_entries", [])
    return json.dumps(world, ensure_ascii=False, indent=2) if world else "[]"


def _chapters_summary(state: dict) -> str:
    chunks = state.get("_chapter_chunks", [])
    texts = [c.get("content", "")[:500] for c in chunks[:5]]
    return "\n\n---\n\n".join(texts) if texts else "(no chapter content loaded)"


def _store_engine(state: dict, engine_type: str, result_dict: dict) -> dict:
    results = dict(state.get("engine_results", {}))
    output: EngineOutput = {
        "engine_type": engine_type,
        "summary": str(result_dict)[:200],
        "details": [json.dumps(result_dict, ensure_ascii=False)],
        "confidence": 0.8,
    }
    results[engine_type] = output
    return {"engine_results": results}


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def node_acquire_lock(state: dict) -> dict:
    try:
        await acquire_lock(state["project_path"], "W5")
    except WorkflowBusyError as e:
        return {"status": "error", "errors": [str(e)]}
    return {}


async def node_setup_scenario(state: dict) -> dict:
    scenario = state.get("scenario_variable", "").strip()
    if not scenario:
        return {"status": "error", "errors": ["scenario_variable is required"]}
    return {"progress": 0.05}


async def node_load_affected_context(state: dict) -> dict:
    chapter_ids = state.get("affected_chapter_ids", [])
    anchor: dict[str, str] = {}
    if chapter_ids:
        anchor["chapter_id"] = chapter_ids[0]
    orig_ctx = state.get("context") or {}
    ctx = await s1_context_builder.build_context(state["project_path"], "simulation", anchor)
    ctx["api_key"] = orig_ctx.get("api_key", "")
    ctx["model"] = orig_ctx.get("model", "deepseek-chat")
    ctx["endpoint"] = orig_ctx.get("endpoint", "https://api.deepseek.com/v1")
    return {"context": dict(ctx), "progress": 0.1}


async def node_chunk_affected_chapters(state: dict) -> dict:
    import pathlib
    root = pathlib.Path(state["project_path"])
    chapter_ids = state.get("affected_chapter_ids", [])
    combined = ""
    for cid in chapter_ids:
        chapter_file = root / "writing" / "chapters" / f"{cid}.json"
        if chapter_file.exists():
            try:
                data = json.loads(chapter_file.read_text(encoding="utf-8"))
                combined += data.get("content", "") + "\n\n"
            except Exception:
                pass

    if not combined.strip():
        return {"_chapter_chunks": [], "progress": 0.15}

    chunks = s3_chunk_manager.chunk_text(
        combined,
        s3_chunk_manager.ChunkConfig(strategy="chapter", chunk_size=500_000, overlap=50_000),
    )
    return {"_chapter_chunks": chunks, "progress": 0.15}


async def node_scenario_engine(state: dict) -> dict:
    if "scenario" not in _selected(state):
        return {}
    model = _get_model(state)
    ctx = state.get("context", {})
    prompt = W5_SCENARIO_ENGINE.format(
        scenario_variable=state.get("scenario_variable", ""),
        affected_chapters_summary=_chapters_summary(state),
        character_profiles=_summarize_chars(ctx),
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        result = _parse_json(resp.content)
    except Exception as e:
        result = {"error": str(e)}
    updates = _store_engine(state, "scenario", result)
    updates["progress"] = 0.25
    return updates


async def node_character_engine(state: dict) -> dict:
    if "character" not in _selected(state):
        return {}
    model = _get_model(state)
    ctx = state.get("context", {})
    prompt = W5_CHARACTER_ENGINE.format(
        scenario_variable=state.get("scenario_variable", ""),
        character_profiles=_summarize_chars(ctx),
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        result = _parse_json(resp.content)
    except Exception as e:
        result = {"error": str(e)}
    updates = _store_engine(state, "character", result)
    updates["progress"] = 0.4
    return updates


async def node_author_engine(state: dict) -> dict:
    if "author" not in _selected(state):
        return {}
    model = _get_model(state)
    ctx = state.get("context", {})
    structure_notes = f"Chapters: {state.get('affected_chapter_ids', [])}"
    prompt = W5_AUTHOR_ENGINE.format(
        scenario_variable=state.get("scenario_variable", ""),
        current_narrative_structure=structure_notes,
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        result = _parse_json(resp.content)
    except Exception as e:
        result = {"error": str(e)}
    updates = _store_engine(state, "author", result)
    updates["progress"] = 0.55
    return updates


async def node_reader_engine(state: dict) -> dict:
    if "reader" not in _selected(state):
        return {}
    model = _get_model(state)
    ctx = state.get("context", {})

    # Try RAG for reader persona notes — gracefully handle missing collection
    collection = f"narrative_{re.sub(r'[^a-zA-Z0-9_-]', '_', state['project_path'].split('/')[-1].split(chr(92))[-1])[:40]}_metadata"
    genre_hints = ", ".join(
        e.get("title", "") for e in ctx.get("world_entries", []) if isinstance(e, dict)
    )[:200]

    try:
        rag_results = rag_search(f"reader reaction {genre_hints[:100]}", collection, n_results=3)
        reader_notes = "\n".join(r.get("content", "")[:300] for r in rag_results)
    except Exception:
        reader_notes = ""

    prompt = W5_READER_ENGINE.format(
        scenario_variable=state.get("scenario_variable", ""),
        genre_hints=genre_hints or "unknown genre",
        reader_persona_notes=reader_notes or "(no metadata available)",
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        result = _parse_json(resp.content)
    except Exception as e:
        result = {"error": str(e)}
    updates = _store_engine(state, "reader", result)
    updates["progress"] = 0.7
    return updates


async def node_logic_engine(state: dict) -> dict:
    if "logic" not in _selected(state):
        return {}
    model = _get_model(state)
    ctx = state.get("context", {})
    prompt = W5_LOGIC_ENGINE.format(
        scenario_variable=state.get("scenario_variable", ""),
        timeline_events=_summarize_timeline(ctx),
        world_rules=_summarize_world(ctx),
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        result = _parse_json(resp.content)
    except Exception as e:
        result = {"error": str(e)}
    updates = _store_engine(state, "logic", result)
    updates["progress"] = 0.8
    return updates


async def node_synthesize_results(state: dict) -> dict:
    """Merge engine results into a coherent synthesis dict."""
    results = state.get("engine_results", {})
    synthesis: list[str] = []
    for engine_type, output in results.items():
        details = output.get("details", [])
        if details:
            try:
                parsed = json.loads(details[0])
                synthesis.append(f"**{engine_type.capitalize()}**: {json.dumps(parsed, ensure_ascii=False)[:300]}")
            except Exception:
                synthesis.append(f"**{engine_type.capitalize()}**: {str(details[0])[:200]}")
    return {"_synthesis": "\n\n".join(synthesis), "progress": 0.88}


async def node_generate_report(state: dict) -> dict:
    """Produce the final Markdown report."""
    scenario = state.get("scenario_variable", "")
    results = state.get("engine_results", {})
    synthesis = state.get("_synthesis", "")

    lines: list[str] = [
        f"## Scenario\n\n{scenario}\n",
        "## Engine Results\n",
    ]
    for engine_type, output in results.items():
        details = output.get("details", [])
        content = ""
        if details:
            try:
                parsed = json.loads(details[0])
                content = json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception:
                content = str(details[0])
        lines.append(f"### {engine_type.capitalize()} Engine\n\n```json\n{content}\n```\n")

    lines += [
        "## Synthesis\n",
        synthesis or "(no synthesis available)",
        "\n## Recommended Actions\n",
        "- Review engine results above and apply relevant story changes.",
        "- Use the Consistency Check (W4) to validate any changes made.",
    ]

    return {"report_markdown": "\n\n".join(lines), "status": "done", "progress": 0.95}


async def node_release_lock(state: dict) -> dict:
    try:
        await release_lock(state["project_path"])
    except Exception:
        pass
    return {"progress": 1.0}


# ── Graph construction ────────────────────────────────────────────────────────

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
    if cache_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[cache_key]

    builder = StateGraph(SimulationState)
    nodes = [
        ("acquire_lock", node_acquire_lock),
        ("setup_scenario", node_setup_scenario),
        ("load_affected_context", node_load_affected_context),
        ("chunk_affected_chapters", node_chunk_affected_chapters),
        ("scenario_engine", node_scenario_engine),
        ("character_engine", node_character_engine),
        ("author_engine", node_author_engine),
        ("reader_engine", node_reader_engine),
        ("logic_engine", node_logic_engine),
        ("synthesize_results", node_synthesize_results),
        ("generate_report", node_generate_report),
        ("release_lock", node_release_lock),
    ]
    for name, fn in nodes:
        builder.add_node(name, fn)

    builder.set_entry_point("acquire_lock")
    for a, b in [
        ("acquire_lock", "setup_scenario"),
        ("setup_scenario", "load_affected_context"),
        ("load_affected_context", "chunk_affected_chapters"),
        ("chunk_affected_chapters", "scenario_engine"),
        ("scenario_engine", "character_engine"),
        ("character_engine", "author_engine"),
        ("author_engine", "reader_engine"),
        ("reader_engine", "logic_engine"),
        ("logic_engine", "synthesize_results"),
        ("synthesize_results", "generate_report"),
        ("generate_report", "release_lock"),
    ]:
        builder.add_edge(a, b)
    builder.add_edge("release_lock", END)

    graph = builder.compile(checkpointer=saver)
    _GRAPH_CACHE[cache_key] = graph
    return graph


async def run(project_path: str, config: dict) -> dict:
    project_path = str(_canonical_project_path(project_path))
    initial_state: dict = {
        "project_path": project_path,
        "workflow_id": "W5",
        "scenario_variable": config.get("scenario_variable", ""),
        "affected_chapter_ids": config.get("affected_chapter_ids", []),
        "engines_selected": config.get("engines_selected", ["scenario", "character", "logic"]),
        "context": config.get("context", {}),
        "engine_results": {},
        "report_markdown": "",
        "progress": 0.0,
        "errors": [],
        "status": "running",
    }
    thread_id = config.get("thread_id", f"w5-{uuid.uuid4().hex[:8]}")
    graph = get_graph(project_path)
    result = await graph.ainvoke(initial_state, {"configurable": {"thread_id": thread_id}})
    return dict(result)
