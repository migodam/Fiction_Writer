"""
W1 Supervisor tool implementations.

Each async tool takes ImportSupervisorState and optional kwargs, runs one
pipeline stage, and returns a partial dict to be merged back into state by
the policy loop.

Tools import private helpers from w1_import directly — NOT via LangGraph
graph invocation.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from sidecar.models.state import (
    ImportSupervisorState,
    WindowExtractionMetrics,
    PROFILE_CONFIGS,
)
from sidecar.workflows.w1_import import (
    _API_SEMAPHORE,
    _append_unique_strings,
    _artifact_dir,
    _build_project_structure_digest,
    _build_prompt_windows,
    _compact_character_card,
    _estimate_tokens,
    _get_llm,
    _invoke_json_prompt,
    _is_world_entity_candidate,
    _merge_prompt_outputs,
    _merge_text_field,
    _normalize_world_category,
    _now_iso,
    _parse_json_response,
    _read_chunk_prompt_cache,
    _registry_summary,
    _resolve_character_id,
    _resolve_character_ids,
    _sha256_text,
    _stable_id,
    _truncate_text_fields,
    _write_chunk_prompt_failure,
    _write_import_artifact,
    IMPORTANCE_MAP,
    IMPORTANCE_TO_GROUP,
    node_architect_timeline,
    node_build_manuscript,
    node_classify_character_tags,
    node_infer_world_settings,
    node_reconcile_entities,
    node_resolve_low_confidence,
    node_review_import,
    node_synthesize_relationships,
    node_write_to_project,
)
from sidecar.prompts.w1_prompts import (
    W1_CROSS_VALIDATE_IMPORT,
    W1_EXTRACT_CHARACTERS_DEEP,
    W1_EXTRACT_EVENTS_DEEP,
    W1_EXTRACT_RELATIONSHIPS_CHUNK,
    W1_EXTRACT_SCENE_SUMMARIES,
    W1_EXTRACT_WORLD_DEEP,
)

# Output token threshold triggering pre-flight split.
_OUTPUT_BUDGET_SPLIT_THRESHOLD = 3_500

# Tokens per chapter for output estimation:
# 1.5 chars × 120 + 3 events × 80 + 2 world × 50
_TOKENS_PER_CHAPTER_ESTIMATE = int(1.5 * 120 + 3 * 80 + 2 * 50)


# ── Output budget pre-flight ────────────────────────────────────────────────────

def estimate_window_output_tokens(window: dict, chapters_per_window: int = 8) -> int:
    """Estimate LLM output tokens for a prompt window."""
    chunk_count = len(window.get("chunk_ids", [])) or max(chapters_per_window, 1)
    return chunk_count * _TOKENS_PER_CHAPTER_ESTIMATE


def window_exceeds_output_budget(window: dict, profile_config: dict) -> bool:
    """Return True when the window's estimated output exceeds the split threshold."""
    est = estimate_window_output_tokens(window, profile_config.get("chapters_per_window", 8))
    return est > _OUTPUT_BUDGET_SPLIT_THRESHOLD


