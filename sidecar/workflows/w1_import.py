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
import hashlib
import json
import math
import re
import uuid
from json import JSONDecodeError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from sidecar.models.state import ImportState, ManuscriptChapter
from sidecar.shared import s2_memory_writer, s3_chunk_manager
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

# Module-level per-project chunk progress tracker.
# node_process_chunks updates this after each chunk so that the polling
# coroutine in _run_w1 (workflows.py) can report real-time progress to
# the status endpoint without waiting for the whole node to finish.
# key: project_path  value: {"completed": int, "total": int}
_chunk_progress: dict[str, dict] = {}

# Module-level per-project chunk log (populated by node_process_chunks).
# key: project_path  value: List[ChunkLogEntry dicts]
_chunk_log: dict[str, list] = {}

# Breakpoint: process_chunks pauses after completing this chunk index (0-based count).
# key: project_path  value: int | None
_breakpoint_chunks: dict[str, int | None] = {}

# Pause events: clear() to block, set() to unblock.
# key: project_path  value: asyncio.Event (starts set = running)
_pause_events: dict[str, asyncio.Event] = {}

# Cancel events: set to signal node_process_chunks to abort early.
# key: project_path  value: asyncio.Event
_cancel_events: dict[str, asyncio.Event] = {}

# ── Importance mapping ──────────────────────────────────────────────────────────
# Maps LLM output values (including legacy) → canonical model values.
IMPORTANCE_MAP: dict[str, str] = {
    "lead":       "core",
    "core":       "core",
    "major":      "major",
    "supporting": "supporting",
    "minor":      "minor",
    "background": "minor",
}

# Group labels assigned during auto-grouping at import time.
IMPORTANCE_TO_GROUP: dict[str, str] = {
    "core":       "Main Characters",
    "major":      "Supporting Cast",
    "supporting": "Supporting Cast",
    "minor":      "Minor Characters",
}

# ── Field truncation ────────────────────────────────────────────────────────────
_FIELD_WORD_LIMITS: dict[str, int] = {
    "summary": 40,
    "background": 60,
    "personality_traits": 0,  # handled as list
    "physical_description": 40,
    "arc_notes": 40,
}


def _truncate_text_fields(char_data: dict) -> dict:
    """Enforce word-count limits on character description fields."""
    for field, limit in _FIELD_WORD_LIMITS.items():
        if limit == 0:
            continue
        val = char_data.get(field, "")
        if val and isinstance(val, str):
            words = val.split()
            if len(words) > limit:
                char_data[field] = " ".join(words[:limit]) + "…"
    return char_data


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


class JsonPromptParseError(ValueError):
    """Raised when an LLM response cannot be normalized into valid JSON."""


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()
    return text


def _extract_json_object_text(text: str) -> str:
    """Return the most likely JSON object/array substring from a model response."""
    text = _strip_json_fence(text)
    starts = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
    if not starts:
        return text
    start = min(starts)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return text[start:]


def _remove_trailing_json_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, tolerating common non-structured-output drift."""
    candidates = []
    extracted = _extract_json_object_text(raw)
    candidates.append(extracted)
    candidates.append(_remove_trailing_json_commas(extracted))
    last_error: Exception | None = None
    for candidate in dict.fromkeys(candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
            raise JsonPromptParseError("JSON root must be an object")
        except Exception as exc:
            last_error = exc
    raise JsonPromptParseError(str(last_error) if last_error else "invalid JSON response")


def _is_truncated_json_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "unterminated string" in message
        or "expecting ',' delimiter" in message
        or "expecting value" in message
        or "char" in message and "line" in message
    )


async def _repair_json_response(llm: ChatOpenAI, raw: str, parse_error: Exception) -> dict:
    """Ask the configured model to repair malformed JSON without changing semantics."""
    repair_prompt = f"""
Repair the following malformed JSON into a single valid JSON object.
Rules:
- Output valid JSON only. No markdown, no explanation.
- Preserve all keys and values that can be recovered.
- Remove trailing commas.
- If a string or object is truncated, close it safely and keep the recovered prefix.
- If a field cannot be recovered, use an empty string, empty array, or null.

Parser error:
{str(parse_error)[:1200]}

