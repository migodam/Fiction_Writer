"""W6 — Beta Reader Workflow.

Reads target chapters from the perspective of a chosen persona and produces
structured feedback scores across five dimensions.

Graph:
  acquire_lock → select_persona → load_target_chapters → chunk_chapters
      → [serial per chunk] read_as_persona → generate_chunk_feedback
      → aggregate_feedback → generate_report → release_lock → END
"""
from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from pathlib import Path

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from sidecar.models.state import BetaReaderState, FeedbackItem, PersonaProfile
from sidecar.shared import s3_chunk_manager
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w6_prompts import W6_READ_AS_PERSONA, W6_GENERATE_FEEDBACK
from sidecar.tools.rag import rag_search


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


_DIMENSIONS = ("engagement", "pacing", "character", "logic", "world")


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def node_acquire_lock(state: dict) -> dict:
    try:
        await acquire_lock(state["project_path"], "W6")
    except WorkflowBusyError as e:
        return {"status": "error", "errors": [str(e)]}
    return {}


async def node_select_persona(state: dict) -> dict:
    """Load PersonaProfile from beta-personas.json and optionally enrich from RAG."""
    root = Path(state["project_path"])
    personas_file = root / "system" / "beta-personas.json"
    persona_id = state.get("persona_id", "")

    persona: PersonaProfile | None = None
    if personas_file.exists():
        try:
            all_personas = json.loads(personas_file.read_text(encoding="utf-8"))
            for p in all_personas if isinstance(all_personas, list) else all_personas.get("personas", []):
                if p.get("persona_id") == persona_id or p.get("id") == persona_id:
                    persona = PersonaProfile(
                        persona_id=p.get("persona_id", p.get("id", persona_id)),
                        name=p.get("name", "Unknown Reader"),
                        type=p.get("type", p.get("archetype", "casual")),
                        traits=p.get("traits", []),
                        focus_areas=p.get("focus_areas", []),
                        metadata_reference_id=p.get("metadata_reference_id"),
                    )
                    break
        except Exception:
            pass

    if persona is None:
        persona = PersonaProfile(
            persona_id=persona_id or "default",
            name="General Reader",
            type="casual",
            traits=["reads for enjoyment"],
            focus_areas=["story", "characters"],
            metadata_reference_id=None,
        )

    # Validate custom persona
    if persona["type"] == "custom" and not persona["traits"]:
        return {"status": "error", "errors": ["Custom persona requires non-empty traits[]"]}

    # Optionally enrich from RAG metadata
    style_context = ""
    if persona.get("metadata_reference_id"):
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", Path(state["project_path"]).name)[:40]
        collection = f"narrative_{safe_id}_metadata"
        focus = " ".join(persona["focus_areas"][:3])
        try:
            results = rag_search(focus, collection, n_results=2)
            style_context = "\n".join(r.get("content", "")[:300] for r in results)
        except Exception:
            style_context = ""

    return {"persona": persona, "_style_context": style_context, "progress": 0.05}


async def node_load_target_chapters(state: dict) -> dict:
    root = Path(state["project_path"])
    chapter_ids = state.get("target_chapter_ids", [])
    combined = ""
    for cid in chapter_ids:
        # Try chapter JSON first
        chapter_file = root / "writing" / "chapters" / f"{cid}.json"
        if chapter_file.exists():
            try:
                data = json.loads(chapter_file.read_text(encoding="utf-8"))
                content = data.get("content", "")
                if content:
                    combined += content + "\n\n"
                    continue
                # No inline content — load scenes via sceneIds
                for sid in data.get("sceneIds", []):
                    scene_md = root / "writing" / "scenes" / f"{sid}.md"
                    if scene_md.exists():
                        combined += scene_md.read_text(encoding="utf-8") + "\n\n"
                if data.get("sceneIds"):
                    continue
            except Exception:
                pass
        # Fallback: scene .md files with matching prefix
        for md_file in sorted((root / "writing" / "scenes").glob(f"{cid}*.md")):
            try:
                combined += md_file.read_text(encoding="utf-8") + "\n\n"
            except Exception:
                pass

    return {"_chapter_text": combined.strip(), "progress": 0.1}


