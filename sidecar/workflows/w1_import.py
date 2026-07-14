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
import tempfile
import uuid
from json import JSONDecodeError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from sidecar.models.state import (
    ImportState,
    ManuscriptChapter,
    make_source_span,
    validate_source_span,
)
from sidecar.supervisor.organizer import organize_project_content, OrganizerInput
from sidecar.shared import s2_memory_writer, s3_chunk_manager
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.workflows.w1_run_events import (
    BudgetPolicy,
    add_token_usage,
    authoritative_usage_ledger,
    configure_budget,
    record_call_usage,
    release_call_reservation,
    reserve_call_budget,
)
from sidecar.prompts.w1_prompts import (
    W1_EXTRACT_CHARACTERS,
    W1_EXTRACT_CHARACTERS_DEEP,
    W1_EXTRACT_EVENTS,
    W1_EXTRACT_EVENTS_DEEP,
    W1_EXTRACT_RELATIONSHIPS_CHUNK,
    W1_EXTRACT_SCENE_SUMMARIES,
    W1_EXTRACT_WORLD_DEEP,
    W1_EXTRACT_WORLD,
    W1_CROSS_VALIDATE_IMPORT,
    W1_SYNTHESIZE_RELATIONSHIPS,
    W1_CLASSIFY_CHARACTER_TAGS,
    W1_INFER_WORLD_SETTINGS,
    W1_WINDOW_SYSTEM_CONTEXT,
    W1_CHARS_DEEP_TASK,
    W1_EVENTS_DEEP_TASK,
    W1_WORLD_DEEP_TASK,
    W1_RELS_CHUNK_TASK,
    W1_SCENES_TASK,
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


def _registry_summary(registry: dict, max_chars: int = 3000, max_world_entries: int = 30) -> str:
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
    # Append top-N world entries by confidence (name + category only)
    world_detailed = registry.get("world_detailed", {})
    if world_detailed:
        top_world = sorted(
            world_detailed.values(),
            key=lambda w: float(w.get("confidence", 0.0)),
            reverse=True,
        )[:max_world_entries]
        lines.append("\nKnown world entities:")
        for wd in top_world:
            lines.append(f"  - {wd.get('name', '?')} ({wd.get('category', 'concept')})")
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


def _extract_llm_usage(response: Any) -> tuple[int, int] | None:
    """Extract (input_tokens, output_tokens) from a LangChain AIMessage.

    Tries usage_metadata first (LangChain ≥0.2), then response_metadata.token_usage
    (OpenAI-compatible fallback). Returns None if neither is present.
    """
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        return int(um.get("input_tokens", 0) or 0), int(um.get("output_tokens", 0) or 0)
    if hasattr(response, "response_metadata") and response.response_metadata:
        tu = response.response_metadata.get("token_usage") or {}
        if tu.get("prompt_tokens") or tu.get("completion_tokens"):
            return int(tu.get("prompt_tokens", 0) or 0), int(tu.get("completion_tokens", 0) or 0)
    return None


async def _repair_json_response(llm: ChatOpenAI, raw: str, parse_error: Exception, session_id: str = "") -> dict:
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
    response = await _ainvoke_with_budget(
        llm,
        [HumanMessage(content=repair_prompt)],
        session_id=session_id,
        estimated_input_tokens=_estimate_tokens(repair_prompt),
    )
    repaired = response.content if isinstance(response.content, str) else str(response.content)
    return _parse_json_response(repaired)


async def _invoke_json_prompt(
    llm: ChatOpenAI,
    prompt_template: str,
    *,
    session_id: str = "",
    system_content: str | None = None,
    **kwargs: Any,
) -> dict:
    """Render a prompt template, invoke the LLM, and parse the JSON response.

    When system_content is provided, it is sent as a SystemMessage before the
    user HumanMessage. All 5 parallel extraction calls within a prompt window
    share the same system_content (entity registry + source text), enabling KV
    prefix caching on the shared tokens.

    Retries up to 4 times with exponential backoff for transient failures:
    - Rate-limit / governor errors (429, 503, 'Authentication Fails (governor)')
    - 'str' object has no attribute 'model_dump' — LangChain streaming parse error
      when DeepSeek injects a governor error into an SSE stream.
    - JSON parse failures (model returned prose instead of JSON).
    """
    prompt = prompt_template.format(**kwargs)
    messages = (
        [SystemMessage(content=system_content), HumanMessage(content=prompt)]
        if system_content is not None
        else [HumanMessage(content=prompt)]
    )
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            response = await _ainvoke_with_budget(
                llm,
                messages,
                session_id=session_id,
                estimated_input_tokens=_estimate_tokens(prompt) + _estimate_tokens(system_content or ""),
            )
            raw = response.content if isinstance(response.content, str) else str(response.content)
            try:
                return _parse_json_response(raw)
            except Exception as parse_exc:
                if _is_truncated_json_error(parse_exc) or isinstance(parse_exc, (JSONDecodeError, JsonPromptParseError, ValueError)):
                    return await _repair_json_response(llm, raw, parse_exc, session_id=session_id)
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


def _llm_model_name(llm: Any) -> str:
    return str(getattr(llm, "model_name", "") or getattr(llm, "model", "") or "")


async def _ainvoke_with_budget(
    llm: Any,
    messages: list[Any],
    *,
    session_id: str = "",
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
) -> Any:
    """Run one provider call with E0 budget guards around the actual I/O."""
    model = _llm_model_name(llm)
    reservation_token = ""
    if session_id:
        reserved = reserve_call_budget(
            session_id,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            model=model,
        )
        if reserved is None:
            raise RuntimeError("budget_exhausted: preflight denied provider call")
        reservation_token = reserved
    try:
        async with _API_SEMAPHORE:
            response = await llm.ainvoke(messages)
    except Exception:
        if session_id:
            release_call_reservation(session_id, reservation_token)
        raise
    if session_id:
        usage = _extract_llm_usage(response)
        if not record_call_usage(
            session_id,
            usage[0] if usage else None,
            usage[1] if usage else None,
            model=model,
            reservation_token=reservation_token,
        ):
            reason = authoritative_usage_ledger(session_id, model).get("budget_status", {}).get("reason", "budget_exhausted")
            raise RuntimeError(f"budget_exhausted: postflight denied provider response ({reason})")
    return response


def configure_w1_budget(config: dict, session_id: str) -> None:
    """Configure the E0 ledger once per W1 run when a policy is supplied."""
    policy_data = config.get("budget_policy") or config.get("context", {}).get("budget_policy")
    if not session_id or not isinstance(policy_data, dict):
        return
    model = str(config.get("context", {}).get("model") or config.get("model") or "deepseek-chat")
    configure_budget(session_id, BudgetPolicy(**policy_data), model=model)


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


def _dedupe_text_segments(text: str) -> str:
    """Collapse repeated semicolon/newline facts in compact import cards."""
    if not isinstance(text, str):
        return ""
    parts = [
        part.strip(" \t\r\n。.;；")
        for part in re.split(r"[；;\n]+", text)
        if part.strip(" \t\r\n。.;；")
    ]
    if not parts:
        return ""
    kept: list[str] = []
    seen_keys: set[str] = set()
    seen_age_keys: set[str] = set()
    for part in parts:
        key = _normal_key(part)
        if not key or key in seen_keys:
            continue
        age_match = re.search(r"(\d+\s*岁|[零〇一二两三四五六七八九十百千]+岁)", part)
        if age_match:
            age_key = age_match.group(1).replace(" ", "")
            if age_key in seen_age_keys:
                # Multiple "十岁/十三岁..." fragments are usually the same basic bio fact.
                continue
            seen_age_keys.add(age_key)
        if any(difflib.SequenceMatcher(None, key[:80], _normal_key(prev)[:80]).ratio() > 0.82 for prev in kept):
            continue
        seen_keys.add(key)
        kept.append(part)
    return "；".join(kept)


_CHARACTER_CARD_TEXT_LIMITS: dict[str, int] = {
    "summary": 180,
    "background": 160,
    "role_in_story": 120,
    "physical_description": 120,
    "speech_style": 100,
    "arc_notes": 140,
}
_CHARACTER_CARD_TRAIT_LIMIT = 10
_CHARACTER_CARD_OPEN_QUESTION_LIMIT = 4


def _compact_text_value(value: Any, limit: int) -> str:
    """Keep character cards reviewable even after many chapter updates."""
    if not isinstance(value, str):
        return ""
    cleaned_lines: list[str] = []
    for line in value.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned and cleaned not in cleaned_lines:
            cleaned_lines.append(cleaned)
    if not cleaned_lines:
        return ""
    text = _dedupe_text_segments("；".join(cleaned_lines))
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip("；,，.。 ") + "…"


def _compact_character_traits(values: Any, limit: int = _CHARACTER_CARD_TRAIT_LIMIT) -> list[str]:
    if not isinstance(values, list):
        return []
    compacted: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = re.sub(r"\s+", " ", value).strip(" -•\t\r\n")
        if not cleaned:
            continue
        # Traits should be labels, not evidence sentences.
        if len(cleaned) > 24:
            cleaned = cleaned[:23].rstrip("，,。.;； ") + "…"
        key = _normal_key(cleaned)
        if key and key not in seen:
            seen.add(key)
            compacted.append(cleaned)
        if len(compacted) >= limit:
            break
    return compacted


def _compact_character_card(entry: dict) -> dict:
    """Final reducer guardrail: import creates character-card drafts, not dossiers."""
    for field, limit in _CHARACTER_CARD_TEXT_LIMITS.items():
        entry[field] = _compact_text_value(entry.get(field, ""), limit)
    entry["personality_traits"] = _compact_character_traits(entry.get("personality_traits", []))
    entry["open_questions"] = _compact_character_traits(
        entry.get("open_questions", []),
        _CHARACTER_CARD_OPEN_QUESTION_LIMIT,
    )
    for field in ("goals", "fears", "secrets"):
        # Import should not hallucinate deep psychology; later action workflows enrich these.
        entry[field] = []
    return entry


_CHARACTER_FALLBACK_EXPERIENCE_LIMIT = 3
_WINDOW_PROVENANCE_NOTE_RE = re.compile(r"^\[window\s+[^\]]+\]\s*(.+)$", re.IGNORECASE)
_CHARACTER_ACTION_STATE_MARKERS = (
    "参加", "进入", "离开", "通过", "未能", "成为", "收为", "收下", "选中", "传授",
    "教授", "学习", "开始", "救", "安排", "留下", "贿赂", "说服", "答应", "介绍",
    "摘", "带", "住", "担任", "当过", "重视", "失去", "获得", "发现", "毫无进展", "允诺",
    "joined", "entered", "left", "became", "selected", "taught", "learned", "rescued",
)
_CHARACTER_IDENTITY_ROLE_MARKERS = (
    "主角", "供奉", "师父", "师长", "弟子", "医师", "大夫", "掌柜", "铁匠", "书童",
    "农家", "村", "出身", "来自", "父", "母", "兄", "妹", "家族", "门", "组织",
    "protagonist", "mentor", "doctor", "apprentice", "from ", "born ",
)


def _serialize_character_experience(character_id: str, *values: Any) -> list[dict[str, str]]:
    """Normalize extractor experience aliases to the frontend character-row contract."""
    serialized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, dict):
                fact = str(
                    candidate.get("fact")
                    or candidate.get("text")
                    or candidate.get("description")
                    or ""
                ).strip()
                chapter = str(candidate.get("chapter") or candidate.get("chapter_hint") or "").strip()
                evidence = str(candidate.get("evidence") or "").strip()
                entry_id = str(candidate.get("id") or "").strip()
            elif isinstance(candidate, str):
                fact, chapter, evidence, entry_id = candidate.strip(), "", "", ""
            else:
                continue
            if not fact:
                continue
            key = (chapter, fact, evidence)
            if key in seen:
                continue
            seen.add(key)
            row = {
                "id": entry_id or f"{character_id}_experience_{len(serialized) + 1}",
                "chapter": chapter,
                "fact": fact,
            }
            if evidence:
                row["evidence"] = evidence
            serialized.append(row)
    return serialized


def _character_evidence_refs(entry: dict, profile_field_evidence: dict) -> list[str]:
    """Return only existing evidence-card references; spans remain provenance metadata."""
    refs: list[str] = []

    def _append(value: Any) -> None:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and item.strip() and item.strip() not in refs:
                refs.append(item.strip())

    for field in ("experience", "experiences", "background"):
        _append(profile_field_evidence.get(field, []))
    _append(entry.get("evidence_refs", []))
    _append(entry.get("evidenceRefs", []))
    return refs


def _character_source_span(entry: dict, profile_field_evidence: dict) -> dict | None:
    """Find a complete SourceSpan already attached to the final character profile."""
    required = {"raw_source_hash", "absolute_start", "absolute_end", "substring_hash"}

    def _valid(value: Any) -> dict | None:
        if isinstance(value, dict) and required.issubset(value):
            return dict(value)
        return None

    for candidate in (entry.get("source_span"), entry.get("sourceSpan")):
        span = _valid(candidate)
        if span:
            return span
    for values in profile_field_evidence.values():
        candidates = values if isinstance(values, list) else [values]
        for candidate in candidates:
            span = _valid(candidate)
            if span:
                return span
    return None


def _is_supported_major_character(entry: dict) -> bool:
    importance = str(entry.get("importance") or entry.get("importImportance") or "").strip().lower()
    group_key = str(entry.get("groupKey") or "").strip().lower()
    return importance in {"core", "major", "main", "protagonist"} or "main character" in group_key


def _action_or_state_note(note: Any) -> str:
    """Keep only source-window action/state claims; trait-only notes never become experience."""
    if not isinstance(note, str):
        return ""
    match = _WINDOW_PROVENANCE_NOTE_RE.match(note.strip())
    if not match:
        return ""
    fact = re.split(r"[，,；;]\s*(?:体现|显示|表明|说明|可见|显得|反映|暗示)", match.group(1).strip(), maxsplit=1)[0].strip()
    if not fact or fact.lower().startswith("open question:"):
        return ""
    lowered = fact.lower()
    return fact if any(marker.lower() in lowered for marker in _CHARACTER_ACTION_STATE_MARKERS) else ""


def _identity_or_role_background(entry: dict) -> str:
    """Choose a literal identity/origin/role clause rather than a personality description."""
    candidates = [entry.get("summary", ""), entry.get("role_in_story", ""), entry.get("roleInStory", "")]
    for value in candidates:
        if not isinstance(value, str):
            continue
        for clause in re.split(r"[。.!！?？；;，,]", value):
            cleaned = clause.strip()
            if cleaned and any(marker.lower() in cleaned.lower() for marker in _CHARACTER_IDENTITY_ROLE_MARKERS):
                return cleaned
    for note in entry.get("notes", []):
        fact = _action_or_state_note(note)
        if fact and any(marker.lower() in fact.lower() for marker in _CHARACTER_IDENTITY_ROLE_MARKERS):
            return fact
    return ""


def _append_profile_field_provenance(
    profile_field_evidence: dict,
    field: str,
    evidence_ref: str,
    source_span: dict,
) -> dict:
    updated = {key: list(value) if isinstance(value, list) else [value] for key, value in profile_field_evidence.items()}
    values = updated.setdefault(field, [])
    if evidence_ref not in values:
        values.append(evidence_ref)
    if source_span not in values:
        values.append(source_span)
    return updated


def _backfill_character_profile_at_write_boundary(character_id: str, entry: dict) -> tuple[list[dict[str, str]], str, dict]:
    """Recover only evidence-bound final-card facts when upstream normalization is empty."""
    experience = _serialize_character_experience(character_id, entry.get("experience", []), entry.get("experiences", []))
    background = str(entry.get("background") or "").strip()
    profile_field_evidence = entry.get("profile_field_evidence")
    profile_field_evidence = dict(profile_field_evidence) if isinstance(profile_field_evidence, dict) else {}

    evidence_refs = _character_evidence_refs(entry, profile_field_evidence)
    source_span = _character_source_span(entry, profile_field_evidence)
    if not evidence_refs or not source_span:
        return experience, background, profile_field_evidence
    evidence_ref = evidence_refs[0]

    if not experience:
        fallback_facts: list[str] = []
        for note in entry.get("notes", []):
            fact = _action_or_state_note(note)
            if fact and fact not in fallback_facts:
                fallback_facts.append(fact)
            if len(fallback_facts) >= _CHARACTER_FALLBACK_EXPERIENCE_LIMIT:
                break
        if fallback_facts:
            experience = _serialize_character_experience(
                character_id,
                [{"fact": fact, "evidence": evidence_ref} for fact in fallback_facts],
            )
            profile_field_evidence = _append_profile_field_provenance(
                profile_field_evidence,
                "experience",
                evidence_ref,
                source_span,
            )

    if not background and _is_supported_major_character(entry):
        fallback_background = _identity_or_role_background(entry)
        if fallback_background:
            background = fallback_background
            profile_field_evidence = _append_profile_field_provenance(
                profile_field_evidence,
                "background",
                evidence_ref,
                source_span,
            )
    return experience, background, profile_field_evidence


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


def _chunk_sort_key(value: Any) -> tuple[int, str]:
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return (int(match.group(0)), value)
    try:
        return (int(value), "")
    except (TypeError, ValueError):
        return (10_000_000, str(value or ""))


def _min_chunk_sort_key(items: list[dict]) -> tuple[int, str]:
    keys = [_chunk_sort_key(item.get("chunk_id")) for item in items]
    return min(keys) if keys else (10_000_000, "")


def _chapter_sort_key(chapter: dict) -> tuple[int, str]:
    chunk_ids = chapter.get("chunk_ids", [])
    if isinstance(chunk_ids, list) and chunk_ids:
        return min(_chunk_sort_key(chunk_id) for chunk_id in chunk_ids)
    if chapter.get("orderIndex") is not None:
        try:
            return (int(chapter.get("orderIndex")), str(chapter.get("title", "")))
        except (TypeError, ValueError):
            pass
    title = str(chapter.get("title", ""))
    chapter_number = _chapter_number_from_title(title)
    if chapter_number is not None:
        return (chapter_number, title)
    return (10_000_000, title)