def _event_cap_from_profile(profile_config: dict, chapter_count: int) -> int:
    density = profile_config.get("event_density", "chapter_level")
    if density == "arc_level":
        return max(2, chapter_count // 2)
    if density == "scene_level":
        return chapter_count * 5
    return min(24, max(8, chapter_count * 3))


# ── Symptom flags for qa_review ────────────────────────────────────────────────

def _symptom_flags(state: ImportSupervisorState) -> dict:
    """Compute diagnostic flags from import artifacts. All flags are bool or count."""
    registry = state.get("entity_registry", {})
    chars = registry.get("characters", {})
    events = registry.get("events", {})
    timeline = state.get("timeline_architecture", {})
    cross_val = state.get("cross_validation", {})
    source_lang = state.get("source_language", "en")

    # groupKey coverage
    missing_groupkey = sum(1 for c in chars.values() if not c.get("groupKey") and not c.get("skip_create"))

    # world/person boundary: orgs in character registry
    org_chars = sum(
        1 for c in chars.values()
        if str(c.get("importance", "")).lower() == "organization" or "organization" in str(c.get("role_in_story", "")).lower()
    )

    # Timeline mainline density
    canonical_events = timeline.get("canonical_events", [])
    mainline_overdense = len(canonical_events) > 30

    # Missing major characters from cross-validation
    missing_majors = len(cross_val.get("missing_major_characters", []))

    # Language consistency: Latin traits for CJK source
    mixed_language_trait_sets = False
    if source_lang == "zh":
        for c in chars.values():
            if c.get("skip_create"):
                continue
            for trait in c.get("personality_traits", []):
                if isinstance(trait, str) and re.search(r"[A-Za-z]{4,}", trait):
                    mixed_language_trait_sets = True
                    break
            if mixed_language_trait_sets:
                break

    return {
        "missing_groupkey_count": missing_groupkey,
        "org_chars_in_registry": org_chars,
        "timeline_mainline_overdense": mainline_overdense,
        "missing_major_characters_count": missing_majors,
        "mixed_language_trait_sets": mixed_language_trait_sets,
    }


# ── Tool: segment_manifest ──────────────────────────────────────────────────────

async def segment_manifest(state: ImportSupervisorState) -> dict:
    """Build or verify the import manifest and prompt_windows list.

    In S1 this uses the existing _build_prompt_windows packer; S2 replaces
    it with the chapter-count-aware windowing.
    """
    import_run_id = state.get("import_run_id", "")
    project_path = state.get("project_path", "")
    chunks = state.get("chunks", [])
    if not chunks or not import_run_id:
        return {"errors": list(state.get("errors", [])) + ["segment_manifest: no chunks or import_run_id"]}

    # Idempotency: if prompt_windows already built and match source_hash, skip
    manifest = state.get("import_run_manifest", {})
    source_hash = manifest.get("source_hash", "")
    existing_windows = state.get("prompt_windows", [])
    if existing_windows and source_hash:
        return {"supervisor_log": list(state.get("supervisor_log", [])) + [f"segment_manifest: {len(existing_windows)} windows already built (cache hit)"]}

    digest = state.get("project_structure_digest") or _build_project_structure_digest(
        {**state, "import_run_id": import_run_id}, import_run_id
    )

    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(state.get("prompt_profile", "balanced"), PROFILE_CONFIGS["balanced"])
    profile_state = {**state, "prompt_profile": state.get("prompt_profile", "balanced")}

    # Build windows from all chunks
    raw_windows: list[dict] = []
    for chunk in chunks:
        windows = _build_prompt_windows(profile_state, [chunk], digest)
        raw_windows.extend(windows)

    # Pre-flight: split windows whose estimated output > threshold
    final_windows: list[dict] = []
    for win in raw_windows:
        chunk_ids = win.get("chunk_ids", [])
        if len(chunk_ids) > 1 and window_exceeds_output_budget(win, profile_config):
            mid = max(1, len(chunk_ids) // 2)
            for part_idx, part_chunk_ids in enumerate([chunk_ids[:mid], chunk_ids[mid:]]):
                part_chunks = [c for c in chunks if c.get("chunk_id") in part_chunk_ids]
                sub_wins = _build_prompt_windows(profile_state, part_chunks, digest)
                for sw in sub_wins:
                    sw["id"] = _stable_id("pwin", import_run_id, *part_chunk_ids, "split", part_idx, source_hash[:8])
                    sw["split_reason"] = "output_budget_preflight"
                    sw["output_token_budget"] = profile_config.get("output_token_budget", 3000)
                    final_windows.append(sw)
        else:
            win["output_token_budget"] = profile_config.get("output_token_budget", 3000)
            final_windows.append(win)

    log = list(state.get("supervisor_log", []))
    log.append(f"segment_manifest: built {len(final_windows)} windows from {len(chunks)} chunks (pre-flight splits applied)")

    return {
        "prompt_windows": final_windows,
        "supervisor_log": log,
        "current_stage": "segment_manifest",
    }


# ── Tool: extract_window ────────────────────────────────────────────────────────

async def extract_window(state: ImportSupervisorState, window_id: str) -> dict:
    """Run 5-parallel LLM extraction for one PromptWindow and update entity_registry."""
    windows = {w.get("id"): w for w in state.get("prompt_windows", [])}
    window = windows.get(window_id)
    if not window:
        return {"errors": list(state.get("errors", [])) + [f"extract_window: window {window_id!r} not found"]}

    llm = _get_llm(state)
    registry = {k: dict(v) if isinstance(v, dict) else v for k, v in state.get("entity_registry", {}).items()}
    registry.setdefault("characters", {})
    registry.setdefault("events", {})
    registry.setdefault("world", {})
    registry.setdefault("world_detailed", {})

    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(state.get("prompt_profile", "balanced"), PROFILE_CONFIGS["balanced"])
    chunk_ids = window.get("chunk_ids", [0])
    chunk_id = chunk_ids[0] if chunk_ids else 0
    total = len(state.get("chunks", [])) or 1
    prompt_text = str(window.get("text", ""))
    registry_summary = _registry_summary(registry)
    chapter_range = str(window.get("chapter_range") or f"chunk_{chunk_id}")

    failed_prompts: list[str] = []

    # 5-parallel extraction
    results = await asyncio.gather(
        _invoke_json_prompt(
            llm, W1_EXTRACT_CHARACTERS_DEEP,
            chunk_content=prompt_text, chunk_id=chunk_id,
            total_chunks=total, entity_registry_summary=registry_summary,
        ),
        _invoke_json_prompt(
            llm, W1_EXTRACT_EVENTS_DEEP,
            chunk_content=prompt_text, chunk_id=chunk_id,
            total_chunks=total, entity_registry_summary=registry_summary,
        ),
        _invoke_json_prompt(
            llm, W1_EXTRACT_WORLD_DEEP,
            chunk_content=prompt_text, chunk_id=chunk_id,
            total_chunks=total, entity_registry_summary=registry_summary,
        ),
        _invoke_json_prompt(
            llm, W1_EXTRACT_RELATIONSHIPS_CHUNK,
            chunk_content=prompt_text, chunk_id=chunk_id,
            total_chunks=total, entity_registry_summary=registry_summary,
        ),
        _invoke_json_prompt(
            llm, W1_EXTRACT_SCENE_SUMMARIES,
            chunk_content=prompt_text, chunk_id=chunk_id,
            total_chunks=total, entity_registry_summary=registry_summary,
            chapter_hint=chapter_range,
        ),
        return_exceptions=True,
    )

    labels = ["character", "event", "world", "relationship", "scene"]
    outputs: list[dict] = []
    for i, (label, result) in enumerate(zip(labels, results)):
        if isinstance(result, Exception):
            failed_prompts.append(f"{label}:{result}")
            outputs.append({})
        else:
            outputs.append(result if isinstance(result, dict) else {})

    char_data, event_data, world_data, rel_data, scene_data = outputs

    # ── Register new characters ──────────────────────────────────────────────
    new_char_ids: list[str] = []
    for nc in char_data.get("new_characters", []):
        name = str(nc.get("canonical_name", "")).strip()
        if not name:
            continue
        matched_id = _resolve_character_id(name, registry)
        if matched_id:
            entry = registry["characters"][matched_id]
            _append_unique_strings(entry.setdefault("aliases", []), nc.get("aliases", []))
            entry["summary"] = _merge_text_field(entry.get("summary", ""), nc.get("summary", ""))
            entry["confidence"] = max(float(entry.get("confidence", 0.7)), float(nc.get("confidence", 0.7)))
            _append_unique_strings(entry.setdefault("personality_traits", []), nc.get("personality_traits", []))
            _compact_character_card(entry)
            continue
        raw_importance = str(nc.get("importance", "")).strip()
        char_id = f"char_{uuid.uuid4().hex[:8]}"
        registry["characters"][char_id] = _compact_character_card(_truncate_text_fields({
            "canonical_id": char_id,
            "canonical_name": name,
            "aliases": list(nc.get("aliases", [])),
            "first_seen_chunk": chunk_id,
            "notes": [f"[window {window_id}] {n.strip()}" for n in nc.get("notes", []) if isinstance(n, str) and n.strip()],
            "confidence": float(nc.get("confidence", 0.7)),
            "summary": str(nc.get("summary", "")).strip(),
            "background": str(nc.get("background", "")).strip(),
            "role_in_story": str(nc.get("role_in_story", "")).strip(),
            "physical_description": str(nc.get("physical_description", "")).strip(),
            "personality_traits": [t.strip() for t in nc.get("personality_traits", []) if isinstance(t, str) and t.strip()][:4],
            "goals": [], "fears": [], "secrets": [],
            "speech_style": str(nc.get("speech_style", "")).strip(),
            "arc_notes": str(nc.get("arc_notes", "")).strip(),
            "importance": IMPORTANCE_MAP.get(raw_importance, raw_importance or "supporting"),
            "tag_ids": [],
            "open_questions": [q.strip() for q in nc.get("open_questions", []) if isinstance(q, str) and q.strip()][:2],
        }))
        new_char_ids.append(char_id)

    # ── Register events ──────────────────────────────────────────────────────
    event_cap = _event_cap_from_profile(profile_config, len(chunk_ids))
    raw_events = [e for e in event_data.get("events", []) if float(e.get("confidence", 0)) >= 0.75]
    raw_events = sorted(raw_events, key=lambda e: float(e.get("confidence", 0)), reverse=True)[:event_cap]
    new_events: list[dict] = []
    for ev in raw_events:
        event_id = f"event_{uuid.uuid4().hex[:8]}"
        char_refs = list(ev.get("character_ids", [])) + list(ev.get("character_names", []))
        resolved_ids = _resolve_character_ids(char_refs, registry)
        chapter_range_ev = ev.get("chapterRange", {})
        if not isinstance(chapter_range_ev, dict):
            chapter_range_ev = {"start": str(chapter_range_ev), "end": str(chapter_range_ev)}
        entry = {
            "event_id": event_id,
            "title": str(ev.get("title", "")).strip(),
            "description": str(ev.get("description", "")).strip(),
            "eventClass": str(ev.get("eventClass", "")).strip(),
            "timelineClass": str(ev.get("timelineClass", "")).strip(),
            "arcId": str(ev.get("arcId", "")).strip(),
            "timelineLaneHint": str(ev.get("timelineLaneHint", "")).strip(),
            "causalPredecessorHints": [str(h).strip() for h in ev.get("causalPredecessorHints", []) if str(h).strip()],
            "forkMergeHint": str(ev.get("forkMergeHint", "")).strip(),
            "dedupeKey": str(ev.get("dedupeKey", "")).strip(),
            "chapterRange": {"start": str(chapter_range_ev.get("start", "")).strip(), "end": str(chapter_range_ev.get("end", "")).strip()},
            "importanceScore": int(float(ev.get("importanceScore", 0) or 0)),
            "character_ids": resolved_ids,
            "character_names": [str(n).strip() for n in ev.get("character_names", []) if str(n).strip()],
            "location_hint": str(ev.get("location_hint", "")).strip() or None,
            "temporal_hint": str(ev.get("temporal_hint", "")).strip() or None,
            "confidence": float(ev.get("confidence", 0.7)),
            "chunk_id": chunk_id,
        }
        registry["events"][event_id] = entry
        new_events.append(entry)

    # ── Register world mentions ──────────────────────────────────────────────
    new_world: list[str] = []
    for wm in world_data.get("world_mentions", []):
        name = str(wm.get("name", "")).strip()
        if not name:
            continue
        category = str(wm.get("category", "concept")).strip() or "concept"
        if name not in registry["world"]:
            registry["world"][name] = category
            new_world.append(name)
        if name not in registry["world_detailed"]:
            registry["world_detailed"][name] = {
                "name": name, "category": category,
                "description": str(wm.get("description", "")).strip(),
                "container_hint": str(wm.get("container_hint", "")).strip(),
                "attributes": wm.get("attributes", []),
                "confidence": float(wm.get("confidence", 0.7)),
            }

    # ── Register raw relationships ──────────────────────────────────────────
    raw_rels: list[dict] = list(state.get("raw_relationships", []))
    for rel in rel_data.get("relationships", []):
        src = str(rel.get("source_character_name") or rel.get("source_name") or rel.get("source", "")).strip()
        tgt = str(rel.get("target_character_name") or rel.get("target_name") or rel.get("target", "")).strip()
        if not src or not tgt:
            continue
        raw_rels.append({
            "chunk_id": chunk_id,
            "window_id": window_id,
            "source_character_name": src,
            "target_character_name": tgt,
            "source_candidate_id": _resolve_character_id(src, registry),
            "target_candidate_id": _resolve_character_id(tgt, registry),
            "type": str(rel.get("type", "")).strip(),
            "description": str(rel.get("description", "")).strip(),
            "category": str(rel.get("category", "other")).strip() or "other",
            "directionality": str(rel.get("directionality", "bidirectional")).strip() or "bidirectional",
            "confidence": float(rel.get("confidence", 0.7)),
        })

    # ── Write window artifact ────────────────────────────────────────────────
    import_run_id = state.get("import_run_id", "")
    project_path = state.get("project_path", "")
    if import_run_id and project_path:
        artifact = {
            "window_id": window_id, "chunk_ids": chunk_ids,
            "chapter_range": chapter_range, "failed_prompts": failed_prompts,
            "char_count": len(new_char_ids), "event_count": len(new_events),
            "world_count": len(new_world),
        }
        _write_import_artifact(project_path, import_run_id, f"windows/{window_id}.json", artifact)

    # ── Build metrics ────────────────────────────────────────────────────────
    metrics: WindowExtractionMetrics = {
        "window_id": window_id,
        "chapter_count": len(chunk_ids),
        "char_count_extracted": len(new_char_ids),
        "event_count_extracted": len(new_events),
        "world_count_extracted": len(new_world),
        "failed_prompts": failed_prompts,
        "confidence_distribution": {},
        "missing_majors_count": 0,
        "duplicate_count": 0,
        "rerun_count": state.get("window_metrics", {}).get(window_id, {}).get("rerun_count", 0),
        "gate_passed": len(failed_prompts) < 3,
    }

    window_metrics = dict(state.get("window_metrics", {}))
    window_metrics[window_id] = metrics

    log = list(state.get("supervisor_log", []))
    log.append(f"extract_window {window_id}: {len(new_char_ids)} chars, {len(new_events)} events, {len(new_world)} world, {len(failed_prompts)} failed")

    return {
        "entity_registry": registry,
        "raw_relationships": raw_rels,
        "window_metrics": window_metrics,
        "supervisor_log": log,
        "current_stage": "extract_window",
    }


# ── Tool: cross_validate_window ─────────────────────────────────────────────────

async def cross_validate_window(state: ImportSupervisorState, window_id: str) -> dict:
    """Run cross-validation LLM call for one window and update window metrics."""
    llm = _get_llm(state)
    registry = state.get("entity_registry", {})
    timeline = state.get("timeline_architecture", {})

    char_json = json.dumps(dict(list(registry.get("characters", {}).items())[:50]), ensure_ascii=False)[:6000]
    event_json = json.dumps(dict(list(registry.get("events", {}).items())[:30]), ensure_ascii=False)[:4000]
    digest_summary = _registry_summary(registry)

    data_block = (
        f"\n\n## Actual Data (Window {window_id})\n\n"
        f"PROJECT DIGEST:\n{digest_summary}\n\n"
        f"CHARACTER CANDIDATES (JSON):\n{char_json}\n\n"
        f"EVENT CANDIDATES (JSON):\n{event_json}\n\n"
        f"REDUCER ARTIFACT (JSON):\n{{}}\n\n"
        f"TIMELINE ARCHITECTURE (JSON):\n{json.dumps(timeline, ensure_ascii=False)[:2000]}\n\n"
        "Analyze the above for the listed issue types. Output the cross-validation JSON only."
    )
    full_prompt = W1_CROSS_VALIDATE_IMPORT + data_block

    result: dict = {}
    try:
        async with _API_SEMAPHORE:
            response = await llm.ainvoke([HumanMessage(content=full_prompt)])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        result = _parse_json_response(raw)
    except Exception as exc:
        log = list(state.get("supervisor_log", []))
        log.append(f"cross_validate_window {window_id}: non-fatal error — {exc}")
        return {"supervisor_log": log}

    missing_majors = len(result.get("missing_major_characters", []))
    duplicate_count = len(result.get("duplicate_characters", [])) + len(result.get("duplicate_events", []))

    window_metrics = dict(state.get("window_metrics", {}))
    wm = dict(window_metrics.get(window_id, {}))
    wm["missing_majors_count"] = missing_majors
    wm["duplicate_count"] = duplicate_count
    window_metrics[window_id] = wm

    # Merge into cross_validation artifact
    existing_cv = dict(state.get("cross_validation", {}))
    for key in ("duplicate_characters", "duplicate_events", "missing_major_characters",
                "suspicious_groups", "contradictory_aliases", "event_merge_recommendations", "warnings"):
        existing_cv.setdefault(key, [])
        existing_cv[key].extend(result.get(key, []))

    log = list(state.get("supervisor_log", []))
    log.append(f"cross_validate_window {window_id}: {missing_majors} missing majors, {duplicate_count} duplicates")

    return {
        "cross_validation": existing_cv,
        "window_metrics": window_metrics,
        "supervisor_log": log,
    }


# ── Tool: rerun_window ──────────────────────────────────────────────────────────

async def rerun_window(
    state: ImportSupervisorState,
    window_id: str,
    strategy: str = "augment",
    missing_char_names: list[str] | None = None,
) -> dict:
    """Rerun extraction for a window using split or augment strategy.

    split:   Divide the window's chunks in half → two new sub-windows.
    augment: Same chunks, new window ID, inject SUPERVISOR_HINT with missing names.
    """
    import_run_id = state.get("import_run_id", "")
    source_hash = state.get("import_run_manifest", {}).get("source_hash", "")[:8]
    windows_by_id = {w.get("id"): w for w in state.get("prompt_windows", [])}
    parent = windows_by_id.get(window_id)
    if not parent:
        return {"errors": list(state.get("errors", [])) + [f"rerun_window: parent window {window_id!r} not found"]}

    profile_config = state.get("profile_config") or PROFILE_CONFIGS.get(state.get("prompt_profile", "balanced"), PROFILE_CONFIGS["balanced"])
    current_metrics = state.get("window_metrics", {}).get(window_id, {})
    rerun_count = int(current_metrics.get("rerun_count", 0)) + 1
    max_reruns = profile_config.get("max_rerun_iterations", 2)

    if rerun_count > max_reruns:
        log = list(state.get("supervisor_log", []))
        log.append(f"rerun_window {window_id}: at max reruns ({max_reruns}), skipping (action=skip)")
        decisions = list(state.get("supervisor_decisions", []))
        decisions.append({
            "iteration": state.get("supervisor_iteration", 0),
            "stage": "rerun_window",
            "tool_called": "rerun_window",
            "reason": f"Max rerun cap {max_reruns} reached for window {window_id}",
            "metrics_before": current_metrics,
            "metrics_after": {},
            "action": "skip",
            "rerun_targets": [],
            "timestamp": _now_iso(),
        })
        return {"supervisor_log": log, "supervisor_decisions": decisions}

    chunk_ids = parent.get("chunk_ids", [])
    prompt_windows = list(state.get("prompt_windows", []))

    if strategy == "split" and len(chunk_ids) >= 2:
        mid = max(1, len(chunk_ids) // 2)
        new_ids: list[str] = []
        for part_idx, part_chunk_ids in enumerate([chunk_ids[:mid], chunk_ids[mid:]]):
            new_id = _stable_id("pwin", import_run_id, *part_chunk_ids, "split", rerun_count, source_hash)
            part_chunks = [c for c in state.get("chunks", []) if c.get("chunk_id") in part_chunk_ids]
            digest = state.get("project_structure_digest") or {}
            profile_state = {**state, "prompt_profile": state.get("prompt_profile", "balanced")}
            sub_wins = _build_prompt_windows(profile_state, part_chunks, digest)
            for sw in sub_wins:
                sw["id"] = new_id
                sw["split_reason"] = f"supervisor_split_of_{window_id}"
                sw["output_token_budget"] = profile_config.get("output_token_budget", 3000)
                prompt_windows.append(sw)
                new_ids.append(new_id)

        log = list(state.get("supervisor_log", []))
        log.append(f"rerun_window {window_id} split → {new_ids}")
        partial: dict = {"prompt_windows": prompt_windows, "supervisor_log": log}
        for new_id in new_ids:
            new_state = {**state, **partial}
            update = await extract_window(new_state, new_id)
            for k, v in update.items():
                if isinstance(v, list) and isinstance(partial.get(k), list):
                    partial[k] = partial[k] + (v if not isinstance(v, list) else v)
                else:
                    partial[k] = v
            # Update rerun_count on the new window metric
            wm = dict(partial.get("window_metrics", {}).get(new_id, {}))
            wm["rerun_count"] = rerun_count
            partial.setdefault("window_metrics", {})[new_id] = wm
        return partial

    # augment strategy (or fallback when chunk_ids < 2)
    new_id = _stable_id("pwin", import_run_id, *chunk_ids, "aug", rerun_count, source_hash)
    hint_block = ""
    if missing_char_names:
        names_list = ", ".join(missing_char_names[:20])
        hint_block = (
            f"\nSUPERVISOR_HINT: The following major character names were flagged as missing "
            f"from prior extraction passes. Ensure they are identified and registered: {names_list}\n\n"
        )
    new_text = hint_block + parent.get("text", "")
    new_win = {
        **parent,
        "id": new_id,
        "text": new_text,
        "estimated_tokens": _estimate_tokens(new_text),
        "split_reason": f"supervisor_augment_of_{window_id}",
        "output_token_budget": profile_config.get("output_token_budget", 3000),
    }
    prompt_windows.append(new_win)

    log = list(state.get("supervisor_log", []))
    log.append(f"rerun_window {window_id} augment → {new_id}")
    partial = {"prompt_windows": prompt_windows, "supervisor_log": log}
    new_state = {**state, **partial}
    update = await extract_window(new_state, new_id)
    partial.update(update)
    wm = dict(partial.get("window_metrics", {}).get(new_id, {}))
    wm["rerun_count"] = rerun_count
    partial.setdefault("window_metrics", {})[new_id] = wm
    return partial


# ── Tool: reduce_entities ───────────────────────────────────────────────────────

async def reduce_entities(state: ImportSupervisorState) -> dict:
    """Reconcile entities + flag low-confidence entries. Reports missing groupKey count."""
    result1 = await node_reconcile_entities(state)
    merged1 = {**state, **result1}
    result2 = await node_resolve_low_confidence(merged1)

    registry = result2.get("entity_registry") or result1.get("entity_registry") or state.get("entity_registry", {})
    chars = registry.get("characters", {})

    missing_groupkey = sum(1 for c in chars.values() if not c.get("groupKey") and not c.get("skip_create"))
    org_chars = sum(
        1 for c in chars.values()
        if "organization" in str(c.get("role_in_story", "")).lower() or
           str(c.get("importance", "")).lower() == "organization"
    )

    log = list(state.get("supervisor_log", []))
    log.append(f"reduce_entities: {len(chars)} chars total, {missing_groupkey} missing groupKey, {org_chars} org-chars")

    updates = {**result1, **result2, "supervisor_log": log, "current_stage": "reduce_entities"}
    return updates


# ── Tool: architect_timeline ────────────────────────────────────────────────────

async def architect_timeline(state: ImportSupervisorState) -> dict:
    """Deduplicate and place events into timeline branches."""
    result = await node_architect_timeline(state)
    timeline = result.get("timeline_architecture") or state.get("timeline_architecture", {})
    canonical_count = len(timeline.get("canonical_events", []))
    branch_count = len(result.get("timeline_branches", state.get("timeline_branches", [])))

    log = list(state.get("supervisor_log", []))
    log.append(f"architect_timeline: {canonical_count} canonical events, {branch_count} branches")

    return {**result, "supervisor_log": log, "current_stage": "architect_timeline"}


# ── Tool: qa_review ─────────────────────────────────────────────────────────────

async def qa_review(state: ImportSupervisorState) -> dict:
    """Run import review and compute symptom flags → gate_failures."""
    result = await node_review_import(state)
    merged = {**state, **result}

    flags = _symptom_flags(merged)
    gate_failures: list[dict] = list(state.get("gate_failures", []))

    if flags["missing_groupkey_count"] > 0:
        gate_failures.append({"gate": "groupKey_coverage", "value": flags["missing_groupkey_count"], "threshold": 0, "windows": []})
    if flags["mixed_language_trait_sets"]:
        gate_failures.append({"gate": "language_consistency", "value": True, "threshold": False, "windows": []})
    if flags["org_chars_in_registry"] > 0:
        gate_failures.append({"gate": "world_person_boundary", "value": flags["org_chars_in_registry"], "threshold": 0, "windows": []})

    report = result.get("import_review_report", {})
    proposal_counts = report.get("proposal_counts", {})

    log = list(state.get("supervisor_log", []))
    log.append(f"qa_review: status={report.get('status', '?')}, gate_failures={len(gate_failures)}, flags={flags}")

    return {
        **result,
        "gate_failures": gate_failures,
        "supervisor_log": log,
        "current_stage": "qa_review",
    }


# ── Tool: minor_repair ──────────────────────────────────────────────────────────

async def minor_repair(state: ImportSupervisorState) -> dict:
    """Deterministic structural repairs — always runs, never triggers reruns.

    Fixes applied:
    1. groupKey normalization for characters missing it.
    2. world/person boundary: migrate org/location chars → world_detailed.
    3. orderIndex re-sequencing per timeline branch.
    4. Language field validation: strip long Latin traits for zh source.
    """
    registry = {k: (dict(v) if isinstance(v, dict) else v) for k, v in state.get("entity_registry", {}).items()}
    chars: dict[str, dict] = {k: dict(v) for k, v in registry.get("characters", {}).items()}
    repair_log: list[str] = list(state.get("minor_repair_log", []))

    # 1. groupKey normalization
    groupkey_fixed = 0
    for cid, entry in chars.items():
        if not entry.get("groupKey") and not entry.get("skip_create"):
            importance = str(entry.get("importance", "supporting"))
            entry["groupKey"] = IMPORTANCE_TO_GROUP.get(importance, "Supporting Cast")
            groupkey_fixed += 1
    if groupkey_fixed:
        repair_log.append(f"groupKey_normalization: fixed {groupkey_fixed} characters")

    # 2. world/person boundary — migrate org-role chars to world_detailed
    world_detailed: dict[str, dict] = dict(registry.get("world_detailed", {}))
    migrated = 0
    for cid, entry in list(chars.items()):
        name = entry.get("canonical_name", cid)
        if _is_world_entity_candidate(name, entry):
            canonical_category = _normalize_world_category(name, entry.get("category", "organization"))
            if name not in world_detailed:
                world_detailed[name] = {
                    "name": name, "category": canonical_category,
                    "description": entry.get("summary", ""),
                    "attributes": entry.get("personality_traits", []),
                    "confidence": float(entry.get("confidence", 0.7)),
                }
            entry["skip_create"] = True
            migrated += 1
    if migrated:
        repair_log.append(f"world_person_boundary: migrated {migrated} org-chars to world_detailed")

    # 3. orderIndex re-sequencing for timeline events
    events: dict[str, dict] = {k: dict(v) for k, v in registry.get("events", {}).items()}
    events_by_branch: dict[str, list[tuple[str, dict]]] = {}
    for eid, ev in events.items():
        branch = str(ev.get("branchId", ev.get("branch_id", "main")))
        events_by_branch.setdefault(branch, []).append((eid, ev))
    resequenced = 0
    for branch, branch_events in events_by_branch.items():
        sorted_items = sorted(branch_events, key=lambda x: int(x[1].get("orderIndex", 0) or 0))
        for new_idx, (eid, ev) in enumerate(sorted_items):
            if ev.get("orderIndex") != new_idx:
                ev["orderIndex"] = new_idx
                resequenced += 1
    if resequenced:
        repair_log.append(f"orderIndex_resequencing: fixed {resequenced} events")

    # 4. Language field validation: strip long Latin-only traits for zh source
    source_lang = state.get("source_language", "en")
    latin_stripped = 0
    if source_lang == "zh":
        for cid, entry in chars.items():
            if entry.get("skip_create"):
                continue
            cleaned_traits = []
            for trait in entry.get("personality_traits", []):
                if isinstance(trait, str) and re.search(r"[A-Za-z]{4,}", trait) and len(trait) > 6:
                    latin_stripped += 1
                else:
                    cleaned_traits.append(trait)
            entry["personality_traits"] = cleaned_traits
        if latin_stripped:
            repair_log.append(f"language_validation: stripped {latin_stripped} Latin-dominant traits for zh source")

    registry["characters"] = chars
    registry["world_detailed"] = world_detailed
    registry["events"] = events

    log = list(state.get("supervisor_log", []))
    log.append(f"minor_repair: groupKey={groupkey_fixed}, orgs_migrated={migrated}, resequenced={resequenced}, latin_stripped={latin_stripped}")

    return {
        "entity_registry": registry,
        "minor_repair_log": repair_log,
        "supervisor_log": log,
        "current_stage": "minor_repair",
    }


# ── Tool: proposal_write ────────────────────────────────────────────────────────

async def proposal_write(state: ImportSupervisorState) -> dict:
    """Run synthesis nodes then write proposals to the project."""
    # Build manuscript chapters
    manuscript_result = await node_build_manuscript(state)
    merged = {**state, **manuscript_result}

    # Synthesis: relationships, character_tags, world_settings
    rel_result = await node_synthesize_relationships(merged)
    merged = {**merged, **rel_result}

    tags_result = await node_classify_character_tags(merged)
    merged = {**merged, **tags_result}

    world_result = await node_infer_world_settings(merged)
    merged = {**merged, **world_result}

    # Write proposals
    write_result = await node_write_to_project(merged)

    proposals = write_result.get("proposals", [])
    log = list(state.get("supervisor_log", []))
    log.append(f"proposal_write: {len(proposals)} proposals written")

    return {
        **manuscript_result,
        **rel_result,
        **tags_result,
        **world_result,
        **write_result,
        "supervisor_log": log,
        "current_stage": "proposal_write",
    }