async def node_chunk_chapters(state: dict) -> dict:
    text = state.get("_chapter_text", "")
    if not text:
        return {"chunks": [], "progress": 0.15}
    chunks = s3_chunk_manager.chunk_text(
        text,
        s3_chunk_manager.ChunkConfig(strategy="paragraph", chunk_size=500_000, overlap=50_000),
    )
    return {"chunks": chunks, "progress": 0.15}


async def node_read_and_feedback(state: dict) -> dict:
    """For each chunk: read_as_persona → generate_chunk_feedback."""
    model = _get_model(state)
    persona = state.get("persona", {})
    chunks = state.get("chunks", [])
    style_context = state.get("_style_context", "")
    total = max(len(chunks), 1)
    all_feedback: list[FeedbackItem] = []
    chapter_ids = state.get("target_chapter_ids", ["unknown"])

    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "")
        if not content.strip():
            continue

        persona_traits = ", ".join(persona.get("traits", []))
        focus_areas = ", ".join(persona.get("focus_areas", []))
        # Prepend style context to help persona simulate informed reader taste
        enriched_content = (f"[Reference style context:\n{style_context}\n]\n\n" + content) if style_context else content

        # Step 1: read as persona
        reactions_dict: dict = {}
        try:
            read_prompt = W6_READ_AS_PERSONA.format(
                persona_name=persona.get("name", "Reader"),
                persona_type=persona.get("type", "casual"),
                persona_traits=persona_traits,
                focus_areas=focus_areas,
                chunk_content=enriched_content[:6000],
            )
            resp = await model.ainvoke([HumanMessage(content=read_prompt)])
            reactions_dict = _parse_json(resp.content)
        except Exception:
            pass

        # Step 2: generate feedback from reactions
        chapter_id = chapter_ids[min(i, len(chapter_ids) - 1)]
        try:
            fb_prompt = W6_GENERATE_FEEDBACK.format(
                persona_name=persona.get("name", "Reader"),
                chunk_reactions_json=json.dumps(reactions_dict, ensure_ascii=False),
                chapter_id=chapter_id,
            )
            fb_resp = await model.ainvoke([HumanMessage(content=fb_prompt)])
            fb_data = _parse_json(fb_resp.content)
            for fb in fb_data.get("feedback", []):
                dim = fb.get("dimension", "")
                if dim in _DIMENSIONS:
                    all_feedback.append(FeedbackItem(
                        chapter_id=chapter_id,
                        dimension=dim,
                        score=int(fb.get("score", 5)),
                        comment=fb.get("comment", ""),
                        excerpt_reference=fb.get("excerpt_reference"),
                    ))
        except Exception:
            pass

        progress = 0.15 + 0.65 * (i + 1) / total

    return {"feedback_items": all_feedback, "progress": 0.8}


async def node_aggregate_feedback(state: dict) -> dict:
    """Average scores per dimension, excluding chunks with no feedback for that dim."""
    feedback_items: list[dict] = state.get("feedback_items", [])
    scores_by_dim: dict[str, list[int]] = defaultdict(list)
    for fb in feedback_items:
        dim = fb.get("dimension", "")
        score = fb.get("score", 0)
        if dim in _DIMENSIONS and isinstance(score, int) and 1 <= score <= 10:
            scores_by_dim[dim].append(score)

    avg_scores: dict[str, float] = {
        dim: round(sum(scores) / len(scores), 1)
        for dim, scores in scores_by_dim.items()
        if scores
    }
    return {"_avg_scores": avg_scores, "progress": 0.85}


