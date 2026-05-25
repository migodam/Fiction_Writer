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
import unicodedata
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from sidecar.models.state import (
    ConvergeTarget,
    ImportSupervisorState,
    JudgeArtifact,
    WindowExtractionMetrics,
    PROFILE_CONFIGS,
    ThematicRerunRequest,
    ToolOperatingSpec,
    plan_converge_target,
    plan_tool_operating_spec,
)
from sidecar.workflows.w1_import import (
    _API_SEMAPHORE,
    _add_world_candidate_to_registry,
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
    _normalize_timeline_event_ontology,
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


def _chapter_count_from_state(state: ImportSupervisorState) -> int:
    chunks = state.get("chunks", [])
    if chunks:
        return max(len(chunks), 1)
    windows = state.get("prompt_windows", [])
    return max(sum(len(w.get("chunk_ids", [])) or 1 for w in windows), 1)


def _active_tool_operating_spec(state: ImportSupervisorState) -> ToolOperatingSpec:
    if state.get("tool_operating_spec"):
        return state["tool_operating_spec"]
    return plan_tool_operating_spec(
        prompt_profile=state.get("prompt_profile", "balanced"),
        source_language=state.get("source_language", "en"),
        chapter_count=_chapter_count_from_state(state),
        overrides=state.get("context", {}).get("tool_operating_spec_overrides", {}),
        use_supervisor=state.get("use_supervisor"),
        use_orchestrator=state.get("context", {}).get("use_orchestrator"),
    )


def _active_converge_target(state: ImportSupervisorState, spec: ToolOperatingSpec | None = None) -> ConvergeTarget:
    if state.get("converge_target"):
        return state["converge_target"]
    active_spec = spec or _active_tool_operating_spec(state)
    return plan_converge_target(
        active_spec,
        source_language=state.get("source_language", "en"),
        chapter_count=_chapter_count_from_state(state),
    )


def _candidate_windows_for_theme(state: ImportSupervisorState, theme: str, spec: ToolOperatingSpec) -> list[str]:
    metrics = state.get("window_metrics", {})
    if not metrics:
        return [w.get("id", "") for w in state.get("prompt_windows", []) if w.get("id")][:3]

    target_ids: list[str] = []
    for window_id, item in metrics.items():
        chapters = max(int(item.get("chapter_count", 1) or 1), 1)
        if theme == "character_undercoverage":
            density = float(item.get("char_count_extracted", 0)) / chapters
            if density < float(spec.get("min_characters_per_chapter", 0.75)):
                target_ids.append(window_id)
        elif theme == "timeline_undercoverage":
            density = float(item.get("event_count_extracted", 0)) / chapters
            if density < float(spec.get("event_density_target", 0.75)):
                target_ids.append(window_id)
    if target_ids:
        return target_ids[:3]
    return [w.get("id", "") for w in state.get("prompt_windows", []) if w.get("id")][:3]


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
    # Assemble source text from state chunks (windows store metadata only, not the text)
    chunk_id_set = set(chunk_ids)
    all_chunks_by_id = {c.get("chunk_id"): c for c in state.get("chunks", [])}
    window_chunks = [all_chunks_by_id[cid] for cid in chunk_ids if cid in all_chunks_by_id]
    prompt_text = "\n\n".join(str(c.get("content", c.get("text", ""))) for c in window_chunks)
    if not prompt_text:
        prompt_text = str(window.get("text", "") or window.get("source_text", ""))
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
        if _is_world_entity_candidate(name, nc):
            _add_world_candidate_to_registry(
                registry,
                name,
                _normalize_world_category(name, nc.get("category") or "organization"),
                str(nc.get("summary") or nc.get("role_in_story") or "").strip(),
                float(nc.get("confidence", 0.72) or 0.72),
            )
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
        ev, _ontology_warnings = _normalize_timeline_event_ontology(ev)
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
            "eventType": str(ev.get("eventType", "")).strip(),
            "arcRole": str(ev.get("arcRole", "")).strip(),
            "causalRole": str(ev.get("causalRole", "")).strip(),
            "branchRole": str(ev.get("branchRole", "")).strip(),
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
            "importance": str(ev.get("importance", "")).strip(),
            "deterministicLaneHints": ev.get("deterministicLaneHints", {}),
            "ontologyWarnings": ev.get("ontologyWarnings", []),
            "confidence": float(ev.get("confidence", 0.7)),
            "chunk_id": chunk_id,
        }
        registry["events"][event_id] = entry
        new_events.append(entry)

    # ── Register world mentions ──────────────────────────────────────────────
    # Apply per-window world entity cap from TOS
    tos = state.get("tool_operating_spec") or {}
    _max_world_per_chapter = int(tos.get("max_world_entities_per_chapter", 5))
    _world_window_cap = _max_world_per_chapter * max(len(chunk_ids), 1)
    raw_world_mentions = sorted(
        world_data.get("world_mentions", []),
        key=lambda w: float(w.get("confidence", 0.7)),
        reverse=True,
    )[:_world_window_cap]

    new_world: list[str] = []
    for wm in raw_world_mentions:
        name = str(wm.get("name", "")).strip()
        if not name:
            continue
        category = _normalize_world_category(name, wm.get("category", "concept"))
        existed = name in registry["world"]
        _add_world_candidate_to_registry(
            registry,
            name,
            category,
            str(wm.get("description", "")).strip(),
            float(wm.get("confidence", 0.7) or 0.7),
        )
        detail = registry["world_detailed"][name]
        if wm.get("attributes"):
            detail["attributes"] = wm.get("attributes", [])
        # Store dedupeKey if model provided one
        raw_dk = str(wm.get("dedupeKey", "")).strip()
        if raw_dk and not detail.get("dedupeKey"):
            detail["dedupeKey"] = raw_dk
        if not existed:
            new_world.append(name)

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

    missing_major_entries = result.get("missing_major_characters", [])
    missing_major_names = [
        str(m.get("name") or m.get("canonical_name") or m.get("name_or_alias") or "").strip()
        for m in missing_major_entries if isinstance(m, dict)
        if str(m.get("name") or m.get("canonical_name") or m.get("name_or_alias") or "").strip()
    ]
    duplicate_count = len(result.get("duplicate_characters", [])) + len(result.get("duplicate_events", []))

    window_metrics = dict(state.get("window_metrics", {}))
    wm = dict(window_metrics.get(window_id, {}))
    wm["missing_majors_count"] = len(missing_major_names)
    wm["missing_majors"] = missing_major_names
    wm["duplicate_count"] = duplicate_count
    window_metrics[window_id] = wm

    # Merge into cross_validation artifact
    existing_cv = dict(state.get("cross_validation", {}))
    for key in ("duplicate_characters", "duplicate_events", "missing_major_characters",
                "suspicious_groups", "contradictory_aliases", "event_merge_recommendations", "warnings"):
        existing_cv.setdefault(key, [])
        existing_cv[key].extend(result.get(key, []))

    log = list(state.get("supervisor_log", []))
    log.append(f"cross_validate_window {window_id}: {len(missing_major_names)} missing majors, {duplicate_count} duplicates")

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
    parameter_overrides: dict | None = None,
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
    if parameter_overrides:
        override_text = json.dumps(parameter_overrides, ensure_ascii=False, sort_keys=True)
        hint_block += (
            "\nORCHESTRATOR_PARAMETER_OVERRIDES: Treat these as soft extraction emphasis only; "
            f"do not write canonical proposals directly: {override_text}\n\n"
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


# ── Tool: reduce_world_entities ────────────────────────────────────────────────

def _normalize_world_dedup_key(name: str, category: str) -> str:
    """Deterministic dedup key: NFC normalize, lowercase, strip spaces/hyphens/underscores/middle-dots."""
    n = unicodedata.normalize("NFC", str(name or "")).lower()
    n = re.sub(r"[\s\-_·・·]+", "", n)
    c = str(category or "concept").lower().strip()
    return f"{n}::{c}"


def reduce_world_entities(state: "ImportSupervisorState") -> dict:
    """Deterministic world entity deduplication across all extraction windows.

    Groups world_detailed entries by dedupeKey (model-provided) or computed
    normalized_name::category. Picks the highest-confidence entry per group as
    canonical and merges attributes from all duplicates.
    """
    registry = {k: dict(v) if isinstance(v, dict) else v for k, v in state.get("entity_registry", {}).items()}
    world_detailed: dict = dict(registry.get("world_detailed", {}))

    # Build groups keyed by dedupeKey (model-provided) or computed fallback
    groups: dict[str, list[tuple[str, dict]]] = {}
    for name, detail in world_detailed.items():
        dk = str(detail.get("dedupeKey", "")).strip()
        if not dk:
            dk = _normalize_world_dedup_key(name, detail.get("category", "concept"))
        groups.setdefault(dk, []).append((name, detail))

    new_world: dict[str, str] = {}
    new_world_detailed: dict[str, dict] = {}
    merge_log: list[str] = []

    for dk, entries in groups.items():
        # Canonical = highest confidence
        sorted_entries = sorted(entries, key=lambda x: float(x[1].get("confidence", 0.0)), reverse=True)
        canonical_name, canonical_detail = sorted_entries[0]

        # Merge attributes from all duplicates (no key collision)
        merged_attrs: list[dict] = list(canonical_detail.get("attributes", []))
        seen_attr_keys = {a.get("key") for a in merged_attrs}
        for dup_name, dup_detail in sorted_entries[1:]:
            for attr in dup_detail.get("attributes", []):
                if attr.get("key") not in seen_attr_keys:
                    merged_attrs.append(attr)
                    seen_attr_keys.add(attr.get("key"))
            if dup_name != canonical_name:
                merge_log.append(f"world_dedup: '{dup_name}' → '{canonical_name}' (key={dk})")

        merged = dict(canonical_detail)
        merged["attributes"] = merged_attrs
        merged["confidence"] = max(float(d.get("confidence", 0.0)) for _, d in sorted_entries)
        merged["dedupeKey"] = dk  # persist key for idempotency

        new_world[canonical_name] = merged.get("category", "concept")
        new_world_detailed[canonical_name] = merged

    new_registry = {**registry, "world": new_world, "world_detailed": new_world_detailed}

    log = list(state.get("supervisor_log", []))
    before = len(world_detailed)
    after = len(new_world_detailed)
    log.append(f"reduce_world_entities: {before} → {after} entries ({len(merge_log)} merges)")

    return {
        "entity_registry": new_registry,
        "supervisor_log": log,
        "current_stage": "reduce_world_entities",
    }


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


# ── Tool: judge_import ─────────────────────────────────────────────────────────

async def judge_import(state: ImportSupervisorState) -> dict:
    """Deterministic convergence judge that may request bounded thematic reruns."""
    spec = _active_tool_operating_spec(state)
    target = _active_converge_target(state, spec)
    registry = state.get("entity_registry", {})
    chars = registry.get("characters", {})
    events = registry.get("events", {})
    world = registry.get("world", {})
    world_detailed = registry.get("world_detailed", {})
    timeline = state.get("timeline_architecture", {})
    canonical_events = timeline.get("canonical_events", []) or list(events.values())
    flags = _symptom_flags(state)

    character_count = sum(1 for c in chars.values() if not c.get("skip_create"))
    event_count = len(canonical_events)
    world_count = len(world_detailed) + len(world)

    failed_gates: list[str] = []
    requests: list[ThematicRerunRequest] = []

    if character_count < int(target.get("expected_min_characters", 1)):
        failed_gates.append("character_undercoverage")
        requests.append({
            "theme": "character_undercoverage",
            "target_windows": _candidate_windows_for_theme(state, "character_undercoverage", spec),
            "reason": f"characters={character_count}<target={target.get('expected_min_characters')}",
            "parameter_overrides": {
                "min_characters_per_chapter": spec.get("min_characters_per_chapter"),
                "character_focus": "recover_named_and_major_characters",
            },
            "expected_repair": "Recover missed named/major characters without writing canonical proposals directly.",
        })

    if event_count < int(target.get("expected_min_events", 1)):
        failed_gates.append("timeline_undercoverage")
        requests.append({
            "theme": "timeline_undercoverage",
            "target_windows": _candidate_windows_for_theme(state, "timeline_undercoverage", spec),
            "reason": f"canonical_events={event_count}<target={target.get('expected_min_events')}",
            "parameter_overrides": {
                "event_density_target": spec.get("event_density_target"),
                "timeline_topology_target": spec.get("timeline_topology_target"),
            },
            "expected_repair": "Recover missing chapter-level timeline events for the reducer/architect path.",
        })

    if flags["org_chars_in_registry"] > 0:
        failed_gates.append("world_boundary")
        requests.append({
            "theme": "world_boundary",
            "target_windows": _candidate_windows_for_theme(state, "world_boundary", spec),
            "reason": f"org_chars_in_registry={flags['org_chars_in_registry']}",
            "parameter_overrides": {
                "world_category_policy": spec.get("world_category_policy"),
                "boundary_focus": "organizations_locations_rules_as_world",
            },
            "expected_repair": "Re-extract world/organization boundary candidates for deterministic repair.",
        })

    if flags["mixed_language_trait_sets"]:
        failed_gates.append("language_mismatch")
        requests.append({
            "theme": "language_mismatch",
            "target_windows": _candidate_windows_for_theme(state, "language_mismatch", spec),
            "reason": f"source_language={target.get('expected_language')} has mixed-language trait fields",
            "parameter_overrides": {
                "language_policy": spec.get("language_policy"),
                "expected_language": target.get("expected_language"),
            },
            "expected_repair": "Re-run extraction with source-language field normalization hints.",
        })

    score = max(0.0, 1.0 - 0.18 * len(failed_gates))
    threshold = float(spec.get("judge_pass_threshold", 0.8))
    passed = score >= threshold and not failed_gates
    artifact: JudgeArtifact = {
        "score": round(score, 3),
        "passed": passed,
        "failed_gates": failed_gates,
        "thematic_rerun_requests": requests,
        "iteration": int(state.get("supervisor_iteration", 0)),
        "metrics_snapshot": {
            "character_count": character_count,
            "canonical_event_count": event_count,
            "world_count": world_count,
            "expected": target,
            "symptom_flags": flags,
            "window_metrics": state.get("window_metrics", {}),
        },
        "rationale": "pass" if passed else f"failed gates: {', '.join(failed_gates)}",
    }

    import_run_id = state.get("import_run_id", "")
    project_path = state.get("project_path", "")
    artifact_paths: dict[str, str] = {}
    if import_run_id and project_path:
        judge_path = _write_import_artifact(project_path, import_run_id, "judge_artifact.json", artifact)
        tos_path = _write_import_artifact(project_path, import_run_id, "tool_operating_spec.json", spec)
        artifact_paths = {"judge_artifact": judge_path, "tool_operating_spec": tos_path}
        artifact["artifact_paths"] = artifact_paths

    log = list(state.get("supervisor_log", []))
    log.append(f"judge_import: score={artifact['score']}, passed={passed}, failed_gates={failed_gates}")

    return {
        "tool_operating_spec": spec,
        "converge_target": target,
        "judge_artifact": artifact,
        "thematic_rerun_requests": requests,
        "judge_score": artifact["score"],
        "converge_status": "passed" if passed else "failed",
        "supervisor_log": log,
        "current_stage": "judge_import",
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
    world_map: dict[str, str] = dict(registry.get("world", {}))
    world_detailed: dict[str, dict] = dict(registry.get("world_detailed", {}))
    migrated = 0
    for cid, entry in list(chars.items()):
        name = entry.get("canonical_name", cid)
        if _is_world_entity_candidate(name, entry):
            canonical_category = _normalize_world_category(name, entry.get("category", "organization"))
            world_map[name] = canonical_category
            if name not in world_detailed:
                world_detailed[name] = {
                    "name": name, "category": canonical_category,
                    "description": entry.get("summary", ""),
                    "attributes": entry.get("personality_traits", []),
                    "container_hint": "organizations" if canonical_category in {"organization", "faction"} else "",
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
    registry["world"] = world_map
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
    # Write diagnostics BEFORE proposal write so they survive an OOM crash
    import_run_id = state.get("import_run_id", "")
    project_path = state.get("project_path", "")
    if import_run_id and project_path:
        _write_import_artifact(
            project_path, import_run_id, "supervisor_decisions.json",
            state.get("supervisor_decisions", []),
        )
        _write_import_artifact(
            project_path, import_run_id, "window_metrics.json",
            state.get("window_metrics", {}),
        )
        _write_import_artifact(
            project_path, import_run_id, "tool_operating_spec.json",
            state.get("tool_operating_spec", _active_tool_operating_spec(state)),
        )
        if state.get("judge_artifact"):
            _write_import_artifact(
                project_path, import_run_id, "judge_artifact.json",
                state.get("judge_artifact", {}),
            )
        if state.get("cross_validation"):
            _write_import_artifact(
                project_path, import_run_id, "cross_validation.json",
                state.get("cross_validation", {}),
            )

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

    return_dict = {
        **manuscript_result,
        **rel_result,
        **tags_result,
        **world_result,
        **write_result,
        "supervisor_log": log,
        "current_stage": "proposal_write",
    }
    return_dict.pop("entity_registry", None)
    return_dict.pop("cross_validation", None)
    return return_dict
