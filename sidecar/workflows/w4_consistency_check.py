"""W4 — Consistency Check Workflow.

Two modes on the same graph, controlled by state["scope"]:
  - "scene" or "chapter" (lightweight): character_checker + item_tracker only
  - "full": all four checkers (timeline, character, world_rule, item_tracker)

Silent mode: scope="scene" called from W3 background. Does NOT acquire workflow.lock.
Full mode: acquires workflow.lock("W4").
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from sidecar.models.state import ConsistencyState, ConsistencyIssue
from sidecar.shared import s1_context_builder, s2_memory_writer, s4_proposal_queue
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w4_prompts import (
    W4_TIMELINE_CHECK,
    W4_CHARACTER_CHECK,
    W4_WORLD_RULE_CHECK,
    W4_ITEM_TRACKER,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_model(state: ConsistencyState) -> ChatOpenAI:
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    base_url = ctx.get("endpoint", "https://api.deepseek.com/v1")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, max_tokens=4096)


def _parse_issues(response_text: str, expected_type: str) -> list[dict]:
    """Strip code fences and parse JSON issues array from LLM response."""
    text = re.sub(r"```(?:json)?", "", response_text).strip().rstrip("`").strip()
    try:
        data = json.loads(text)
        return data.get("issues", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def _build_issue(raw: dict, scene_id: str) -> ConsistencyIssue:
    return ConsistencyIssue(
        issue_id=f"issue_{uuid.uuid4().hex[:8]}",
        type=raw.get("type", "character"),
        severity=raw.get("severity", "LOW"),
        description=raw.get("description", ""),
        scene_id=scene_id,
        entity_ids=raw.get("entity_ids", []),
        suggested_fix=raw.get("suggested_fix"),
    )


def _summarize_characters(ctx: dict) -> str:
    chars = ctx.get("characters", [])
    if not chars:
        return "No character profiles loaded."
    return json.dumps([
        {"id": c.get("id"), "name": c.get("name"), "role": c.get("role"),
         "status": c.get("status"), "aliases": c.get("aliases", [])}
        for c in chars
    ], ensure_ascii=False, indent=2)


def _summarize_timeline(ctx: dict) -> str:
    events = ctx.get("timeline_events", [])
    if not events:
        return "No timeline events loaded."
    return json.dumps([
        {"id": e.get("id"), "title": e.get("title"), "order": e.get("order")}
        for e in events
    ], ensure_ascii=False, indent=2)


def _summarize_world(ctx: dict) -> str:
    world = ctx.get("world_entries", [])
    if not world:
        return "No world entries loaded."
    return json.dumps(world, ensure_ascii=False, indent=2)


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def node_build_context(state: ConsistencyState) -> dict:
    """Load project context via S1."""
    scope = state.get("scope", "full")
    target_id = state.get("target_id", "")
    anchor: dict[str, str] = {}
    if scope == "scene":
        anchor["scene_id"] = target_id
    elif scope == "chapter":
        anchor["chapter_id"] = target_id

    orig_ctx = state.get("context") or {}
    ctx = await s1_context_builder.build_context(
        state["project_path"], "consistency", anchor
    )

    # Preserve LLM credentials from original context
    ctx["api_key"] = orig_ctx.get("api_key", "")
    ctx["model"] = orig_ctx.get("model", "deepseek-chat")
    ctx["endpoint"] = orig_ctx.get("endpoint", "https://api.deepseek.com/v1")

    # Load scene/chapter content for checker prompts
    content_lines: list[str] = []
    import pathlib
    root = pathlib.Path(state["project_path"])

    if scope == "scene" and target_id:
        scene_file = root / "writing" / "scenes" / f"{target_id}.md"
        if scene_file.exists():
            content_lines.append(scene_file.read_text(encoding="utf-8"))
    elif scope == "chapter" and target_id:
        chapter_file = root / "writing" / "chapters" / f"{target_id}.json"
        if chapter_file.exists():
            chapter_data = json.loads(chapter_file.read_text(encoding="utf-8"))
            content_lines.append(chapter_data.get("content", ""))
    elif scope == "full":
        # Load all scene files
        scenes_dir = root / "writing" / "scenes"
        if scenes_dir.exists():
            for md_file in sorted(scenes_dir.glob("*.md")):
                content_lines.append(md_file.read_text(encoding="utf-8"))

    scene_content = "\n\n---\n\n".join(content_lines) if content_lines else "(no content loaded)"

    # Store scene_content inside context dict (ConsistencyState has no top-level scene_content field)
    ctx["scene_content"] = scene_content
    return {"context": dict(ctx), "progress": 0.1}


async def node_acquire_lock(state: ConsistencyState) -> dict:
    """Acquire workflow lock for full-scope runs. Silent mode skips."""
    if state.get("scope") in ("scene", "chapter"):
        return {}  # Silent mode — no lock
    try:
        await acquire_lock(state["project_path"], "W4")
    except WorkflowBusyError as e:
        return {"status": "error", "errors": [str(e)]}
    return {}


async def node_timeline_checker(state: ConsistencyState) -> dict:
    """Check timeline ordering and causality (full mode only)."""
    model = _get_model(state)
    ctx = state.get("context", {})
    scene_content = ctx.pop("scene_content", "(no content)") if isinstance(ctx, dict) else "(no content)"
    # Keep scene_content in context for subsequent nodes
    ctx_copy = dict(ctx)
    ctx_copy["scene_content"] = scene_content

    prompt = W4_TIMELINE_CHECK.format(
        timeline_events_json=_summarize_timeline(ctx_copy),
        scene_content=scene_content,
    )
    response = await model.ainvoke([HumanMessage(content=prompt)])
    raw_issues = _parse_issues(response.content, "timeline")
    target_id = state.get("target_id", "")
    new_issues = [_build_issue(r, target_id) for r in raw_issues]
    existing = list(state.get("issues", []))
    return {"issues": existing + new_issues, "context": ctx_copy, "progress": 0.3}


async def node_character_checker(state: ConsistencyState) -> dict:
    """Check character attribute consistency."""
    model = _get_model(state)
    ctx = state.get("context", {})
    scene_content = ctx.get("scene_content", "(no content)")

    prompt = W4_CHARACTER_CHECK.format(
        character_profiles_json=_summarize_characters(ctx),
        scene_content=scene_content,
    )
    response = await model.ainvoke([HumanMessage(content=prompt)])
    raw_issues = _parse_issues(response.content, "character")
    target_id = state.get("target_id", "")
    new_issues = [_build_issue(r, target_id) for r in raw_issues]
    existing = list(state.get("issues", []))
    scope = state.get("scope", "full")
    progress = 0.5 if scope in ("scene", "chapter") else 0.55
    return {"issues": existing + new_issues, "progress": progress}


async def node_world_rule_checker(state: ConsistencyState) -> dict:
    """Check world rule violations (full mode only)."""
    model = _get_model(state)
    ctx = state.get("context", {})
    scene_content = ctx.get("scene_content", "(no content)")

    prompt = W4_WORLD_RULE_CHECK.format(
        world_rules_json=_summarize_world(ctx),
        scene_content=scene_content,
    )
    response = await model.ainvoke([HumanMessage(content=prompt)])
    raw_issues = _parse_issues(response.content, "world_rule")
    target_id = state.get("target_id", "")
    new_issues = [_build_issue(r, target_id) for r in raw_issues]
    existing = list(state.get("issues", []))
    return {"issues": existing + new_issues, "progress": 0.7}


async def node_item_tracker(state: ConsistencyState) -> dict:
    """Track physical item continuity."""
    model = _get_model(state)
    ctx = state.get("context", {})
    scene_content = ctx.get("scene_content", "(no content)")

    # Build item mentions from world entries that are physical items
    world = ctx.get("world_entries", [])
    item_mentions = [e for e in world if isinstance(e, dict) and e.get("category") in ("item", "object", "artifact")]
    item_json = json.dumps(item_mentions, ensure_ascii=False, indent=2) if item_mentions else "[]"

    prompt = W4_ITEM_TRACKER.format(
        item_mentions_json=item_json,
        scene_content=scene_content,
    )
    response = await model.ainvoke([HumanMessage(content=prompt)])
    raw_issues = _parse_issues(response.content, "item_tracking")
    target_id = state.get("target_id", "")
    new_issues = [_build_issue(r, target_id) for r in raw_issues]
    existing = list(state.get("issues", []))
    scope = state.get("scope", "full")
    progress = 0.75 if scope in ("scene", "chapter") else 0.8
    return {"issues": existing + new_issues, "progress": progress}


async def node_merge_issues(state: ConsistencyState) -> dict:
    """Deduplicate issues and finalize the list."""
    issues = list(state.get("issues", []))
    # Simple dedup by description
    seen: set[str] = set()
    unique: list[Any] = []
    for issue in issues:
        key = issue.get("description", "")[:80]
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return {"issues": unique, "progress": 0.85}


async def node_rank_severity(state: ConsistencyState) -> dict:
    """Sort issues HIGH→MED→LOW and populate severity_counts."""
    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    issues = sorted(state.get("issues", []), key=lambda i: order.get(i.get("severity", "LOW"), 2))
    counts: dict[str, int] = {"HIGH": 0, "MED": 0, "LOW": 0}
    for issue in issues:
        sev = issue.get("severity", "LOW")
        counts[sev] = counts.get(sev, 0) + 1
    return {"issues": issues, "severity_counts": counts, "progress": 0.9}


async def node_route_output_lightweight(state: ConsistencyState) -> dict:
    """Lightweight path: push inline annotation event (not Inbox)."""
    # In-process notification — renderer listens for 'w4:annotation' IPC event
    # The router endpoint will emit this via SSE when wired; for now return issues in state
    return {"status": "done", "progress": 1.0}


async def node_generate_fix_proposals(state: ConsistencyState) -> dict:
    """Full path: generate fix proposals for HIGH severity issues via S2."""
    proposals: list[dict] = []
    for issue in state.get("issues", []):
        if issue.get("severity") != "HIGH":
            continue
        if not issue.get("suggested_fix"):
            continue
        proposal = await s2_memory_writer.propose_write(
            op={
                "op_type": "update",
                "entity_type": "scene",
                "entity_id": issue.get("scene_id", "unknown"),
                "data": {"consistency_fix": issue["suggested_fix"], "issue_id": issue["issue_id"]},
                "source_workflow": "W4",
                "confidence": 0.65,
                "auto_apply": False,
            },
            project_path=state["project_path"],
        )
        if proposal:
            proposals.append(proposal)
            await s4_proposal_queue.push_to_inbox(proposal, state["project_path"])

    return {"proposals": proposals}


async def node_release_lock(state: ConsistencyState) -> dict:
    """Release workflow lock after full-scope run."""
    if state.get("scope") not in ("scene", "chapter"):
        try:
            await release_lock(state["project_path"])
        except Exception:
            pass
    return {"status": "done", "progress": 1.0}


# ── Routing functions ─────────────────────────────────────────────────────────

def route_by_scope(state: ConsistencyState) -> str:
    scope = state.get("scope", "full")
    return "lightweight" if scope in ("scene", "chapter") else "full"


def route_output(state: ConsistencyState) -> str:
    scope = state.get("scope", "full")
    return "lightweight" if scope in ("scene", "chapter") else "full"


# ── Graph construction ────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(ConsistencyState)

    builder.add_node("build_context", node_build_context)
    builder.add_node("acquire_lock", node_acquire_lock)
    builder.add_node("timeline_checker", node_timeline_checker)
    builder.add_node("character_checker", node_character_checker)
    builder.add_node("world_rule_checker", node_world_rule_checker)
    builder.add_node("item_tracker", node_item_tracker)
    builder.add_node("merge_issues", node_merge_issues)
    builder.add_node("rank_severity", node_rank_severity)
    builder.add_node("route_output_lightweight", node_route_output_lightweight)
    builder.add_node("generate_fix_proposals", node_generate_fix_proposals)
    builder.add_node("release_lock", node_release_lock)

    builder.set_entry_point("build_context")
    builder.add_edge("build_context", "acquire_lock")

    # Conditional routing after lock acquisition
    builder.add_conditional_edges(
        "acquire_lock",
        route_by_scope,
        {
            "lightweight": "character_checker",
            "full": "timeline_checker",
        },
    )

    # Full path
    builder.add_edge("timeline_checker", "character_checker")
    builder.add_edge("character_checker", "world_rule_checker")
    builder.add_edge("world_rule_checker", "item_tracker")

    # Lightweight path: character_checker → item_tracker
    # Note: lightweight also goes through character_checker → item_tracker
    # The conditional edge above handles the branching; item_tracker is shared.
    builder.add_edge("item_tracker", "merge_issues")
    builder.add_edge("merge_issues", "rank_severity")

    builder.add_conditional_edges(
        "rank_severity",
        route_output,
        {
            "lightweight": "route_output_lightweight",
            "full": "generate_fix_proposals",
        },
    )

    builder.add_edge("route_output_lightweight", END)
    builder.add_edge("generate_fix_proposals", "release_lock")
    builder.add_edge("release_lock", END)

    memory = MemorySaver()
    _graph = builder.compile(checkpointer=memory)
    return _graph


async def run(project_path: str, config: dict) -> dict:
    """Entry point for W4. config must include scope, target_id, and optionally context."""
    initial_state: ConsistencyState = {
        "project_path": project_path,
        "workflow_id": "W4",
        "scope": config.get("scope", "full"),
        "target_id": config.get("target_id", ""),
        "context": config.get("context", {}),
        "issues": [],
        "severity_counts": {},
        "proposals": [],
        "progress": 0.0,
        "errors": [],
        "status": "running",
    }
    thread_id = config.get("thread_id", f"w4-{uuid.uuid4().hex[:8]}")
    graph = get_graph()
    result = await graph.ainvoke(initial_state, {"configurable": {"thread_id": thread_id}})
    return dict(result)