Malformed JSON:
{raw[:24000]}
"""
    async with _API_SEMAPHORE:
        response = await llm.ainvoke([HumanMessage(content=repair_prompt)])
    repaired = response.content if isinstance(response.content, str) else str(response.content)
    return _parse_json_response(repaired)


async def _invoke_json_prompt(llm: ChatOpenAI, prompt_template: str, **kwargs: Any) -> dict:
    """Render a prompt template, invoke the LLM, and parse the JSON response.

    Retries up to 4 times with exponential backoff for transient failures:
    - Rate-limit / governor errors (429, 503, 'Authentication Fails (governor)')
    - 'str' object has no attribute 'model_dump' — LangChain streaming parse error
      when DeepSeek injects a governor error into an SSE stream.
    - JSON parse failures (model returned prose instead of JSON).
    """
    prompt = prompt_template.format(**kwargs)
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            async with _API_SEMAPHORE:
                response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = response.content if isinstance(response.content, str) else str(response.content)
            try:
                return _parse_json_response(raw)
            except Exception as parse_exc:
                if _is_truncated_json_error(parse_exc) or isinstance(parse_exc, (JSONDecodeError, JsonPromptParseError, ValueError)):
                    return await _repair_json_response(llm, raw, parse_exc)
                raise
        except Exception as exc:
            err_str = str(exc).lower()
            is_retryable = (
                "model_dump" in err_str          # SSE governor parse error
                or "rate limit" in err_str
                or "governor" in err_str
                or "too many requests" in err_str
                or "503" in err_str
                or "502" in err_str
                or "timeout" in err_str
                or "401" in err_str              # transient DeepSeek auth blip
                or "no api key" in err_str
                or "didn't provide an api key" in err_str
                or isinstance(exc, (json.JSONDecodeError, ValueError))
            )
            if is_retryable and attempt < max_attempts - 1:
                # Give 401 a longer backoff — DeepSeek occasionally has transient
                # auth blips that resolve within a few seconds.
                if "401" in err_str or "no api key" in err_str or "didn't provide an api key" in err_str:
                    wait = 5 * (attempt + 1)  # 5s, 10s, 15s
                else:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait)
                continue
            raise


def _append_unique_strings(target: list[str], values: list[Any]) -> None:
    """Append unique non-empty string values, preserving order."""
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


def _merge_text_field(existing: str, incoming: Any) -> str:
    """Merge a short text field without duplicating identical or near-duplicate lines."""
    if not isinstance(incoming, str):
        return existing
    cleaned = incoming.strip()
    if not cleaned:
        return existing
    existing_lines = [line.strip() for line in existing.splitlines() if line.strip()]
    if cleaned in existing_lines:
        return existing
    # Skip near-duplicate content (catches bilingual translations of the same fact)
    for line in existing_lines:
        ratio = difflib.SequenceMatcher(None, cleaned.lower()[:200], line.lower()[:200]).ratio()
        if ratio > 0.65:
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


# ── Import compiler artifacts ─────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _stable_id(prefix: str, *parts: Any, length: int = 12) -> str:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _normal_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\W_]+", "", text)


def _artifact_dir(project_path: str | Path, import_run_id: str) -> Path:
    return Path(project_path) / "system" / "imports" / import_run_id


def _write_import_artifact(project_path: str | Path, import_run_id: str, filename: str, payload: dict | list) -> str:
    directory = _artifact_dir(project_path, import_run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)


def _chunk_cache_path(project_path: str | Path, import_run_id: str, chunk_id: int) -> Path:
    return _artifact_dir(project_path, import_run_id) / "chunks" / f"chunk_{chunk_id}.json"


def _read_chunk_prompt_cache(state: ImportState, chunk: dict) -> dict | None:
    import_run_id = state.get("import_run_id")
    if not import_run_id:
        return None
    chunk_id = int(chunk.get("chunk_id", 0) or 0)
    path = _chunk_cache_path(state["project_path"], import_run_id, chunk_id)
    payload = _safe_read_json(path, None)
    if not isinstance(payload, dict):
        return None
    raw = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
    if payload.get("chunk_hash") != _sha256_text(raw):
        return None
    if payload.get("prompt_profile") != (state.get("prompt_profile") or "balanced"):
        return None
    if payload.get("prompt_window_contract") != "chapter_window_v1":
        return None
    prompts = payload.get("prompt_outputs")
    return prompts if isinstance(prompts, dict) else None


def _write_chunk_prompt_cache(state: ImportState, chunk: dict, prompt_outputs: dict) -> None:
    import_run_id = state.get("import_run_id")
    if not import_run_id:
        return
    chunk_id = int(chunk.get("chunk_id", 0) or 0)
    raw = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
    path = _chunk_cache_path(state["project_path"], import_run_id, chunk_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "chunk_id": chunk_id,
            "segment_id": chunk.get("segment_id"),
            "chunk_hash": _sha256_text(raw),
            "prompt_profile": state.get("prompt_profile") or "balanced",
            "prompt_window_contract": "chapter_window_v1",
            "written_at": _now_iso(),
            "prompt_outputs": prompt_outputs,
        }, f, ensure_ascii=False, indent=2)


def _write_chunk_prompt_failure(state: ImportState, chunk: dict, failures: list[dict]) -> None:
    import_run_id = state.get("import_run_id")
    if not import_run_id or not failures:
        return
    chunk_id = int(chunk.get("chunk_id", 0) or 0)
    raw = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
    path = _artifact_dir(state["project_path"], import_run_id) / "chunks" / f"chunk_{chunk_id}_failures.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "chunk_id": chunk_id,
            "segment_id": chunk.get("segment_id"),
            "chunk_hash": _sha256_text(raw),
            "prompt_profile": state.get("prompt_profile") or "balanced",
            "written_at": _now_iso(),
            "failures": failures,
        }, f, ensure_ascii=False, indent=2)


def _profile_text_budget(profile: str) -> int:
    """Bound per-prompt source text so long novels do not blow model context."""
    budgets = {
        "fast": 24_000,
        "balanced": 64_000,
        "deep": 128_000,
        "custom": 128_000,
    }
    return budgets.get(profile, budgets["balanced"])


_DEEP_PROMPT_TOTAL_TOKEN_BUDGET = 256_000
_SCHEMA_POLICY_RESERVE_TOKENS = 24_000
_DIGEST_RESERVE_TOKENS = 24_000
_VALIDATION_RESERVE_TOKENS = 8_000


def _estimate_tokens(text: str) -> int:
    """Cheap mixed English/CJK token estimate for prompt accounting."""
    if not text:
        return 0
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", text))
    non_cjk_chars = max(len(text) - cjk_chars, 0)
    return max(1, math.ceil(cjk_chars + (non_cjk_chars / 4)))


def _prompt_total_token_budget(profile: str) -> int:
    if profile in {"deep", "custom"}:
        return _DEEP_PROMPT_TOTAL_TOKEN_BUDGET
    # Keep smaller profiles bounded while moving away from head/tail truncation.
    return max(_profile_text_budget(profile) // 2, 16_000)


def _bounded_chunk_content(state: ImportState, chunk_content: str) -> str:
    budget = _profile_text_budget(state.get("prompt_profile") or state.get("context", {}).get("prompt_profile", "balanced"))
    if len(chunk_content) <= budget:
        return chunk_content
    head = chunk_content[: budget // 2]
    tail = chunk_content[-(budget // 2):]
    return f"{head}\n\n[...middle omitted by W1 prompt profile context budget...]\n\n{tail}"


def _safe_read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return fallback
    return fallback


def _read_json_files(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    for file_path in sorted(path.glob("*.json")):
        item = _safe_read_json(file_path, None)
        if isinstance(item, dict):
            items.append(item)
    return items


def _read_json_list(path: Path) -> list[dict]:
    value = _safe_read_json(path, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _load_existing_project_snapshot(project_path: str | Path) -> dict:
    """Load a compact project snapshot for deterministic import reconciliation."""
    root = Path(project_path)
    entities = root / "entities"
    timeline_dir = entities / "timeline"
    writing_dir = root / "writing"
    world_dir = entities / "world"
    snapshot = {
        "characters": _read_json_files(entities / "characters"),
        "character_tags": _safe_read_json(entities / "character_tags.json", []),
        "relationships": _safe_read_json(entities / "relationships.json", []),
        "world_items": [
            item for item in _read_json_files(world_dir)
            if item.get("id") and not str(item.get("id", "")).startswith(("cont_", "map_"))
        ],
        "world_containers": _read_json_list(world_dir / "containers.json"),
        "timeline_events": _read_json_files(timeline_dir),
        "timeline_branches": _safe_read_json(timeline_dir / "branches.json", []),
        "chapters": _read_json_files(writing_dir / "chapters"),
        "scenes": _read_json_files(writing_dir / "scenes"),
        "issues": _safe_read_json(root / "system" / "issues.json", []),
        "inbox": _safe_read_json(root / "system" / "inbox.json", []),
    }
    for key, value in list(snapshot.items()):
        if not isinstance(value, list):
            snapshot[key] = []
    return snapshot


def _clip_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _project_proposal_risk_summary(snapshot: dict) -> dict:
    inbox = snapshot.get("inbox", [])
    issues = snapshot.get("issues", [])
    statuses: dict[str, int] = {}
    severities: dict[str, int] = {}
    for item in inbox:
        status = str(item.get("status") or item.get("state") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        risk = str(item.get("risk_level") or item.get("riskLevel") or "")
        if risk:
            severities[risk] = severities.get(risk, 0) + 1
    for issue in issues:
        severity = str(issue.get("severity") or "unknown")
        severities[severity] = severities.get(severity, 0) + 1
    return {
        "open_inbox_items": len(inbox),
        "open_issues": len(issues),
        "statuses": statuses,
        "risk_or_severity": severities,
    }


def _build_project_structure_digest(state: ImportState, import_run_id: str) -> dict:
    """Assemble a compact import context from existing project structure."""
    snapshot = _load_existing_project_snapshot(state["project_path"])
    characters = []
    for character in snapshot.get("characters", [])[:80]:
        characters.append({
            "id": character.get("id") or character.get("canonical_id"),
            "name": character.get("name") or character.get("canonical_name"),
            "aliases": character.get("aliases", [])[:6],
            "tagIds": character.get("tagIds") or character.get("tag_ids") or [],
            "group": character.get("groupId") or character.get("group") or character.get("importImportance") or character.get("importance"),
            "summary": _clip_text(character.get("summary"), 220),
        })

    character_groups: dict[str, int] = {}
    for character in snapshot.get("characters", []):
        group = str(character.get("groupId") or character.get("group") or character.get("importImportance") or character.get("importance") or "ungrouped")
        character_groups[group] = character_groups.get(group, 0) + 1

    relationships = []
    for relationship in snapshot.get("relationships", [])[:80]:
        relationships.append({
            "id": relationship.get("id"),
            "sourceId": relationship.get("sourceId") or relationship.get("source_character_id"),
            "targetId": relationship.get("targetId") or relationship.get("target_character_id"),
            "type": relationship.get("type"),
            "category": relationship.get("category"),
            "status": relationship.get("status"),
            "description": _clip_text(relationship.get("description"), 180),
        })

    timeline_branches = []
    for branch in snapshot.get("timeline_branches", [])[:40]:
        timeline_branches.append({
            "id": branch.get("id"),
            "name": branch.get("name"),
            "parentBranchId": branch.get("parentBranchId"),
            "mode": branch.get("mode"),
            "description": _clip_text(branch.get("description"), 180),
        })

    world_containers = []
    for container in snapshot.get("world_containers", [])[:40]:
        world_containers.append({
            "id": container.get("id"),
            "name": container.get("name"),
            "type": container.get("type"),
            "description": _clip_text(container.get("description"), 180),
        })

    world_items = []
    for item in snapshot.get("world_items", [])[:100]:
        world_items.append({
            "id": item.get("id"),
            "name": item.get("name") or item.get("title"),
            "type": item.get("type") or item.get("category"),
            "containerId": item.get("containerId"),
            "summary": _clip_text(item.get("summary") or item.get("description"), 180),
        })

    digest_payload = {
        "version": 1,
        "import_run_id": import_run_id,
        "counts": {
            "characters": len(snapshot.get("characters", [])),
            "character_tags": len(snapshot.get("character_tags", [])),
            "relationships": len(snapshot.get("relationships", [])),
            "timeline_branches": len(snapshot.get("timeline_branches", [])),
            "world_containers": len(snapshot.get("world_containers", [])),
            "world_items": len(snapshot.get("world_items", [])),
            "open_inbox_items": len(snapshot.get("inbox", [])),
            "open_issues": len(snapshot.get("issues", [])),
        },
        "characters": characters,
        "character_groups": character_groups,
        "character_tags": snapshot.get("character_tags", [])[:80],
        "relationships": relationships,
        "timeline_branches": timeline_branches,
        "world_containers": world_containers,
        "world_items": world_items,
        "proposal_risk_summary": _project_proposal_risk_summary(snapshot),
    }
    content = json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "import_run_id": import_run_id,
        "artifact_path": str(_artifact_dir(state["project_path"], import_run_id) / "project_structure_digest.json"),
        "content": content,
        "estimated_tokens": _estimate_tokens(content),
        "counts": digest_payload["counts"],
    }


def _previous_validation_summary(state: ImportState) -> str:
    report = state.get("import_review_report") or {}
    if not report:
        return json.dumps({"status": "none", "warnings": [], "errors": []}, separators=(",", ":"))
    payload = {
        "status": report.get("status", "unknown"),
        "warnings": report.get("warnings", [])[:20],
        "errors": report.get("errors", [])[:20],
        "failed_chunks": report.get("failed_chunks", [])[:20],
        "low_confidence_items": report.get("low_confidence_items", [])[:20],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fit_text_to_token_budget(text: str, token_budget: int) -> str:
    if _estimate_tokens(text) <= token_budget:
        return text
    if token_budget <= 0:
        return ""
    char_budget = max(token_budget * 2, 1)
    clipped = text[:char_budget].rstrip()
    while clipped and _estimate_tokens(clipped) > token_budget:
        clipped = clipped[: max(len(clipped) - 256, 0)].rstrip()
    return clipped + "\n[...digest clipped to prompt reserve...]"


def _split_text_by_paragraph_budget(text: str, token_budget: int) -> list[str]:
    if _estimate_tokens(text) <= token_budget:
        return [text]
    paragraphs = re.split(r"(\n{2,}|(?<=。)\s*|(?<=\.)\s+)", text)
    units: list[str] = []
    for i in range(0, len(paragraphs), 2):
        unit = paragraphs[i]
        if i + 1 < len(paragraphs):
            unit += paragraphs[i + 1]
        if unit:
            units.append(unit)
    if not units:
        units = [text]

    windows: list[str] = []
    current = ""
    for unit in units:
        if current and _estimate_tokens(current + unit) > token_budget:
            windows.append(current)
            current = ""
        if _estimate_tokens(unit) > token_budget:
            char_budget = max(token_budget, 1)
            for start in range(0, len(unit), char_budget):
                part = unit[start:start + char_budget]
                if part:
                    windows.append(part)
            continue
        current += unit
    if current:
        windows.append(current)
    return windows or [text]


def _build_prompt_windows(state: ImportState, chunks: list[dict], digest: dict) -> list[dict]:
    profile = state.get("prompt_profile") or state.get("context", {}).get("prompt_profile", "balanced")
    total_budget = _prompt_total_token_budget(profile)
    validation_summary = _previous_validation_summary(state)
    digest_content = _fit_text_to_token_budget(str(digest.get("content", "")), _DIGEST_RESERVE_TOKENS)
    validation_content = _fit_text_to_token_budget(validation_summary, _VALIDATION_RESERVE_TOKENS)
    digest_tokens = _estimate_tokens(digest_content)
    validation_tokens = _estimate_tokens(validation_content)
    source_budget = max(total_budget - _SCHEMA_POLICY_RESERVE_TOKENS - digest_tokens - validation_tokens, 1_000)
    windows: list[dict] = []

    for chunk in chunks:
        chunk_id = int(chunk.get("chunk_id", len(windows)) or 0)
        source_text = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
        chapter_hint = str(chunk.get("chapter_hint") or f"Segment {chunk_id + 1}")
        parts = _split_text_by_paragraph_budget(source_text, source_budget)
        for part_index, part in enumerate(parts):
            split_reason = "complete_chapter"
            if len(parts) > 1:
                split_reason = "single_oversized_chapter_paragraph_split"
            header = (
                "PROJECT_STRUCTURE_DIGEST:\n"
                f"{digest_content}\n\n"
                "PREVIOUS_VALIDATION_SUMMARY:\n"
                f"{validation_content}\n\n"
                "PROMPT_WINDOW_POLICY:\n"
                f"total_estimated_token_budget={total_budget}; "
                f"schema_policy_reserve_tokens={_SCHEMA_POLICY_RESERVE_TOKENS}; "
                f"source_budget_tokens={source_budget}; "
                "preserve complete chapters; only paragraph-split a single oversized chapter.\n\n"
                f"SOURCE_CHAPTERS [{chapter_hint}]:\n"
            )
            window_text = header + part
            source_start = int(chunk.get("source_span", {}).get("start", chunk.get("char_start", 0)) or 0)
            windows.append({
                "id": _stable_id("pwin", state.get("import_run_id") or "import", chunk_id, part_index, _sha256_text(part)[:16]),
                "chunk_ids": [chunk_id],
                "chapter_range": chapter_hint if len(parts) == 1 else f"{chapter_hint} part {part_index + 1}/{len(parts)}",
                "text": window_text,
                "estimated_tokens": _estimate_tokens(window_text) + _SCHEMA_POLICY_RESERVE_TOKENS,
                "source_chars": len(part),
                "digest_token_estimate": digest_tokens,
                "validation_token_estimate": validation_tokens,
                "split_reason": split_reason,
                "source_span": {"start": source_start, "end": source_start + len(source_text)},
            })
    return windows


def _prompt_window_manifest_entry(window: dict) -> dict:
    return {
        "id": window.get("id"),
        "chapter_range": window.get("chapter_range"),
        "chunk_ids": window.get("chunk_ids", []),
        "estimated_tokens": window.get("estimated_tokens", 0),
        "source_chars": window.get("source_chars", 0),
        "digest_token_estimate": window.get("digest_token_estimate", 0),
        "validation_token_estimate": window.get("validation_token_estimate", 0),
        "split_reason": window.get("split_reason", ""),
        "source_span": window.get("source_span", {}),
    }


def _merge_prompt_outputs(outputs: list[dict]) -> dict:
    merged: dict[str, Any] = {}
    for output in outputs:
        if not isinstance(output, dict):
            continue
        for key, value in output.items():
            if isinstance(value, list):
                merged.setdefault(key, [])
                merged[key].extend(value)
            elif isinstance(value, dict):
                merged.setdefault(key, {})
                merged[key].update(value)
            elif key not in merged or not merged.get(key):
                merged[key] = value
    return merged


def _build_import_manifest(state: ImportState, text: str, chunks: list[dict]) -> dict:
    source_hash = _sha256_text(text)
    prompt_profile = state.get("prompt_profile") or state.get("context", {}).get("prompt_profile") or "balanced"
    import_run_id = state.get("import_run_id") or _stable_id(
        "import",
        state.get("source_file_path", ""),
        source_hash,
        state.get("import_mode", "import_all"),
        prompt_profile,
    )
    model = state.get("context", {}).get("model", "deepseek-chat")
    segments: list[dict] = []
    running_offset = 0
    for index, chunk in enumerate(chunks):
        raw = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
        chapter_hint = chunk.get("chapter_hint") or f"Segment {index + 1}"
        segment_id = _stable_id("seg", import_run_id, index, chapter_hint, _sha256_text(raw)[:16])
        start = running_offset
        end = start + len(raw)
        running_offset = end
        chunk["segment_id"] = segment_id
        chunk["source_span"] = {"start": start, "end": end}
        segments.append({
            "id": segment_id,
            "level": "chapter" if chunk.get("chapter_hint") else "window",
            "title": chapter_hint,
            "chunk_id": index,
            "chapter_index": index,
            "source_span": {"start": start, "end": end},
            "hash": _sha256_text(raw),
            "char_count": len(raw),
        })
    return {
        "import_run_id": import_run_id,
        "source_file_path": state.get("source_file_path", ""),
        "source_hash": source_hash,
        "import_mode": state.get("import_mode", "import_all"),
        "prompt_profile": prompt_profile,
        "model": model,
        "created_at": _now_iso(),
        "segment_count": len(segments),
        "artifact_dir": str(_artifact_dir(state["project_path"], import_run_id)),
        "segments": segments,
    }


def _build_evidence_cards(state: ImportState) -> list[dict]:
    """Convert chunk extraction output into raw evidence cards.

    Evidence cards are intentionally non-canonical. Reducers can merge, reject,
    or promote them without losing source provenance.
    """
    manifest = state.get("import_run_manifest", {})
    segments = {segment.get("chunk_id"): segment for segment in manifest.get("segments", [])}
    cards: list[dict] = []
    for extraction in state.get("chunk_extractions", []):
        chunk_id = extraction.get("chunk_id", 0)
        segment = segments.get(chunk_id, {})
        segment_id = segment.get("id", f"chunk_{chunk_id}")
        source_span = segment.get("source_span", {})

        for character in extraction.get("new_characters", []):
            name = character.get("canonical_name") or character.get("name") or ""
            cards.append({
                "id": _stable_id("evc", manifest.get("import_run_id", "import"), chunk_id, "character", name),
                "kind": "character",
                "source_chunk_id": chunk_id,
                "source_segment_id": segment_id,
                "source_span": source_span,
                "summary": character.get("summary", ""),
                "candidate_names": [name, *character.get("aliases", [])],
                "candidate_ids": [character.get("canonical_id") or character.get("id", "")],
                "confidence": float(character.get("confidence", 0.7)),
                "uncertainty": "",
                "raw": character,
            })

        for event in extraction.get("events", []):
            cards.append({
                "id": _stable_id("evc", manifest.get("import_run_id", "import"), chunk_id, "event", event.get("title", ""), event.get("description", "")),
                "kind": "event",
                "source_chunk_id": chunk_id,
                "source_segment_id": segment_id,
                "source_span": source_span,
                "summary": event.get("description", ""),
                "candidate_names": [event.get("title", "")],
                "candidate_ids": [event.get("event_id", "")],
                "temporal_hint": event.get("temporal_hint") or "",
                "location_hint": event.get("location_hint") or "",
                "confidence": float(event.get("confidence", 0.7)),
                "uncertainty": "timeline placement is pending Timeline Architect",
                "raw": event,
            })

        for world in extraction.get("world_mentions_detailed", []):
            cards.append({
                "id": _stable_id("evc", manifest.get("import_run_id", "import"), chunk_id, "world", world.get("name", "")),
                "kind": "world",
                "source_chunk_id": chunk_id,
                "source_segment_id": segment_id,
                "source_span": source_span,
                "summary": world.get("description", ""),
                "candidate_names": [world.get("name", "")],
                "candidate_ids": [],
                "confidence": float(world.get("confidence", 0.7)),
                "uncertainty": "",
                "raw": world,
            })

        for relationship in extraction.get("raw_relationships", []):
            cards.append({
                "id": _stable_id("evc", manifest.get("import_run_id", "import"), chunk_id, "relationship", relationship.get("source_character_name", ""), relationship.get("target_character_name", ""), relationship.get("type", "")),
                "kind": "relationship",
                "source_chunk_id": chunk_id,
                "source_segment_id": segment_id,
                "source_span": source_span,
                "summary": relationship.get("description", ""),
                "candidate_names": [relationship.get("source_character_name", ""), relationship.get("target_character_name", "")],
                "candidate_ids": [relationship.get("source_candidate_id") or "", relationship.get("target_candidate_id") or ""],
                "confidence": float(relationship.get("confidence", 0.7)),
                "uncertainty": "",
                "raw": relationship,
            })

        for scene in extraction.get("scenes", []):
            cards.append({
                "id": _stable_id("evc", manifest.get("import_run_id", "import"), chunk_id, "scene", scene.get("title", "")),
                "kind": "scene",
                "source_chunk_id": chunk_id,
                "source_segment_id": segment_id,
                "source_span": source_span,
                "summary": scene.get("summary", ""),
                "candidate_names": [scene.get("title", ""), *scene.get("character_names", [])],
                "candidate_ids": scene.get("character_ids", []),
                "temporal_hint": scene.get("time_hint", ""),
                "location_hint": scene.get("location_hint", ""),
                "confidence": float(scene.get("confidence", 0.7)),
                "uncertainty": "",
                "raw": scene,
            })
    return cards


# ── LLM helper ──────────────────────────────────────────────────────────────────

# Semaphore to cap the number of concurrent DeepSeek API calls.
# DeepSeek's "governor" rate-limits sustained high concurrency; 3 concurrent
# calls per chunk * N chunks in flight keeps us well under the threshold.
_API_SEMAPHORE = asyncio.Semaphore(3)

_ENDPOINT_CORRECTIONS: dict[str, str] = {
    # Web console URL → actual API URL
    "https://platform.deepseek.com": "https://api.deepseek.com/v1",
    "https://platform.deepseek.com/": "https://api.deepseek.com/v1",
    "https://api.deepseek.com": "https://api.deepseek.com/v1",
    "https://api.deepseek.com/": "https://api.deepseek.com/v1",
}


def _get_llm(state: ImportState) -> ChatOpenAI:
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    raw_endpoint = ctx.get("endpoint", "https://api.deepseek.com/v1") or "https://api.deepseek.com/v1"
    # Correct common endpoint mistakes (e.g. web console URL instead of API URL)
    base_url = _ENDPOINT_CORRECTIONS.get(raw_endpoint.rstrip("/"),
               _ENDPOINT_CORRECTIONS.get(raw_endpoint, raw_endpoint))
    # streaming=False: prevents the 'str' object has no attribute 'model_dump'
    # error that occurs when DeepSeek's governor injects an error into an SSE
    # stream and LangChain tries to parse it as a ChatCompletionChunk.
    # timeout=120: prevent hung requests when DeepSeek accepts the TCP connection
    # but stops sending data mid-response (seen as ESTABLISHED socket with no progress).
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url,
                      max_tokens=4096, streaming=False, timeout=120)


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

    # Validate API key is present before starting the (potentially hours-long) run
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"status": "error", "errors": [
            "No API key configured. Open Settings → AI Providers, add your provider key, "
            "and set it as Active before importing."
        ]}

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

    # Try multiple encodings with charset detection as fallback
    _ENCODING_TRIES = ["utf-8", "gb18030", "gbk", "big5", "shift_jis"]
    text = None
    last_err = None
    for enc in _ENCODING_TRIES:
        try:
            with open(source_path, "r", encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_err = exc
            continue

    if text is None:
        # Last resort: use charset-normalizer for auto-detection
        try:
            from charset_normalizer import from_bytes
            with open(source_path, "rb") as f:
                raw = f.read()
            result = from_bytes(raw).best()
            if result:
                text = str(result)
            else:
                # Absolute last resort: UTF-8 with replacement
                text = raw.decode("utf-8", errors="replace")
        except Exception as e:
            return {"status": "error", "errors": [f"Cannot read file with any encoding: {last_err} / {e}"]}

    # Try chapter strategy first
    config = s3_chunk_manager.ChunkConfig(strategy="chapter", chunk_size=500_000, overlap=50_000)
    chunks = s3_chunk_manager.chunk_text(text, config)

    # Fallback to paragraph if no chapter headings detected and text is large
    if len(chunks) == 1 and len(text) > 500_000:
        config = s3_chunk_manager.ChunkConfig(strategy="paragraph", chunk_size=500_000, overlap=50_000)
        chunks = s3_chunk_manager.chunk_text(text, config)

    # Ensure chunk_id and manuscript_content on each chunk.
    # Use raw_content (no overlap prefix) so manuscript reflects actual chapter boundaries.
    for i, chunk in enumerate(chunks):
        chunk["manuscript_content"] = chunk.get("raw_content", chunk.get("content", ""))
        chunk["chunk_id"] = i

    manifest = _build_import_manifest(state, text, chunks)
    digest = _build_project_structure_digest({**state, "import_run_id": manifest["import_run_id"]}, manifest["import_run_id"])
    prompt_windows = _build_prompt_windows(
        {**state, "import_run_id": manifest["import_run_id"], "import_run_manifest": manifest},
        chunks,
        digest,
    )
    _write_import_artifact(
        state["project_path"],
        manifest["import_run_id"],
        "project_structure_digest.json",
        {key: value for key, value in digest.items() if key != "content"} | {"content": digest.get("content", "")},
    )
    _write_import_artifact(
        state["project_path"],
        manifest["import_run_id"],
        "prompt_windows.json",
        [_prompt_window_manifest_entry(window) | {"text_hash": _sha256_text(window.get("text", ""))} for window in prompt_windows],
    )
    manifest["project_structure_digest"] = {
        "artifact_path": digest["artifact_path"],
        "estimated_tokens": digest["estimated_tokens"],
        "counts": digest.get("counts", {}),
    }
    manifest["prompt_window_budget"] = {
        "total_estimated_tokens": _prompt_total_token_budget(manifest["prompt_profile"]),
        "schema_policy_reserve_tokens": _SCHEMA_POLICY_RESERVE_TOKENS,
        "digest_reserve_tokens": _DIGEST_RESERVE_TOKENS,
        "validation_reserve_tokens": _VALIDATION_RESERVE_TOKENS,
    }
    manifest["prompt_windows"] = [_prompt_window_manifest_entry(window) for window in prompt_windows]
    manifest["artifact_paths"] = {
        "project_structure_digest": str(_artifact_dir(state["project_path"], manifest["import_run_id"]) / "project_structure_digest.json"),
        "prompt_windows": str(_artifact_dir(state["project_path"], manifest["import_run_id"]) / "prompt_windows.json"),
    }
    _write_import_artifact(state["project_path"], manifest["import_run_id"], "manifest.json", manifest)

    return {
        "chunks": chunks,
        "import_run_id": manifest["import_run_id"],
        "prompt_profile": manifest["prompt_profile"],
        "import_run_manifest": manifest,
        "project_structure_digest": digest,
        "prompt_windows": prompt_windows,
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

    return {
        "entity_registry": registry,
        "raw_relationships": state.get("raw_relationships", []),  # preserve for node_synthesize_relationships
        "progress": 0.82,
    }


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
                c.get("manuscript_content", c.get("raw_content", c.get("content", ""))) for c in chapter_chunks
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


async def node_build_evidence_cards(state: ImportState) -> dict:
    """Persist raw, non-canonical evidence cards for reducer/reviewer stages."""
    import_run_id = state.get("import_run_id") or state.get("import_run_manifest", {}).get("import_run_id")
    if not import_run_id:
        return {"evidence_cards": [], "progress": state.get("progress", 0.8)}
    cards = _build_evidence_cards(state)
    _write_import_artifact(state["project_path"], import_run_id, "evidence_cards.json", cards)
    return {"evidence_cards": cards, "progress": max(float(state.get("progress", 0.8)), 0.82)}


async def node_reconcile_entities(state: ImportState) -> dict:
    """Align imported candidates with existing project data before proposals."""
    project_path = state["project_path"]
    snapshot = _load_existing_project_snapshot(project_path)
    registry = dict(state.get("entity_registry", {}))
    registry.setdefault("characters", {})
    relationships = list(state.get("relationships", []))
    character_tags = list(state.get("character_tags", []))
    duplicate_candidates: list[dict] = []
    skipped_existing: list[dict] = []
    dependency_edges: list[dict] = []
    character_id_map: dict[str, str] = {}
    tag_id_map: dict[str, str] = {}

    existing_character_keys: dict[str, dict] = {}
    for character in snapshot.get("characters", []):
        for name in [character.get("name", ""), *character.get("aliases", [])]:
            key = _normal_key(name)
            if key:
                existing_character_keys[key] = character

    for cid, entry in registry.get("characters", {}).items():
        names = [entry.get("canonical_name", ""), *entry.get("aliases", [])]
        match = next((existing_character_keys.get(_normal_key(name)) for name in names if _normal_key(name) in existing_character_keys), None)
        if match and match.get("id"):
            entry["existing_project_id"] = match["id"]
            entry["skip_create"] = True
            character_id_map[cid] = match["id"]
            skipped_existing.append({
                "entity_type": "character",
                "import_id": cid,
                "existing_id": match["id"],
                "name": entry.get("canonical_name", ""),
                "reason": "matched existing character name or alias",
            })

    existing_tag_keys: dict[str, dict] = {}
    for tag in snapshot.get("character_tags", []):
        key = _normal_key(tag.get("name", ""))
        if key:
            existing_tag_keys[key] = tag

    reconciled_tags: list[dict] = []
    seen_new_tag_keys: set[str] = set()
    for tag in character_tags:
        key = _normal_key(tag.get("name", ""))
        if not key:
            continue
        existing = existing_tag_keys.get(key)
        if existing and existing.get("id"):
            tag_id_map[tag.get("id", "")] = existing["id"]
            skipped_existing.append({
                "entity_type": "character_tag",
                "import_id": tag.get("id", ""),
                "existing_id": existing["id"],
                "name": tag.get("name", ""),
                "reason": "matched existing tag name",
            })
            continue
        if key in seen_new_tag_keys:
            duplicate_candidates.append({"entity_type": "character_tag", "name": tag.get("name", ""), "reason": "duplicate imported tag name"})
            continue
        seen_new_tag_keys.add(key)
        reconciled_tags.append(tag)

    for cid, entry in registry.get("characters", {}).items():
        mapped_tags: list[str] = []
        for tag_id in entry.get("tag_ids", []):
            mapped = tag_id_map.get(tag_id, tag_id)
            if mapped:
                mapped_tags.append(mapped)
            if tag_id not in tag_id_map:
                dependency_edges.append({"from": cid, "to": tag_id, "type": "character_uses_tag"})
        entry["tag_ids"] = mapped_tags

    existing_relationship_keys: set[tuple[str, str, str]] = set()
    for rel in snapshot.get("relationships", []):
        left = str(rel.get("sourceId") or rel.get("source_id") or "")
        right = str(rel.get("targetId") or rel.get("target_id") or "")
        label = _normal_key(rel.get("type", "") or rel.get("category", ""))
        if left and right:
            existing_relationship_keys.add((left, right, label))
            existing_relationship_keys.add((right, left, label))

    reconciled_relationships: list[dict] = []
    seen_relationship_keys: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        source = character_id_map.get(relationship.get("sourceId", ""), relationship.get("sourceId", ""))
        target = character_id_map.get(relationship.get("targetId", ""), relationship.get("targetId", ""))
        relationship = {**relationship, "sourceId": source, "targetId": target}
        key = (source, target, _normal_key(relationship.get("type", "") or relationship.get("category", "")))
        if key in existing_relationship_keys:
            skipped_existing.append({
                "entity_type": "relationship",
                "sourceId": source,
                "targetId": target,
                "type": relationship.get("type", ""),
                "reason": "matched existing relationship pair",
            })
            continue
        if key in seen_relationship_keys:
            duplicate_candidates.append({"entity_type": "relationship", "sourceId": source, "targetId": target, "reason": "duplicate imported relationship"})
            continue
        seen_relationship_keys.add(key)
        reconciled_relationships.append(relationship)

    registry["character_id_map"] = character_id_map
    registry["tag_id_map"] = tag_id_map
    artifact = {
        "import_run_id": state.get("import_run_id", ""),
        "existing_matches": {"characters": character_id_map, "character_tags": tag_id_map},
        "duplicate_candidates": duplicate_candidates,
        "dependency_edges": dependency_edges,
        "skipped_existing": skipped_existing,
        "warnings": [],
    }
    if state.get("import_run_id"):
        _write_import_artifact(project_path, state["import_run_id"], "reducer_artifact.json", artifact)
    return {
        "entity_registry": registry,
        "relationships": reconciled_relationships,
        "character_tags": reconciled_tags,
        "reducer_artifact": artifact,
        "progress": max(float(state.get("progress", 0.84)), 0.86),
    }


def _event_signature(event: dict) -> str:
    parts = [
        _normal_key(event.get("title", "")),
        _normal_key(event.get("description", ""))[:80],
        _normal_key(event.get("temporal_hint", "")),
        _normal_key(event.get("location_hint", "")),
        ",".join(sorted(event.get("character_ids", []))),
    ]
    return "|".join(parts)


def _event_sequence_key(event: dict) -> tuple[int, int, str]:
    position_rank = {"early": 0, "middle": 1, "late": 2}
    return (
        int(event.get("chunk_id", 0) or 0),
        position_rank.get(str(event.get("chunk_position", "")).lower(), 1),
        _normal_key(event.get("title", "")),
    )


def _timeline_theme_key(event: dict) -> tuple[str, str, str]:
    text = " ".join([
        str(event.get("title", "")),
        str(event.get("description", "")),
        str(event.get("stakes", "")),
        str(event.get("temporal_hint", "")),
    ]).lower()
    if any(token in text for token in ("flashback", "memory", "remembered", "past", "before", "ago", "回忆", "曾经", "当年", "过去")):
        return ("theme", "background", "Backstory / Memory Lane")
    if any(token in text for token in ("betray", "enemy", "antagonist", "ambush", "murder", "death", "背叛", "敌", "伏击", "杀", "死")):
        return ("theme", "conflict", "Conflict Escalation")
    if any(token in text for token in ("sect", "court", "clan", "faction", "alliance", "宗门", "朝廷", "家族", "联盟", "势力")):
        return ("theme", "faction", "Faction / Power Line")
    return ("theme", "main", "Main Plot")


def _safe_branch_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", "_", value.strip()).strip("_").lower()
    return slug[:36] or uuid.uuid4().hex[:8]


def _timeline_branch_color(index: int) -> str:
    colors = ["#38bdf8", "#f97316", "#22c55e", "#a855f7", "#eab308", "#ec4899", "#14b8a6"]
    return colors[index % len(colors)]


async def node_architect_timeline(state: ImportState) -> dict:
    """Deduplicate and place timeline candidates into branch-aware event data."""
    project_path = state["project_path"]
    snapshot = _load_existing_project_snapshot(project_path)
    registry = dict(state.get("entity_registry", {}))
    events = registry.get("events", {})
    character_id_map = registry.get("character_id_map", {})
    discarded_duplicates: list[dict] = []
    warnings: list[str] = []

    existing_branches = snapshot.get("timeline_branches", [])
    root_branch = next((branch for branch in existing_branches if branch.get("mode") == "root"), None) or (existing_branches[0] if existing_branches else None)
    root_branch_id = root_branch.get("id") if root_branch else "branch_import_main"
    imported_branches = [branch for branch in state.get("timeline_branches", []) if branch.get("id")]
    root_geometry = (root_branch or {}).get("geometry") or {}
    timeline_branches: list[dict] = [{
        **(root_branch or {}),
        "id": root_branch_id,
        "name": (root_branch or {}).get("name", "Imported Main Timeline"),
        "description": (root_branch or {}).get("description", "Primary imported narrative timeline."),
        "parentBranchId": (root_branch or {}).get("parentBranchId"),
        "forkEventId": (root_branch or {}).get("forkEventId"),
        "mergeEventId": (root_branch or {}).get("mergeEventId"),
        "color": (root_branch or {}).get("color", "#38bdf8"),
        "sortOrder": 0,
        "mode": "root",
        "startAnchor": (root_branch or {}).get("startAnchor"),
        "endAnchor": (root_branch or {}).get("endAnchor"),
        "endMode": (root_branch or {}).get("endMode", "open"),
        "mergeTargetBranchId": (root_branch or {}).get("mergeTargetBranchId"),
        "geometry": {**root_geometry, "laneOffset": 0, "bend": root_geometry.get("bend", 0.25), "thickness": 2},
        "layoutHint": {"eventBudget": 24, "clusterOverflow": True},
    }]

    existing_event_keys = {
        (_normal_key(event.get("title", "")), _normal_key(event.get("summary", ""))[:80])
        for event in snapshot.get("timeline_events", [])
    }
    seen_signatures: dict[str, str] = {}
    canonical_events: dict[str, dict] = {}
    chunk_event_counts: dict[int, int] = {}
    density_limit_per_chunk = 3
    branch_event_budget = 24
    prelim_events: dict[str, dict] = {}

    for event_id, event in events.items():
        title = event.get("title", "").strip()
        if not title:
            discarded_duplicates.append({"event_id": event_id, "timelineClass": "discarded_duplicate", "reason": "missing title"})
            continue
        existing_key = (_normal_key(title), _normal_key(event.get("description", ""))[:80])
        if existing_key in existing_event_keys:
            discarded_duplicates.append({"event_id": event_id, "title": title, "timelineClass": "discarded_duplicate", "reason": "matches existing timeline event"})
            continue
        chunk_id = int(event.get("chunk_id", 0) or 0)
        chunk_event_counts[chunk_id] = chunk_event_counts.get(chunk_id, 0) + 1
        if chunk_event_counts[chunk_id] > density_limit_per_chunk and float(event.get("confidence", 0.7)) < 0.9:
            discarded_duplicates.append({"event_id": event_id, "title": title, "timelineClass": "scene_beat", "reason": "demoted by density policy"})
            continue
        signature = _event_signature(event)
        if signature in seen_signatures:
            primary_id = seen_signatures[signature]
            primary = prelim_events[primary_id]
            primary.setdefault("mergedEventIds", []).append(event_id)
            primary["summary"] = _merge_text_field(primary.get("summary", ""), event.get("description", ""))
            discarded_duplicates.append({"event_id": event_id, "merged_into": primary_id, "title": title, "timelineClass": "discarded_duplicate", "reason": "duplicate event signature"})
            continue
        seen_signatures[signature] = event_id
        participant_ids = [character_id_map.get(cid, cid) for cid in event.get("character_ids", [])]
        prelim_events[event_id] = {
            **event,
            "event_id": event_id,
            "summary": event.get("description", ""),
            "locationIds": [],
            "participantCharacterIds": [cid for cid in participant_ids if cid],
            "linkedSceneIds": [],
            "linkedWorldItemIds": [],
            "tags": ["imported"],
            "sharedBranchIds": [],
            "importance": "major" if float(event.get("confidence", 0.7)) >= 0.86 else "minor",
            "timelineClass": "canonical_event",
            "mergedEventIds": [],
            "_sequence": _event_sequence_key(event),
        }

    location_counts: dict[str, int] = {}
    participant_counts: dict[str, int] = {}
    theme_counts: dict[str, int] = {}
    for event in prelim_events.values():
        location_key = _normal_key(event.get("location_hint", ""))
        if location_key:
            location_counts[location_key] = location_counts.get(location_key, 0) + 1
        for participant_id in event.get("participantCharacterIds", [])[:2]:
            participant_counts[participant_id] = participant_counts.get(participant_id, 0) + 1
        _, theme_key, _ = _timeline_theme_key(event)
        theme_counts[theme_key] = theme_counts.get(theme_key, 0) + 1

    total_events = len(prelim_events)
    branch_threshold = 2 if total_events >= 10 else 3
    branch_defs: dict[str, dict] = {root_branch_id: timeline_branches[0]}

    def _ensure_branch(branch_id: str, name: str, reason: str) -> None:
        if branch_id in branch_defs or len(branch_defs) >= 7:
            return
        idx = len(branch_defs)
        branch = {
            "id": branch_id,
            "name": name,
            "description": f"Imported timeline lane inferred from {reason}.",
            "parentBranchId": root_branch_id,
            "forkEventId": None,
            "mergeEventId": None,
            "color": _timeline_branch_color(idx),
            "sortOrder": idx,
            "mode": "forked",
            "startAnchor": None,
            "endAnchor": None,
            "endMode": "open",
            "mergeTargetBranchId": root_branch_id,
            "geometry": {"laneOffset": idx * 140, "bend": 0.18 + (idx % 3) * 0.08, "thickness": 2},
            "layoutHint": {"eventBudget": branch_event_budget, "clusterOverflow": True},
        }
        branch_defs[branch_id] = branch
        timeline_branches.append(branch)

    for branch in imported_branches:
        branch_id = branch.get("id")
        if branch_id and branch_id not in branch_defs and len(branch_defs) < 7:
            idx = len(branch_defs)
            branch_defs[branch_id] = {
                **branch,
                "parentBranchId": branch.get("parentBranchId") or root_branch_id,
                "sortOrder": branch.get("sortOrder", idx),
                "mode": branch.get("mode", "forked"),
                "geometry": {**branch.get("geometry", {}), "laneOffset": branch.get("geometry", {}).get("laneOffset", idx * 140)},
                "layoutHint": {**branch.get("layoutHint", {}), "eventBudget": branch_event_budget, "clusterOverflow": True},
            }
            timeline_branches.append(branch_defs[branch_id])

    for theme_key, count in theme_counts.items():
        if theme_key != "main" and count >= branch_threshold:
            _ensure_branch(f"branch_import_{theme_key}", _timeline_theme_key({"title": theme_key})[2] if theme_key == "main" else theme_key.replace("_", " ").title(), f"{count} {theme_key} events")

    for location_key, count in sorted(location_counts.items(), key=lambda item: item[1], reverse=True)[:3]:
        if count >= branch_threshold:
            _ensure_branch(f"branch_loc_{_safe_branch_slug(location_key)}", f"Location: {location_key}", f"{count} events at this location")

    for participant_id, count in sorted(participant_counts.items(), key=lambda item: item[1], reverse=True)[:2]:
        if count >= max(branch_threshold + 1, 3):
            _ensure_branch(f"branch_char_{_safe_branch_slug(participant_id)}", f"Character Arc: {participant_id}", f"{count} events for one participant")

    def _select_branch(event: dict) -> str:
        _, theme_key, _ = _timeline_theme_key(event)
        theme_branch_id = f"branch_import_{theme_key}"
        if theme_branch_id in branch_defs and theme_key != "main":
            return theme_branch_id
        location_key = _normal_key(event.get("location_hint", ""))
        location_branch_id = f"branch_loc_{_safe_branch_slug(location_key)}" if location_key else ""
        if location_branch_id in branch_defs:
            return location_branch_id
        for participant_id in event.get("participantCharacterIds", [])[:2]:
            participant_branch_id = f"branch_char_{_safe_branch_slug(participant_id)}"
            if participant_branch_id in branch_defs:
                return participant_branch_id
        return root_branch_id

    branch_buckets: dict[str, list[tuple[str, dict]]] = {}
    for event_id, event in prelim_events.items():
        branch_id = _select_branch(event)
        branch_buckets.setdefault(branch_id, []).append((event_id, event))

    global_order_index = len(snapshot.get("timeline_events", []))
    for branch_id, branch_events in branch_buckets.items():
        branch_events.sort(key=lambda item: item[1].get("_sequence", (0, 0, "")))
        if len(branch_events) > branch_event_budget:
            warnings.append(f"Branch {branch_id} has {len(branch_events)} canonical events; lower-importance events were converted to scene beats.")
        visible_index = 0
        for event_id, event in branch_events:
            if visible_index >= branch_event_budget and event.get("importance") != "major":
                discarded_duplicates.append({"event_id": event_id, "title": event.get("title", ""), "timelineClass": "scene_beat", "reason": "branch event budget overflow"})
                continue
            cleaned = {k: v for k, v in event.items() if not k.startswith("_")}
            cleaned["branchId"] = branch_id
            cleaned["orderIndex"] = visible_index
            cleaned["globalOrderIndex"] = global_order_index
            cleaned["sharedBranchIds"] = [root_branch_id] if branch_id != root_branch_id else []
            cleaned["layoutHints"] = {"density": len(branch_events), "branchEventBudget": branch_event_budget}
            canonical_events[event_id] = cleaned
            visible_index += 1
            global_order_index += 1

    registry["events"] = canonical_events
    artifact = {
        "import_run_id": state.get("import_run_id", ""),
        "root_branch_id": root_branch_id,
        "branches": timeline_branches,
        "canonical_events": list(canonical_events.values()),
        "discarded_duplicates": discarded_duplicates,
        "density_policy": {
            "max_events_per_chunk": density_limit_per_chunk,
            "max_events_per_branch": branch_event_budget,
            "branch_threshold": branch_threshold,
            "low_confidence_threshold": 0.9,
        },
        "layout_hints": {
            "strategy": "semantic_branch_topology",
            "max_branch_count": 7,
            "branch_lane_spacing": 140,
        },
        "warnings": warnings,
    }
    if state.get("import_run_id"):
        _write_import_artifact(project_path, state["import_run_id"], "timeline_architecture.json", artifact)
    return {
        "entity_registry": registry,
        "timeline_branches": timeline_branches,
        "timeline_architecture": artifact,
        "progress": max(float(state.get("progress", 0.88)), 0.9),
    }


async def node_review_import(state: ImportState) -> dict:
    """Validate compiler outputs before proposal writes."""
    registry = state.get("entity_registry", {})
    reducer = state.get("reducer_artifact", {})
    timeline = state.get("timeline_architecture", {})
    warnings: list[str] = list(reducer.get("warnings", [])) + list(timeline.get("warnings", []))
    errors: list[str] = list(state.get("errors", []))
    low_confidence_items: list[dict] = []

    for cid, character in registry.get("characters", {}).items():
        if character.get("skip_create"):
            continue
        if float(character.get("confidence", 0.7)) < 0.65:
            low_confidence_items.append({"entity_type": "character", "id": cid, "confidence": character.get("confidence", 0.7)})

    required_event_fields = ["branchId", "orderIndex", "locationIds", "participantCharacterIds", "linkedSceneIds", "linkedWorldItemIds", "tags"]
    for eid, event in registry.get("events", {}).items():
        missing = [field for field in required_event_fields if field not in event]
        if missing:
            errors.append(f"Timeline event {eid} missing required fields: {', '.join(missing)}")
        if float(event.get("confidence", 0.7)) < 0.65:
            low_confidence_items.append({"entity_type": "timeline_event", "id": eid, "confidence": event.get("confidence", 0.7)})

    report = {
        "import_run_id": state.get("import_run_id", ""),
        "status": "fail" if errors else "warning" if warnings or low_confidence_items else "pass",
        "warnings": warnings,
        "errors": errors,
        "proposal_counts": {
            "characters": len([c for c in registry.get("characters", {}).values() if not c.get("skip_create")]),
            "timeline_events": len(registry.get("events", {})),
            "relationships": len(state.get("relationships", [])),
            "character_tags": len(state.get("character_tags", [])),
            "timeline_branches": len(state.get("timeline_branches", [])),
        },
        "safe_accept_ids": [],
        "blocked_ids": [],
        "failed_chunks": [
            {"chunk_id": entry.get("chunk_id"), "errors": entry.get("errors", [])}
            for entry in _chunk_log.get(state.get("project_path", ""), [])
            if entry.get("errors")
        ],
        "model": state.get("context", {}).get("model", "deepseek-chat"),
        "prompt_profile": state.get("prompt_profile", "balanced"),
        "artifact_paths": {
            "manifest": str(_artifact_dir(state["project_path"], state.get("import_run_id", "")) / "manifest.json") if state.get("import_run_id") else "",
            "reducer": str(_artifact_dir(state["project_path"], state.get("import_run_id", "")) / "reducer_artifact.json") if state.get("import_run_id") else "",
            "timeline": str(_artifact_dir(state["project_path"], state.get("import_run_id", "")) / "timeline_architecture.json") if state.get("import_run_id") else "",
            "review": str(_artifact_dir(state["project_path"], state.get("import_run_id", "")) / "review_report.json") if state.get("import_run_id") else "",
        },
        "duplicate_merges": timeline.get("discarded_duplicates", []) + reducer.get("duplicate_candidates", []),
        "low_confidence_items": low_confidence_items,
    }
    if state.get("import_run_id"):
        _write_import_artifact(state["project_path"], state["import_run_id"], "review_report.json", report)
    return {"import_review_report": report, "errors": errors, "progress": max(float(state.get("progress", 0.91)), 0.92)}


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
    character_id_map = registry.get("character_id_map", {})

    # Write character proposals
    for cid, entry in registry.get("characters", {}).items():
        if entry.get("skip_create"):
            continue
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
                "goals": [],
                "fears": [],
                "secrets": [],
                "speechStyle": "",
                "arc": "",
                "tagIds": entry.get("tag_ids", []),
                "linkedEventIds": character_event_links.get(cid, []),
                "roleInStory": entry.get("role_in_story", ""),
                "physicalDescription": entry.get("physical_description", ""),
                "notes": [
                    *entry.get("notes", [])[:4],
                    *[f"Open question: {question}" for question in entry.get("open_questions", [])[:2]],
                ],
                "importConfidence": entry.get("confidence", 0.7),
                "importImportance": entry.get("importance", ""),
                "importCardType": "draft",
                "enrichmentRecommended": bool(entry.get("open_questions")),
                "importance": entry.get("importance", "supporting") or "supporting",
                "groupKey": entry.get("groupKey", IMPORTANCE_TO_GROUP.get(entry.get("importance", ""), "")) or "",
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": entry.get("tag_ids", []),
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose character {cid}: {str(e)}")

    # Determine default branch for event assignment, creating one when the
    # compiler did not infer any timeline branches.
    default_branch_id = next(
        (b["id"] for b in timeline_branches if b.get("mode") == "root"),
        None,
    ) or next((b["id"] for b in timeline_branches), None)

    if not default_branch_id:
        default_branch_id = f"branch_{uuid.uuid4().hex[:8]}"
        timeline_branches = [{
            "id": default_branch_id,
            "name": "Main Timeline",
            "description": "Primary narrative timeline",
            "mode": "root",
            "color": "#38bdf8",
            "sortOrder": 0,
            "isDefault": True,
        }]

    # Write timeline branch proposals before events so imported events can
    # depend on branch proposals in the Workbench review queue.
    for branch in timeline_branches:
        branch_id = branch.get("id") or default_branch_id or f"branch_{uuid.uuid4().hex[:8]}"
        if branch.get("mode") == "root":
            default_branch_id = branch_id
        op = {
            "op_type": "create",
            "entity_type": "timeline_branch",
            "entity_id": branch_id,
            "data": {**branch, "id": branch_id, "isDefault": bool(branch.get("isDefault", branch.get("mode") == "root"))},
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

    # Deduplicate events by title before writing proposals.
    def _is_duplicate_event(title: str, seen_titles: list[str]) -> bool:
        norm = re.sub(r'\s+', '', title).lower()
        for s in seen_titles:
            if difflib.SequenceMatcher(None, norm, s).ratio() > 0.80:
                return True
        return False

    seen_event_title_norms: list[str] = []
    deduped_events: dict[str, dict] = {}
    for eid, entry in registry.get("events", {}).items():
        title = entry.get("title", "")
        title_key = re.sub(r'\s+', '', title).lower()
        if not title_key:
            continue
        if title_key in seen_event_title_norms or _is_duplicate_event(title_key, seen_event_title_norms):
            continue
        seen_event_title_norms.append(title_key)
        deduped_events[eid] = entry

    # Sort by temporal_hint for stable orderIndex assignment
    sorted_events = sorted(
        deduped_events.items(),
        key=lambda kv: kv[1].get("temporal_hint", "") or "",
    )

    # Write event proposals
    for order_idx, (eid, entry) in enumerate(sorted_events):
        op = {
            "op_type": "create",
            "entity_type": "timeline_event",
            "entity_id": eid,
            "data": {
                "id": eid,
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "branchId": entry.get("branchId") or default_branch_id,
                "orderIndex": order_idx,
                "locationIds": entry.get("locationIds", []),
                "participantCharacterIds": entry.get("participantCharacterIds")
                    or [character_id_map.get(cid, cid) for cid in entry.get("character_ids", [])],
                "linkedSceneIds": entry.get("linkedSceneIds", []),
                "linkedWorldItemIds": entry.get("linkedWorldItemIds", []),
                "tags": entry.get("tags", ["imported"]),
                "time": entry.get("temporal_hint", ""),
                "sharedBranchIds": entry.get("sharedBranchIds", []),
                "importance": entry.get("importance", "minor"),
                "importConfidence": entry.get("confidence", 0.7),
                "importRunId": state.get("import_run_id", ""),
                "mergedEventIds": entry.get("mergedEventIds", []),
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [entry.get("branchId") or default_branch_id],
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
            "depends_on": [relationship.get("sourceId", ""), relationship.get("targetId", "")],
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

    # ── Scene proposals ───────────────────────────────────────────────────────
    # Scenes are extracted per-chunk by W1_EXTRACT_SCENE_SUMMARIES.
    # Deduplicate by title to avoid creating the same scene multiple times
    # (scenes may appear in multiple chunk extractions with overlap).
    seen_scene_titles: set[str] = set()
    for extraction in state.get("chunk_extractions", []):
        for scene in extraction.get("scenes", []):
            title = scene.get("title", "").strip()
            if not title or title in seen_scene_titles:
                continue
            seen_scene_titles.add(title)
            scene_id = f"scene_{uuid.uuid4().hex[:8]}"
            op = {
                "op_type": "create",
                "entity_type": "scene",
                "entity_id": scene_id,
                "data": {
                    "id": scene_id,
                    "title": title,
                    "summary": scene.get("summary", ""),
                    "povCharacterId": None,
                    "linkedCharacterIds": [],
                    "linkedEventIds": [],
                    "linkedWorldItemIds": [],
                    "status": "draft",
                    "notes": "",
                    "chapterId": None,
                    "location": scene.get("location_hint", ""),
                },
                "source_workflow": "W1_import",
                "confidence": float(scene.get("confidence", 0.70)),
                "auto_apply": False,
                "depends_on": [],
            }
            try:
                proposal = await s2_memory_writer.propose_write(op, str(project_path))
                proposals.append(proposal)
            except Exception as e:
                errors.append(f"Failed to propose scene '{title}': {str(e)}")

    # ── Chapter proposals ─────────────────────────────────────────────────────
    # manuscript_chapters are assembled by node_build_manuscript from chapter_hint grouping.
    # Each one becomes a Chapter entity proposal for user review.
    for mc in state.get("manuscript_chapters", []):
        chap_id = mc.get("chapter_id") or f"chap_{uuid.uuid4().hex[:8]}"
        title = mc.get("title", "Untitled Chapter").strip()
        if not title:
            continue
        op = {
            "op_type": "create",
            "entity_type": "chapter",
            "entity_id": chap_id,
            "data": {
                "id": chap_id,
                "title": title,
                "summary": "",
                "goal": "",
                "notes": f"Imported from: {state.get('source_file_path', '')}",
                "sceneIds": [],
                "status": "draft",
            },
            "source_workflow": "W1_import",
            "confidence": 0.90,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            proposals.append(proposal)
        except Exception as e:
            errors.append(f"Failed to propose chapter '{title}': {str(e)}")

    proposal_counts: dict[str, int] = {}
    for proposal in proposals:
        ops = proposal.get("operations", [])
        entity_type = ops[0].get("entityType", "unknown") if ops else "unknown"
        proposal_counts[entity_type] = proposal_counts.get(entity_type, 0) + 1

    review_report = dict(state.get("import_review_report", {}))
    if review_report:
        review_report["proposal_counts"] = proposal_counts
        all_proposal_ids = [proposal.get("id", "") for proposal in proposals if proposal.get("id")]
        blocked_ids = [
            proposal.get("id", "")
            for proposal in proposals
            if proposal.get("status") == "blocked" or proposal.get("blockedReason") or proposal.get("requiresManualReview")
        ]
        safe_types = {"character_tag", "timeline_branch", "chapter", "scene"}
        safe_accept_ids: list[str] = []
        for proposal in proposals:
            ops = proposal.get("operations", [])
            entity_type = ops[0].get("entityType", "unknown") if ops else "unknown"
            confidence = float(proposal.get("confidence", 0.0) or 0.0)
            if proposal.get("id") and entity_type in safe_types and confidence >= 0.7:
                safe_accept_ids.append(proposal["id"])
        review_report["safe_accept_ids"] = safe_accept_ids
        review_report["blocked_ids"] = [pid for pid in blocked_ids if pid]
        review_report["proposal_ids"] = all_proposal_ids
        if state.get("import_run_id"):
            _write_import_artifact(str(project_path), state["import_run_id"], "review_report.json", review_report)

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
            "context": state.get("context", {}),
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
        "import_review_report": review_report,
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
        raw_imp = str(update.get("importance", "")).strip()
        if raw_imp:
            importance = IMPORTANCE_MAP.get(raw_imp, raw_imp)
            registry["characters"][cid]["importance"] = importance
            group = IMPORTANCE_TO_GROUP.get(importance)
            if group:
                registry["characters"][cid]["groupKey"] = group

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
    windows_by_chunk: dict[int, list[dict]] = {}
    for window in state.get("prompt_windows", []):
        for window_chunk_id in window.get("chunk_ids", []):
            windows_by_chunk.setdefault(int(window_chunk_id), []).append(window)

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", 0)
        if chunk_id in completed_ids:
            continue

        chunk_content = chunk.get("content", "")
        prompt_windows = windows_by_chunk.get(int(chunk_id), [])
        if not prompt_windows:
            digest = state.get("project_structure_digest") or _build_project_structure_digest(state, state.get("import_run_id", "import"))
            prompt_windows = _build_prompt_windows(state, [chunk], digest)
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
            cached_outputs = _read_chunk_prompt_cache(state, chunk)
            if cached_outputs:
                char_data = cached_outputs.get("character", {})
                event_data = cached_outputs.get("event", {})
                world_data = cached_outputs.get("world", {})
                relationship_data = cached_outputs.get("relationship", {})
                scene_data = cached_outputs.get("scene", {})
                chunk_notes.append("Loaded Scout prompt outputs from import artifact cache.")
            else:
                window_outputs: dict[str, list[dict]] = {
                    "character": [],
                    "event": [],
                    "world": [],
                    "relationship": [],
                    "scene": [],
                }
                prompt_failures: list[dict] = []

                def _coerce_result(results: list[Any], index: int, label: str, window: dict) -> dict:
                    result = results[index]
                    if isinstance(result, Exception):
                        window_id = window.get("id", "window")
                        chunk_notes.append(f"{label} extraction failed in {window_id}: {result}")
                        errors.append(f"Chunk {chunk_id} {label} extraction failed in {window_id}: {result}")
                        prompt_failures.append({
                            "label": label,
                            "error": str(result),
                            "chunk_id": chunk_id,
                            "prompt_window_id": window_id,
                        })
                        return {}
                    return result

                for prompt_window in prompt_windows:
                    prompt_chunk_content = str(prompt_window.get("text", ""))
                    results = await asyncio.gather(
                        _invoke_json_prompt(
                            llm,
                            W1_EXTRACT_CHARACTERS_DEEP,
                            chunk_content=prompt_chunk_content,
                            chunk_id=chunk_id,
                            total_chunks=total,
                            entity_registry_summary=registry_summary,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_EXTRACT_EVENTS_DEEP,
                            chunk_content=prompt_chunk_content,
                            chunk_id=chunk_id,
                            total_chunks=total,
                            entity_registry_summary=registry_summary,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_EXTRACT_WORLD_DEEP,
                            chunk_content=prompt_chunk_content,
                            chunk_id=chunk_id,
                            total_chunks=total,
                            entity_registry_summary=registry_summary,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_EXTRACT_RELATIONSHIPS_CHUNK,
                            chunk_content=prompt_chunk_content,
                            chunk_id=chunk_id,
                            total_chunks=total,
                            entity_registry_summary=registry_summary,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_EXTRACT_SCENE_SUMMARIES,
                            chunk_content=prompt_chunk_content,
                            chunk_id=chunk_id,
                            total_chunks=total,
                            entity_registry_summary=registry_summary,
                            chapter_hint=prompt_window.get("chapter_range") or scene_hint,
                        ),
                        return_exceptions=True,
                    )
                    window_outputs["character"].append(_coerce_result(results, 0, "character", prompt_window))
                    window_outputs["event"].append(_coerce_result(results, 1, "event", prompt_window))
                    window_outputs["world"].append(_coerce_result(results, 2, "world", prompt_window))
                    window_outputs["relationship"].append(_coerce_result(results, 3, "relationship", prompt_window))
                    window_outputs["scene"].append(_coerce_result(results, 4, "scene", prompt_window))

                char_data = _merge_prompt_outputs(window_outputs["character"])
                event_data = _merge_prompt_outputs(window_outputs["event"])
                world_data = _merge_prompt_outputs(window_outputs["world"])
                relationship_data = _merge_prompt_outputs(window_outputs["relationship"])
                scene_data = _merge_prompt_outputs(window_outputs["scene"])
                prompt_outputs = {
                    "character": char_data,
                    "event": event_data,
                    "world": world_data,
                    "relationship": relationship_data,
                    "scene": scene_data,
                }
                if prompt_failures:
                    _write_chunk_prompt_failure(state, chunk, prompt_failures)
                else:
                    _write_chunk_prompt_cache(state, chunk, prompt_outputs)

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
                entry.setdefault("open_questions", [])

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
                _append_unique_strings(entry["open_questions"], update.get("open_questions", []))
                if isinstance(update.get("importance_update"), str) and update["importance_update"].strip():
                    raw_imp = update["importance_update"].strip()
                    entry["importance"] = IMPORTANCE_MAP.get(raw_imp, raw_imp)
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
                    entry.setdefault("open_questions", [])

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
                    _append_unique_strings(entry["open_questions"], nc.get("open_questions", []))
                    if isinstance(nc.get("importance"), str) and nc["importance"].strip():
                        raw_imp = nc["importance"].strip()
                        entry["importance"] = IMPORTANCE_MAP.get(raw_imp, raw_imp)
                    entry["confidence"] = max(float(entry.get("confidence", 0.7)), float(nc.get("confidence", 0.7)))
                    continue

                char_id = f"char_{uuid.uuid4().hex[:8]}"
                aliases: list[str] = []
                _append_unique_strings(aliases, nc.get("aliases", []))
                raw_importance = str(nc.get("importance", "")).strip()
                registry["characters"][char_id] = _truncate_text_fields({
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
                    "personality_traits": [trait.strip() for trait in nc.get("personality_traits", []) if isinstance(trait, str) and trait.strip()][:4],
                    "goals": [],
                    "fears": [],
                    "secrets": [],
                    "speech_style": str(nc.get("speech_style", "")).strip(),
                    "arc_notes": str(nc.get("arc_notes", "")).strip(),
                    "importance": IMPORTANCE_MAP.get(raw_importance, raw_importance or "supporting"),
                    "tag_ids": [],
                    "open_questions": [question.strip() for question in nc.get("open_questions", []) if isinstance(question, str) and question.strip()][:2],
                })
                new_chars.append(registry["characters"][char_id])

            # Enforce confidence floor and density cap per chunk
            raw_events = event_data.get("events", [])
            raw_events = [e for e in raw_events if float(e.get("confidence", 0)) >= 0.75]
            raw_events = sorted(raw_events, key=lambda e: float(e.get("confidence", 0)), reverse=True)[:3]

            for ev in raw_events:
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
        chunk_duration_ms = int((asyncio.get_event_loop().time() - _chunk_start_time) * 1000) if "_chunk_start_time" in dir() else 0

        # Update mid-node progress so the polling coroutine in _run_w1 can
        # report real-time chunk counts without waiting for the node to finish.
        _chunk_progress[project_path] = {"completed": completed, "total": total}

        # Emit a chunk log entry for the console
        last_extraction = extractions[-1] if extractions else {}
        log_entry: dict = {
            "chunk_id": chunk_id,
            "total_chunks": total,
            "step": "process_chunks",
            "new_characters": len(new_chars),
            "updated_characters": len(alias_updates),
            "new_events": len(events),
            "new_world": len(world_mentions),
            "duration_ms": chunk_duration_ms,
            "excerpt": chunk_content[:200],
            "errors": [n for n in chunk_notes if "fail" in n.lower() or "error" in n.lower()],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if project_path not in _chunk_log:
            _chunk_log[project_path] = []
        _chunk_log[project_path].append(log_entry)

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

        # Check for cancel signal
        cancel_event = _cancel_events.get(project_path)
        if cancel_event and cancel_event.is_set():
            break

        # Check for breakpoint — pause until resume endpoint sets the pause_event
        bp = _breakpoint_chunks.get(project_path)
        if bp is not None and completed >= bp:
            if project_path not in _pause_events:
                ev = asyncio.Event()
                ev.set()
                _pause_events[project_path] = ev
            pause_event = _pause_events[project_path]
            pause_event.clear()
            await pause_event.wait()

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
                       infer_world_settings → evidence → reconcile → timeline_architect →
                       todos → review → write
    """
    builder: StateGraph = StateGraph(ImportState)

    # Shared nodes
    builder.add_node("validate_file", node_validate_file)
    builder.add_node("load_or_init_checkpoint", node_load_or_init_checkpoint)
    builder.add_node("split_chunks", node_split_chunks)
    builder.add_node("build_manuscript", node_build_manuscript)
    builder.add_node("generate_import_todos", node_generate_import_todos)
    builder.add_node("build_evidence_cards", node_build_evidence_cards)
    builder.add_node("reconcile_entities", node_reconcile_entities)
    builder.add_node("architect_timeline", node_architect_timeline)
    builder.add_node("review_import", node_review_import)
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
    builder.add_edge("infer_world_settings", "build_evidence_cards")
    builder.add_edge("build_evidence_cards", "reconcile_entities")
    builder.add_edge("reconcile_entities", "architect_timeline")
    builder.add_edge("architect_timeline", "generate_import_todos")

    builder.add_edge("generate_import_todos", "review_import")
    builder.add_edge("review_import", "write_to_project")
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
        "prompt_profile": config.get("prompt_profile") or config.get("context", {}).get("prompt_profile", "balanced"),
        "context": config.get("context", {}),
        "chunks": [],
        "import_run_manifest": {},
        "evidence_cards": [],
        "reducer_artifact": {},
        "timeline_architecture": {},
        "import_review_report": {},
        "project_structure_digest": {},
        "prompt_windows": [],
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