_ZH_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_zh_int(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return int(cleaned)
    total = 0
    current = 0
    units = {"十": 10, "百": 100, "千": 1000}
    for char in cleaned:
        if char in _ZH_DIGITS:
            current = _ZH_DIGITS[char]
            continue
        if char in units:
            unit = units[char]
            total += (current or 1) * unit
            current = 0
            continue
        return None
    return total + current if total or current else None


def _chapter_number_from_title(title: str) -> int | None:
    arabic = re.search(r"(?:chapter|ch\.?|第)?\s*(\d+)\s*(?:章|回|节)?", title, flags=re.IGNORECASE)
    if arabic:
        return int(arabic.group(1))
    zh = re.search(r"第\s*([零〇一二两三四五六七八九十百千\d]+)\s*[章节回]", title)
    if zh:
        return _parse_zh_int(zh.group(1))
    return None


def _sort_manuscript_chapters(chapters: list[dict]) -> list[dict]:
    """Keep imported chapters in source order even after async/cache/resume paths."""
    ordered = sorted(chapters, key=_chapter_sort_key)
    for idx, chapter in enumerate(ordered):
        chapter["orderIndex"] = idx
    return ordered


def _chapter_summary_fallback(title: str, content: str, limit: int = 180) -> str:
    """Cheap writer-facing synopsis fallback; never leaves chapter cards blank."""
    cleaned = re.sub(r"\s+", " ", str(content or "")).strip()
    if not cleaned:
        return f"{title}：导入正文为空，需人工核对原文。"
    paragraphs = [p.strip() for p in re.split(r"\n{2,}|(?<=[。！？!?])\s+", str(content)) if p.strip()]
    if paragraphs:
        summary = paragraphs[0]
        if len(paragraphs) > 1 and len(summary) < limit * 0.6:
            summary = f"{summary}……{paragraphs[-1]}"
    else:
        summary = cleaned
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > limit:
        summary = summary[: max(limit - 1, 0)].rstrip("，,。.;； ") + "…"
    return summary


def _chapter_goal_fallback(language: str = "zh") -> str:
    return _localized_text(language, "梳理本章导入正文，核对人物、事件与设定引用。", "Review imported chapter prose and verify character, event, and world references.")


def _chapter_notes_fallback(source_file: Any, chunk_ids: list[Any]) -> str:
    chunks = ", ".join(str(cid) for cid in chunk_ids)
    source = str(source_file or "").strip()
    parts = []
    if source:
        parts.append(f"Imported from: {source}")
    if chunks:
        parts.append(f"Chunks: {chunks}")
    return "\n".join(parts)


def _enrich_manuscript_chapter(chapter: dict, state: ImportState | dict, content: str) -> dict:
    title = str(chapter.get("title") or "Chapter").strip()
    chunk_ids = list(chapter.get("chunk_ids") or [])
    chapter_number = _chapter_number_from_title(title)
    enriched = {
        **chapter,
        "summary": chapter.get("summary") or _chapter_summary_fallback(title, content),
        "goal": chapter.get("goal") or _chapter_goal_fallback(str(state.get("source_language", "zh"))),
        "notes": chapter.get("notes") or _chapter_notes_fallback(state.get("source_file_path"), chunk_ids),
    }
    if chapter_number is not None:
        enriched["chapterNumber"] = chapter_number
    return enriched


def _dedupe_manuscript_chapters(chapters: list[dict]) -> list[dict]:
    """Merge accidental duplicate chapter records by parsed chapter number/title."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for chapter in chapters:
        title = str(chapter.get("title") or "").strip()
        number = _chapter_number_from_title(title)
        key = f"num:{number}" if number is not None else f"title:{_normal_key(title)}"
        if key not in merged:
            merged[key] = dict(chapter)
            order.append(key)
            continue
        current = merged[key]
        current["chunk_ids"] = list(dict.fromkeys([*current.get("chunk_ids", []), *chapter.get("chunk_ids", [])]))
        current["manuscript_content"] = "\n\n".join(
            part for part in [current.get("manuscript_content", ""), chapter.get("manuscript_content", "")]
            if str(part).strip()
        )
        for field in ("summary", "goal", "notes"):
            current[field] = _merge_text_field(str(current.get(field, "")), chapter.get(field, ""))
    return [merged[key] for key in order]


def _detect_language(sample: str) -> str:
    """Return ISO 639-1 language code inferred from a short text sample."""
    if not sample:
        return "en"
    cjk_count = sum(1 for c in sample if '一' <= c <= '鿿')
    return "zh" if cjk_count / max(len(sample), 1) >= 0.3 else "en"


_WORLD_ENTITY_NAME_PATTERNS = (
    "门", "派", "宗", "帮", "会", "盟", "阁", "殿", "宫", "谷", "山庄", "书院",
    "城", "镇", "村", "谷", "山", "峰", "河", "湖", "岛", "国", "州", "府",
)
_ORGANIZATION_HINTS = ("门", "派", "宗", "帮", "会", "盟", "山庄", "书院")
_LOCATION_HINTS = ("城", "镇", "村", "谷", "山", "峰", "河", "湖", "岛", "国", "州", "府", "岭", "洞", "堂", "院", "阁", "殿", "宫", "楼", "台")
_WORLD_MODULE_CONTAMINATION_NAMES = {
    "人物关系图", "人物关系", "关系图", "关系网络", "事件时间线", "时间线", "timeline", "relationship graph",
}
_WORLD_ROLE_RANK_HINTS = ("弟子", "门丁", "护法", "堂主", "师兄", "师弟", "师姐", "师妹", "长老", "供奉")
WORLD_ONTOLOGY_CATEGORIES: tuple[str, ...] = (
    "location",
    "organization",
    "faction",
    "item",
    "artifact",
    "rule",
    "system",
    "cultivation_method",
    "concept",
    "culture",
    "custom",
)
WORLD_ONTOLOGY_LABELS: dict[str, dict[str, str]] = {
    "location": {"en": "Location", "zh": "地点", "zh_description": "地名、区域、建筑或地理空间。"},
    "organization": {"en": "Organization", "zh": "组织", "zh_description": "门派、宗门、帮派、机构或正式团体。"},
    "faction": {"en": "Faction", "zh": "势力", "zh_description": "势力、派系、联盟或阵营。"},
    "item": {"en": "Item", "zh": "物品", "zh_description": "普通物品、丹药、装备或重要道具。"},
    "artifact": {"en": "Artifact", "zh": "法器", "zh_description": "法器、宝物、灵器或特殊器物。"},
    "rule": {"en": "Rule", "zh": "规则", "zh_description": "明确规则、禁制、法则或制度约束。"},
    "system": {"en": "System", "zh": "体系", "zh_description": "功法、法术、修炼体系或能力系统。"},
    "cultivation_method": {"en": "Cultivation Method", "zh": "功法与术法", "zh_description": "功法、法诀、术法、秘术或修炼法门。"},
    "concept": {"en": "Concept", "zh": "概念", "zh_description": "世界观概念、术语或设定。"},
    "culture": {"en": "Culture", "zh": "文化", "zh_description": "文化、习俗、礼法或社会惯例。"},
    "custom": {"en": "Custom", "zh": "自定义", "zh_description": "无法归入固定类别但需要保留的设定。"},
}
_MAINLINE_ARC_HINTS = {
    "main",
    "main_arc",
    "main_story",
    "main_plot",
    "root",
    "protagonist_origin",
    "sect_entry",
    "cultivation_progress",
    "core_progression",
    "journey",
    "training_progress",
}
_SIDE_ARC_HINTS = {
    "mentor_control",
    "mentor_threat",
    "faction_conflict",
    "sect_conflict",
    "bottle_secret",
    "romance",
    "rivalry",
    "antagonist",
    "family",
    "world_lore",
}
_WORLD_CATEGORY_ALIASES: dict[str, str] = {
    "place": "location",
    "location": "location",
    "map": "location",
    "地名": "location",
    "地点": "location",
    "organization": "organization",
    "organisation": "organization",
    "faction": "faction",
    "势力": "faction",
    "sect": "organization",
    "门派": "organization",
    "宗门": "organization",
    "帮派": "organization",
    "clan": "organization",
    "guild": "organization",
    "object": "item",
    "artifact": "artifact",
    "法器": "artifact",
    "item": "item",
    "丹药": "item",
    "物品": "item",
    "weapon": "item",
    "treasure": "artifact",
    "concept": "concept",
    "lore": "concept",
    "rule": "rule",
    "规则": "rule",
    "system": "system",
    "功法": "cultivation_method",
    "法术": "cultivation_method",
    "术法": "cultivation_method",
    "法诀": "cultivation_method",
    "magic": "rule",
    "cultivation": "cultivation_method",
    "culture": "culture",
    "custom": "custom",
}

# Arc IDs the LLM might emit that are world entity categories, not semantic arc lanes.
# If an event's arcId matches any of these, treat arcId as absent and fall through
# to the semantic/theme-based lane inference in _timeline_lane_key.
_WORLD_CATEGORY_BRANCH_BLOCKLIST: frozenset[str] = frozenset({
    "item", "artifact", "location", "rule", "system", "concept",
    "culture", "custom", "faction", "organization", "organisation",
    "place", "object", "weapon", "treasure", "magic", "cultivation",
    "lore", "clan", "guild", "sect", "map",
    # Chinese equivalents
    "地名", "地点", "门派", "宗门", "帮派", "势力", "物品", "丹药",
    "法器", "功法", "法术", "术法", "法诀", "规则", "地图",
})

TIMELINE_EVENT_CLASSES: tuple[str, ...] = (
    "canonical_event",
    "scene_beat",
    "background_reference",
    "discarded_duplicate",
)
_LEGACY_EVENT_TYPE_VALUES = {
    "inciting_choice",
    "journey_departure",
    "test_or_trial",
    "discovery",
    "training_breakthrough",
    "confrontation",
    "betrayal_or_reveal",
    "alliance_or_bond",
    "power_shift",
    "injury_or_death",
    "escape_or_pursuit",
    "faction_move",
    "other",
}
_TIMELINE_BRANCH_ROLES = {"mainline", "fork", "merge", "parallel", "callback", "side_lane", "unknown"}
_TIMELINE_CAUSAL_ROLES = {"cause", "effect", "turning_point", "setup", "payoff", "background", "unknown"}
_TIMELINE_ARC_ROLES = {
    "mainline",
    "protagonist",
    "faction",
    "organization",
    "location",
    "antagonist",
    "training",
    "power_progression",
    "background",
    "side",
}


def _is_zh_state(state: ImportState | dict) -> bool:
    return state.get("source_language") == "zh"


def _localized_text(state_or_language: ImportState | dict | str, zh: str, en: str) -> str:
    language = state_or_language if isinstance(state_or_language, str) else state_or_language.get("source_language", "en")
    return zh if language == "zh" else en


def _normalize_world_category(name: str, category: Any = "") -> str:
    raw = str(category or "").strip().lower()
    clean_name = str(name or "").strip()
    if any(token in raw for token in ("person", "character", "人物", "角色", "人名")):
        return "custom"
    if any(token in clean_name for token in _WORLD_ROLE_RANK_HINTS) and not any(clean_name.endswith(token) for token in ("堂", "峰", "谷", "院", "阁", "殿", "宫", "楼", "台")):
        # Ranks/roles are organizational concepts, not cultivation methods and
        # not standalone people in the World Model.
        return "rule"
    if any(token in raw for token in ("method", "spell", "cultivation", "功法", "法术", "术法", "法诀", "秘术", "修炼法门")):
        return "cultivation_method"
    if any(token in clean_name for token in _LOCATION_HINTS):
        return "location"
    if any(token in clean_name for token in _ORGANIZATION_HINTS):
        return "organization"
    normalized = _WORLD_CATEGORY_ALIASES.get(raw)
    if normalized:
        return normalized
    if any(token in raw for token in ("organization", "organisation", "sect", "clan", "guild", "组织", "门派", "宗门", "帮派")):
        return "organization"
    if any(token in raw for token in ("faction", "alliance", "势力", "阵营", "联盟", "派系")):
        return "faction"
    if any(token in raw for token in ("location", "place", "map", "地点", "位置", "地理")):
        return "location"
    if any(token in raw for token in ("artifact", "treasure", "法器", "宝物", "灵器")):
        return "artifact"
    if any(token in raw for token in ("item", "object", "物品", "丹药", "道具")):
        return "item"
    if any(token in raw for token in ("system", "体系", "修炼")):
        return "system"
    if any(token in raw for token in ("rule", "law", "规则", "法则", "制度")):
        return "rule"
    if any(token in raw for token in ("culture", "custom", "文化", "习俗")):
        return "culture"
    if any(token in raw for token in ("custom", "自定义")):
        return "custom"
    if any(token in name for token in _LOCATION_HINTS):
        return "location"
    if any(token in name for token in _ORGANIZATION_HINTS):
        return "organization"
    return "concept"


def _world_container_key(category: Any) -> str:
    normalized = _normalize_world_category("", category)
    if normalized == "location":
        return "locations"
    if normalized in {"organization", "faction"}:
        return "organizations"
    if normalized in {"item", "artifact"}:
        return "items"
    if normalized == "cultivation_method":
        return "cultivation_methods"
    if normalized in {"rule", "system"}:
        return "rules"
    if normalized == "culture":
        return "culture"
    return "concepts"


def _default_world_container_specs(language: str) -> list[dict]:
    zh = language == "zh"
    labels = {
        "locations": ("地理位置", "Locations", "map"),
        "organizations": ("门派组织", "Organizations & Factions", "notebook"),
        "items": ("物品与法器", "Items & Artifacts", "notebook"),
        "cultivation_methods": ("功法与术法", "Cultivation Methods", "notebook"),
        "rules": ("修炼境界与制度", "Rules & Systems", "notebook"),
        "concepts": ("概念与设定", "Concepts & Lore", "notebook"),
        "culture": ("文化与习俗", "Culture", "notebook"),
    }
    specs: list[dict] = []
    for index, (key, (zh_name, en_name, container_type)) in enumerate(labels.items()):
        name = zh_name if zh else en_name
        specs.append({
            "id": f"cont_import_{key}",
            "name": name,
            "type": container_type,
            "isDefault": index == 0,
            "sortOrder": index,
            "description": _localized_text(language, f"W1 导入的{name}条目。", f"W1 imported {name.lower()} entries."),
            "importCategoryKey": key,
            "categoryPath": ["世界模型", name] if zh else ["World Model", name],
        })
    return specs


def _is_world_model_module_contamination(name: Any, container_type: Any = "") -> bool:
    text = str(name or "").strip().lower()
    ctype = str(container_type or "").strip().lower()
    if not text:
        return False
    if text in {item.lower() for item in _WORLD_MODULE_CONTAMINATION_NAMES}:
        return True
    return ctype in {"timeline", "graph"} and any(
        token in text for token in ("时间线", "timeline", "关系", "relationship")
    )


def _world_category_path(category: str, name: str = "") -> list[str]:
    category = _normalize_world_category(name, category)
    labels = {
        "location": ["世界模型", "地理位置"],
        "organization": ["世界模型", "门派组织"],
        "faction": ["世界模型", "门派组织", "势力派系"],
        "item": ["世界模型", "物品与法器"],
        "artifact": ["世界模型", "物品与法器", "法器宝物"],
        "cultivation_method": ["世界模型", "功法与术法"],
        "rule": ["世界模型", "修炼境界与制度"],
        "system": ["世界模型", "修炼境界与制度"],
        "culture": ["世界模型", "文化与习俗"],
        "concept": ["世界模型", "概念与设定"],
        "custom": ["世界模型", "概念与设定"],
    }
    return labels.get(category, labels["concept"])


def _is_world_entity_candidate(name: str, candidate: dict | None = None) -> bool:
    cleaned = str(name or "").strip()
    if not cleaned:
        return False
    candidate = candidate or {}
    group_key = str(candidate.get("groupKey") or candidate.get("groupKey_update") or "").lower()
    story_function = str(candidate.get("story_function") or candidate.get("story_function_update") or "").lower()
    category = _normalize_world_category(cleaned, candidate.get("category") or candidate.get("world_category") or "")
    role_text = " ".join(str(candidate.get(field, "")) for field in ("role_in_story", "summary", "background", "notes", "aliases"))
    if category in {"organization", "faction"} and any(token in cleaned for token in _ORGANIZATION_HINTS):
        return True
    if group_key in {"organizations", "organization", "faction", "factions", "world", "locations"}:
        return True
    if story_function in {"organization", "faction", "location"}:
        return True
    if any(token in cleaned for token in _WORLD_ENTITY_NAME_PATTERNS):
        # Personal names such as 墨大夫 or 厉飞雨 should not match these suffixes.
        return len(cleaned) >= 3 and not any(title in cleaned for title in ("大夫", "师兄", "师姐", "师父", "师傅", "叔", "父", "母"))
    return any(token in role_text.lower() for token in ("organization", "sect", "faction", "location", "门派", "宗门", "帮派", "组织", "势力", "地点"))


def _add_world_candidate_to_registry(registry: dict, name: str, category: str, description: str = "", confidence: float = 0.72) -> None:
    name = str(name or "").strip()
    if not name:
        return
    normalized_category = _normalize_world_category(name, category)
    registry.setdefault("world", {})
    registry.setdefault("world_detailed", {})
    registry["world"][name] = normalized_category
    detail = registry["world_detailed"].setdefault(name, {
        "name": name,
        "category": normalized_category,
        "description": "",
        "container_hint": _world_container_key(normalized_category),
        "attributes": [],
        "confidence": confidence,
    })
    detail["category"] = _normalize_world_category(name, detail.get("category") or normalized_category)
    detail["container_hint"] = detail.get("container_hint") or _world_container_key(detail["category"])
    if description and not detail.get("description"):
        detail["description"] = description
    detail["confidence"] = max(float(detail.get("confidence", 0.7) or 0.7), confidence)


def _remove_world_entities_from_character_registry(registry: dict) -> dict:
    removed: dict[str, str] = {}
    for cid, entry in list(registry.get("characters", {}).items()):
        name = str(entry.get("canonical_name") or entry.get("name") or "").strip()
        if not _is_world_entity_candidate(name, entry):
            continue
        category = _normalize_world_category(name, entry.get("category") or "organization")
        _add_world_candidate_to_registry(
            registry,
            name,
            category,
            entry.get("summary") or entry.get("role_in_story") or "",
            float(entry.get("confidence", 0.72) or 0.72),
        )
        removed[cid] = name
        registry["characters"].pop(cid, None)
    if removed:
        for event in registry.get("events", {}).values():
            event["character_ids"] = [cid for cid in event.get("character_ids", []) if cid not in removed]
            event["character_names"] = [
                name for name in event.get("character_names", [])
                if _normal_key(name) not in {_normal_key(value) for value in removed.values()}
            ]
        registry.setdefault("world_entity_character_removals", {}).update(removed)
    return removed


def _seed_character_from_name(registry: dict, name: str, chunk_id: int, language: str, *, role_hint: str = "", confidence: float = 0.72) -> dict | None:
    name = str(name or "").strip()
    if not name or _resolve_character_id(name, registry) or _is_world_entity_candidate(name):
        return None
    char_id = f"char_{uuid.uuid4().hex[:8]}"
    summary = f"{name}在导入文本中被多处提及，需要后续确认角色卡。" if language == "zh" else f"{name} is mentioned in imported evidence and needs review."
    registry.setdefault("characters", {})[char_id] = _compact_character_card({
        "canonical_id": char_id,
        "canonical_name": name,
        "aliases": [],
        "first_seen_chunk": chunk_id,
        "notes": [role_hint or (f"[chunk {chunk_id}] Evidence-derived character seed.")],
        "confidence": confidence,
        "summary": summary,
        "background": "",
        "role_in_story": role_hint[:80],
        "physical_description": "",
        "personality_traits": [],
        "goals": [],
        "fears": [],
        "secrets": [],
        "speech_style": "",
        "arc_notes": "",
        "importance": "supporting" if confidence >= 0.74 else "minor",
        "groupKey": "allies_family" if any(token in role_hint for token in ("父", "母", "叔", "妹", "family")) else "minor_characters",
        "tag_ids": [],
        "open_questions": [f"确认{name}的角色功能与分组。" if language == "zh" else f"Confirm {name}'s role and group."],
    })
    return registry["characters"][char_id]


def _importance_sort_value(event: dict) -> tuple[float, float, str]:
    """Prefer high-impact events without letting confidence alone hide story beats."""
    importance = float(event.get("importanceScore", 0) or 0)
    confidence = float(event.get("confidence", 0) or 0)
    timeline_class = str(event.get("timelineClass", "")).strip()
    class_bonus = 8 if timeline_class == "canonical_event" else 0
    return (importance + class_bonus, confidence, str(event.get("title", "")))


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


_ZH_TAG_LABELS: dict[str, str] = {
    "protagonist": "主角", "main character": "主要角色", "main characters": "主要角色",
    "mentor": "师长", "mentors": "师长", "antagonist": "反派", "antagonists": "反派",
    "ally": "盟友", "allies": "盟友", "family": "家人", "friends": "友人",
    "minor character": "次要角色", "minor characters": "次要角色",
    "villain": "反派", "rival": "对手", "cultivator": "修士",
}


def _normalize_character_tag(tag: dict, source_language: str) -> tuple[dict | None, dict | None]:
    """Keep source tag evidence while guaranteeing a non-empty localized tag name."""
    candidate = dict(tag)
    raw_name = str(candidate.get("name", "")).strip()
    if not raw_name:
        return None, {"reason": "empty_tag_name", "source_tag": tag}
    if source_language != "zh" or not re.search(r"[A-Za-z]", raw_name):
        return candidate, None
    normalized = _ZH_TAG_LABELS.get(raw_name.lower())
    if not normalized:
        return None, {
            "reason": "unmapped_english_tag_for_chinese_source",
            "source_name": raw_name,
            "source_tag": tag,
        }
    candidate["name"] = normalized
    candidate["sourceName"] = raw_name
    candidate["normalization"] = "english_label_translated_to_chinese"
    return candidate, None


def _merge_evidence_values(existing: Any, incoming: Any) -> list[Any]:
    """Stable union for list-like evidence while preserving structured entries."""
    values = list(existing) if isinstance(existing, list) else ([existing] if existing else [])
    additions = list(incoming) if isinstance(incoming, list) else ([incoming] if incoming else [])
    seen = {json.dumps(value, ensure_ascii=False, sort_keys=True, default=str) for value in values}
    for value in additions:
        if not value:
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            values.append(value)
            seen.add(key)
    return values


def _entity_merge_decision(existing: dict, incoming: dict, import_id: str) -> dict:
    """Produce an auditable, field-specific merge plan without mutating canonical data."""
    decision: dict[str, Any] = {
        "contract": "EntityMergeDecision/v1",
        "import_id": import_id,
        "existing_id": str(existing.get("id", "")),
        "fields": {},
        "conflicts": [],
    }
    aliases = _merge_evidence_values(existing.get("aliases", []), incoming.get("aliases", []))
    canonical = str(incoming.get("canonical_name") or incoming.get("name") or "").strip()
    if canonical:
        aliases = _merge_evidence_values(aliases, [canonical])
    decision["fields"]["aliases"] = {"action": "union", "value": aliases, "source": "existing+import"}
    for field in ("background", "physical_description", "speech_style", "arc_notes"):
        old, new = str(existing.get(field, "") or "").strip(), str(incoming.get(field, "") or "").strip()
        merged = _merge_text_field(old, new)
        action = "preserve_existing" if not new or merged == old else "evidence_append"
        decision["fields"][field] = {"action": action, "value": merged, "source": "existing+import"}
        if old and new and merged != old and _normal_key(old) != _normal_key(new):
            decision["conflicts"].append({"field": field, "existing": old, "incoming": new, "resolution": "preserve_and_append"})
    for field in ("experience", "experiences", "personality_traits", "traits", "notes"):
        value = _merge_evidence_values(existing.get(field, []), incoming.get(field, []))
        if value:
            decision["fields"][field] = {"action": "union", "value": value, "source": "existing+import"}
    old_confidence = float(existing.get("importConfidence", existing.get("confidence", 0)) or 0)
    new_confidence = float(incoming.get("confidence", 0) or 0)
    decision["fields"]["confidence"] = {"action": "max", "value": max(old_confidence, new_confidence), "source": "existing+import"}
    return decision


def _artifact_dir(project_path: str | Path, import_run_id: str) -> Path:
    return Path(project_path) / "system" / "imports" / import_run_id


_RAW_SOURCE_EVIDENCE_FILENAME = "raw_source.txt"


def _stage_raw_source_evidence(state: ImportState) -> Path:
    """Atomically preserve the submitted source inside its project-local import run."""
    source_path = Path(str(state["source_file_path"]))
    source_bytes = source_path.read_bytes()
    evidence_path = _artifact_dir(state["project_path"], str(state.get("import_run_id", ""))) / _RAW_SOURCE_EVIDENCE_FILENAME
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    if evidence_path.exists():
        if evidence_path.read_bytes() != source_bytes:
            raise ValueError("Raw source evidence is immutable for an existing import run")
        return evidence_path
    fd, temporary_path = tempfile.mkstemp(prefix=".raw_source_", suffix=".tmp", dir=evidence_path.parent)
    try:
        with os.fdopen(fd, "wb") as temporary_file:
            temporary_file.write(source_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, evidence_path)
    except BaseException:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
    return evidence_path


def _write_import_artifact(project_path: str | Path, import_run_id: str, filename: str, payload: dict | list) -> str:
    directory = _artifact_dir(project_path, import_run_id)
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)


def persist_w1_usage_ledger(state: ImportState) -> dict[str, Any] | None:
    """Persist the authoritative provider-usage ledger once an import run exists."""
    project_path = state.get("project_path")
    import_run_id = state.get("import_run_id") or state.get("import_run_manifest", {}).get("import_run_id")
    session_id = str(state.get("session_id") or state.get("context", {}).get("session_id") or "")
    if not project_path or not import_run_id or not session_id:
        return None
    model = str(state.get("context", {}).get("model") or state.get("model") or "")
    ledger = authoritative_usage_ledger(session_id, model)
    directory = _artifact_dir(project_path, import_run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "usage_ledger.json"
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return ledger


def _chunk_cache_path(project_path: str | Path, import_run_id: str, chunk_id: int) -> Path:
    return _artifact_dir(project_path, import_run_id) / "chunks" / f"chunk_{chunk_id}.json"


def _prompt_window_cache_path(project_path: str | Path, import_run_id: str, window_id: str) -> Path:
    return _artifact_dir(project_path, import_run_id) / "windows" / f"{window_id}.json"


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
    if payload.get("prompt_window_contract") not in {"chapter_window_v1", "packed_chapter_window_v2"}:
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


def _read_prompt_window_cache(state: ImportState, window: dict) -> dict | None:
    import_run_id = state.get("import_run_id")
    window_id = str(window.get("id") or "")
    if not import_run_id or not window_id:
        return None
    path = _prompt_window_cache_path(state["project_path"], import_run_id, window_id)
    payload = _safe_read_json(path, None)
    if not isinstance(payload, dict):
        return None
    source_text = "".join(
        str(block.get("text", ""))
        for block in window.get("source_blocks", [])
        if isinstance(block, dict)
    )
    if payload.get("source_hash") != _sha256_text(source_text):
        return None
    if payload.get("prompt_profile") != (state.get("prompt_profile") or "balanced"):
        return None
    if payload.get("prompt_window_contract") != "packed_chapter_window_v2":
        return None
    prompts = payload.get("prompt_outputs")
    return prompts if isinstance(prompts, dict) else None


def _write_prompt_window_cache(state: ImportState, window: dict, prompt_outputs: dict) -> None:
    import_run_id = state.get("import_run_id")
    window_id = str(window.get("id") or "")
    if not import_run_id or not window_id:
        return
    source_text = "".join(
        str(block.get("text", ""))
        for block in window.get("source_blocks", [])
        if isinstance(block, dict)
    )
    path = _prompt_window_cache_path(state["project_path"], import_run_id, window_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "prompt_window_id": window_id,
            "chunk_ids": window.get("chunk_ids", []),
            "source_hash": _sha256_text(source_text),
            "prompt_profile": state.get("prompt_profile") or "balanced",
            "prompt_window_contract": "packed_chapter_window_v2",
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
_PACKED_WINDOW_TARGET_FILL_RATIO = 0.88



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
        "character_tags": _safe_read_json(
            entities / "character-tags.json",
            _safe_read_json(entities / "character_tags.json", []),
        ),
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


def _proposal_graph_existing_ids(snapshot: dict) -> dict[str, set[str]]:
    """Project snapshot IDs accepted by the proposal reference compiler."""
    collection_types = {
        "characters": "character",
        "character_tags": "character_tag",
        "timeline_events": "timeline_event",
        "timeline_branches": "timeline_branch",
        "world_items": "world_item",
        "world_containers": "world_container",
        "chapters": "chapter",
        "scenes": "scene",
    }
    return {
        entity_type: {
            str(item.get("id") or item.get("canonical_id") or "").strip()
            for item in snapshot.get(collection, [])
            if isinstance(item, dict) and str(item.get("id") or item.get("canonical_id") or "").strip()
        }
        for collection, entity_type in collection_types.items()
    }


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
    cross_validation = state.get("cross_validation") or {}
    if cross_validation:
        payload = {
            "status": "rolling_cross_validation",
            "duplicate_characters": cross_validation.get("duplicate_characters", [])[:12],
            "duplicate_events": cross_validation.get("duplicate_events", [])[:12],
            "missing_major_characters": cross_validation.get("missing_major_characters", [])[:12],
            "suspicious_groups": cross_validation.get("suspicious_groups", [])[:12],
            "contradictory_aliases": cross_validation.get("contradictory_aliases", [])[:12],
            "event_merge_recommendations": cross_validation.get("event_merge_recommendations", [])[:12],
            "warnings": cross_validation.get("warnings", [])[:12],
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

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


def _chapter_range_label(blocks: list[dict]) -> str:
    hints = [str(block.get("chapter_hint") or f"Segment {block.get('chunk_id', 0)}") for block in blocks]
    if not hints:
        return "Empty window"
    if len(hints) == 1:
        return hints[0]
    return f"{hints[0]} – {hints[-1]}"


def _render_prompt_window_text(
    *,
    digest_content: str,
    validation_content: str,
    total_budget: int,
    source_budget: int,
    source_blocks: list[dict],
) -> str:
    source_sections: list[str] = []
    for block in source_blocks:
        chapter_hint = str(block.get("chapter_hint") or f"Segment {block.get('chunk_id', 0)}")
        source_sections.append(
            f"### CHAPTER {block.get('chunk_id', '')}: {chapter_hint}\n"
            f"{block.get('text', '')}"
        )
    header = (
        "PROJECT_STRUCTURE_DIGEST:\n"
        f"{digest_content}\n\n"
        "PREVIOUS_VALIDATION_SUMMARY:\n"
        f"{validation_content}\n\n"
        "PROMPT_WINDOW_POLICY:\n"
        f"total_estimated_token_budget={total_budget}; "
        f"schema_policy_reserve_tokens={_SCHEMA_POLICY_RESERVE_TOKENS}; "
        f"source_budget_tokens={source_budget}; "
        "packed_chapter_window=true; preserve complete chapters; "
        "only paragraph-split a single oversized chapter; every extracted item must carry chapterRange/source chapter evidence.\n\n"
        f"SOURCE_CHAPTERS [{_chapter_range_label(source_blocks)}]:\n"
    )
    return header + "\n\n".join(source_sections)


def _source_blocks_from_chunks(chunks: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    for chunk in chunks:
        chunk_id = int(chunk.get("chunk_id", len(blocks)) or 0)
        source_text = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
        blocks.append({
            "chunk_id": chunk_id,
            "chapter_hint": str(chunk.get("chapter_hint") or f"Segment {chunk_id + 1}"),
            "text": source_text,
            "source_tokens": _estimate_tokens(source_text),
            "source_chars": len(source_text),
            "source_span": chunk.get("source_span"),
        })
    return blocks


def _window_source_span(state: ImportState | dict, source_blocks: list[dict]) -> dict:
    """Build one valid span for a prompt window from its raw-source blocks."""
    raw_source = str(state.get("source_text", "") or "")
    spans = [block.get("source_span") for block in source_blocks]
    if raw_source and spans:
        for span in spans:
            ok, errors = validate_source_span(span or {}, raw_source)
            if not ok:
                raise ValueError(f"Invalid source span while building prompt window: {errors}")
        return make_source_span(
            raw_source,
            min(span["absolute_start"] for span in spans),
            max(span["absolute_end"] for span in spans),
        )
    # Compatibility for historical checkpoints that did not retain raw source.
    # New W1 runs use the validated branch above.
    combined = "".join(str(block.get("text", "") or "") for block in source_blocks)
    return make_source_span(combined, 0, len(combined))


def _window_source_text(state: ImportState | dict, source_blocks: list[dict]) -> str:
    """Return exactly the raw substring identified by a window SourceSpan."""
    raw_source = str(state.get("source_text", "") or "")
    spans = [block.get("source_span") for block in source_blocks]
    if raw_source and spans and all(validate_source_span(span or {}, raw_source)[0] for span in spans):
        start = min(int(span["absolute_start"]) for span in spans)
        end = max(int(span["absolute_end"]) for span in spans)
        return raw_source[start:end]
    return "".join(str(block.get("text", "") or "") for block in source_blocks)


def _split_source_block_by_budget(state: ImportState | dict, block: dict, token_budget: int) -> list[dict]:
    """Split one oversized source block while retaining exact absolute spans."""
    parts = _split_text_by_paragraph_budget(str(block.get("text", "") or ""), token_budget)
    raw_source = str(state.get("source_text", "") or "")
    parent_span = block.get("source_span")
    if not raw_source or not parent_span or not validate_source_span(parent_span, raw_source)[0]:
        return [
            {
                **block,
                "text": part,
                "source_tokens": _estimate_tokens(part),
                "source_chars": len(part),
            }
            for part in parts
        ]

    parent_start = int(parent_span["absolute_start"])
    parent_end = int(parent_span["absolute_end"])
    cursor = parent_start
    result: list[dict] = []
    for part in parts:
        start = raw_source.find(part, cursor, parent_end)
        if start < 0:
            raise ValueError("Prompt-window split text could not be located in its SourceSpan")
        end = start + len(part)
        result.append({
            **block,
            "text": part,
            "source_tokens": _estimate_tokens(part),
            "source_chars": len(part),
            "source_span": make_source_span(raw_source, start, end),
        })
        cursor = end
    return result


def _make_prompt_window(
    state: ImportState,
    *,
    source_blocks: list[dict],
    part_index: int,
    split_reason: str,
    digest_content: str,
    validation_content: str,
    total_budget: int,
    source_budget: int,
    digest_tokens: int,
    validation_tokens: int,
) -> dict:
    window_text = _render_prompt_window_text(
        digest_content=digest_content,
        validation_content=validation_content,
        total_budget=total_budget,
        source_budget=source_budget,
        source_blocks=source_blocks,
    )
    chunk_ids = [int(block.get("chunk_id", 0) or 0) for block in source_blocks]
    source_tokens = sum(int(block.get("source_tokens", 0) or 0) for block in source_blocks)
    source_chars = sum(int(block.get("source_chars", 0) or 0) for block in source_blocks)
    fill_ratio = round(source_tokens / max(source_budget, 1), 4)
    source_text = _window_source_text(state, source_blocks)
    return {
        "id": _stable_id(
            "pwin",
            state.get("import_run_id") or "import",
            ",".join(str(chunk_id) for chunk_id in chunk_ids),
            part_index,
            _sha256_text("".join(str(block.get("text", "")) for block in source_blocks))[:16],
        ),
        "chunk_ids": chunk_ids,
        "chapter_range": _chapter_range_label(source_blocks),
        # `text` is the exact source payload identified by source_span. The
        # rendered prompt is retained separately because its policy header is
        # not part of the imported raw source.
        "text": source_text,
        "source_text": source_text,
        "prompt_text": window_text,
        "source_blocks": source_blocks,
        "estimated_tokens": _estimate_tokens(window_text) + _SCHEMA_POLICY_RESERVE_TOKENS,
        "source_token_estimate": source_tokens,
        "source_chars": source_chars,
        "digest_token_estimate": digest_tokens,
        "validation_token_estimate": validation_tokens,
        "schema_policy_reserve_tokens": _SCHEMA_POLICY_RESERVE_TOKENS,
        "total_token_budget": total_budget,
        "source_budget_tokens": source_budget,
        "target_fill_ratio": _PACKED_WINDOW_TARGET_FILL_RATIO,
        "fill_ratio": fill_ratio,
        "split_reason": split_reason,
        "source_span": _window_source_span(state, source_blocks),
    }


def _refresh_prompt_window_text(state: ImportState, window: dict, digest: dict) -> dict:
    profile = state.get("prompt_profile") or state.get("context", {}).get("prompt_profile", "balanced")
    total_budget = _prompt_total_token_budget(profile)
    digest_content = _fit_text_to_token_budget(str(digest.get("content", "")), _DIGEST_RESERVE_TOKENS)
    validation_content = _fit_text_to_token_budget(_previous_validation_summary(state), _VALIDATION_RESERVE_TOKENS)
    source_budget = max(
        total_budget
        - _SCHEMA_POLICY_RESERVE_TOKENS
        - _estimate_tokens(digest_content)
        - _VALIDATION_RESERVE_TOKENS,
        1_000,
    )
    source_blocks = [dict(block) for block in window.get("source_blocks", []) if isinstance(block, dict)]
    if not source_blocks:
        return dict(window)
    refreshed = dict(window)
    refreshed["prompt_text"] = _render_prompt_window_text(
        digest_content=digest_content,
        validation_content=validation_content,
        total_budget=total_budget,
        source_budget=source_budget,
        source_blocks=source_blocks,
    )
    refreshed["validation_token_estimate"] = _estimate_tokens(validation_content)
    refreshed["estimated_tokens"] = _estimate_tokens(refreshed["prompt_text"]) + _SCHEMA_POLICY_RESERVE_TOKENS
    refreshed["source_budget_tokens"] = source_budget
    refreshed["fill_ratio"] = round(
        int(refreshed.get("source_token_estimate", 0) or 0) / max(source_budget, 1),
        4,
    )
    return refreshed


def _build_prompt_windows(state: ImportState, chunks: list[dict], digest: dict) -> list[dict]:
    profile = state.get("prompt_profile") or state.get("context", {}).get("prompt_profile", "balanced")
    total_budget = _prompt_total_token_budget(profile)
    validation_summary = _previous_validation_summary(state)
    digest_content = _fit_text_to_token_budget(str(digest.get("content", "")), _DIGEST_RESERVE_TOKENS)
    validation_content = _fit_text_to_token_budget(validation_summary, _VALIDATION_RESERVE_TOKENS)
    digest_tokens = _estimate_tokens(digest_content)
    validation_tokens = _estimate_tokens(validation_content)
    # Pack against the full validation reserve, not the current summary length.
    # Otherwise the first window can overfill source text and later rolling
    # validation summaries can push refreshed prompts above the hard 256k cap.
    source_budget = max(total_budget - _SCHEMA_POLICY_RESERVE_TOKENS - digest_tokens - _VALIDATION_RESERVE_TOKENS, 1_000)
    windows: list[dict] = []

    current_blocks: list[dict] = []
    current_tokens = 0

    def flush_current() -> None:
        nonlocal current_blocks, current_tokens
        if not current_blocks:
            return
        windows.append(_make_prompt_window(
            state,
            source_blocks=current_blocks,
            part_index=len(windows),
            split_reason="packed_complete_chapters" if len(current_blocks) > 1 else "complete_chapter",
            digest_content=digest_content,
            validation_content=validation_content,
            total_budget=total_budget,
            source_budget=source_budget,
            digest_tokens=digest_tokens,
            validation_tokens=validation_tokens,
        ))
        current_blocks = []
        current_tokens = 0

    for block in _source_blocks_from_chunks(chunks):
        block_tokens = int(block.get("source_tokens", 0) or 0)
        if block_tokens > source_budget:
            flush_current()
            part_blocks = _split_source_block_by_budget(state, block, source_budget)
            for part_index, part_block in enumerate(part_blocks):
                part_block["chapter_hint"] = f"{block.get('chapter_hint')} part {part_index + 1}/{len(part_blocks)}"
                windows.append(_make_prompt_window(
                    state,
                    source_blocks=[part_block],
                    part_index=part_index,
                    split_reason="single_oversized_chapter_paragraph_split",
                    digest_content=digest_content,
                    validation_content=validation_content,
                    total_budget=total_budget,
                    source_budget=source_budget,
                    digest_tokens=digest_tokens,
                    validation_tokens=validation_tokens,
                ))
            continue

        if current_blocks and current_tokens + block_tokens > source_budget:
            flush_current()
        current_blocks.append(block)
        current_tokens += block_tokens

    flush_current()
    return windows


# ── Supervisor windowing ────────────────────────────────────────────────────────

# Estimated output tokens per chapter used for pre-flight budget checking.
# Formula: 1.5 chars × 120 tokens + 3 events × 80 tokens + 2 world × 50 tokens
_SUPERVISOR_TOKENS_PER_CHAPTER: int = int(1.5 * 120 + 3 * 80 + 2 * 50)
_SUPERVISOR_OUTPUT_BUDGET_THRESHOLD: int = 3_500


def _estimate_window_output_tokens(window: dict, profile: str = "balanced") -> int:
    """Estimate LLM output tokens for a supervised prompt window."""
    from sidecar.models.state import PROFILE_CONFIGS
    config = PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS["balanced"])
    chapters_per_window = config.get("chapters_per_window", 12)
    chapter_count = len(window.get("chunk_ids", [])) or max(chapters_per_window, 1)
    return chapter_count * _SUPERVISOR_TOKENS_PER_CHAPTER


def _build_supervised_prompt_windows(state: ImportState, chunks: list[dict], digest: dict) -> list[dict]:
    """Chapter-count-aware windowing for the supervisor path.

    Primary constraint: chapters_per_window from profile_config.
    Secondary constraint: input_window_budget source tokens (hard cap).

    Differences from _build_prompt_windows:
    - Groups chunks into batches of chapters_per_window instead of greedily
      packing until the token budget is exhausted.
    - Pre-flight: if a batch's estimated output tokens > _SUPERVISOR_OUTPUT_BUDGET_THRESHOLD,
      halves the batch recursively until within budget.
    - Writes output_token_budget onto each window dict.
    """
    from sidecar.models.state import PROFILE_CONFIGS

    profile = state.get("prompt_profile") or state.get("context", {}).get("prompt_profile", "balanced")
    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS["balanced"])
    chapters_per_window: int = profile_config.get("chapters_per_window", 12)
    input_token_budget: int = profile_config.get("input_window_budget", 48_000)
    output_token_budget: int = profile_config.get("output_token_budget", 4_000)

    validation_summary = _previous_validation_summary(state)
    # digest_content (full token-clipped) is used only in the window header fallback;
    # for source budget computation, use the 8000-char clip that extract_window /
    # _rolling_window_context actually sends to the model — this avoids reserving
    # ~20k tokens that never reach the prompt, allowing larger source windows.
    _raw_digest_str = str(digest.get("content", ""))
    digest_content = _fit_text_to_token_budget(_raw_digest_str, _DIGEST_RESERVE_TOKENS)
    validation_content = _fit_text_to_token_budget(validation_summary, _VALIDATION_RESERVE_TOKENS)
    digest_tokens = _estimate_tokens(_raw_digest_str[:8000])   # matches _rolling_window_context clip
    validation_tokens = _estimate_tokens(validation_content)

    import_run_id = state.get("import_run_id") or "import"
    source_hash = state.get("import_run_manifest", {}).get("source_hash", "")[:8]

    windows: list[dict] = []

    def _make_windows_from_batch(
        batch: list[dict],
        late_zone: bool = False,
        effective_cpw: int = 0,
        iteration: int = 0,
    ) -> list[dict]:
        """Recursively split a chunk batch if it exceeds the output budget."""
        if not batch:
            return []
        est_output = len(batch) * _SUPERVISOR_TOKENS_PER_CHAPTER
        if est_output > _SUPERVISOR_OUTPUT_BUDGET_THRESHOLD and len(batch) > 1 and iteration < 4:
            mid = max(1, len(batch) // 2)
            return _make_windows_from_batch(batch[:mid], late_zone, effective_cpw, iteration + 1) + \
                   _make_windows_from_batch(batch[mid:], late_zone, effective_cpw, iteration + 1)

        chunk_ids = [int(c.get("chunk_id", 0)) for c in batch]
        source_blocks = _source_blocks_from_chunks(batch)
        # Prefer the raw contiguous source slice, which is the only text a
        # SourceSpan can faithfully reconstruct. Compatibility checkpoints fall
        # back to the original chunk concatenation.
        source_text = _window_source_text(state, source_blocks)
        chapter_hints = [str(c.get("chapter_hint") or f"Segment {c.get('chunk_id', 0) + 1}") for c in batch]
        chapter_range = f"{chapter_hints[0]}" if len(chapter_hints) == 1 else f"{chapter_hints[0]}–{chapter_hints[-1]}"

        source_budget = max(input_token_budget - _SCHEMA_POLICY_RESERVE_TOKENS - digest_tokens - validation_tokens, 1_000)
        batch_block = {
            "chunk_id": chunk_ids[0] if chunk_ids else 0,
            "chapter_hint": chapter_range,
            "text": source_text,
            "source_span": _window_source_span(state, source_blocks),
        }
        part_blocks = _split_source_block_by_budget(state, batch_block, source_budget)

        batch_windows: list[dict] = []
        for part_idx, part_block in enumerate(part_blocks):
            part = str(part_block["text"])
            header = (
                "PROJECT_STRUCTURE_DIGEST:\n"
                f"{digest_content}\n\n"
                "PREVIOUS_VALIDATION_SUMMARY:\n"
                f"{validation_content}\n\n"
                "PROMPT_WINDOW_POLICY:\n"
                f"chapters_per_window={chapters_per_window}; "
                f"input_window_budget={input_token_budget}; "
                f"output_token_budget={output_token_budget}; "
                "supervisor-managed windowing.\n\n"
                f"SOURCE_CHAPTERS [{chapter_range}]:\n"
            )
            window_text = header + part
            split_reason = "complete_chapter_batch" if len(part_blocks) == 1 else "oversized_batch_paragraph_split"
            win_id = _stable_id("pwin", import_run_id, *chunk_ids, part_idx, source_hash, iteration)
            source_token_estimate = _estimate_tokens(part)
            estimated_input_tokens = _estimate_tokens(window_text) + _SCHEMA_POLICY_RESERVE_TOKENS
            batch_windows.append({
                "id": win_id,
                "chunk_ids": chunk_ids,
                "chapter_range": chapter_range if len(part_blocks) == 1 else f"{chapter_range} part {part_idx + 1}/{len(part_blocks)}",
                "text": part,
                "source_text": part,
                "prompt_text": window_text,
                "estimated_tokens": estimated_input_tokens,
                "estimated_input_tokens": estimated_input_tokens,
                "total_token_budget": input_token_budget,
                "source_budget_tokens": source_budget,
                "source_token_estimate": source_token_estimate,
                "source_chars": len(part),
                "digest_token_estimate": digest_tokens,
                "validation_token_estimate": validation_tokens,
                "project_digest_token_estimate": digest_tokens,
                "validation_summary_token_estimate": validation_tokens,
                "schema_policy_reserve_tokens": _SCHEMA_POLICY_RESERVE_TOKENS,
                "fill_ratio": round(source_token_estimate / max(source_budget, 1), 4),
                "split_reason": split_reason,
                "source_span": part_block.get("source_span") or _window_source_span(state, source_blocks),
                "output_token_budget": output_token_budget,
                "late_window_cap_applied": late_zone,
                "late_window_threshold": late_threshold,
                "late_chapters_per_window": late_cpw,
                "effective_chapters_per_window": effective_cpw or len(batch),
                "chapters_per_window_config": chapters_per_window,
            })
        return batch_windows

    # Group chunks into batches; apply tighter cap for late (last 25%) chapters
    total_chunks = len(chunks)
    late_threshold = max(1, int(total_chunks * 0.75))
    late_cpw = max(3, chapters_per_window // 2) if chapters_per_window >= 6 else chapters_per_window

    i = 0
    while i < total_chunks:
        effective_cpw = late_cpw if i >= late_threshold else chapters_per_window
        late_zone = i >= late_threshold
        batch = chunks[i: i + effective_cpw]
        windows.extend(_make_windows_from_batch(batch, late_zone=late_zone, effective_cpw=effective_cpw))
        i += effective_cpw

    return windows


def _prompt_window_manifest_entry(window: dict) -> dict:
    estimated_input_tokens = int(window.get("estimated_input_tokens", window.get("estimated_tokens", 0)) or 0)
    project_digest_tokens = int(
        window.get("project_digest_token_estimate", window.get("digest_token_estimate", 0)) or 0
    )
    validation_summary_tokens = int(
        window.get("validation_summary_token_estimate", window.get("validation_token_estimate", 0)) or 0
    )
    entry = {
        "id": window.get("id"),
        "chapter_range": window.get("chapter_range"),
        "chunk_ids": window.get("chunk_ids", []),
        "estimated_tokens": window.get("estimated_tokens", 0),
        "estimated_input_tokens": estimated_input_tokens,
        "total_token_budget": window.get("total_token_budget", 0),
        "source_budget_tokens": window.get("source_budget_tokens", 0),
        "source_token_estimate": window.get("source_token_estimate", 0),
        "source_chars": window.get("source_chars", 0),
        "digest_token_estimate": window.get("digest_token_estimate", 0),
        "validation_token_estimate": window.get("validation_token_estimate", 0),
        "project_digest_token_estimate": project_digest_tokens,
        "validation_summary_token_estimate": validation_summary_tokens,
        "schema_policy_reserve_tokens": window.get("schema_policy_reserve_tokens", 0),
        "target_fill_ratio": window.get("target_fill_ratio", 0),
        "fill_ratio": window.get("fill_ratio", 0),
        "split_reason": window.get("split_reason", ""),
        "source_span": window.get("source_span", {}),
        "late_window_cap_applied": window.get("late_window_cap_applied", False),
        "late_window_threshold": window.get("late_window_threshold", 0),
        "late_chapters_per_window": window.get("late_chapters_per_window", 0),
        "effective_chapters_per_window": window.get("effective_chapters_per_window", 0),
        "chapters_per_window_config": window.get("chapters_per_window_config", 0),
    }
    prompt_variant_manifest = (
        window.get("prompt_variant_manifest")
        or window.get("selected_prompt_variants")
        or window.get("selected_prompt_variant_manifest")
    )
    if prompt_variant_manifest:
        entry["prompt_variant_manifest"] = prompt_variant_manifest
    return entry


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


_CROSS_VALIDATION_FIELDS = (
    "duplicate_characters",
    "duplicate_events",
    "missing_major_characters",
    "suspicious_groups",
    "contradictory_aliases",
    "event_merge_recommendations",
    "warnings",
)


def _json_for_prompt(value: Any, token_budget: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _fit_text_to_token_budget(text, token_budget)


def _normalize_cross_validation_artifact(payload: dict, import_run_id: str, window: dict | None = None) -> dict:
    artifact: dict[str, Any] = {"import_run_id": import_run_id}
    window_id = window.get("id") if isinstance(window, dict) else None
    for field in _CROSS_VALIDATION_FIELDS:
        values = payload.get(field, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        normalized_values: list[Any] = []
        for value in values:
            if isinstance(value, dict) and window_id:
                normalized_values.append({"source_prompt_window_id": window_id, **value})
            else:
                normalized_values.append(value)
        artifact[field] = normalized_values
    return artifact


def _merge_cross_validation_artifacts(existing: dict | None, incoming: dict | None, import_run_id: str) -> dict:
    merged: dict[str, Any] = {"import_run_id": import_run_id}
    for field in _CROSS_VALIDATION_FIELDS:
        seen: set[str] = set()
        merged[field] = []
        for source in (existing or {}, incoming or {}):
            values = source.get(field, []) if isinstance(source, dict) else []
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            for value in values:
                key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                merged[field].append(value)
        # Keep the rolling summary bounded; full prompt outputs remain in window artifacts.
        merged[field] = merged[field][-40:]
    return merged


async def _run_cross_validation_for_window(
    llm: ChatOpenAI,
    state: ImportState,
    *,
    window: dict,
    digest: dict,
    prompt_outputs: dict,
    cross_validation: dict | None,
    session_id: str = "",
) -> dict:
    import_run_id = state.get("import_run_id") or state.get("import_run_manifest", {}).get("import_run_id") or "import"
    prompt_template = W1_CROSS_VALIDATE_IMPORT + """

## Actual Artifacts For This Review
PROJECT_DIGEST_JSON:
{project_digest_json}

PREVIOUS_VALIDATION_SUMMARY_JSON:
{previous_validation_summary_json}

PROMPT_WINDOW_MANIFEST_JSON:
{prompt_window_manifest_json}

CHARACTER_CANDIDATES_JSON:
{character_candidates_json}

EVENT_CANDIDATES_JSON:
{event_candidates_json}

RELATIONSHIP_CANDIDATES_JSON:
{relationship_candidates_json}

SCENE_CANDIDATES_JSON:
{scene_candidates_json}
"""
    rendered_state = {**state, "cross_validation": cross_validation or {}}
    raw_artifact = await _invoke_json_prompt(
        llm,
        prompt_template,
        session_id=session_id,
        project_digest_json=_fit_text_to_token_budget(str(digest.get("content", "")), _DIGEST_RESERVE_TOKENS),
        previous_validation_summary_json=_fit_text_to_token_budget(_previous_validation_summary(rendered_state), _VALIDATION_RESERVE_TOKENS),
        prompt_window_manifest_json=_json_for_prompt(_prompt_window_manifest_entry(window), 2_000),
        character_candidates_json=_json_for_prompt(prompt_outputs.get("character", {}), 12_000),
        event_candidates_json=_json_for_prompt(prompt_outputs.get("event", {}), 12_000),
        relationship_candidates_json=_json_for_prompt(prompt_outputs.get("relationship", {}), 8_000),
        scene_candidates_json=_json_for_prompt(prompt_outputs.get("scene", {}), 8_000),
    )
    return _normalize_cross_validation_artifact(raw_artifact, import_run_id, window)


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
    search_offset = 0
    for index, chunk in enumerate(chunks):
        raw = chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content", "")
        chapter_hint = chunk.get("chapter_hint") or f"Segment {index + 1}"
        segment_id = _stable_id("seg", import_run_id, index, chapter_hint, _sha256_text(raw)[:16])
        candidate_start = int(chunk.get("char_start", search_offset) or search_offset)
        if text[candidate_start:candidate_start + len(raw)] == raw:
            start = candidate_start
        else:
            start = text.find(raw, search_offset)
        if start < 0:
            raise ValueError(f"Cannot reconstruct source span for import segment {index}")
        end = start + len(raw)
        search_offset = end
        source_span = make_source_span(text, start, end)
        chunk["segment_id"] = segment_id
        chunk["source_span"] = source_span
        segments.append({
            "id": segment_id,
            "level": "chapter" if chunk.get("chapter_hint") else "window",
            "title": chapter_hint,
            "chunk_id": index,
            "chapter_index": index,
            "source_span": source_span,
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


def _build_supervisor_evidence_cards(state: ImportState | dict) -> dict:
    """Build final-entity cards with hash-checked, claim-local raw-source snippets."""
    import_run_id = str(state.get("import_run_id") or "import")
    raw_source = str(state.get("source_text", "") or "")
    if not raw_source:
        source_path = Path(str(state.get("source_file_path", "") or ""))
        if source_path.is_file():
            raw_source = source_path.read_text(encoding="utf-8")
    raw_source_hash = _sha256_text(raw_source) if raw_source else ""
    windows = {str(window.get("id")): window for window in state.get("prompt_windows", []) if window.get("id")}
    manifest_segments = {
        str(segment.get("chunk_id")): segment
        for segment in state.get("import_run_manifest", {}).get("segments", [])
        if isinstance(segment, dict) and segment.get("chunk_id") is not None
    }
    registry = state.get("entity_registry", {}) or {}
    updated_registry = {key: dict(value) if isinstance(value, dict) else value for key, value in registry.items()}
    cards: list[dict] = []

    def _card_id(kind: str, entity_id: str, window_id: str) -> str:
        return _stable_id("evc", import_run_id, "supervisor", kind, entity_id, window_id)

    def _source_metadata(window_id: str) -> dict:
        window = windows.get(window_id, {})
        chunk_ids = list(window.get("chunk_ids", []))
        segments = [manifest_segments[str(chunk_id)] for chunk_id in chunk_ids if str(chunk_id) in manifest_segments]
        span = _validated_span(window.get("source_span"))
        if not span and raw_source and segments:
            segment_spans = [_validated_span(segment.get("source_span")) for segment in segments]
            if all(segment_spans) and len(segment_spans) == len(chunk_ids):
                span = make_source_span(
                    raw_source,
                    min(segment_span["absolute_start"] for segment_span in segment_spans),
                    max(segment_span["absolute_end"] for segment_span in segment_spans),
                )
        return {
            "source_prompt_window_id": window_id,
            "source_chunk_ids": chunk_ids,
            "source_chunk_id": chunk_ids[0] if chunk_ids else None,
            "source_segment_ids": [segment.get("id") for segment in segments if segment.get("id")],
            "source_segment_id": segments[0].get("id") if len(segments) == 1 else "",
            "source_span": span or {},
        }

    def _validated_span(span: object) -> dict | None:
        if not isinstance(span, dict) or not raw_source:
            return None
        try:
            start, end = int(span["absolute_start"]), int(span["absolute_end"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (0 <= start < end <= len(raw_source)):
            return None
        excerpt = raw_source[start:end]
        if span.get("raw_source_hash") != raw_source_hash or span.get("substring_hash") != _sha256_text(excerpt):
            return None
        return {"raw_source_hash": raw_source_hash, "absolute_start": start, "absolute_end": end, "substring_hash": _sha256_text(excerpt)}

    def _values(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str) and item.strip()]
        return []

    def _claim_local_source(value: dict, kind: str, span: dict) -> tuple[str, dict] | None:
        """Return a bounded source clause, preferring explicit evidence before names."""
        start, end = span["absolute_start"], span["absolute_end"]
        region = raw_source[start:end]
        explicit = [
            *(_values(value.get("evidence"))),
            *(_values(value.get("notes"))),
            str(value.get("summary") or value.get("description") or ""),
        ]
        names = _values(value.get("aliases")) + [
            str(value.get("canonical_name") or value.get("name") or value.get("title") or ""),
        ]
        anchors = [re.sub(r"^\[window [^\]]+\]\s*", "", item).strip() for item in explicit]
        # A character card's identity is a claim in its own right. Prefer it to
        # a generated note so the bound snippet actually identifies the card.
        if kind == "character":
            anchors = [*names, *anchors]
        else:
            anchors.extend(names)

        def _anchor_position(anchor: str) -> int:
            position = region.find(anchor)
            if position >= 0:
                return position
            # Generated summaries often paraphrase a source clause. Search all
            # meaningful contiguous fragments, not just a summary prefix, but
            # never emit text unless one of those fragments is in raw source.
            normalized = re.sub(r"\s+", "", anchor)
            max_width = min(24, len(normalized))
            for width in range(max_width, 1, -1):
                for offset in range(len(normalized) - width + 1):
                    fragment = normalized[offset:offset + width]
                    if len(re.sub(r"[^\w\u4e00-\u9fff]", "", fragment)) < 2:
                        continue
                    position = region.find(fragment)
                    if position >= 0:
                        return position
            return -1

        match_start = -1
        for anchor in anchors:
            if len(anchor) < 2:
                continue
            match_start = _anchor_position(anchor)
            if match_start >= 0:
                break
        if match_start < 0:
            return None
        absolute = start + match_start
        left = max(start, max(raw_source.rfind(mark, start, absolute) + 1 for mark in "\n。！？.!?"))
        right_candidates = [raw_source.find(mark, absolute, end) for mark in "\n。！？.!?"]
        right = min((point for point in right_candidates if point >= 0), default=end)
        if right < end:
            right += 1
        if right - left > 480:
            left = max(start, absolute - 160)
            right = min(end, absolute + 320)
        snippet = raw_source[left:right].strip()
        if not snippet:
            return None
        local_start = raw_source.find(snippet, left, right)
        local_end = local_start + len(snippet)
        return snippet, {
            "raw_source_hash": raw_source_hash,
            "absolute_start": local_start,
            "absolute_end": local_end,
            "substring_hash": _sha256_text(raw_source[local_start:local_end]),
        }

    def _window_ids_for_item(item: dict) -> list[str]:
        """Resolve candidate provenance to real prompt windows without inventing spans."""
        explicit_ids = [
            *[str(window_id) for window_id in (item.get("source_prompt_window_ids") or [])],
            str(item.get("source_prompt_window_id") or ""),
        ]
        for note in _values(item.get("notes")):
            explicit_ids.extend(re.findall(r"\[window\s+([^\]\s]+)", note))
        chunk_ids = {
            str(chunk_id)
            for chunk_id in [
                *(item.get("source_chunk_ids") or []),
                item.get("source_chunk_id"),
                item.get("chunk_id"),
                item.get("first_seen_chunk"),
            ]
            if chunk_id is not None and str(chunk_id)
        }
        resolved: list[str] = []
        for window_id, window in windows.items():
            if window_id in explicit_ids:
                resolved.append(window_id)
                continue
            if chunk_ids & {str(chunk_id) for chunk_id in window.get("chunk_ids", [])}:
                resolved.append(window_id)
                continue
            chapter_text = " ".join(
                str(item.get(key) or "")
                for key in ("chapter_range", "chapterRange", "time")
            )
            chapter_labels = re.findall(r"第[一二三四五六七八九十百千0-9]+章", chapter_text)
            if any(label in str(window.get("chapter_range") or "") for label in chapter_labels):
                resolved.append(window_id)
        resolved = list(dict.fromkeys(window_id for window_id in resolved if window_id in windows))
        if resolved:
            return resolved
        # Final canonicalization can predate provenance fields. Recover only
        # cards whose note/title can be anchored in a real prompt window below.
        return list(windows)

    def _append_cards(kind: str, items: dict) -> None:
        for entity_id, value in items.items():
            if not isinstance(value, dict):
                continue
            window_ids = _window_ids_for_item(value)
            if not window_ids:
                continue
            refs: list[str] = []
            seen_substrings: set[str] = set()
            for window_id in window_ids:
                source = _source_metadata(window_id)
                span = _validated_span(source.get("source_span"))
                if not span:
                    continue
                claim = _claim_local_source(value, kind, span)
                if not claim:
                    continue
                snippet, source_span = claim
                substring_hash = source_span["substring_hash"]
                if substring_hash in seen_substrings:
                    continue
                seen_substrings.add(substring_hash)
                card_id = _stable_id("evc", import_run_id, "supervisor", kind, entity_id, substring_hash)
                segment_id = next((
                    str(segment.get("id")) for segment in manifest_segments.values()
                    if _validated_span(segment.get("source_span"))
                    and int(segment["source_span"]["absolute_start"]) <= source_span["absolute_start"]
                    and source_span["absolute_end"] <= int(segment["source_span"]["absolute_end"])
                ), "")
                refs.append(card_id)
                cards.append({
                    "id": card_id,
                    "card_id": card_id,
                    "entity_id": str(entity_id),
                    "entityId": str(entity_id),
                    "kind": kind,
                    **source,
                    "source_segment_id": segment_id,
                    "source_span": source_span,
                    "snippets": [snippet],
                    "summary": str(value.get("summary") or value.get("description") or value.get("title") or value.get("canonical_name") or ""),
                    "candidate_names": [str(value.get("canonical_name") or value.get("name") or value.get("title") or entity_id)],
                    "candidate_ids": [str(entity_id)],
                    "confidence": float(value.get("confidence", 0.7) or 0.7),
                    "uncertainty": "",
                    "raw": value,
                })
            item = dict(value)
            item["evidence_refs"] = list(dict.fromkeys(refs))
            if refs:
                first_card = next(card for card in cards if card["card_id"] == refs[0])
                item["source_span"] = first_card["source_span"]
                item["source_segment_id"] = first_card["source_segment_id"]
                item["source_chunk_id"] = first_card["source_chunk_id"]
            else:
                # Final canonical objects must never carry a stale window span into proposals.
                item.pop("source_span", None)
                item.pop("source_segment_id", None)
                item.pop("source_chunk_id", None)
            items[entity_id] = item

    for kind, domain in (("character", "characters"), ("event", "events"), ("world", "world_detailed")):
        items = dict(updated_registry.get(domain, {}) or {})
        _append_cards(kind, items)
        updated_registry[domain] = items

    raw_relationships: list[dict] = []
    for index, relationship in enumerate(state.get("raw_relationships", []) or []):
        if not isinstance(relationship, dict):
            continue
        item = dict(relationship)
        relationship_id = str(item.get("id") or _stable_id(
            "relationship", item.get("source_character_name", ""), item.get("target_character_name", ""), index
        ))
        window_ids = _window_ids_for_item(item)
        refs: list[str] = []
        seen_substrings: set[str] = set()
        for window_id in window_ids:
            source = _source_metadata(window_id)
            span = _validated_span(source.get("source_span"))
            if not span:
                continue
            claim = _claim_local_source(item, "relationship", span)
            if not claim:
                continue
            snippet, source_span = claim
            substring_hash = source_span["substring_hash"]
            if substring_hash in seen_substrings:
                continue
            seen_substrings.add(substring_hash)
            card_id = _stable_id("evc", import_run_id, "supervisor", "relationship", relationship_id, substring_hash)
            segment_id = next((
                str(segment.get("id")) for segment in manifest_segments.values()
                if _validated_span(segment.get("source_span"))
                and int(segment["source_span"]["absolute_start"]) <= source_span["absolute_start"]
                and source_span["absolute_end"] <= int(segment["source_span"]["absolute_end"])
            ), "")
            refs.append(card_id)
            cards.append({
                "id": card_id,
                "card_id": card_id,
                "entity_id": relationship_id,
                "entityId": relationship_id,
                "kind": "relationship",
                **source,
                "source_segment_id": segment_id,
                "source_span": source_span,
                "snippets": [snippet],
                "summary": str(item.get("description", "")),
                "candidate_names": [str(item.get("source_character_name", "")), str(item.get("target_character_name", ""))],
                "candidate_ids": [str(item.get("source_candidate_id", "")), str(item.get("target_candidate_id", ""))],
                "confidence": float(item.get("confidence", 0.7) or 0.7),
                "uncertainty": "",
                "raw": item,
            })
        item["id"] = relationship_id
        item["evidence_refs"] = list(dict.fromkeys(refs))
        if refs:
            first_card = next(card for card in cards if card["card_id"] == refs[0])
            item["source_span"] = first_card["source_span"]
            item["source_segment_id"] = first_card["source_segment_id"]
            item["source_chunk_id"] = first_card["source_chunk_id"]
        else:
            item.pop("source_span", None)
            item.pop("source_segment_id", None)
            item.pop("source_chunk_id", None)
        raw_relationships.append(item)

    return {
        "entity_registry": updated_registry,
        "raw_relationships": raw_relationships,
        "evidence_cards": cards,
    }


def _finalize_registry_for_proposal_staging(state: ImportState | dict) -> dict:
    """Apply the final deterministic character remap before review and proposal staging."""
    original_registry = state.get("entity_registry", {}) or {}
    registry = {
        **original_registry,
        "characters": {
            cid: dict(entry) for cid, entry in (original_registry.get("characters", {}) or {}).items()
            if isinstance(entry, dict)
        },
        "events": {
            eid: dict(entry) for eid, entry in (original_registry.get("events", {}) or {}).items()
            if isinstance(entry, dict)
        },
    }
    relationships = [dict(item) if isinstance(item, dict) else item for item in state.get("relationships", []) or []]
    characters = registry["characters"]
    character_id_map = dict(registry.get("character_id_map", {}) or {})
    by_identity: dict[str, str] = {}
    importance_rank = {"core": 4, "major": 3, "supporting": 2, "minor": 1}

    for cid, entry in list(characters.items()):
        identities = [
            _normal_key(entry.get("canonical_name") or entry.get("name") or ""),
            *[_normal_key(alias) for alias in entry.get("aliases", []) if alias],
        ]
        primary_id = next((by_identity[key] for key in identities if key and key in by_identity), "")
        if not primary_id:
            for key in identities:
                if key:
                    by_identity.setdefault(key, cid)
            continue
        primary = characters[primary_id]
        for key in ("aliases", "notes", "open_questions", "tag_ids", "evidence_refs", "source_prompt_window_ids", "source_chunk_ids", "source_segment_ids"):
            primary[key] = list(dict.fromkeys([*(primary.get(key) or []), *(entry.get(key) or [])]))
        primary["aliases"] = list(dict.fromkeys([
            *primary["aliases"], entry.get("canonical_name") or entry.get("name") or "",
        ]))
        primary["summary"] = _merge_text_field(primary.get("summary", ""), entry.get("summary", ""))
        primary["confidence"] = max(float(primary.get("confidence", 0.7) or 0.7), float(entry.get("confidence", 0.7) or 0.7))
        if importance_rank.get(str(entry.get("importance", "")), 0) > importance_rank.get(str(primary.get("importance", "")), 0):
            primary["importance"] = entry.get("importance")
            primary["groupKey"] = entry.get("groupKey", primary.get("groupKey", ""))
        character_id_map[cid] = primary_id
        del characters[cid]

    def _map_character_ids(ids: list) -> list:
        return list(dict.fromkeys([character_id_map.get(cid, cid) for cid in ids if cid]))

    for event in registry["events"].values():
        event["character_ids"] = _map_character_ids(event.get("character_ids", []))
        event["participantCharacterIds"] = _map_character_ids(event.get("participantCharacterIds", []))
    for relationship in relationships:
        if isinstance(relationship, dict):
            relationship["sourceId"] = character_id_map.get(relationship.get("sourceId", ""), relationship.get("sourceId", ""))
            relationship["targetId"] = character_id_map.get(relationship.get("targetId", ""), relationship.get("targetId", ""))

    registry["character_id_map"] = character_id_map
    return {"entity_registry": registry, "relationships": relationships}


def _finalize_supervisor_evidence_bindings(state: ImportState | dict) -> dict:
    """Rebuild evidence after canonical remaps so reviewer refs resolve to final entities."""
    if not (state.get("use_supervisor") or state.get("context", {}).get("use_supervisor")):
        return {}
    update = _build_supervisor_evidence_cards(state)
    if state.get("project_path") and state.get("import_run_id"):
        _write_import_artifact(state["project_path"], state["import_run_id"], "evidence_cards.json", update["evidence_cards"])
    return update


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
    from sidecar.models.state import PROFILE_CONFIGS
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    raw_endpoint = ctx.get("endpoint", "https://api.deepseek.com/v1") or "https://api.deepseek.com/v1"
    # Correct common endpoint mistakes (e.g. web console URL instead of API URL)
    base_url = _ENDPOINT_CORRECTIONS.get(raw_endpoint.rstrip("/"),
               _ENDPOINT_CORRECTIONS.get(raw_endpoint, raw_endpoint))
    # max_tokens is profile-aware: deep/custom get 5120 to allow richer per-window output.
    profile = state.get("prompt_profile", "balanced")
    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS["balanced"])
    max_tokens = int(profile_config.get("max_tokens_per_call", 4096))
    # streaming=False: prevents the 'str' object has no attribute 'model_dump'
    # error that occurs when DeepSeek's governor injects an error into an SSE
    # stream and LangChain tries to parse it as a ChatCompletionChunk.
    # timeout=120: prevent hung requests when DeepSeek accepts the TCP connection
    # but stops sending data mid-response (seen as ESTABLISHED socket with no progress).
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url,
                      max_tokens=max_tokens, streaming=False, timeout=120)


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

    source_language = _detect_language(text[:8000])
    manifest = _build_import_manifest(state, text, chunks)
    digest = _build_project_structure_digest({**state, "import_run_id": manifest["import_run_id"]}, manifest["import_run_id"])
    windowing_state = {**state, "import_run_id": manifest["import_run_id"], "import_run_manifest": manifest, "source_language": source_language}
    use_supervisor = bool(state.get("use_supervisor") or state.get("context", {}).get("use_supervisor"))
    if use_supervisor:
        prompt_windows = _build_supervised_prompt_windows(windowing_state, chunks, digest)
    else:
        prompt_windows = _build_prompt_windows(windowing_state, chunks, digest)
    prompt_variant_manifest = (
        state.get("prompt_variant_manifest")
        or state.get("selected_prompt_variants")
        or state.get("extraction_prompt_variants")
    )
    if prompt_variant_manifest:
        prompt_windows = [
            {**window, "prompt_variant_manifest": prompt_variant_manifest}
            for window in prompt_windows
        ]
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

    source_language = _detect_language(text[:500])

    return {
        "chunks": chunks,
        "source_text": text,
        "import_run_id": manifest["import_run_id"],
        "prompt_profile": manifest["prompt_profile"],
        "import_run_manifest": manifest,
        "project_structure_digest": digest,
        "prompt_windows": prompt_windows,
        "source_language": source_language,
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
        "world_detailed": {k: dict(v) for k, v in registry.get("world_detailed", {}).items()},
    }
    extractions: list[dict] = list(state.get("chunk_extractions", []))
    errors: list[str] = list(state.get("errors", []))
    project_path = state["project_path"]
    checkpoint_path = state.get("checkpoint_path", "")

    # Determine which chunks are already done
    completed_ids: set[int] = {e.get("chunk_id", -1) for e in extractions}
    total = len(chunks)

    _session_id = str(state.get("session_id", "") or state.get("context", {}).get("session_id", "") or "")
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
            char_response = await _ainvoke_with_budget(
                llm, [HumanMessage(content=char_prompt)], session_id=_session_id,
                estimated_input_tokens=_estimate_tokens(char_prompt),
            )
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
                name = str(nc.get("canonical_name", "")).strip()
                if _is_world_entity_candidate(name, nc):
                    _add_world_candidate_to_registry(
                        registry,
                        name,
                        _normalize_world_category(name, nc.get("category") or "organization"),
                        str(nc.get("summary") or nc.get("role_in_story") or "").strip(),
                        float(nc.get("confidence", 0.72) or 0.72),
                    )
                    continue
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
            event_response = await _ainvoke_with_budget(
                llm, [HumanMessage(content=event_prompt)], session_id=_session_id,
                estimated_input_tokens=_estimate_tokens(event_prompt),
            )
            event_data = _parse_json_response(event_response.content)

            events: list[dict] = []
            for ev in event_data.get("events", []):
                ev, _ontology_warnings = _normalize_timeline_event_ontology(ev)
                event_id = f"event_{uuid.uuid4().hex[:8]}"
                registry["events"][event_id] = {
                    "event_id": event_id,
                    "title": ev.get("title", ""),
                    "description": ev.get("description", ""),
                    "eventClass": ev.get("eventClass", "canonical_event"),
                    "timelineClass": ev.get("timelineClass", "canonical_event"),
                    "eventType": ev.get("eventType", ""),
                    "arcRole": ev.get("arcRole", ""),
                    "causalRole": ev.get("causalRole", ""),
                    "branchRole": ev.get("branchRole", ""),
                    "timelineLaneHint": ev.get("timelineLaneHint", ""),
                    "importance": ev.get("importance", "medium"),
                    "deterministicLaneHints": ev.get("deterministicLaneHints", {}),
                    "ontologyWarnings": ev.get("ontologyWarnings", []),
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
            world_response = await _ainvoke_with_budget(
                llm, [HumanMessage(content=world_prompt)], session_id=_session_id,
                estimated_input_tokens=_estimate_tokens(world_prompt),
            )
            world_data = _parse_json_response(world_response.content)

            world_mentions: list[str] = []
            for wm in world_data.get("world_mentions", []):
                name = wm.get("name", "")
                category = _normalize_world_category(name, wm.get("category", "concept"))
                if name:
                    _add_world_candidate_to_registry(
                        registry,
                        name,
                        category,
                        str(wm.get("description", "")).strip(),
                        float(wm.get("confidence", 0.7) or 0.7),
                    )
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
        completed = len(completed_ids)
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
    source_text = str(state.get("source_text", "") or "")

    def _build_from_chunks(raw_chunks: list[dict]) -> list[dict]:
        chapter_map: dict[str, list[dict]] = {}
        chapter_order: list[str] = []

        for chunk in raw_chunks:
            chunk_id = chunk.get("chunk_id", 0)
            hint = chunk.get("chapter_hint") or f"Chapter {len(chapter_order) + 1}"
            if hint not in chapter_map:
                chapter_map[hint] = []
                chapter_order.append(hint)
            chapter_map[hint].append(chunk)

        manuscript_chapters: list[dict] = []
        ordered_hints = sorted(chapter_order, key=lambda hint: _min_chunk_sort_key(chapter_map[hint]))
        for hint in ordered_hints:
            chapter_chunks = sorted(chapter_map[hint], key=lambda chunk: _chunk_sort_key(chunk.get("chunk_id")))
            spans = [c.get("source_span") for c in chapter_chunks]
            valid_spans = [span for span in spans if isinstance(span, dict)]
            if source_text and len(valid_spans) == len(chapter_chunks):
                for span in valid_spans:
                    ok, errors = validate_source_span(span, source_text)
                    if not ok:
                        raise ValueError(f"Invalid source span while building manuscript: {errors}")
                start = min(span["absolute_start"] for span in valid_spans)
                end = max(span["absolute_end"] for span in valid_spans)
                content = source_text[start:end]
                source_span = make_source_span(source_text, start, end)
            else:
                # Compatibility fallback for pre-contract checkpoints. New imports
                # always enter the branch above with the original raw source text.
                content = "\n\n".join(
                    c.get("manuscript_content", c.get("raw_content", c.get("content", ""))) for c in chapter_chunks
                )
                source_span = make_source_span(content, 0, len(content))
            chapter = {
                "chapter_id": _stable_id("chap", source_span["raw_source_hash"], source_span["absolute_start"], source_span["absolute_end"], hint),
                "title": hint,
                "chunk_ids": [c["chunk_id"] for c in chapter_chunks],
                "manuscript_content": content,
                "source_span": source_span,
                "orderIndex": len(manuscript_chapters),
            }
            manuscript_chapters.append(_enrich_manuscript_chapter(chapter, state, content))
        return _sort_manuscript_chapters(_dedupe_manuscript_chapters(manuscript_chapters))

    # Manuscript prose is always a deterministic raw-source projection. LLM
    # extraction may describe scenes, but it must never supply a chapter body.
    if chunks:
        return {"manuscript_chapters": _build_from_chunks(chunks), "progress": 0.88}

    return {"manuscript_chapters": [], "progress": 0.88}


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
    semantic_conflicts: list[dict] = []
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
            decision = _entity_merge_decision(match, entry, cid)
            entry["entity_merge_decision"] = decision
            semantic_conflicts.extend([{**conflict, "entity_type": "character", "import_id": cid, "existing_id": match["id"]} for conflict in decision["conflicts"]])
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
    tag_rejections: list[dict] = []
    seen_new_tag_keys: set[str] = set()
    for tag in character_tags:
        tag, rejection = _normalize_character_tag(tag, state.get("source_language", "en"))
        if rejection:
            tag_rejections.append(rejection)
            continue
        assert tag is not None
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

    existing_relationship_keys: set[tuple[str, str, str, str]] = set()
    for rel in snapshot.get("relationships", []):
        left = str(rel.get("sourceId") or rel.get("source_id") or "")
        right = str(rel.get("targetId") or rel.get("target_id") or "")
        normalized = _relationship_ontology(rel, state.get("source_language", "en"))
        if normalized is None:
            continue
        if left and right:
            existing_relationship_keys.add(_relationship_dedupe_key(left, right, normalized))

    reconciled_relationships: list[dict] = []
    seen_relationship_keys: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        source = character_id_map.get(relationship.get("sourceId", ""), relationship.get("sourceId", ""))
        target = character_id_map.get(relationship.get("targetId", ""), relationship.get("targetId", ""))
        relationship = {**relationship, "sourceId": source, "targetId": target}
        normalized = _relationship_ontology(relationship, state.get("source_language", "en"))
        if normalized is None:
            semantic_conflicts.append({"entity_type": "relationship", "sourceId": source, "targetId": target, "label": relationship.get("type", ""), "resolution": "demoted_to_evidence"})
            continue
        relationship.update(normalized)
        key = _relationship_dedupe_key(source, target, relationship)
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
        "semantic_conflicts": semantic_conflicts,
        "tag_rejections": tag_rejections,
    }
    if state.get("import_run_id"):
        _write_import_artifact(project_path, state["import_run_id"], "reducer_artifact.json", artifact)
    return {
        "entity_registry": registry,
        "relationships": reconciled_relationships,
        "character_tags": reconciled_tags,
        "tag_rejections": tag_rejections,
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


_TIMELINE_SEMANTIC_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("han_li_leave_home", ("离家", "告别父母", "离开村", "离开家", "前往青牛镇", "随三叔离家", "踏上旅程")),
    ("third_uncle_sect_offer", ("三叔提议", "韩胖子提议", "参加七玄门", "七玄门考验", "七玄门测试", "送韩立入七玄门", "内门弟子考验")),
    ("join_seven_mysteries", ("加入七玄门", "进入七玄门", "抵达七玄门", "七玄门选拔", "正式进入七玄门", "前往七玄门")),
    ("doctor_mo_accepts_disciple", ("墨大夫收徒", "墨大夫收为弟子", "拜墨大夫", "成为墨大夫弟子", "收韩立为徒")),
    ("cultivation_breakthrough", ("突破", "练成", "功法大成", "修为提升", "cultivation breakthrough")),
    ("mentor_threat", ("墨大夫威胁", "师父威胁", "mentor threat", "doctor mo threatens")),
    ("faction_conflict", ("冲突", "伏击", "争斗", "敌袭", "ambush", "conflict")),
    ("wang_guard_takes_han_li", (
        "王护法接走韩立", "七玄门王护法接走韩立", "王护法带走韩立",
        "护法接走韩立", "护法带走韩立", "王护法领走韩立",
    )),
    ("third_uncle_proposal", (
        "三叔让韩立", "三叔建议韩立",
    )),
    ("admission_test", (
        "入门测试", "入门考验", "七玄门入门", "七玄门测试", "七玄门考核",
    )),
]


def _timeline_chapter_anchor(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("start") or value.get("end") or ""
    text = str(value or "").strip()
    match = re.search(r"(第[一二三四五六七八九十百零\d]+[章节回]|chapter\s*\d+|\b\d+\b)", text, re.IGNORECASE)
    return _normal_key(match.group(1) if match else text)[:24]


def _timeline_event_participant_key(event: dict) -> str:
    participants = event.get("participantCharacterIds") or event.get("character_ids") or event.get("character_names") or []
    return ",".join(sorted(_normal_key(participant) for participant in participants if _normal_key(participant)))


def _timeline_semantic_title_key(event: dict) -> str:
    """Reduce title variants into stable semantic beats before proposal write."""
    text = " ".join([
        str(event.get("dedupeKey", "")),
        str(event.get("title", "")),
        str(event.get("description", "")),
        str(event.get("stakes", "")),
    ]).lower()
    for semantic_key, patterns in _TIMELINE_SEMANTIC_PATTERNS:
        if any(pattern.lower() in text for pattern in patterns):
            return semantic_key
    title_key = _normal_key(event.get("title", ""))
    _raw_title = str(event.get("title", ""))
    _stripped_title = re.sub(
        r"^(七玄门|墨大夫|三叔|韩家|青牛镇|落水河村|黄枫谷|神手谷)",
        "",
        _raw_title.strip(),
    )
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", (_stripped_title or _raw_title).lower())
    if not tokens:
        return title_key[:48]
    # Keep the title signal compact enough for near-duplicate variants to meet.
    return _normal_key("".join(tokens[:4]))[:48] or title_key[:48]


def _event_semantic_signature(event: dict) -> str:
    dedupe_key = _normal_key(event.get("dedupeKey", ""))
    participants = _timeline_event_participant_key(event)
    chapter = _timeline_chapter_anchor(event.get("chapterRange") or event.get("temporal_hint", ""))
    semantic_title = _timeline_semantic_title_key(event)
    if dedupe_key:
        return f"dedupe:{dedupe_key}|p:{participants}|c:{chapter}|t:{semantic_title}"
    return f"semantic:{semantic_title}|p:{participants}|c:{chapter}"


def _event_loose_semantic_signature(event: dict) -> str:
    participants = _timeline_event_participant_key(event)
    chapter = _timeline_chapter_anchor(event.get("chapterRange") or event.get("temporal_hint", ""))
    return f"loose:{_timeline_semantic_title_key(event)}|p:{participants}|c:{chapter}"


def _event_sequence_key(event: dict) -> tuple[int, int, str]:
    position_rank = {"early": 0, "middle": 1, "late": 2}
    return (
        int(event.get("chunk_id", 0) or 0),
        position_rank.get(str(event.get("chunk_position", "")).lower(), 1),
        _normal_key(event.get("title", "")),
    )


def _normalize_timeline_importance(event: dict) -> str:
    raw = str(event.get("importance", "")).strip().lower()
    if raw in {"critical", "high", "medium", "low"}:
        return raw
    score = int(float(event.get("importanceScore", 0) or 0))
    confidence = float(event.get("confidence", 0.7) or 0.7)
    if score >= 90:
        return "critical"
    if score >= 75 or confidence >= 0.86:
        return "high"
    if score >= 50 or confidence >= 0.75:
        return "medium"
    return "low"


def _infer_timeline_arc_role(event: dict) -> str:
    raw = str(event.get("arcRole", "")).strip().lower()
    if raw in _TIMELINE_ARC_ROLES:
        return raw
    arc_id = _safe_branch_slug(str(event.get("arcId", "")).strip()) if str(event.get("arcId", "")).strip() else ""
    if arc_id in {"cultivation_progress", "training_progress", "core_progression"}:
        return "power_progression"
    if arc_id in _MAINLINE_ARC_HINTS:
        return "protagonist"
    if arc_id in {"mentor_control", "mentor_threat"}:
        return "antagonist"
    if arc_id in {"faction_conflict", "sect_conflict"}:
        return "faction"
    text = " ".join([
        str(event.get("arcId", "")),
        str(event.get("timelineLaneHint", "")),
        str(event.get("title", "")),
        str(event.get("description", "")),
        str(event.get("stakes", "")),
    ]).lower()
    if any(token in text for token in ("antagonist", "villain", "enemy", "反派", "敌", "仇")):
        return "antagonist"
    if any(token in text for token in ("training", "cultivation", "breakthrough", "power", "修炼", "功法", "突破", "练功")):
        return "power_progression"
    if any(token in text for token in ("faction", "sect", "organization", "clan", "门派", "宗门", "帮派", "势力", "七玄门")):
        return "faction"
    if str(event.get("location_hint", "")).strip():
        return "location"
    if any(token in text for token in ("protagonist", "origin", "main", "主角", "韩立")):
        return "protagonist"
    return "mainline"


def _normalize_timeline_role(value: Any, allowed: set[str], default: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in allowed:
        return raw
    if raw in {"root", "main", "main_arc", "mainline"} and "mainline" in allowed:
        return "mainline"
    if raw in {"forked", "branch", "side"} and "side_lane" in allowed:
        return "side_lane"
    if raw in {"cause", "causal"} and "cause" in allowed:
        return "cause"
    if raw in {"effect", "result"} and "effect" in allowed:
        return "effect"
    return default


def _deterministic_timeline_lane_hint(event: dict) -> str:
    existing = str(event.get("timelineLaneHint", "")).strip()
    if existing:
        return existing
    arc_role = _infer_timeline_arc_role(event)
    if arc_role in {"mainline", "protagonist"}:
        return "Main Arc"
    if arc_role in {"faction", "organization"}:
        return "Faction / Organization"
    if arc_role == "location":
        location = str(event.get("location_hint", "")).strip()
        return f"Location: {location}" if location else "Location"
    if arc_role == "antagonist":
        return "Antagonist Pressure"
    if arc_role in {"training", "power_progression"}:
        return "Training / Power Progression"
    return "Main Arc"


def _normalize_timeline_event_ontology(event: dict) -> tuple[dict, list[str]]:
    """Apply deterministic timeline ontology before prompt-derived fields are trusted."""
    normalized = dict(event)
    warnings: list[str] = []
    raw_event_class = str(normalized.get("eventClass", "")).strip().lower()
    raw_timeline_class = str(normalized.get("timelineClass", "")).strip().lower()
    event_type = str(normalized.get("eventType", "")).strip()

    if raw_event_class in TIMELINE_EVENT_CLASSES:
        event_class = raw_event_class
    elif raw_timeline_class in TIMELINE_EVENT_CLASSES:
        event_class = raw_timeline_class
        if raw_event_class:
            warnings.append(f"Coerced invalid eventClass '{raw_event_class}' to '{event_class}' from timelineClass.")
    elif raw_event_class in _LEGACY_EVENT_TYPE_VALUES:
        event_type = event_type or raw_event_class
        event_class = "canonical_event"
        warnings.append(f"Coerced legacy eventClass '{raw_event_class}' to 'canonical_event'.")
    elif raw_event_class == "scene_beat":
        event_class = "scene_beat"
    else:
        score = int(float(normalized.get("importanceScore", 0) or 0))
        confidence = float(normalized.get("confidence", 0.7) or 0.7)
        if score and score < 50:
            event_class = "background_reference"
        elif confidence < 0.75:
            event_class = "background_reference"
        else:
            event_class = "canonical_event"
        if raw_event_class:
            warnings.append(f"Coerced invalid eventClass '{raw_event_class}' to '{event_class}'.")

    normalized["eventClass"] = event_class
    normalized["timelineClass"] = event_class
    if event_type:
        normalized["eventType"] = event_type
    normalized["arcRole"] = _infer_timeline_arc_role(normalized)
    normalized["causalRole"] = _normalize_timeline_role(normalized.get("causalRole"), _TIMELINE_CAUSAL_ROLES, "turning_point" if event_class == "canonical_event" else "background")
    normalized["branchRole"] = _normalize_timeline_role(normalized.get("branchRole") or normalized.get("forkMergeHint"), _TIMELINE_BRANCH_ROLES, "mainline" if normalized["arcRole"] in {"mainline", "protagonist"} else "side_lane")
    normalized["importance"] = _normalize_timeline_importance(normalized)
    normalized["timelineLaneHint"] = _deterministic_timeline_lane_hint(normalized)
    normalized["deterministicLaneHints"] = {
        "mainline": normalized["arcRole"] in {"mainline", "protagonist"},
        "factionOrOrganization": normalized["arcRole"] in {"faction", "organization"},
        "location": normalized["arcRole"] == "location",
        "antagonist": normalized["arcRole"] == "antagonist",
        "trainingOrPowerProgression": normalized["arcRole"] in {"training", "power_progression"},
    }
    if warnings:
        normalized["ontologyWarnings"] = list(normalized.get("ontologyWarnings", [])) + warnings
    return normalized, warnings


def _minimum_canonical_event_count(state: ImportState | dict, total_candidates: int) -> int:
    if total_candidates <= 0:
        return 0
    targets = state.get("converge_target") or state.get("converge_targets") or state.get("convergence_targets") or {}
    tos = state.get("tool_operating_spec") or state.get("tos") or {}
    explicit = int(targets.get("expected_min_events") or tos.get("expected_min_events") or 0)
    chunks = state.get("chunks") or []
    manuscript = state.get("manuscript_chapters") or []
    chapter_count = len(manuscript) or len(chunks)
    if not chapter_count:
        anchors = {
            _timeline_chapter_anchor(event.get("chapterRange") or event.get("temporal_hint", ""))
            for event in state.get("entity_registry", {}).get("events", {}).values()
        }
        chapter_count = len([anchor for anchor in anchors if anchor])
    density_target = float(tos.get("event_density_target", 0) or 0)
    density_min = math.ceil(chapter_count * density_target) if chapter_count and density_target else 0
    profile = state.get("profile_config") or {}
    profile_density = profile.get("event_density") or state.get("prompt_profile")
    profile_min = 0
    if chapter_count >= 20 and profile_density in {"chapter_level", "deep", "balanced"}:
        profile_min = max(8, math.ceil(chapter_count * 0.25))
    if chapter_count >= 50:
        profile_min = max(profile_min, 8)
    return min(total_candidates, max(explicit, density_min, profile_min))


def _build_prelim_timeline_event(event_id: str, event: dict, character_id_map: dict, class_reason: str) -> dict:
    participant_ids = [character_id_map.get(cid, cid) for cid in event.get("character_ids", [])]
    importance_score = int(event.get("importanceScore", 0) or 0)
    importance = _normalize_timeline_importance(event)
    return {
        **event,
        "event_id": event_id,
        "summary": event.get("description", ""),
        "locationIds": [],
        "participantCharacterIds": [cid for cid in participant_ids if cid],
        "linkedSceneIds": [],
        "linkedWorldItemIds": [],
        "tags": ["imported"],
        "sharedBranchIds": [],
        "importance": importance or ("critical" if importance_score >= 90 else "high"),
        "timelineClass": "canonical_event",
        "eventClass": "canonical_event",
        "classificationReason": class_reason,
        "mergedEventIds": [],
        "mergeReasons": [],
        "_sequence": _event_sequence_key(event),
    }


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


def _timeline_lane_key(event: dict) -> tuple[str, str, str]:
    raw_arc_id = str(event.get("arcId", "")).strip()
    arc_id = _safe_branch_slug(raw_arc_id) if raw_arc_id else ""
    # arc_id catches lowercased English terms; raw_arc_id catches CJK strings
    # that _safe_branch_slug doesn't transform.
    if arc_id in _WORLD_CATEGORY_BRANCH_BLOCKLIST or raw_arc_id in _WORLD_CATEGORY_BRANCH_BLOCKLIST:
        arc_id = ""
    lane_hint = str(event.get("timelineLaneHint", "")).strip()
    fork_hint = str(event.get("forkMergeHint", "")).strip().lower()
    importance = float(event.get("importanceScore", 0) or 0)
    arc_role = str(event.get("arcRole", "")).strip().lower() or _infer_timeline_arc_role(event)
    if arc_role in {"mainline", "protagonist"} and importance >= 65:
        return ("root", "main", "Main Plot")
    if arc_role in {"faction", "organization"}:
        return ("theme", "faction", lane_hint or "Faction / Organization")
    if arc_role == "antagonist":
        return ("theme", "antagonist", lane_hint or "Antagonist Pressure")
    if arc_role in {"training", "power_progression"}:
        return ("theme", "training", lane_hint or "Training / Power Progression")
    if arc_role == "location" and str(event.get("location_hint", "")).strip():
        location = str(event.get("location_hint", "")).strip()
        return ("location", _safe_branch_slug(location), f"Location: {location}")
    if arc_id in _MAINLINE_ARC_HINTS and importance >= 65:
        return ("root", "main", "Main Plot")
    if arc_id in _SIDE_ARC_HINTS:
        return ("arc", arc_id, lane_hint or arc_id.replace("_", " ").title())
    if arc_id and arc_id not in {"main", "main_arc", "root", "unknown"}:
        return ("arc", arc_id, lane_hint or arc_id.replace("_", " ").title())
    if lane_hint and _normal_key(lane_hint) not in {"mainarc", "mainplot", "maintimeline"}:
        return ("lane", _safe_branch_slug(lane_hint), lane_hint)
    if fork_hint == "root" and importance >= 80:
        return ("root", "main", "Main Plot")
    theme_kind, theme_key, theme_name = _timeline_theme_key(event)
    if theme_key != "main":
        return (theme_kind, theme_key, theme_name)
    location = str(event.get("location_hint", "")).strip()
    if location:
        return ("location", _safe_branch_slug(location), f"Location: {location}")
    participants = event.get("participantCharacterIds", [])
    if participants and importance < 85:
        participant_id = str(participants[0])
        return ("character", _safe_branch_slug(participant_id), f"Character Arc: {participant_id}")
    return ("root", "main", "Main Plot")


def _timeline_candidate_class(event: dict) -> tuple[str, str]:
    explicit = str(event.get("timelineClass", "")).strip()
    event_class = str(event.get("eventClass", "")).strip()
    importance = float(event.get("importanceScore", 0) or 0)
    confidence = float(event.get("confidence", 0.7) or 0.7)
    if explicit == "scene_beat" or event_class == "scene_beat":
        return ("scene_beat", "model classified candidate as scene_beat")
    if explicit == "background_reference":
        return ("background_reference", "model classified candidate as background_reference")
    if importance and importance < 50:
        return ("background_reference", f"importanceScore {importance:g} is below canonical threshold")
    if confidence < 0.75:
        return ("background_reference", f"confidence {confidence:.2f} is below canonical threshold")
    return ("canonical_event", "candidate preserves story state, causal, or arc-level change")


def _timeline_branch_color(index: int) -> str:
    colors = ["#38bdf8", "#f97316", "#22c55e", "#a855f7", "#eab308", "#ec4899", "#14b8a6"]
    return colors[index % len(colors)]


async def node_architect_timeline(state: ImportState) -> dict:
    """Deduplicate and place timeline candidates into branch-aware event data."""
    if state.get("extract_timeline") is False:
        _sid = state.get("session_id", "")
        if _sid:
            from sidecar.workflows.w1_run_events import append_event
            append_event(_sid, {"phase": "skip", "tool": "architect_timeline", "status": "skipped", "message": "Timeline extraction disabled by user toggle."})
        return {"timeline_branches": [], "timeline_architecture": {}, "progress": state.get("progress", 0.75)}

    project_path = state["project_path"]
    snapshot = _load_existing_project_snapshot(project_path)
    registry = dict(state.get("entity_registry", {}))
    events = registry.get("events", {})
    character_id_map = registry.get("character_id_map", {})
    discarded_duplicates: list[dict] = []
    warnings: list[str] = []
    event_classifications: list[dict] = []
    scene_beats: list[dict] = []
    background_references: list[dict] = []
    fork_merge_anchors: list[dict] = []

    existing_branches = snapshot.get("timeline_branches", [])
    root_branch = next((branch for branch in existing_branches if branch.get("mode") == "root"), None) or (existing_branches[0] if existing_branches else None)
    root_branch_id = root_branch.get("id") if root_branch else "branch_import_main"
    imported_branches = [branch for branch in state.get("timeline_branches", []) if branch.get("id")]
    root_geometry = (root_branch or {}).get("geometry") or {}
    _source_lang = state.get("source_language", "en")
    _default_branch_name = "主时间线" if _source_lang == "zh" else "Main Timeline"
    _default_branch_desc = "主叙事时间线" if _source_lang == "zh" else "Primary narrative timeline."
    timeline_branches: list[dict] = [{
        **(root_branch or {}),
        "id": root_branch_id,
        "name": (root_branch or {}).get("name", _default_branch_name),
        "description": (root_branch or {}).get("description", _default_branch_desc),
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
        "rankStart": 0,
        "rankEnd": 0,
        "laneId": "lane_0_main",
        "layoutHint": {"eventBudget": 36, "clusterOverflow": False, "densityClass": "normal"},
    }]

    existing_event_keys = {
        (_normal_key(event.get("title", "")), _normal_key(event.get("summary", ""))[:80])
        for event in snapshot.get("timeline_events", [])
    }
    seen_signatures: dict[str, str] = {}
    seen_loose_signatures: dict[str, str] = {}
    seen_title_keys: dict[str, str] = {}
    canonical_events: dict[str, dict] = {}
    chunk_event_counts: dict[int, int] = {}
    density_limit_per_chunk = 8
    branch_event_budget = 36
    prelim_events: dict[str, dict] = {}
    demoted_candidates: list[tuple[str, dict, dict, str]] = []

    for event_id, raw_event in events.items():
        event, ontology_warnings = _normalize_timeline_event_ontology(raw_event)
        warnings.extend(f"{event_id}: {warning}" for warning in ontology_warnings)
        title = event.get("title", "").strip()
        if not title:
            discarded_duplicates.append({"event_id": event_id, "timelineClass": "discarded_duplicate", "reason": "missing title"})
            continue
        title_key = _normal_key(title)
        title_numbers = tuple(re.findall(r"\d+", str(title)))
        title_duplicate_id = seen_title_keys.get(title_key)
        if not title_duplicate_id:
            title_duplicate_id = next(
                (
                    existing_id
                    for existing_title_key, existing_id in seen_title_keys.items()
                    if title_key
                    and existing_title_key
                    and (not title_numbers or tuple(re.findall(r"\d+", existing_title_key)) == title_numbers)
                    and difflib.SequenceMatcher(None, title_key, existing_title_key).ratio() > 0.92
                ),
                "",
            )
        if title_duplicate_id and title_duplicate_id in prelim_events:
            primary = prelim_events[title_duplicate_id]
            primary.setdefault("mergedEventIds", []).append(event_id)
            primary.setdefault("mergeReasons", []).append(f"Merged '{title}' by high-confidence title similarity.")
            primary["summary"] = _merge_text_field(primary.get("summary", ""), event.get("description", ""))
            primary["confidence"] = max(float(primary.get("confidence", 0.7)), float(event.get("confidence", 0.7)))
            discarded_duplicates.append({
                "event_id": event_id,
                "merged_into": title_duplicate_id,
                "title": title,
                "timelineClass": "discarded_duplicate",
                "reason": "high-confidence duplicate title",
            })
            continue
        existing_key = (_normal_key(title), _normal_key(event.get("description", ""))[:80])
        if existing_key in existing_event_keys:
            discarded_duplicates.append({"event_id": event_id, "title": title, "timelineClass": "discarded_duplicate", "reason": "matches existing timeline event"})
            continue
        candidate_class, class_reason = _timeline_candidate_class(event)
        event_classifications.append({
            "event_id": event_id,
            "title": title,
            "classification": candidate_class,
            "reason": class_reason,
            "dedupeKey": event.get("dedupeKey", ""),
            "semanticTitleKey": _timeline_semantic_title_key(event),
        })
        if candidate_class == "scene_beat":
            item = {"event_id": event_id, "title": title, "timelineClass": "scene_beat", "reason": class_reason}
            scene_beats.append(item)
            discarded_duplicates.append(item)
            demoted_candidates.append((event_id, event, item, class_reason))
            continue
        if candidate_class == "background_reference":
            item = {"event_id": event_id, "title": title, "timelineClass": "background_reference", "reason": class_reason}
            background_references.append(item)
            discarded_duplicates.append(item)
            demoted_candidates.append((event_id, event, item, class_reason))
            continue
        chunk_id = int(event.get("chunk_id", 0) or 0)
        chunk_event_counts[chunk_id] = chunk_event_counts.get(chunk_id, 0) + 1
        event_importance = float(event.get("importanceScore", 0) or 0)
        if (
            chunk_event_counts[chunk_id] > density_limit_per_chunk
            and float(event.get("confidence", 0.7)) < 0.88
            and event_importance < 82
        ):
            discarded_duplicates.append({"event_id": event_id, "title": title, "timelineClass": "scene_beat", "reason": "demoted by density policy"})
            continue
        signature = _event_signature(event)
        semantic_signature = _event_semantic_signature(event)
        loose_signature = _event_loose_semantic_signature(event)
        primary_id = seen_signatures.get(signature) or seen_signatures.get(semantic_signature) or seen_loose_signatures.get(loose_signature)
        if primary_id:
            primary = prelim_events[primary_id]
            primary.setdefault("mergedEventIds", []).append(event_id)
            primary.setdefault("mergeReasons", []).append(
                f"Merged '{title}' by semantic signature {loose_signature}; participants/chapter/semantic title overlap."
            )
            primary["summary"] = _merge_text_field(primary.get("summary", ""), event.get("description", ""))
            primary["confidence"] = max(float(primary.get("confidence", 0.7)), float(event.get("confidence", 0.7)))
            primary["importanceScore"] = max(int(primary.get("importanceScore", 0) or 0), int(event.get("importanceScore", 0) or 0))
            discarded_duplicates.append({
                "event_id": event_id,
                "merged_into": primary_id,
                "title": title,
                "timelineClass": "discarded_duplicate",
                "reason": "semantic duplicate: same dedupe/participants/chapter/normalized title",
                "dedupeKey": event.get("dedupeKey", ""),
                "semanticSignature": loose_signature,
            })
            continue
        seen_signatures[signature] = event_id
        seen_signatures[semantic_signature] = event_id
        seen_loose_signatures[loose_signature] = event_id
        seen_title_keys[title_key] = event_id
        prelim_events[event_id] = _build_prelim_timeline_event(event_id, event, character_id_map, class_reason)

    min_canonical_events = _minimum_canonical_event_count(state, len(events))
    if len(prelim_events) < min_canonical_events and demoted_candidates:
        promoted_ids: set[str] = set()
        for event_id, event, _item, class_reason in sorted(
            demoted_candidates,
            key=lambda item: _importance_sort_value(item[1]),
            reverse=True,
        ):
            if len(prelim_events) >= min_canonical_events:
                break
            if event_id in prelim_events:
                continue
            signature = _event_signature(event)
            semantic_signature = _event_semantic_signature(event)
            loose_signature = _event_loose_semantic_signature(event)
            if seen_signatures.get(signature) or seen_signatures.get(semantic_signature) or seen_loose_signatures.get(loose_signature):
                continue
            promoted = _build_prelim_timeline_event(
                event_id,
                {**event, "eventClass": "canonical_event", "timelineClass": "canonical_event"},
                character_id_map,
                f"promoted by minimum canonical density policy after {class_reason}",
            )
            prelim_events[event_id] = promoted
            seen_signatures[signature] = event_id
            seen_signatures[semantic_signature] = event_id
            seen_loose_signatures[loose_signature] = event_id
            promoted_ids.add(event_id)
            warnings.append(f"{event_id}: promoted to canonical_event to satisfy minimum event density.")
        if promoted_ids:
            discarded_duplicates = [item for item in discarded_duplicates if item.get("event_id") not in promoted_ids]
            scene_beats = [item for item in scene_beats if item.get("event_id") not in promoted_ids]
            background_references = [item for item in background_references if item.get("event_id") not in promoted_ids]

    # Assign source-faithful metadata before branch bucketing.
    _sorted_by_source = sorted(
        prelim_events.items(),
        key=lambda kv: kv[1].get("_sequence", (0, 0, "")),
    )
    for _source_order, (_eid, _ev) in enumerate(_sorted_by_source):
        _chapter_start = (
            (_ev.get("chapterRange") or {}).get("start")
            or _ev.get("temporal_hint", "")
        )
        _ev["sourceOrder"] = _source_order
        _ev["chapterNumber"] = _chapter_number_from_title(str(_chapter_start)) or 0
        _ev["sourceChunkIds"] = [int(_ev.get("chunk_id", 0) or 0)]

    lane_counts: dict[tuple[str, str, str], int] = {}
    for event in prelim_events.values():
        lane_key = _timeline_lane_key(event)
        lane_counts[lane_key] = lane_counts.get(lane_key, 0) + 1

    total_events = len(prelim_events)
    branch_threshold = 2 if total_events >= 10 else 3
    branch_defs: dict[str, dict] = {root_branch_id: timeline_branches[0]}

    def _ensure_branch(branch_id: str, name: str, reason: str, *, lane_key: str = "") -> None:
        if branch_id in branch_defs or len(branch_defs) >= 10:
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
            "rankStart": 0,
            "rankEnd": 0,
            "laneId": lane_key or f"lane_{idx}_{_safe_branch_slug(name)}",
            "layoutHint": {"eventBudget": branch_event_budget, "clusterOverflow": False, "densityClass": "normal"},
        }
        branch_defs[branch_id] = branch
        timeline_branches.append(branch)

    for branch in imported_branches:
        branch_id = branch.get("id")
        if branch_id and branch_id not in branch_defs and len(branch_defs) < 10:
            idx = len(branch_defs)
            branch_defs[branch_id] = {
                **branch,
                "parentBranchId": branch.get("parentBranchId") or root_branch_id,
                "sortOrder": branch.get("sortOrder", idx),
                "mode": branch.get("mode", "forked"),
                "geometry": {**branch.get("geometry", {}), "laneOffset": branch.get("geometry", {}).get("laneOffset", idx * 140)},
                "rankStart": branch.get("rankStart", 0),
                "rankEnd": branch.get("rankEnd", 0),
                "laneId": branch.get("laneId", f"lane_{idx}_{_safe_branch_slug(branch.get('name', branch_id))}"),
                "layoutHint": {**branch.get("layoutHint", {}), "eventBudget": branch_event_budget, "clusterOverflow": False},
            }
            timeline_branches.append(branch_defs[branch_id])

    for lane_tuple, count in sorted(lane_counts.items(), key=lambda item: item[1], reverse=True):
        lane_kind, lane_key, lane_name = lane_tuple
        if lane_kind == "root":
            continue
        if count >= branch_threshold:
            _ensure_branch(
                f"branch_{lane_kind}_{_safe_branch_slug(lane_key)}",
                lane_name,
                f"{count} events on {lane_kind} lane '{lane_name}'",
                lane_key=f"lane_{lane_kind}_{_safe_branch_slug(lane_key)}",
            )

    def _select_branch(event: dict) -> str:
        lane_kind, lane_key, _ = _timeline_lane_key(event)
        lane_branch_id = f"branch_{lane_kind}_{_safe_branch_slug(lane_key)}"
        if lane_branch_id in branch_defs:
            return lane_branch_id
        return root_branch_id

    branch_buckets: dict[str, list[tuple[str, dict]]] = {}
    for event_id, event in prelim_events.items():
        branch_id = _select_branch(event)
        branch_buckets.setdefault(branch_id, []).append((event_id, event))

    for branch_id, branch_events in branch_buckets.items():
        branch_events.sort(key=lambda item: item[1].get("_sequence", (0, 0, "")))
        if len(branch_events) > branch_event_budget:
            warnings.append(f"Branch {branch_id} has {len(branch_events)} canonical events; lower-importance events were converted to scene beats.")
            branch_defs[branch_id]["layoutHint"]["clusterOverflow"] = True
            branch_defs[branch_id]["layoutHint"]["densityClass"] = "overflow"
            branch_defs[branch_id]["layoutHint"]["overflowCount"] = len(branch_events) - branch_event_budget
        else:
            branch_defs[branch_id]["layoutHint"]["densityClass"] = "dense" if len(branch_events) > max(branch_event_budget // 2, 1) else "normal"
        visible_index = 0
        for event_id, event in branch_events:
            if visible_index >= branch_event_budget:
                item = {
                    "event_id": event_id,
                    "title": event.get("title", ""),
                    "timelineClass": "scene_beat",
                    "reason": f"branch event budget overflow on {branch_id}",
                }
                scene_beats.append(item)
                discarded_duplicates.append(item)
                continue
            cleaned = {k: v for k, v in event.items() if not k.startswith("_")}
            cleaned["branchId"] = branch_id
            cleaned["orderIndex"] = visible_index
            cleaned["globalOrderIndex"] = -1  # placeholder; reassigned below by source order
            cleaned["sharedBranchIds"] = [root_branch_id] if branch_id != root_branch_id else []
            cleaned["layoutHints"] = {"density": len(branch_events), "branchEventBudget": branch_event_budget}
            canonical_events[event_id] = cleaned
            visible_index += 1
        branch_defs[branch_id]["rankStart"] = 0
        branch_defs[branch_id]["rankEnd"] = max(visible_index - 1, 0)

    # Reassign globalOrderIndex in source-faithful order.
    _existing_count = len(snapshot.get("timeline_events", []))
    _all_canonical_sorted = sorted(
        canonical_events.values(),
        key=lambda ev: ev.get("sourceOrder", 0),
    )
    for _gi, _ev in enumerate(_all_canonical_sorted):
        _ev["globalOrderIndex"] = _existing_count + _gi

    for branch_id, branch in branch_defs.items():
        if branch_id == root_branch_id:
            continue
        branch_events = sorted(
            [event for event in canonical_events.values() if event.get("branchId") == branch_id],
            key=lambda event: event.get("orderIndex", 0),
        )
        if not branch_events:
            continue
        branch["forkEventId"] = branch.get("forkEventId") or branch_events[0].get("event_id")
        merge_event = next((event for event in reversed(branch_events) if str(event.get("forkMergeHint", "")).lower() in {"merge", "callback"}), None)
        if merge_event:
            branch["mergeEventId"] = branch.get("mergeEventId") or merge_event.get("event_id")
            branch["endMode"] = "merge"
        fork_merge_anchors.append({
            "branchId": branch_id,
            "parentBranchId": branch.get("parentBranchId"),
            "forkEventId": branch.get("forkEventId"),
            "mergeEventId": branch.get("mergeEventId"),
            "reason": "deterministic first canonical event fork anchor with optional model merge/callback hint",
        })

    registry["events"] = canonical_events
    artifact = {
        "import_run_id": state.get("import_run_id", ""),
        "root_branch_id": root_branch_id,
        "branches": timeline_branches,
        "canonical_events": list(canonical_events.values()),
        "event_classifications": event_classifications,
        "discarded_duplicates": discarded_duplicates,
        "scene_beats": scene_beats,
        "background_references": background_references,
        "fork_merge_anchors": fork_merge_anchors,
        "density_policy": {
            "max_events_per_chunk": density_limit_per_chunk,
            "max_events_per_branch": branch_event_budget,
            "branch_threshold": branch_threshold,
            "minimum_canonical_events": min_canonical_events,
            "low_confidence_threshold": 0.9,
            "canonical_classes": ["canonical_event"],
            "noncanonical_classes": ["scene_beat", "background_reference", "discarded_duplicate"],
        },
        "layout_hints": {
            "strategy": "semantic_branch_topology",
            "max_branch_count": 10,
            "branch_lane_spacing": 140,
            "root_branch_policy": "mainline only for arc-level turning points or deterministic fallback",
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


async def node_organize_project(state: ImportState) -> dict:
    """Deterministic world-item routing: filter module-contamination, enrich categoryPath/parentId.

    Updates both entity_registry["world_detailed"] (full detail dicts) and
    entity_registry["world"] (name→category index) so that proposal_write
    never sees excluded names in either structure.
    """
    registry = dict(state.get("entity_registry", {}))
    world_candidates: dict = {k: dict(v) for k, v in registry.get("world_detailed", {}).items()}

    if not world_candidates:
        return {}

    organizer_input = OrganizerInput(
        characters=registry.get("characters", {}),
        events=list(registry.get("events", {}).values()),
        relationships=state.get("relationships", []),
        world_candidates=world_candidates,
        manuscript_notes=[],
        timeline_architecture=dict(state.get("timeline_architecture") or {}),
        project_digest={},
        source_language=state.get("source_language", "en"),
    )

    result = organize_project_content(organizer_input)
    if state.get("import_run_id"):
        _write_import_artifact(state["project_path"], state["import_run_id"], "organizer_output.json", result)

    excluded_names: set[str] = {item["name"] for item in result.get("excluded_items", [])}
    enrichments: dict[str, dict] = {item["name"]: item for item in result.get("world_items", [])}

    updated_world_detailed: dict = {}
    for name, detail in world_candidates.items():
        if name in excluded_names:
            continue
        if name in enrichments:
            enriched = enrichments[name]
            detail = {
                **detail,
                "categoryPath": enriched.get("categoryPath", []),
                "parentId": enriched.get("parentId"),
                "container_key": enriched.get("container_key", ""),
                "containerId": enriched.get("containerId", ""),
            }
        updated_world_detailed[name] = detail

    # Mirror the exclusion filter onto the flat world index so proposal_write
    # does not iterate excluded names from entity_registry["world"].
    updated_world: dict = {}
    for name, cat in registry.get("world", {}).items():
        if name in excluded_names:
            continue
        enriched = enrichments.get(name)
        updated_world[name] = enriched.get("category") if enriched else cat

    updated_registry = {**registry, "world_detailed": updated_world_detailed, "world": updated_world}
    # Organizer targets replace model-suggested containers for imported items;
    # their stable IDs make container/item proposal dependencies deterministic.
    world_containers = [
        {
            "id": container["id"],
            "name": container["label"],
            "type": container["type"],
            "importCategoryKey": container["container_key"],
            "isDefault": False,
        }
        for container in result.get("world_containers", [])
    ]
    return {"entity_registry": updated_registry, "world_containers": world_containers}


def _reviewer_proposals_from_state(state: ImportState | dict) -> list[dict]:
    """Build a compact Proposal-like view so direct W1 graph reviews run reviewers too."""
    registry = state.get("entity_registry", {}) or {}
    operations: list[dict] = []

    for cid, character in (registry.get("characters", {}) or {}).items():
        if not isinstance(character, dict) or character.get("skip_create"):
            continue
        operations.append({
            "op": "create",
            "entityType": "character",
            "entityId": cid,
            "fields": {
                "name": character.get("canonical_name") or character.get("name") or "",
                "summary": character.get("summary") or "；".join(character.get("notes", [])[:3]),
                "background": character.get("background", ""),
                "aliases": character.get("aliases", []),
                "importance": character.get("importance", ""),
                "evidence_refs": character.get("evidence_refs", []),
                "source_span": character.get("source_span"),
                "source_segment_id": character.get("source_segment_id", ""),
                "source_chunk_id": character.get("source_chunk_id"),
            },
        })

    for eid, event in (registry.get("events", {}) or {}).items():
        if not isinstance(event, dict):
            continue
        operations.append({
            "op": "create",
            "entityType": "timeline_event",
            "entityId": eid,
            "fields": {
                **event,
                "title": event.get("title", ""),
                "branchId": event.get("branchId") or event.get("branch_id") or "",
                "timelineClass": event.get("timelineClass") or event.get("eventClass") or "canonical_event",
            },
        })

    for name, detail in (registry.get("world_detailed", {}) or {}).items():
        if not isinstance(detail, dict):
            continue
        operations.append({
            "op": "create",
            "entityType": "world",
            "entityId": detail.get("id") or name,
            "fields": {
                "name": detail.get("name") or name,
                "category": detail.get("category", ""),
                "description": detail.get("description", ""),
                "categoryPath": detail.get("categoryPath", []),
                "parentId": detail.get("parentId"),
            },
        })

    for idx, relationship in enumerate(state.get("relationships", []) or []):
        if not isinstance(relationship, dict):
            continue
        rid = relationship.get("id") or relationship.get("relationship_id") or f"relationship_{idx}"
        operations.append({
            "op": "create",
            "entityType": "relationship",
            "entityId": rid,
            "fields": relationship,
        })

    return [{"id": f"{state.get('import_run_id', 'w1')}_review_batch", "operations": operations}]


async def node_review_import(state: ImportState) -> dict:
    """Validate pre-proposal compiler outputs; final proposal receipts are not available yet."""
    # Review the same deterministic entity set that proposal staging will write.
    finalized_state = {**state, **_finalize_registry_for_proposal_staging(state)}
    finalized_state = {**finalized_state, **_finalize_supervisor_evidence_bindings(finalized_state)}
    registry = finalized_state.get("entity_registry", {})
    reducer = state.get("reducer_artifact", {})
    timeline = state.get("timeline_architecture", {})
    warnings: list[str] = list(reducer.get("warnings", [])) + list(timeline.get("warnings", []))
    errors: list[str] = list(finalized_state.get("errors", []))
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

    manuscript_chapters = finalized_state.get("manuscript_chapters", [])
    observability: dict = {
        "observability_phase": "pre_proposal",
        "characters_extracted": len([c for c in registry.get("characters", {}).values() if not c.get("skip_create")]),
        "events_extracted": len(registry.get("events", {})),
        "world_items_extracted": len(registry.get("world_detailed", {})),
        "relationships_preproposal_count": len(finalized_state.get("relationships", [])),
        "manuscript_chapters_preproposal_count": len(manuscript_chapters),
        "manuscript_staging_pending": True,
        "canonical_events_count": len(timeline.get("canonical_events", [])),
        "branch_count": len(finalized_state.get("timeline_branches", [])),
        "duplicate_count": len(timeline.get("discarded_duplicates", [])),
        "topology_warning_count": len(timeline.get("warnings", [])),
    }

    reviewer_reports: dict[str, dict] = {}
    try:
        from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer
        from sidecar.supervisor.reviewers.fact_reviewer import FactReviewer
        from sidecar.supervisor.reviewers.consistency_reviewer import ConsistencyReviewer

        reviewer_state = {
            **finalized_state,
            "proposals": _reviewer_proposals_from_state(finalized_state),
            "inbox_proposals": _reviewer_proposals_from_state(finalized_state),
        }
        reviewer_reports = {
            "quality": QualityReviewer().review(reviewer_state),
            "fact": FactReviewer().review(reviewer_state),
            "consistency": ConsistencyReviewer().review(reviewer_state),
        }
        for reviewer_name, reviewer_report in reviewer_reports.items():
            for finding in reviewer_report.get("findings", [])[:6]:
                finding_id = finding.get("finding_id") or finding.get("id") or "finding"
                severity = finding.get("severity", "unknown")
                message = finding.get("description") or finding.get("message", "")
                warnings.append(f"{reviewer_name}_reviewer:{severity}:{finding_id}: {message}")
    except Exception as exc:
        warnings.append(f"reviewers_unavailable: {exc}")

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
        "import_observability": observability,
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
        "reviewer_reports": reviewer_reports,
    }
    if finalized_state.get("import_run_id"):
        _write_import_artifact(finalized_state["project_path"], finalized_state["import_run_id"], "review_report.json", report)
    return {
        "entity_registry": registry,
        "relationships": finalized_state.get("relationships", []),
        "evidence_cards": finalized_state.get("evidence_cards", state.get("evidence_cards", [])),
        "import_review_report": report,
        "errors": errors,
        "progress": max(float(finalized_state.get("progress", 0.91)), 0.92),
    }


def _write_manuscript_json(project_path: Path, state: ImportState, manuscript_chapters: list[dict]) -> None:
    """Legacy canonical manuscript writer; proposal mode stages content instead of calling this."""
    manuscript_path = project_path / "manuscript.json"
    _ms_now = datetime.now(timezone.utc).isoformat()
    with open(manuscript_path, "w", encoding="utf-8") as _ms_f:
        _ms_f.write('{\n')
        _ms_f.write(f'  "source_file": {json.dumps(state["source_file_path"], ensure_ascii=False)},\n')
        _ms_f.write(f'  "imported_at": {json.dumps(_ms_now)},\n')
        _ms_f.write('  "chapters": [\n')
        for _ms_i, _ms_ch in enumerate(manuscript_chapters):
            if _ms_i > 0:
                _ms_f.write(',\n')
            _ms_f.write('    ')
            json.dump(_ms_ch, _ms_f, ensure_ascii=False)
        _ms_f.write('\n  ]\n}\n')


def _safe_node_id(raw_id: str) -> str:
    """Return a filename-safe version of raw_id for use in ManuscriptNode ids and .md filenames."""
    safe = re.sub(r"[/\\:*?\"<>| \x00-\x1f]", "_", raw_id)
    return safe if safe else "mn_unknown"


def _estimate_word_count(text: str, source_language: str) -> int:
    """CJK: count characters in U+4E00-U+9FFF; Latin: whitespace-split tokens."""
    if source_language == "zh":
        return sum(1 for ch in text if "一" <= ch <= "鿿")
    return len(text.split())


def _write_manuscript_nodes(
    project_path: Path,
    manuscript_scene_pairs: list[tuple[dict, dict]],
    source_language: str,
) -> None:
    """Write ManuscriptNode tree + per-chapter .md content to writing/manuscript/.

    Called BEFORE proposal writes so the projection survives proposal cancellation.
    Follows the same early-write semantics as _write_manuscript_json.
    """
    ms_dir = project_path / "writing" / "manuscript"
    ms_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = ms_dir / "nodes.json"
    if not manuscript_scene_pairs:
        if nodes_path.exists():
            try:
                existing = json.loads(nodes_path.read_text(encoding="utf-8"))
                if isinstance(existing, list) and existing:
                    return
            except Exception:
                return
        return
    source_is_zh = source_language == "zh"
    scene_title = "章节正文" if source_is_zh else "Chapter Text"
    nodes: list[dict] = []
    for idx, (chapter_info, mc) in enumerate(manuscript_scene_pairs):
        chap_id = chapter_info["chapter_id"]
        scene_id = chapter_info["scene_id"]
        chap_node_id = _safe_node_id(f"mn_{chap_id}")
        scene_node_id = _safe_node_id(f"mn_{scene_id}")
        if not chap_node_id:
            chap_node_id = f"mn_unknown_{idx}"
        if not scene_node_id:
            scene_node_id = f"mn_unknown_scene_{idx}"
        content = chapter_info.get("content", "") or ""
        word_count = _estimate_word_count(content, source_language)
        nodes.append({
            "id": chap_node_id,
            "title": chapter_info["title"],
            "type": "chapter_outline",
            "parentId": None,
            "orderIndex": idx,
            "linkedChapterId": chap_id,
            "linkedSceneId": None,
            "depth": 0,
            "collapsed": False,
            "wordCount": word_count,
            "source_span": mc.get("source_span"),   # propagate from chunk; None if absent
        })
        nodes.append({
            "id": scene_node_id,
            "title": scene_title,
            "type": "scene_outline",
            "parentId": chap_node_id,
            "orderIndex": 0,
            "linkedChapterId": chap_id,
            "linkedSceneId": scene_id,
            "depth": 1,
            "collapsed": False,
            "wordCount": word_count,
        })
        (ms_dir / f"{scene_node_id}.md").write_text(content, encoding="utf-8")
    with open(nodes_path, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)


def _stage_manuscript_projection(
    state: ImportState,
    manuscript_scene_pairs: list[tuple[dict, dict]],
    source_language: str,
) -> dict:
    """Persist an acceptance-gated manuscript projection outside canonical storage."""
    raw_source = str(state.get("source_text", "") or "")
    chapters: list[dict] = []
    nodes: list[dict] = []
    scene_documents: list[dict] = []
    scene_title = "章节正文" if source_language == "zh" else "Chapter Text"
    for index, (chapter_info, chapter) in enumerate(manuscript_scene_pairs):
        source_span = chapter.get("source_span")
        if raw_source:
            ok, errors = validate_source_span(source_span or {}, raw_source)
            if not ok:
                raise ValueError(f"Cannot stage manuscript projection with invalid source span: {errors}")
        elif not isinstance(source_span, dict) or not {"raw_source_hash", "absolute_start", "absolute_end", "substring_hash"}.issubset(source_span):
            # Compatibility for historical checkpoints that predate SourceSpan.
            # New imports always use the raw-source branch above.
            source_span = make_source_span(str(chapter_info.get("content", "") or ""), 0, len(str(chapter_info.get("content", "") or "")))
            chapter["source_span"] = source_span
        chapter_id = chapter_info["chapter_id"]
        scene_id = chapter_info["scene_id"]
        chapter_node_id = _safe_node_id(f"mn_{chapter_id}")
        scene_node_id = _safe_node_id(f"mn_{scene_id}")
        content = chapter_info.get("content", "") or ""
        word_count = _estimate_word_count(content, source_language)
        chapters.append({
            **chapter_info,
            "source_span": source_span,
            "acceptance_status": "pending",
        })
        nodes.extend([
            {
                "id": chapter_node_id,
                "title": chapter_info["title"],
                "type": "chapter_outline",
                "parentId": None,
                "orderIndex": index,
                "linkedChapterId": chapter_id,
                "linkedSceneId": None,
                "depth": 0,
                "collapsed": False,
                "wordCount": word_count,
                "source_span": source_span,
            },
            {
                "id": scene_node_id,
                "title": scene_title,
                "type": "scene_outline",
                "parentId": chapter_node_id,
                "orderIndex": 0,
                "linkedChapterId": chapter_id,
                "linkedSceneId": scene_id,
                "depth": 1,
                "collapsed": False,
                "wordCount": word_count,
                "source_span": source_span,
            },
        ])
        scene_documents.append({"node_id": scene_node_id, "scene_id": scene_id, "content": content, "source_span": source_span})
    payload = {
        "contract_version": "w1-staged-manuscript-v1",
        "import_run_id": state.get("import_run_id", ""),
        "source_file_path": state.get("source_file_path", ""),
        "acceptance_required": True,
        "application_target": "canonical_manuscript_after_proposal_acceptance",
        "chapters": chapters,
        "nodes": nodes,
        "scene_documents": scene_documents,
    }
    artifact_path = _write_import_artifact(
        state["project_path"], str(state.get("import_run_id", "")), "staged_manuscript_projection.json", payload
    )
    return {"artifact_path": artifact_path, "contract_version": payload["contract_version"]}


async def node_write_to_project(state: ImportState) -> dict:
    """Create W1 proposals, stage manuscript content, and trigger W2 post-import work."""
    import gc as _gc
    finalized_staging = _finalize_registry_for_proposal_staging(state)
    # Proposal writing progressively pops entities to bound memory. Preserve that
    # long-standing mutation contract while replacing it with the final snapshot.
    original_registry = state.get("entity_registry")
    if isinstance(original_registry, dict):
        original_registry.clear()
        original_registry.update(finalized_staging["entity_registry"])
        finalized_staging["entity_registry"] = original_registry
    state = {**state, **finalized_staging}
    project_path = Path(state["project_path"])
    registry = state.get("entity_registry", {})
    manuscript_chapters = state.get("manuscript_chapters", [])
    relationships = state.get("relationships", [])
    character_tags = state.get("character_tags", [])
    world_settings = state.get("world_settings", {})
    timeline_branches = state.get("timeline_branches", [])
    source_language = state.get("source_language", "en")
    import_run_id = str(state.get("import_run_id", "") or "")
    raw_source_evidence_path = _stage_raw_source_evidence(state)
    staged_state = {**state, "source_file_path": str(raw_source_evidence_path)}
    world_containers = list(state.get("world_containers", []))
    existing_container_keys = {
        str(container.get("importCategoryKey", "")).strip()
        for container in world_containers
        if str(container.get("importCategoryKey", "")).strip()
    }
    existing_container_ids = {str(container.get("id", "")).strip() for container in world_containers if str(container.get("id", "")).strip()}
    for spec in _default_world_container_specs(source_language):
        if spec["importCategoryKey"] in existing_container_keys or spec["id"] in existing_container_ids:
            continue
        world_containers.append({**spec, "sortOrder": len(world_containers)})
        existing_container_keys.add(spec["importCategoryKey"])
        existing_container_ids.add(spec["id"])

    # Compact receipts — one small dict per proposal — replace the old full-payload list.
    receipts: list[dict] = []
    errors: list[str] = list(state.get("errors", []))

    # The staged contract is durable even if a later proposal operation is
    # cancelled. It is deliberately outside canonical manuscript storage.
    preaccept_pairs: list[tuple[dict, dict]] = []
    for index, chapter in enumerate(_sort_manuscript_chapters(list(manuscript_chapters))):
        content = str(chapter.get("manuscript_content", "") or "")
        chapter_id = chapter.get("chapter_id") or _stable_id("chap", chapter.get("title", "Chapter"), index, _sha256_text(content))
        scene_id = chapter.get("scene_id") or f"scene_{str(chapter_id).removeprefix('chap_')}"
        preaccept_pairs.append((
            {
                "chapter_id": chapter_id,
                "scene_id": scene_id,
                "title": str(chapter.get("title") or "Untitled Chapter"),
                "summary": str(chapter.get("summary") or _chapter_summary_fallback(str(chapter.get("title") or "Chapter"), content)),
                "goal": str(chapter.get("goal") or _chapter_goal_fallback(source_language)),
                "notes": str(chapter.get("notes") or _chapter_notes_fallback(staged_state["source_file_path"], list(chapter.get("chunk_ids", [])))),
                "orderIndex": index,
                "content": content,
            },
            chapter,
        ))
    _stage_manuscript_projection(staged_state, preaccept_pairs, source_language)

    # Timeline Architect is the sole authority for canonical event identity.
    # Build every reverse link from that finalized set before any proposal is
    # emitted; proposal writing must never run a second identity/dedupe pass.
    canonical_events = {
        str(event_id): dict(event)
        for event_id, event in (registry.get("events", {}) or {}).items()
        if str(event_id).strip() and isinstance(event, dict)
    }
    registry["events"] = canonical_events
    character_event_links: dict[str, list[str]] = {}
    for event_id, event in canonical_events.items():
        for cid in event.get("character_ids", []):
            character_event_links.setdefault(cid, [])
            if event_id not in character_event_links[cid]:
                character_event_links[cid].append(event_id)
    character_id_map = registry.get("character_id_map", {})
    imported_character_names = {
        str(entry.get("canonical_name") or entry.get("name") or "").strip()
        for entry in registry.get("characters", {}).values()
        if str(entry.get("canonical_name") or entry.get("name") or "").strip()
    }

    # Write character proposals — iterate-with-pop so each entry is GC-eligible
    # immediately after its await, rather than holding the full snapshot.
    characters = registry.pop("characters", {})
    print(f"[proposal_write] writing {len(characters)} character proposals...", flush=True)
    for cid in list(characters.keys()):
        entry = characters.pop(cid)
        if entry.get("skip_create"):
            decision = entry.get("entity_merge_decision")
            existing_id = str(entry.get("existing_project_id") or "")
            if not isinstance(decision, dict) or not existing_id:
                errors.append(f"Matched character {cid} has no executable EntityMergeDecision")
                continue
            fields = decision.get("fields", {})
            update_data = {
                "id": existing_id,
                "aliases": fields.get("aliases", {}).get("value", []),
                "background": fields.get("background", {}).get("value", ""),
                "experience": fields.get("experience", {}).get("value", []),
                "experiences": fields.get("experiences", {}).get("value", []),
                "traits": fields.get("traits", {}).get("value", fields.get("personality_traits", {}).get("value", [])),
                "personalityTraits": fields.get("personality_traits", {}).get("value", fields.get("traits", {}).get("value", [])),
                "notes": fields.get("notes", {}).get("value", []),
                "physicalDescription": fields.get("physical_description", {}).get("value", ""),
                "speechStyle": fields.get("speech_style", {}).get("value", ""),
                "arcNotes": fields.get("arc_notes", {}).get("value", ""),
                "importConfidence": fields.get("confidence", {}).get("value", entry.get("confidence", 0)),
                "mergeEvidence": {
                    "importCharacterId": cid,
                    "entityMergeDecision": decision,
                    "semanticConflicts": decision.get("conflicts", []),
                },
                "importRunId": import_run_id,
            }
            op = {
                "op_type": "update",
                "entity_type": "character",
                "entity_id": existing_id,
                "data": update_data,
                "source_workflow": "W1_import",
                "confidence": float(fields.get("confidence", {}).get("value", entry.get("confidence", 0.7)) or 0.7),
                "auto_apply": False,
                "depends_on": [],
                "diagnostics": {
                    "contract": "EntityMergeDecision/v1",
                    "semantic_conflicts": decision.get("conflicts", []),
                },
            }
            try:
                proposal = await s2_memory_writer.propose_write(op, str(project_path))
                receipts.append({
                    "id": proposal.get("id", ""),
                    "entity_type": "character",
                    "status": proposal.get("status", ""),
                    "confidence": float(proposal.get("confidence", op["confidence"]) or op["confidence"]),
                    "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
                })
            except Exception as e:
                errors.append(f"Failed to propose character merge {cid}->{existing_id}: {str(e)}")
            continue
        entry = _compact_character_card(dict(entry))
        experience, background, profile_field_evidence = _backfill_character_profile_at_write_boundary(cid, entry)
        op = {
            "op_type": "create",
            "entity_type": "character",
            "entity_id": cid,
            "data": {
                "id": cid,
                "name": entry.get("canonical_name", ""),
                "aliases": entry.get("aliases", []),
                "summary": entry.get("summary", "") or " ".join(entry.get("notes", [])[:2]),
                "background": background,
                "traits": entry.get("personality_traits", []),
                "goals": [],
                "fears": [],
                "secrets": [],
                "speechStyle": "",
                "arc": "",
                "experience": experience,
                "tagIds": entry.get("tag_ids", []),
                "linkedEventIds": character_event_links.get(cid, []),
                "roleInStory": entry.get("role_in_story", ""),
                "physicalDescription": entry.get("physical_description", ""),
                "notes": [
                    *entry.get("notes", [])[:4],
                    *[f"Open question: {question}" for question in entry.get("open_questions", [])[:2]],
                ],
                "importConfidence": entry.get("confidence", 0.7),
                "importRunId": import_run_id,
                "importImportance": entry.get("importance", ""),
                "importCardType": "draft",
                "evidenceRefs": entry.get("evidence_refs", []),
                "sourceSpan": entry.get("source_span"),
                "sourceSegmentId": entry.get("source_segment_id", ""),
                "enrichmentRecommended": bool(entry.get("open_questions")),
                "importance": entry.get("importance", "supporting") or "supporting",
                "groupKey": entry.get("groupKey", IMPORTANCE_TO_GROUP.get(entry.get("importance", ""), "")) or "",
                **({"profile_field_evidence": profile_field_evidence} if profile_field_evidence else {}),
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": entry.get("tag_ids", []),
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "character",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose character {cid}: {str(e)}")
    del characters
    _gc.collect()
    print(f"[proposal_write] characters done ({len(receipts)} receipts)", flush=True)

    # Determine default branch for event assignment, creating one when the
    # compiler did not infer any timeline branches.
    event_branch_refs = {
        str(event.get("branchId") or event.get("branch_id") or "").strip()
        for event in registry.get("events", {}).values()
        if str(event.get("branchId") or event.get("branch_id") or "").strip()
    }
    if timeline_branches:
        filtered_branches: list[dict] = []
        seen_branch_ids: set[str] = set()
        for branch in timeline_branches:
            branch_id = str(branch.get("id") or branch.get("branchId") or "").strip()
            if not branch_id or branch_id in seen_branch_ids:
                continue
            has_events = branch_id in event_branch_refs
            is_root = branch.get("mode") == "root" or branch.get("isDefault")
            if has_events or (is_root and not event_branch_refs):
                filtered_branches.append(branch)
                seen_branch_ids.add(branch_id)
        if filtered_branches:
            timeline_branches = filtered_branches

    default_branch_id = next(
        (b["id"] for b in timeline_branches if b.get("mode") == "root"),
        None,
    ) or next((b["id"] for b in timeline_branches), None)

    if not default_branch_id:
        _wtp_lang = source_language
        default_branch_id = f"branch_{uuid.uuid4().hex[:8]}"
        timeline_branches = [{
            "id": default_branch_id,
            "name": "主时间线" if _wtp_lang == "zh" else "Main Timeline",
            "description": "主叙事时间线" if _wtp_lang == "zh" else "Primary narrative timeline",
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
            "data": {
                **branch,
                "id": branch_id,
                "isDefault": bool(branch.get("isDefault", branch.get("mode") == "root")),
                "importRunId": import_run_id,
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "timeline_branch",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose timeline branch {branch_id}: {str(e)}")

    valid_branch_ids = {str(branch.get("id", "")).strip() for branch in timeline_branches if str(branch.get("id", "")).strip()}

    def _proposal_event_branch_id(entry: dict) -> str:
        branch_id = str(entry.get("branchId") or entry.get("branch_id") or "").strip()
        if branch_id in valid_branch_ids:
            return branch_id
        return str(default_branch_id or next(iter(valid_branch_ids), "")).strip()

    # Timeline Architect already reduced candidates into canonical events and
    # recorded every merge. Re-deduping here used to discard IDs without a
    # remap, leaving character.linkedEventIds dangling in the review package.
    events_snapshot = registry.pop("events", {})

    # Keep Timeline Architect's branch-local orderIndex when present. Falling
    # back to temporal hints preserves legacy behavior for older checkpoints.
    sorted_events = sorted(
        events_snapshot.items(),
        key=lambda kv: (
            _proposal_event_branch_id(kv[1]),
            int(kv[1].get("orderIndex", 10_000) or 0),
            kv[1].get("temporal_hint", "") or "",
        ),
    )

    # Write event proposals
    print(f"[proposal_write] writing {len(sorted_events)} event proposals...", flush=True)
    for fallback_order_idx, (eid, entry) in enumerate(sorted_events):
        order_index = int(entry.get("orderIndex", fallback_order_idx) or 0)
        branch_id = _proposal_event_branch_id(entry)
        op = {
            "op_type": "create",
            "entity_type": "timeline_event",
            "entity_id": eid,
            "data": {
                "id": eid,
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "branchId": branch_id,
                "orderIndex": order_index,
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
                "importRunId": import_run_id,
                "mergedEventIds": entry.get("mergedEventIds", []),
                "layoutHints": entry.get("layoutHints", {}),
                "evidenceRefs": entry.get("evidence_refs", []),
                "sourceSpan": entry.get("source_span"),
                "sourceSegmentId": entry.get("source_segment_id", ""),
            },
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [branch_id],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "timeline_event",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose event {eid}: {str(e)}")
    del events_snapshot, sorted_events
    _gc.collect()
    print(f"[proposal_write] events done ({len(receipts)} receipts)", flush=True)

    # Write world item proposals
    # Route by semantic category, not just container type. This prevents
    # organizations/rules/items from collapsing into the first map/notebook.
    container_by_key: dict[str, str] = {}
    for container in world_containers:
        container_id = str(container.get("id", "")).strip()
        if not container_id:
            continue
        key = str(container.get("importCategoryKey", "")).strip()
        if not key:
            key = _world_container_key(container.get("category") or container.get("name") or container.get("type"))
        container_by_key.setdefault(key, container_id)
    fallback_world_container_id = (
        container_by_key.get("concepts")
        or container_by_key.get("locations")
        or next(iter(container_by_key.values()), "")
    )
    valid_world_parent_ids = {
        str(container.get("id", "")).strip()
        for container in world_containers
        if str(container.get("id", "")).strip()
    }

    def _resolve_container_id(name: str, cat: str) -> tuple[str, str]:
        resolved_category = _normalize_world_category(name, cat)
        container_key = _world_container_key(resolved_category)
        return resolved_category, container_by_key.get(container_key) or fallback_world_container_id

    # Write world container proposals before items so batch or sequential accept
    # can satisfy item.containerId references without manual ordering.
    for container in world_containers:
        container_id = container.get("id") or f"cont_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "world_container",
            "entity_id": container_id,
            "data": {**container, "id": container_id, "importRunId": import_run_id},
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "world_container",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose world container {container_id}: {str(e)}")

    def _is_person_like_world_entry(name: str, detail: dict, category: str) -> bool:
        raw_category = str(detail.get("category") or category or "").lower()
        if name in imported_character_names:
            return True
        if any(token in raw_category for token in ("person", "character", "人物", "角色", "人名")):
            return True
        return False

    # Pop world dicts from registry — they can be large (366 entries × attributes).
    world_detailed = registry.pop("world_detailed", {})
    world_snapshot = registry.pop("world", {})
    print(f"[proposal_write] writing {len(world_snapshot)} world item proposals...", flush=True)
    for name, category in world_snapshot.items():
        wid = f"world_{uuid.uuid4().hex[:8]}"
        detail = world_detailed.pop(name, {})  # Progressive release as we iterate
        if _is_person_like_world_entry(name, detail, category):
            continue
        resolved_category, resolved_container_id = _resolve_container_id(name, detail.get("category", category))
        detail_container_id = str(detail.get("containerId") or "").strip()
        container_id = (
            detail_container_id
            if detail_container_id in valid_world_parent_ids
            else resolved_container_id
        )
        detail_parent_id = str(detail.get("parentId") or "").strip()
        parent_id = (
            detail_parent_id
            if detail_parent_id in valid_world_parent_ids
            else container_id
        )
        op = {
            "op_type": "create",
            "entity_type": "world_item",
            "entity_id": wid,
            "data": {
                "id": wid,
                "name": name,
                "category": resolved_category,
                "type": resolved_category,
                "containerId": container_id,
                "categoryPath": detail.get("categoryPath") or _world_category_path(resolved_category, name),
                "parentId": parent_id,
                "description": detail.get("description", ""),
                "attributes": detail.get("attributes", []),
                "importRunId": import_run_id,
            },
            "source_workflow": "W1_import",
            "confidence": 0.70,
            "auto_apply": False,
            "depends_on": [container_id] if container_id else [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "world_item",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.70) or 0.70),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose world entry '{name}': {str(e)}")
    del world_snapshot, world_detailed
    _gc.collect()
    print(f"[proposal_write] world items done ({len(receipts)} receipts)", flush=True)

    # Write relationship proposals
    for relationship in relationships:
        rel_id = relationship.get("id") or f"rel_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "relationship",
            "entity_id": rel_id,
            "data": {**relationship, "id": rel_id, "importRunId": import_run_id},
            "source_workflow": "W1_import",
            "confidence": float(relationship.get("importConfidence", 0.75)),
            "auto_apply": False,
            "depends_on": [relationship.get("sourceId", ""), relationship.get("targetId", "")],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "relationship",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose relationship {rel_id}: {str(e)}")

    # Write character tag proposals
    for tag in character_tags:
        tag_id = tag.get("id") or f"tag_{uuid.uuid4().hex[:8]}"
        op = {
            "op_type": "create",
            "entity_type": "character_tag",
            "entity_id": tag_id,
            "data": {**tag, "id": tag_id, "importRunId": import_run_id},
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "character_tag",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose character tag {tag_id}: {str(e)}")

    # Write world settings proposal
    if world_settings:
        op = {
            "op_type": "update",
            "entity_type": "world_settings",
            "entity_id": "world_settings",
            "data": {**world_settings, "importRunId": import_run_id},
            "source_workflow": "W1_import",
            "confidence": 0.75,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "world_settings",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.75) or 0.75),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose world settings: {str(e)}")

    # ── Chapter + manuscript scene proposals ──────────────────────────────────
    # manuscript_chapters are assembled by node_build_manuscript from chapter_hint grouping.
    # Each one becomes a Chapter entity proposal for user review.
    manuscript_scene_pairs: list[tuple[dict, dict]] = []
    source_is_zh = source_language == "zh"

    def _chapter_excerpt(text: str, limit: int = 180) -> str:
        return re.sub(r"\s+", " ", text or "").strip()[:limit]

    for idx, mc in enumerate(_sort_manuscript_chapters(list(state.get("manuscript_chapters", [])))):
        chap_id = mc.get("chapter_id") or f"chap_{uuid.uuid4().hex[:8]}"
        title = mc.get("title", "Untitled Chapter").strip()
        if not title:
            continue
        manuscript_content = str(mc.get("manuscript_content", "") or "")
        scene_id = mc.get("scene_id") or f"scene_{str(chap_id).removeprefix('chap_')}"
        summary = str(mc.get("summary") or _chapter_excerpt(manuscript_content, 220))
        goal = str(
            mc.get("goal")
            or ("梳理本章导入正文并核对人物、事件与设定引用。" if source_is_zh else "Review imported chapter text and reconcile character, event, and world references.")
        )
        manuscript_scene_pairs.append((
            {
                "chapter_id": chap_id,
                "scene_id": scene_id,
                "title": title,
                "summary": summary,
                "goal": goal,
                "notes": f"Imported from: {staged_state['source_file_path']}; chunks: {', '.join(map(str, mc.get('chunk_ids', [])))}",
                "orderIndex": idx,
                "content": manuscript_content,
            },
            mc,
        ))

    # Stage the deterministic manuscript projection. Canonical manuscript files
    # are written only by the proposal-acceptance path, never by W1 extraction.
    staged_manuscript_projection = _stage_manuscript_projection(staged_state, manuscript_scene_pairs, source_language)

    # Phase 3: chapter proposals
    for chapter_info, mc in manuscript_scene_pairs:
        chap_id = chapter_info["chapter_id"]
        op = {
            "op_type": "create",
            "entity_type": "chapter",
            "entity_id": chap_id,
            "data": {
                "id": chap_id,
                "title": chapter_info["title"],
                "orderIndex": chapter_info["orderIndex"],
                "content": chapter_info["content"],
                "manuscriptContent": chapter_info["content"],
                "summary": chapter_info["summary"],
                "goal": chapter_info["goal"],
                "notes": chapter_info["notes"],
                "sceneIds": [],
                "status": "draft",
                "importRunId": import_run_id,
                "sourceSpan": mc.get("source_span"),
                "stagedManuscriptProjection": {
                    **staged_manuscript_projection,
                    "chapter_id": chap_id,
                    "scene_id": chapter_info["scene_id"],
                },
            },
            "source_workflow": "W1_import",
            "confidence": 0.90,
            "auto_apply": False,
            "depends_on": [],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "chapter",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.90) or 0.90),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose chapter '{chapter_info['title']}': {str(e)}")

    for chapter_info, mc in manuscript_scene_pairs:
        scene_title = "章节正文" if source_is_zh else "Chapter Text"
        op = {
            "op_type": "create",
            "entity_type": "scene",
            "entity_id": chapter_info["scene_id"],
            "data": {
                "id": chapter_info["scene_id"],
                "chapterId": chapter_info["chapter_id"],
                "title": scene_title,
                "summary": chapter_info["summary"],
                "content": chapter_info["content"],
                "orderIndex": 0,
                "povCharacterId": None,
                "linkedCharacterIds": [],
                "linkedEventIds": [],
                "linkedWorldItemIds": [],
                "status": "draft",
                "notes": chapter_info["notes"],
                "importRunId": import_run_id,
                "sourceSpan": mc.get("source_span"),
                "stagedManuscriptProjection": {
                    **staged_manuscript_projection,
                    "chapter_id": chapter_info["chapter_id"],
                    "scene_id": chapter_info["scene_id"],
                },
            },
            "source_workflow": "W1_import",
            "confidence": 0.90,
            "auto_apply": False,
            "depends_on": [chapter_info["chapter_id"]],
        }
        try:
            proposal = await s2_memory_writer.propose_write(op, str(project_path))
            receipts.append({
                "id": proposal.get("id", ""),
                "entity_type": "scene",
                "status": proposal.get("status", ""),
                "confidence": float(proposal.get("confidence", 0.90) or 0.90),
                "blocked": bool(proposal.get("blockedReason") or proposal.get("requiresManualReview")),
            })
        except Exception as e:
            errors.append(f"Failed to propose manuscript scene for chapter '{chapter_info['title']}': {str(e)}")
    print(f"[proposal_write] all entity groups done — {len(receipts)} total receipts", flush=True)

    # Compile the complete import package as a typed reference graph before it
    # becomes reviewable. Optional backlinks are remapped/dropped explicitly;
    # unresolved structural edges fail closed and remove the whole staged run.
    if import_run_id:
        from sidecar.shared.proposal_graph import compile_import_run_package

        graph_result = compile_import_run_package(
            project_path,
            import_run_id,
            _proposal_graph_existing_ids(_load_existing_project_snapshot(project_path)),
            remove_invalid_package=True,
        )
        if not graph_result["atomic"]:
            errors.append(
                "Proposal graph compilation failed; staged package removed: "
                + json.dumps(graph_result["blockingErrors"], ensure_ascii=False, sort_keys=True)
            )
            receipts.clear()
        elif graph_result["droppedRefs"]:
            print(
                f"[proposal_write] graph compiler normalized {len(graph_result['droppedRefs'])} optional dangling reference(s)",
                flush=True,
            )

    # Build review_report counts and ID lists from compact receipts.
    safe_types = {"character_tag", "timeline_branch", "world_container", "chapter", "scene"}
    proposal_counts: dict[str, int] = {}
    all_proposal_ids: list[str] = []
    blocked_ids: list[str] = []
    safe_accept_ids: list[str] = []
    for receipt in receipts:
        et = receipt["entity_type"]
        proposal_counts[et] = proposal_counts.get(et, 0) + 1
        pid = receipt["id"]
        if pid:
            all_proposal_ids.append(pid)
            if receipt.get("blocked") or receipt.get("status") == "blocked":
                blocked_ids.append(pid)
            if et in safe_types and receipt["confidence"] >= 0.7:
                safe_accept_ids.append(pid)

    review_report = dict(state.get("import_review_report", {}))
    if review_report:
        review_report["proposal_counts"] = proposal_counts
        review_report["safe_accept_ids"] = safe_accept_ids
        review_report["blocked_ids"] = blocked_ids
        review_report["proposal_ids"] = all_proposal_ids
        if state.get("import_run_id"):
            _write_import_artifact(str(project_path), state["import_run_id"], "review_report.json", review_report)

    if state.get("import_run_id"):
        _write_import_artifact(
            str(project_path),
            state["import_run_id"],
            "proposal_write_receipts.json",
            {"proposal_counts": proposal_counts, "proposal_ids": all_proposal_ids, "receipts": receipts},
        )

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
        "proposals": receipts,
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


# ── Relationship type normalization helpers ───────────────────────────────────

_ZH_CATEGORY_LABELS: dict[str, str] = {
    "family":          "家族关系",
    "romantic":        "情感关系",
    "rivalry":         "竞争关系",
    "mentor_disciple": "师徒关系",
    "sworn_brothers":  "结拜关系",
    "political":       "政治关系",
    "conflict":        "对立关系",
    "unknown":         "关系",
}

_RELATIONSHIP_ONTOLOGY: dict[str, dict[str, str]] = {
    "family": {"label": "家族关系", "directionality": "symmetric"},
    "romantic": {"label": "情感关系", "directionality": "symmetric"},
    "rivalry": {"label": "竞争关系", "directionality": "symmetric"},
    "sworn_brothers": {"label": "结拜关系", "directionality": "symmetric"},
    "conflict": {"label": "对立关系", "directionality": "symmetric"},
    "mentor_disciple": {"label": "师徒关系", "directionality": "directed"},
    "political": {"label": "政治关系", "directionality": "directed"},
    "alliance": {"label": "盟友关系", "directionality": "symmetric"},
}
_ZH_REL_CATEGORY_ALIASES = {
    "家族": "family", "family": "family", "romance": "romantic", "情感": "romantic",
    "竞争": "rivalry", "rivalry": "rivalry", "师徒": "mentor_disciple", "mentor": "mentor_disciple",
    "政治": "political", "political": "political", "结拜": "sworn_brothers", "conflict": "conflict",
    "对立": "conflict", "alliance": "alliance", "盟友": "alliance",
}
_RELATIONSHIP_FALSE_LABELS = frozenset({"解惑", "选拔", "冷冰冰的师兄"})


def _relationship_ontology(relationship: dict, source_language: str) -> dict | None:
    """Normalize only ontology-backed relationships; phrase/events stay as evidence."""
    raw_type = str(relationship.get("type", "")).strip()
    raw_category = str(relationship.get("category", "")).strip().lower()
    if raw_type in _RELATIONSHIP_FALSE_LABELS or (len(raw_type) > 4 and any(token in raw_type for token in ("师兄", "师姐", "师弟", "师妹"))):
        return None
    key = _ZH_REL_CATEGORY_ALIASES.get(raw_category) or _ZH_REL_CATEGORY_ALIASES.get(raw_type.lower())
    if not key:
        # Chinese typed labels map through their canonical semantic forms only.
        key = next((candidate for candidate, metadata in _RELATIONSHIP_ONTOLOGY.items() if raw_type == metadata["label"]), None)
    metadata = _RELATIONSHIP_ONTOLOGY.get(key or "")
    if not metadata:
        return None if source_language == "zh" else {"ontologyType": raw_category or "other", "ontologyDirection": "directed"}
    return {
        "category": key,
        "type": metadata["label"] if source_language == "zh" else raw_type or key,
        "ontologyType": key,
        "ontologyDirection": metadata["directionality"],
        "sourceLabel": raw_type if raw_type and raw_type != metadata["label"] else relationship.get("sourceLabel", ""),
        "directionality": "bidirectional" if metadata["directionality"] == "symmetric" else "source_to_target",
    }


def _relationship_dedupe_key(source_id: str, target_id: str, relationship: dict) -> tuple[str, str, str, str]:
    direction = relationship.get("ontologyDirection") or relationship.get("directionality", "directed")
    left, right = (tuple(sorted((source_id, target_id))) if direction == "symmetric" or relationship.get("directionality") == "bidirectional" else (source_id, target_id))
    return left, right, str(relationship.get("ontologyType") or relationship.get("category", "other")), str(direction)


def _normalize_relationship_type(raw_type: str, category: str, source_language: str) -> tuple[str, str]:
    """Return (display_type, source_label). For zh: map category → canonical Chinese label;
    preserve raw_type as source_label if it differs from canonical."""
    if source_language != "zh":
        return raw_type, ""
    canonical = _RELATIONSHIP_ONTOLOGY.get(_ZH_REL_CATEGORY_ALIASES.get(category, category), {}).get("label", "关系")
    source_label = raw_type if (raw_type and raw_type != canonical) else ""
    return canonical, source_label


# ── Synthesis node stubs (populated by Codex in Steps 3–5) ───────────────────

async def node_synthesize_relationships(state: ImportState) -> dict:
    """Post-chunk: consolidate raw relationship candidates into final relationships."""
    if state.get("extract_relationships") is False:
        _sid = state.get("session_id", "")
        if _sid:
            from sidecar.workflows.w1_run_events import append_event
            append_event(_sid, {"phase": "skip", "tool": "synthesize_relationships", "status": "skipped", "message": "Relationship extraction disabled by user toggle."})
        return {"relationships": [], "progress": state.get("progress", 0.87)}

    if not _HAS_DEEP_PROMPTS:
        return {"relationships": [], "progress": state.get("progress", 0.87)}

    raw_relationships = state.get("raw_relationships", [])
    if not raw_relationships:
        return {"relationships": [], "progress": 0.87}

    errors: list[str] = list(state.get("errors", []))
    registry = state.get("entity_registry", {})
    llm = _get_llm(state)

    def _fallback_relationships() -> list[dict]:
        """Deterministically preserve evidence-grounded relationship candidates."""
        fallback: list[dict] = []
        seen_keys: set[tuple[Any, ...]] = set()
        for rel in raw_relationships:
            source_id = _resolve_character_id(
                rel.get("source_candidate_id") or rel.get("source_character_name"),
                registry,
            )
            target_id = _resolve_character_id(
                rel.get("target_candidate_id") or rel.get("target_character_name"),
                registry,
            )
            if not source_id or not target_id or source_id == target_id:
                continue
            evidence = rel.get("evidence", [])
            if isinstance(evidence, str):
                evidence = [evidence]
            evidence_list = [item.strip() for item in evidence if isinstance(item, str) and item.strip()]
            if not evidence_list and str(rel.get("description", "")).strip():
                evidence_list = [str(rel.get("description", "")).strip()]
            if not evidence_list:
                continue
            normalized = _relationship_ontology(rel, state.get("source_language", "zh"))
            if normalized is None:
                continue
            key = _relationship_dedupe_key(source_id, target_id, normalized)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fallback.append({
                "id": f"rel_{uuid.uuid4().hex[:8]}",
                "sourceId": source_id,
                "targetId": target_id,
                "type": normalized["type"],
                "sourceLabel": normalized.get("sourceLabel", ""),
                "description": str(rel.get("description", "")).strip(),
                "strength": None,
                "category": normalized["category"],
                "directionality": normalized["directionality"],
                "ontologyType": normalized.get("ontologyType"),
                "ontologyDirection": normalized.get("ontologyDirection"),
                "status": "inferred_from_import",
                "sourceNotes": "\n".join(evidence_list[:4]),
                "importConfidence": float(rel.get("confidence", 0.70) or 0.70),
            })
        return fallback

    _session_id = str(state.get("session_id", "") or state.get("context", {}).get("session_id", "") or "")
    _src_lang = state.get("source_language", "zh")
    _src_lang_label = "Chinese (Simplified)" if _src_lang == "zh" else "English"
    _lang_policy = state.get("context", {}).get("language_policy", "preserve_source")
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
            session_id=_session_id,
            entity_registry_json=json.dumps(registry_payload, ensure_ascii=False, indent=2),
            relationship_candidates_json=json.dumps(raw_relationships, ensure_ascii=False, indent=2),
            source_language_label=_src_lang_label,
            language_policy=_lang_policy,
        )
    except Exception as e:
        errors.append(f"Relationship synthesis failed: {str(e)}")
        return {"relationships": _fallback_relationships(), "errors": errors, "progress": 0.87}

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

        normalized = _relationship_ontology(rel, state.get("source_language", "zh"))
        if normalized is None:
            continue
        key = _relationship_dedupe_key(source_id, target_id, normalized)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        relationships.append({
            "id": rel.get("id") or f"rel_{uuid.uuid4().hex[:8]}",
            "sourceId": source_id,
            "targetId": target_id,
            "type": normalized["type"],
            "sourceLabel": normalized.get("sourceLabel", ""),
            "description": str(rel.get("description", "")).strip(),
            "strength": rel.get("strength"),
            "category": normalized["category"],
            "directionality": normalized["directionality"],
            "ontologyType": normalized.get("ontologyType"),
            "ontologyDirection": normalized.get("ontologyDirection"),
            "status": str(rel.get("status", "unknown")).strip() or "unknown",
            "sourceNotes": "\n".join(evidence_list),
            "importConfidence": float(rel.get("confidence", 0.75)),
        })

    if not relationships:
        relationships = _fallback_relationships()
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

    _src_lang = state.get("source_language", "zh")
    _src_lang_label = "Chinese (Simplified)" if _src_lang == "zh" else "English"
    _lang_policy = state.get("context", {}).get("language_policy", "preserve_source")
    llm = _get_llm(state)
    _session_id = str(state.get("session_id", "") or state.get("context", {}).get("session_id", "") or "")
    try:
        result = await _invoke_json_prompt(
            llm,
            W1_CLASSIFY_CHARACTER_TAGS,
            session_id=_session_id,
            characters_json=json.dumps(characters_payload, ensure_ascii=False, indent=2),
            source_language_label=_src_lang_label,
            language_policy=_lang_policy,
        )
    except Exception as e:
        errors.append(f"Character tag classification failed: {str(e)}")
        return {"character_tags": [], "entity_registry": registry, "errors": errors, "progress": 0.89}

    used_tag_ids: set[str] = set()
    character_tags: list[dict] = []
    tag_rejections: list[dict] = []
    for index, tag in enumerate(result.get("tags", [])):
        normalized_tag, rejection = _normalize_character_tag(tag, _src_lang)
        if rejection:
            tag_rejections.append(rejection)
            continue
        assert normalized_tag is not None
        tag = normalized_tag
        name = str(tag["name"])

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
            **({"sourceName": tag["sourceName"], "normalization": tag["normalization"]} if tag.get("sourceName") else {}),
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
        "tag_rejections": tag_rejections,
        "progress": 0.89,
    }


async def node_infer_world_settings(state: ImportState) -> dict:
    """Post-chunk: infer world settings plus suggested branches and containers."""
    if state.get("extract_world") is False:
        _sid = state.get("session_id", "")
        if _sid:
            from sidecar.workflows.w1_run_events import append_event
            append_event(_sid, {"phase": "skip", "tool": "infer_world_settings", "status": "skipped", "message": "World model extraction disabled by user toggle."})
        return {"world_settings": {}, "timeline_branches": [], "world_containers": [], "progress": state.get("progress", 0.91)}

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

    _infer_lang = state.get("source_language", "en")
    _lang_label = "Chinese (Simplified)" if _infer_lang == "zh" else "English"

    llm = _get_llm(state)
    _session_id = str(state.get("session_id", "") or state.get("context", {}).get("session_id", "") or "")
    try:
        result = await _invoke_json_prompt(
            llm,
            W1_INFER_WORLD_SETTINGS,
            session_id=_session_id,
            text_sample=text_sample,
            source_language_label=_lang_label,
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
    default_container_specs = _default_world_container_specs(_infer_lang)
    world_containers: list[dict] = []
    used_container_ids: set[str] = set()
    used_container_keys: set[str] = set()
    for index, container in enumerate(result.get("suggested_world_containers", [])):
        name = str(container.get("name", "")).strip()
        if not name:
            continue
        container_type = str(container.get("type", "notebook")).strip().lower() or "notebook"
        if _is_world_model_module_contamination(name, container_type):
            continue
        if container_type not in allowed_container_types:
            container_type = "notebook"
        import_key = str(container.get("importCategoryKey", "")).strip() or _world_container_key(
            container.get("category") or name
        )
        used_container_keys.add(import_key)
        world_containers.append({
            "id": container.get("id") or _stable_generated_id("cont", name, used_container_ids),
            "name": name,
            "type": container_type,
            "isDefault": bool(container.get("is_default", container.get("isDefault", False))),
            "sortOrder": index,
            "description": str(container.get("description", "")).strip(),
            "importCategoryKey": import_key,
            "categoryPath": ["世界模型", name] if _infer_lang == "zh" else ["World Model", name],
        })
    for spec in default_container_specs:
        key = spec["importCategoryKey"]
        if key in used_container_keys:
            continue
        world_containers.append({**spec, "sortOrder": len(world_containers)})
        used_container_keys.add(key)

    raw_branches = result.get("inferred_timeline_branches", [])
    timeline_branches: list[dict] = []
    existing_timeline_branches = [branch for branch in state.get("timeline_branches", []) if branch.get("id")]
    used_branch_ids: set[str] = set()
    branch_name_to_id: dict[str, str] = {}
    if existing_timeline_branches:
        # Timeline Architect owns branch topology. World-settings inference may
        # suggest broad story lanes, but it must not overwrite fork/merge-ready
        # branches already inferred from concrete event candidates.
        timeline_branches = existing_timeline_branches
    else:
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
        "world_detailed": {k: dict(v) for k, v in registry_seed.get("world_detailed", {}).items()},
    }
    extractions: list[dict] = list(state.get("chunk_extractions", []))
    raw_relationships: list[dict] = list(state.get("raw_relationships", []))
    errors: list[str] = list(state.get("errors", []))
    project_path = state["project_path"]
    source_language = state.get("source_language", "en")
    _src_lang_label = "Chinese (Simplified)" if source_language == "zh" else "English"
    _lang_policy = state.get("context", {}).get("language_policy", "preserve_source")
    checkpoint_path = state.get("checkpoint_path", "")
    completed_ids: set[int] = {e.get("chunk_id", -1) for e in extractions}
    total = len(chunks)
    completed = len(completed_ids)

    llm = _get_llm(state)
    _session_id = str(state.get("session_id", "") or state.get("context", {}).get("session_id", "") or "")
    chunk_index_by_id = {chunk.get("chunk_id", i): i for i, chunk in enumerate(chunks)}
    windows_by_chunk: dict[int, list[dict]] = {}
    for window in state.get("prompt_windows", []):
        window_chunk_ids = [int(window_chunk_id) for window_chunk_id in window.get("chunk_ids", [])]
        if not window_chunk_ids:
            continue
        # A packed window must run exactly once. Anchor it to the first not-yet
        # completed source chunk, otherwise resume paths would repeat extraction.
        anchor_id = next((window_chunk_id for window_chunk_id in window_chunk_ids if window_chunk_id not in completed_ids), window_chunk_ids[0])
        windows_by_chunk.setdefault(anchor_id, []).append(window)
    cross_validation: dict = dict(state.get("cross_validation") or {})

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", 0)
        if chunk_id in completed_ids:
            continue

        chunk_content = chunk.get("content", "")
        prompt_windows = windows_by_chunk.get(int(chunk_id), [])
        if not prompt_windows:
            digest = state.get("project_structure_digest") or _build_project_structure_digest(state, state.get("import_run_id", "import"))
            prompt_windows = _build_prompt_windows(state, [chunk], digest)
        else:
            digest = state.get("project_structure_digest") or _build_project_structure_digest(state, state.get("import_run_id", "import"))
        covered_chunk_ids = sorted({
            int(window_chunk_id)
            for prompt_window in prompt_windows
            for window_chunk_id in prompt_window.get("chunk_ids", [chunk_id])
        }, key=lambda value: chunk_index_by_id.get(value, value))
        if not covered_chunk_ids:
            covered_chunk_ids = [int(chunk_id)]
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
            is_packed_window = any(len(prompt_window.get("chunk_ids", [])) > 1 for prompt_window in prompt_windows)
            # Use window-level cache for the compiler path so cross-validation
            # still runs once per prompt window, including single-chapter windows.
            cached_outputs = None
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
                    prompt_window = _refresh_prompt_window_text(
                        {**state, "cross_validation": cross_validation},
                        prompt_window,
                        digest,
                    )
                    window_cached_outputs = _read_prompt_window_cache(state, prompt_window)
                    if window_cached_outputs:
                        window_outputs["character"].append(window_cached_outputs.get("character", {}))
                        window_outputs["event"].append(window_cached_outputs.get("event", {}))
                        window_outputs["world"].append(window_cached_outputs.get("world", {}))
                        window_outputs["relationship"].append(window_cached_outputs.get("relationship", {}))
                        window_outputs["scene"].append(window_cached_outputs.get("scene", {}))
                        chunk_notes.append(f"Loaded Scout prompt outputs from packed window cache {prompt_window.get('id')}.")
                        try:
                            incoming_cross_validation = await _run_cross_validation_for_window(
                                llm,
                                state,
                                window=prompt_window,
                                digest=digest,
                                prompt_outputs=window_cached_outputs,
                                cross_validation=cross_validation,
                                session_id=_session_id,
                            )
                            cross_validation = _merge_cross_validation_artifacts(
                                cross_validation,
                                incoming_cross_validation,
                                state.get("import_run_id") or "import",
                            )
                            _write_import_artifact(
                                state["project_path"],
                                state.get("import_run_id") or "import",
                                "cross_validation.json",
                                cross_validation,
                            )
                        except Exception as validation_exc:
                            warning = f"Cross-validation failed in cached {prompt_window.get('id', 'window')}: {validation_exc}"
                            errors.append(warning)
                            chunk_notes.append(warning)
                        continue

                    prompt_chunk_content = str(prompt_window.get("text", ""))
                    window_system_content = W1_WINDOW_SYSTEM_CONTEXT.format(
                        chunk_id=chunk_id,
                        total_chunks=total,
                        entity_registry_summary=registry_summary,
                        chunk_content=prompt_chunk_content,
                    )
                    results = await asyncio.gather(
                        _invoke_json_prompt(
                            llm,
                            W1_CHARS_DEEP_TASK,
                            session_id=_session_id,
                            system_content=window_system_content,
                            source_language_label=_src_lang_label,
                            language_policy=_lang_policy,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_EVENTS_DEEP_TASK,
                            session_id=_session_id,
                            system_content=window_system_content,
                            source_language_label=_src_lang_label,
                            language_policy=_lang_policy,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_WORLD_DEEP_TASK,
                            session_id=_session_id,
                            system_content=window_system_content,
                            source_language_label=_src_lang_label,
                            language_policy=_lang_policy,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_RELS_CHUNK_TASK,
                            session_id=_session_id,
                            system_content=window_system_content,
                            source_language_label=_src_lang_label,
                            language_policy=_lang_policy,
                        ),
                        _invoke_json_prompt(
                            llm,
                            W1_SCENES_TASK,
                            session_id=_session_id,
                            system_content=window_system_content,
                            chapter_hint=prompt_window.get("chapter_range") or scene_hint,
                            source_language_label=_src_lang_label,
                            language_policy=_lang_policy,
                        ),
                        return_exceptions=True,
                    )
                    window_outputs["character"].append(_coerce_result(results, 0, "character", prompt_window))
                    window_outputs["event"].append(_coerce_result(results, 1, "event", prompt_window))
                    window_outputs["world"].append(_coerce_result(results, 2, "world", prompt_window))
                    window_outputs["relationship"].append(_coerce_result(results, 3, "relationship", prompt_window))
                    window_outputs["scene"].append(_coerce_result(results, 4, "scene", prompt_window))
                    prompt_outputs_for_window = {
                        "character": window_outputs["character"][-1],
                        "event": window_outputs["event"][-1],
                        "world": window_outputs["world"][-1],
                        "relationship": window_outputs["relationship"][-1],
                        "scene": window_outputs["scene"][-1],
                    }
                    if not any(
                        failure.get("prompt_window_id") == prompt_window.get("id")
                        for failure in prompt_failures
                    ):
                        _write_prompt_window_cache(state, prompt_window, prompt_outputs_for_window)
                        try:
                            incoming_cross_validation = await _run_cross_validation_for_window(
                                llm,
                                state,
                                window=prompt_window,
                                digest=digest,
                                prompt_outputs=prompt_outputs_for_window,
                                cross_validation=cross_validation,
                                session_id=_session_id,
                            )
                            cross_validation = _merge_cross_validation_artifacts(
                                cross_validation,
                                incoming_cross_validation,
                                state.get("import_run_id") or "import",
                            )
                            _write_import_artifact(
                                state["project_path"],
                                state.get("import_run_id") or "import",
                                "cross_validation.json",
                                cross_validation,
                            )
                        except Exception as validation_exc:
                            warning = f"Cross-validation failed in {prompt_window.get('id', 'window')}: {validation_exc}"
                            errors.append(warning)
                            chunk_notes.append(warning)

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
                elif not is_packed_window:
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
                _compact_character_card(entry)

            for nc in char_data.get("new_characters", []):
                name = str(nc.get("canonical_name", "")).strip()
                if not name:
                    continue
                if _is_world_entity_candidate(name, nc):
                    _add_world_candidate_to_registry(
                        registry,
                        name,
                        _normalize_world_category(name, "organization"),
                        str(nc.get("summary") or nc.get("role_in_story") or "").strip(),
                        float(nc.get("confidence", 0.72) or 0.72),
                    )
                    world_mentions.append(name)
                    world_mentions_detailed.append(registry.get("world_detailed", {}).get(name, {"name": name}))
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
                    _compact_character_card(entry)
                    continue

                char_id = f"char_{uuid.uuid4().hex[:8]}"
                aliases: list[str] = []
                _append_unique_strings(aliases, nc.get("aliases", []))
                raw_importance = str(nc.get("importance", "")).strip()
                registry["characters"][char_id] = _compact_character_card(_truncate_text_fields({
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
                }))
                new_chars.append(registry["characters"][char_id])

            # Seed thin character cards from relationship/event/scene evidence
            # before event resolution, so missing-but-important names do not
            # vanish just because the character scout was conservative.
            for rel in relationship_data.get("relationships", []):
                for field in ("source_character_name", "target_character_name", "source_name", "target_name", "source", "target"):
                    candidate_name = str(rel.get(field, "")).strip()
                    if candidate_name:
                        seeded = _seed_character_from_name(
                            registry,
                            candidate_name,
                            int(chunk_id),
                            source_language,
                            role_hint=str(rel.get("description") or rel.get("type") or "relationship evidence")[:100],
                            confidence=float(rel.get("confidence", 0.72) or 0.72),
                        )
                        if seeded:
                            new_chars.append(seeded)
            for ev in event_data.get("events", []):
                for candidate_name in ev.get("character_names", []):
                    seeded = _seed_character_from_name(
                        registry,
                        str(candidate_name).strip(),
                        int(chunk_id),
                        source_language,
                        role_hint=str(ev.get("title") or "timeline evidence")[:100],
                        confidence=max(0.7, float(ev.get("confidence", 0.72) or 0.72) - 0.05),
                    )
                    if seeded:
                        new_chars.append(seeded)
            for scene in scene_data.get("scenes", []):
                for candidate_name in scene.get("character_names", []):
                    seeded = _seed_character_from_name(
                        registry,
                        str(candidate_name).strip(),
                        int(chunk_id),
                        source_language,
                        role_hint=str(scene.get("title") or "scene evidence")[:100],
                        confidence=max(0.68, float(scene.get("confidence", 0.72) or 0.72) - 0.08),
                    )
                    if seeded:
                        new_chars.append(seeded)

            for missing in cross_validation.get("missing_major_characters", []) if isinstance(cross_validation, dict) else []:
                missing_name = str(missing.get("name_or_alias") or missing.get("name") or "").strip()
                if not missing_name:
                    continue
                seeded = _seed_character_from_name(
                    registry,
                    missing_name,
                    int(chunk_id),
                    source_language,
                    role_hint=str(missing.get("observed_role") or missing.get("suggested_groupKey") or "cross-validation missing major")[:100],
                    confidence=max(0.72, float(missing.get("confidence", 0.72) or 0.72)),
                )
                if seeded:
                    new_chars.append(seeded)

            _remove_world_entities_from_character_registry(registry)

            # Enforce confidence floor and density cap per packed source window.
            raw_events = event_data.get("events", [])
            raw_events = [e for e in raw_events if float(e.get("confidence", 0)) >= 0.75]
            event_cap = min(24, max(8, len(covered_chunk_ids) * 4))
            raw_events = sorted(raw_events, key=_importance_sort_value, reverse=True)[:event_cap]

            for ev in raw_events:
                ev, _ontology_warnings = _normalize_timeline_event_ontology(ev)
                event_id = f"event_{uuid.uuid4().hex[:8]}"
                character_refs = list(ev.get("character_ids", [])) + list(ev.get("character_names", []))
                resolved_character_ids = _resolve_character_ids(character_refs, registry)
                chapter_range = ev.get("chapterRange", {})
                if not isinstance(chapter_range, dict):
                    chapter_range = {"start": str(chapter_range), "end": str(chapter_range)}
                registry["events"][event_id] = {
                    "event_id": event_id,
                    "title": str(ev.get("title", "")).strip(),
                    "description": str(ev.get("description", "")).strip(),
                    "eventClass": str(ev.get("eventClass", "")).strip(),
                    "timelineClass": str(ev.get("timelineClass", "")).strip(),
                    "eventType": str(ev.get("eventType", "")).strip(),
                    "arcRole": str(ev.get("arcRole", "")).strip(),
                    "causalRole": str(ev.get("causalRole", "")).strip(),
                    "branchRole": str(ev.get("branchRole", "")).strip(),
                    "arcId": str(ev.get("arcId", "")).strip(),
                    "timelineLaneHint": str(ev.get("timelineLaneHint", "")).strip(),
                    "causalPredecessorHints": [str(item).strip() for item in ev.get("causalPredecessorHints", []) if str(item).strip()],
                    "forkMergeHint": str(ev.get("forkMergeHint", "")).strip(),
                    "dedupeKey": str(ev.get("dedupeKey", "")).strip(),
                    "chapterRange": {
                        "start": str(chapter_range.get("start", "")).strip(),
                        "end": str(chapter_range.get("end", "")).strip(),
                    },
                    "importanceScore": int(float(ev.get("importanceScore", 0) or 0)),
                    "character_ids": resolved_character_ids,
                    "character_names": [str(name).strip() for name in ev.get("character_names", []) if str(name).strip()],
                    "location_hint": str(ev.get("location_hint", "")).strip() or None,
                    "temporal_hint": str(ev.get("temporal_hint", "")).strip() or None,
                    "chunk_position": str(ev.get("chunk_position", "")).strip(),
                    "stakes": str(ev.get("stakes", "")).strip(),
                    "mergeCandidateTitles": [str(item).strip() for item in ev.get("mergeCandidateTitles", []) if str(item).strip()],
                    "deterministicLaneHints": ev.get("deterministicLaneHints", {}),
                    "ontologyWarnings": ev.get("ontologyWarnings", []),
                    "confidence": float(ev.get("confidence", 0.7)),
                    "chunk_id": chunk_id,
                }
                events.append(registry["events"][event_id])

            for wm in world_data.get("world_mentions", []):
                name = str(wm.get("name", "")).strip()
                if not name:
                    continue
                category = _normalize_world_category(name, str(wm.get("category", "concept")).strip() or "concept")
                description = str(wm.get("description", "")).strip()
                _add_world_candidate_to_registry(
                    registry,
                    name,
                    category,
                    description,
                    float(wm.get("confidence", 0.7) or 0.7),
                )
                detail = registry["world_detailed"][name]
                if wm.get("attributes"):
                    detail["attributes"] = wm.get("attributes", [])
                world_mentions.append(name)
                world_mentions_detailed.append({
                    "name": name,
                    "category": detail.get("category", category),
                    "description": detail.get("description", description),
                    "container_hint": detail.get("container_hint", _world_container_key(category)),
                    "attributes": detail.get("attributes", []),
                    "confidence": float(detail.get("confidence", 0.7) or 0.7),
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

            for covered_chunk_id in covered_chunk_ids:
                covered_chunk = chunks[chunk_index_by_id.get(covered_chunk_id, 0)] if chunks else chunk
                is_primary_chunk = covered_chunk_id == chunk_id
                extractions.append({
                    "chunk_id": covered_chunk_id,
                    "new_characters": new_chars if is_primary_chunk else [],
                    "updated_aliases": alias_updates if is_primary_chunk else [],
                    "events": events if is_primary_chunk else [],
                    "world_mentions": world_mentions if is_primary_chunk else [],
                    "world_mentions_detailed": world_mentions_detailed if is_primary_chunk else [],
                    "raw_relationships": chunk_raw_relationships if is_primary_chunk else [],
                    "scenes": scenes if is_primary_chunk else [],
                    "chapter_hint": covered_chunk.get("chapter_hint") or chapter_hint,
                    "manuscript_content": covered_chunk.get("manuscript_content", covered_chunk.get("content", "")),
                    "notes": chunk_notes if is_primary_chunk else [f"Covered by packed prompt window anchored at chunk {chunk_id}."],
                })
                completed_ids.add(covered_chunk_id)

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
                "cross_validation": cross_validation,
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

    completed = len(completed_ids)
    progress = 0.1 + (0.7 * (completed / max(total, 1)))
    return {
        "chunks": chunks,
        "entity_registry": registry,
        "chunk_extractions": extractions,
        "raw_relationships": raw_relationships,
        "cross_validation": cross_validation,
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
    builder.add_node("organize_world_items", node_organize_project)
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
    builder.add_edge("architect_timeline", "organize_world_items")
    builder.add_edge("organize_world_items", "generate_import_todos")

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
    session_id = str(config.get("session_id", "") or config.get("context", {}).get("session_id", "") or "")
    configure_w1_budget(config, session_id)
    state: ImportState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "import_mode": import_mode,
        "prompt_profile": config.get("prompt_profile") or config.get("context", {}).get("prompt_profile", "balanced"),
        "context": {**config.get("context", {}), "session_id": session_id, "budget_policy": config.get("budget_policy")},
        "session_id": session_id,
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
    prompt_profile = config.get("prompt_profile") or config.get("context", {}).get("prompt_profile", "balanced")
    session_id = str(config.get("session_id", "") or config.get("context", {}).get("session_id", "") or "")
    configure_w1_budget(config, session_id)
    if session_id:
        from sidecar.workflows.w1_run_events import append_event
        append_event(session_id, {
            "phase": "start",
            "tool": "run_streaming",
            "status": "start",
            "message": f"W1 streaming runner started with profile={prompt_profile}.",
        })
    supervisor_configured = config.get("use_supervisor")
    context_supervisor_configured = config.get("context", {}).get("use_supervisor")
    supervisor_defaulted = (
        supervisor_configured is None
        and context_supervisor_configured is None
        and prompt_profile in {"deep", "custom"}
    )
    if supervisor_configured or context_supervisor_configured or supervisor_defaulted:
        from sidecar.supervisor.policy import run_supervisor_streaming
        async for update in run_supervisor_streaming(project_path, config):
            yield update
        return

    import_mode = config.get("import_mode", "import_all")
    _profile_cfg: dict = config.get("profile_config") or {}
    initial_state: ImportState = {
        "project_path": project_path,
        "workflow_id": "W1",
        "source_file_path": config.get("source_file_path", ""),
        "import_mode": import_mode,
        "prompt_profile": prompt_profile,
        "context": {**config.get("context", {}), "session_id": session_id, "budget_policy": config.get("budget_policy")},
        "session_id": session_id,
        "import_run_id": config.get("import_run_id", ""),
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
        "extract_relationships": _profile_cfg.get("extract_relationships", True),
        "extract_world": _profile_cfg.get("extract_world", True),
        "extract_timeline": _profile_cfg.get("extract_timeline", True),
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
            if session_id:
                from sidecar.workflows.w1_run_events import append_event
                append_event(session_id, {
                    "phase": node_name,
                    "tool": node_name,
                    "status": "fail" if errors else "success",
                    "level": "error" if errors else "info",
                    "message": f"Completed W1 node {node_name}.",
                    "completed": completed_chunks,
                    "total": total_chunks,
                    "error": "; ".join(str(e) for e in errors[:3]) if isinstance(errors, list) and errors else "",
                })

            yield {
                "progress": progress,
                "errors": errors if isinstance(errors, list) else [],
                "completed_chunks": completed_chunks,
                "total_chunks": total_chunks,
                "current_node": node_name,
                "import_review_report": node_output.get("import_review_report", {}),
                "proposals_count": len(node_output.get("proposals", [])) if isinstance(node_output.get("proposals", []), list) else 0,
                "window_metrics": node_output.get("window_metrics", {}),
            }