async def node_generate_report(state: dict) -> dict:
    persona = state.get("persona", {})
    avg_scores = state.get("_avg_scores", {})
    feedback_items: list[dict] = state.get("feedback_items", [])
    chapter_ids = state.get("target_chapter_ids", [])

    # Score table
    score_rows = "\n".join(
        f"| {dim.capitalize()} | {avg_scores.get(dim, 'N/A')} |"
        for dim in _DIMENSIONS
    )

    # Detailed feedback by dimension
    dim_sections: list[str] = []
    for dim in _DIMENSIONS:
        items = [fb for fb in feedback_items if fb.get("dimension") == dim]
        if not items:
            continue
        comments = "\n".join(f"- {fb['comment']}" + (f" *(ref: {fb['excerpt_reference']})*" if fb.get("excerpt_reference") else "")
                              for fb in items[:5])
        dim_sections.append(f"### {dim.capitalize()}\n\n{comments}")

    # Standout moments (high and low extremes)
    standouts = [fb for fb in feedback_items if fb.get("score", 5) >= 9 or fb.get("score", 5) <= 2][:6]
    standout_text = "\n".join(
        f"- [{fb['dimension']} score {fb['score']}] {fb['comment']}"
        for fb in standouts
    ) if standouts else "No extreme scores noted."

    report = "\n\n".join([
        f"## Reader Persona\n\n**{persona.get('name', 'Reader')}** ({persona.get('type', 'casual')})\n"
        f"Traits: {', '.join(persona.get('traits', []))}\n"
        f"Focus: {', '.join(persona.get('focus_areas', []))}\n"
        f"Chapters reviewed: {', '.join(chapter_ids)}",

        f"## Overall Scores\n\n| Dimension | Score (1-10) |\n|---|---|\n{score_rows}",

        "## Detailed Feedback by Dimension\n\n" + ("\n\n".join(dim_sections) if dim_sections else "(no feedback)"),

        f"## Standout Moments\n\n{standout_text}",

        "## Recommendations\n\n"
        "- Address low-scoring dimensions before final publication.\n"
        "- Consider the persona's focus areas when revising.\n"
        "- Use W4 Consistency Check to validate structural changes.",
    ])

    return {"report_markdown": report, "status": "done", "progress": 0.95}


async def node_release_lock(state: dict) -> dict:
    try:
        await release_lock(state["project_path"])
    except Exception:
        pass
    return {"progress": 1.0}


# ── Graph construction ────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(BetaReaderState)
    nodes = [
        ("acquire_lock", node_acquire_lock),
        ("select_persona", node_select_persona),
        ("load_target_chapters", node_load_target_chapters),
        ("chunk_chapters", node_chunk_chapters),
        ("read_and_feedback", node_read_and_feedback),
        ("aggregate_feedback", node_aggregate_feedback),
        ("generate_report", node_generate_report),
        ("release_lock", node_release_lock),
    ]
    for name, fn in nodes:
        builder.add_node(name, fn)

    builder.set_entry_point("acquire_lock")
    for a, b in [
        ("acquire_lock", "select_persona"),
        ("select_persona", "load_target_chapters"),
        ("load_target_chapters", "chunk_chapters"),
        ("chunk_chapters", "read_and_feedback"),
        ("read_and_feedback", "aggregate_feedback"),
        ("aggregate_feedback", "generate_report"),
        ("generate_report", "release_lock"),
    ]:
        builder.add_edge(a, b)
    builder.add_edge("release_lock", END)

    memory = MemorySaver()
    _graph = builder.compile(checkpointer=memory)
    return _graph


async def run(project_path: str, config: dict) -> dict:
    initial_state: dict = {
        "project_path": project_path,
        "workflow_id": "W6",
        "persona_id": config.get("persona_id", ""),
        "persona": {},
        "target_chapter_ids": config.get("target_chapter_ids", []),
        "chunks": [],
        "feedback_items": [],
        "report_markdown": "",
        "progress": 0.0,
        "errors": [],
        "status": "running",
        "context": config.get("context", {}),
    }
    thread_id = config.get("thread_id", f"w6-{uuid.uuid4().hex[:8]}")
    graph = get_graph()
    result = await graph.ainvoke(initial_state, {"configurable": {"thread_id": thread_id}})
    return dict(result)