async def run_streaming(project_path: str, config: dict):
    """Streaming entry point — yields intermediate state dicts after each node.

    Each yielded dict has: progress, errors, completed_chunks, total_chunks.
    The caller can use these to update a status endpoint in real time.
    """
    import_mode = config.get("import_mode", "import_all")
    initial_state: ImportState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "import_mode": import_mode,
        "prompt_profile": config.get("prompt_profile") or config.get("context", {}).get("prompt_profile", "balanced"),
        "context": config.get("context", {}),
        "chunks": [],
        "import_run_manifest": {},
        "evidence_cards": [],
        "reducer_artifact": {},
        "timeline_architecture": {},
        "import_review_report": {},
        "project_structure_digest": {},
        "prompt_windows": [],
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

    total_chunks = 0
    completed_chunks = 0

    async for event in compiled.astream(initial_state, {"configurable": {"thread_id": thread_id}}):
        # astream yields {node_name: node_output} per node
        for node_name, node_output in event.items():
            if not isinstance(node_output, dict):
                continue

            # Track chunk counts from split_chunks and process_chunks
            if node_name == "split_chunks":
                chunks = node_output.get("chunks", [])
                total_chunks = len(chunks)
                completed_chunks = 0

            if node_name in ("process_chunks",):
                extractions = node_output.get("chunk_extractions", [])
                completed_chunks = len(extractions)
                total_chunks = max(total_chunks, completed_chunks)

            if node_name == "build_manuscript":
                chapters = node_output.get("manuscript_chapters", [])
                completed_chunks = total_chunks  # All chunks processed

            progress = node_output.get("progress", 0.0)
            errors = node_output.get("errors", [])

            yield {
                "progress": progress,
                "errors": errors if isinstance(errors, list) else [],
                "completed_chunks": completed_chunks,
                "total_chunks": total_chunks,
                "current_node": node_name,
                "import_review_report": node_output.get("import_review_report", {}),
                "proposals_count": len(node_output.get("proposals", [])) if isinstance(node_output.get("proposals", []), list) else 0,
            }
