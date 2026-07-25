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
import inspect
import json
import re
import unicodedata
import uuid
from time import perf_counter
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
    _ainvoke_with_budget,
    _append_unique_strings,
    _artifact_dir,
    _build_project_structure_digest,
    _build_prompt_windows,
    _build_supervised_prompt_windows,
    _compact_character_card,
    _estimate_tokens,
    _get_llm,
    _invoke_json_prompt,
    _is_world_entity_candidate,
    _merge_prompt_outputs,
    _merge_text_field,
    _normalize_character_tag,
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
from sidecar.workflows.w1_run_events import (
    ProviderCallRequiresHumanConfirmation,
    append_event,
    set_active_call,
)
from sidecar.supervisor.prompt_policy import build_directives_header
from sidecar.prompts.w1_prompts import (
    W1_CROSS_VALIDATE_IMPORT,
    W1_EXTRACT_CHARACTERS_DEEP,
    W1_EXTRACT_CHARACTERS_DEEP_BALANCED,
    W1_EXTRACT_CHARACTERS_DEEP_FINE,
    W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL,
    W1_EXTRACT_EVENTS_DEEP,
    W1_EXTRACT_EVENTS_DEEP_ARC,
    W1_EXTRACT_EVENTS_DEEP_CHAPTER,
    W1_EXTRACT_EVENTS_DEEP_DENSE,
    W1_EXTRACT_EVENTS_DEEP_SPARSE,
    W1_EXTRACT_RELATIONSHIPS_CHUNK,
    W1_EXTRACT_RELATIONSHIPS_CORE,
    W1_EXTRACT_RELATIONSHIPS_DENSE,
    W1_EXTRACT_RELATIONSHIPS_RECURRING,
    W1_EXTRACT_SCENE_SUMMARIES,
    W1_EXTRACT_WORLD_DEEP,
    W1_EXTRACT_WORLD_DEEP_LORE,
    W1_EXTRACT_WORLD_DEEP_SPARSE,
    W1_EXTRACT_WORLD_DEEP_STRUCTURAL,
)

# Output token threshold triggering pre-flight split.
_OUTPUT_BUDGET_SPLIT_THRESHOLD = 3_500


def _is_budget_exhausted_error(exc: Exception) -> bool:
    """True if exc signals an API HTTP 402 / insufficient-balance error."""
    msg = str(exc).lower()
    if "budget_exhausted" in msg or "402" in msg or "insufficient balance" in msg or "insufficient_balance" in msg:
        return True
    try:
        import openai  # type: ignore[import-not-found]
        if isinstance(exc, openai.APIStatusError) and getattr(exc, "status_code", 0) == 402:
            return True
    except ImportError:
        pass
    return False

# Tokens per chapter for output estimation:
# 1.5 chars × 120 + 3 events × 80 + 2 world × 50
_TOKENS_PER_CHAPTER_ESTIMATE = int(1.5 * 120 + 3 * 80 + 2 * 50)


def _session_id(state: ImportSupervisorState) -> str:
    return str(state.get("session_id") or state.get("context", {}).get("session_id") or "")


def _clip_for_window_context(value: Any, max_chars: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def _rolling_window_context(
    state: ImportSupervisorState,
    registry: dict,
    *,
    include_digest: bool = True,
    include_source_marker: bool = True,
) -> str:
    """Build the bounded project/context preamble each window actually sees."""
    digest = state.get("project_structure_digest") or {}
    digest_content = digest.get("content", digest) if isinstance(digest, dict) else digest
    cross_validation = state.get("cross_validation") or {}
    validation_payload = {
        "duplicate_characters": cross_validation.get("duplicate_characters", [])[-12:],
        "duplicate_events": cross_validation.get("duplicate_events", [])[-12:],
        "missing_major_characters": cross_validation.get("missing_major_characters", [])[-12:],
        "event_merge_recommendations": cross_validation.get("event_merge_recommendations", [])[-12:],
        "warnings": cross_validation.get("warnings", [])[-12:],
    }
    plan_payload = {
        "granularity_profile": state.get("import_granularity_profile", {}),
        "prompt_policy": (state.get("import_plan") or {}).get("prompt_policy", {}),
        "converge_target": state.get("converge_target", {}),
    }
    parts: list[str] = []
    if include_digest:
        parts.append(
            "PROJECT_STRUCTURE_DIGEST:\n"
            f"{_clip_for_window_context(digest_content, 8000)}\n\n"
        )
    parts.extend([
        "ROLLING_ENTITY_REGISTRY_SUMMARY:\n"
        f"{_clip_for_window_context(_registry_summary(registry), 6000)}\n\n",
        "PREVIOUS_VALIDATION_SUMMARY:\n"
        f"{_clip_for_window_context(validation_payload, 4000)}\n\n",
        "IMPORT_PLAN_CONTEXT:\n"
        f"{_clip_for_window_context(plan_payload, 3000)}\n\n",
    ])
    if include_source_marker:
        parts.append("SOURCE_CHAPTERS:\n")
    return "".join(parts)


async def _invoke_window_prompt_with_activity(
    state: ImportSupervisorState,
    window_id: str,
    chapter_range: str,
    label: str,
    llm: Any,
    prompt_template: str,
    **kwargs: Any,
) -> dict:
    session_id = _session_id(state)
    started = perf_counter()
    if session_id:
        append_event(session_id, {
            "phase": "extracting",
            "tool": "extract_window",
            "window_id": window_id,
            "chapter_range": chapter_range,
            "prompt_label": label,
            "status": "start",
            "message": f"Running {label} prompt for {window_id}.",
        })
        set_active_call(session_id, 1)
    try:
        maybe_result = _invoke_json_prompt(llm, prompt_template, session_id=session_id, **kwargs)
        result = await maybe_result if inspect.isawaitable(maybe_result) else maybe_result
        if session_id:
            append_event(session_id, {
                "phase": "extracting",
                "tool": "extract_window",
                "window_id": window_id,
                "chapter_range": chapter_range,
                "prompt_label": label,
                "status": "success",
                "message": f"Finished {label} prompt for {window_id}.",
                "duration_ms": int((perf_counter() - started) * 1000),
            })
        return result
    except ProviderCallRequiresHumanConfirmation:
        raise
    except Exception as exc:
        if session_id:
            is_budget = _is_budget_exhausted_error(exc)
            append_event(session_id, {
                "phase": "extracting",
                "tool": "extract_window",
                "window_id": window_id,
                "chapter_range": chapter_range,
                "prompt_label": label,
                "status": "fail",
                "level": "error",
                "message": (
                    f"Budget exhausted while running {label} prompt for {window_id}."
                    if is_budget
                    else f"Failed {label} prompt for {window_id}."
                ),
                "duration_ms": int((perf_counter() - started) * 1000),
                "error": str(exc),
            })
        raise
    finally:
        if session_id:
            set_active_call(session_id, -1)


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
    if density == "sparse_turning_points":
        return max(2, min(8, (chapter_count + 2) // 3))
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

    # Build supervised windows from all chunks so the planner can pack multiple
    # chapters per extraction window instead of paying prompt overhead per chapter.
    raw_windows = _build_supervised_prompt_windows(profile_state, chunks, digest)

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
                    sw["output_token_budget"] = profile_config.get("output_token_budget", 4000)
                    final_windows.append(sw)
        else:
            win["output_token_budget"] = profile_config.get("output_token_budget", 4000)
            final_windows.append(win)

    log = list(state.get("supervisor_log", []))
    log.append(f"segment_manifest: built {len(final_windows)} windows from {len(chunks)} chunks (pre-flight splits applied)")

    return {
        "prompt_windows": final_windows,
        "supervisor_log": log,
        "current_stage": "segment_manifest",
    }


# ── Extraction variant dispatch ──────────────────────────────────────────────

_CHAR_PROMPT_BY_GRANULARITY: dict[str, str] = {
    "major_only": W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL,
    "named_only": W1_EXTRACT_CHARACTERS_DEEP_BALANCED,
    "all":        W1_EXTRACT_CHARACTERS_DEEP_FINE,
}
_EVENT_PROMPT_BY_DENSITY: dict[str, str] = {
    "sparse_turning_points": W1_EXTRACT_EVENTS_DEEP_SPARSE,
    "arc_level":     W1_EXTRACT_EVENTS_DEEP_ARC,
    "chapter_level": W1_EXTRACT_EVENTS_DEEP_CHAPTER,
    "scene_level":   W1_EXTRACT_EVENTS_DEEP_DENSE,
}
_WORLD_PROMPT_BY_DENSITY: dict[str, str] = {
    "named_only": W1_EXTRACT_WORLD_DEEP_SPARSE,
    "structural": W1_EXTRACT_WORLD_DEEP_STRUCTURAL,
    "full_lore":  W1_EXTRACT_WORLD_DEEP_LORE,
}
_REL_PROMPT_BY_DEPTH: dict[str, str] = {
    "core":      W1_EXTRACT_RELATIONSHIPS_CORE,
    "recurring": W1_EXTRACT_RELATIONSHIPS_RECURRING,
    "dense":     W1_EXTRACT_RELATIONSHIPS_DENSE,
}


def _select_extraction_prompts(state: ImportSupervisorState) -> dict[str, str]:
    profile = state.get("import_granularity_profile") or {}
    return {
        "character": _CHAR_PROMPT_BY_GRANULARITY.get(
            profile.get("character_granularity", ""),
            W1_EXTRACT_CHARACTERS_DEEP,
        ),
        "event": _EVENT_PROMPT_BY_DENSITY.get(
            profile.get("event_density", ""),
            W1_EXTRACT_EVENTS_DEEP,
        ),
        "world": _WORLD_PROMPT_BY_DENSITY.get(
            profile.get("world_density", ""),
            W1_EXTRACT_WORLD_DEEP,
        ),
        "relationship": _REL_PROMPT_BY_DEPTH.get(
            profile.get("relationship_depth", ""),
            W1_EXTRACT_RELATIONSHIPS_CHUNK,
        ),
    }


def _selected_extraction_prompt_manifest(state: ImportSupervisorState) -> dict[str, dict[str, str]]:
    """Return a compact, artifact-safe manifest of selected prompt variants."""
    profile = state.get("import_granularity_profile") or {}
    prompts = _select_extraction_prompts(state)
    variant_names = {
        id(W1_EXTRACT_CHARACTERS_DEEP): "W1_EXTRACT_CHARACTERS_DEEP",
        id(W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL): "W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL",
        id(W1_EXTRACT_CHARACTERS_DEEP_BALANCED): "W1_EXTRACT_CHARACTERS_DEEP_BALANCED",
        id(W1_EXTRACT_CHARACTERS_DEEP_FINE): "W1_EXTRACT_CHARACTERS_DEEP_FINE",
        id(W1_EXTRACT_EVENTS_DEEP): "W1_EXTRACT_EVENTS_DEEP",
        id(W1_EXTRACT_EVENTS_DEEP_SPARSE): "W1_EXTRACT_EVENTS_DEEP_SPARSE",
        id(W1_EXTRACT_EVENTS_DEEP_ARC): "W1_EXTRACT_EVENTS_DEEP_ARC",
        id(W1_EXTRACT_EVENTS_DEEP_CHAPTER): "W1_EXTRACT_EVENTS_DEEP_CHAPTER",
        id(W1_EXTRACT_EVENTS_DEEP_DENSE): "W1_EXTRACT_EVENTS_DEEP_DENSE",
        id(W1_EXTRACT_WORLD_DEEP): "W1_EXTRACT_WORLD_DEEP",
        id(W1_EXTRACT_WORLD_DEEP_SPARSE): "W1_EXTRACT_WORLD_DEEP_SPARSE",
        id(W1_EXTRACT_WORLD_DEEP_STRUCTURAL): "W1_EXTRACT_WORLD_DEEP_STRUCTURAL",
        id(W1_EXTRACT_WORLD_DEEP_LORE): "W1_EXTRACT_WORLD_DEEP_LORE",
        id(W1_EXTRACT_RELATIONSHIPS_CHUNK): "W1_EXTRACT_RELATIONSHIPS_CHUNK",
        id(W1_EXTRACT_RELATIONSHIPS_CORE): "W1_EXTRACT_RELATIONSHIPS_CORE",
        id(W1_EXTRACT_RELATIONSHIPS_RECURRING): "W1_EXTRACT_RELATIONSHIPS_RECURRING",
        id(W1_EXTRACT_RELATIONSHIPS_DENSE): "W1_EXTRACT_RELATIONSHIPS_DENSE",
        id(W1_EXTRACT_SCENE_SUMMARIES): "W1_EXTRACT_SCENE_SUMMARIES",
    }
    return {
        "character": {
            "profile_field": "character_granularity",
            "profile_value": str(profile.get("character_granularity", "")),
            "prompt_constant": variant_names.get(id(prompts["character"]), "unknown"),
        },
        "event": {
            "profile_field": "event_density",
            "profile_value": str(profile.get("event_density", "")),
            "prompt_constant": variant_names.get(id(prompts["event"]), "unknown"),
        },
        "world": {
            "profile_field": "world_density",
            "profile_value": str(profile.get("world_density", "")),
            "prompt_constant": variant_names.get(id(prompts["world"]), "unknown"),
        },
        "relationship": {
            "profile_field": "relationship_depth",
            "profile_value": str(profile.get("relationship_depth", "")),
            "prompt_constant": variant_names.get(id(prompts["relationship"]), "unknown"),
        },
        "scene": {
            "profile_field": "",
            "profile_value": "",
            "prompt_constant": "W1_EXTRACT_SCENE_SUMMARIES",
        },
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
    # Prompt windows retain exact source_text for split windows. Reassembling from
    # chunks would silently expand a paragraph-split window back to its parent.
    chunk_id_set = set(chunk_ids)
    all_chunks_by_id = {c.get("chunk_id"): c for c in state.get("chunks", [])}
    window_chunks = [all_chunks_by_id[cid] for cid in chunk_ids if cid in all_chunks_by_id]
    prompt_text = str(window.get("source_text", "") or "")
    if not prompt_text:
        prompt_text = "\n\n".join(str(c.get("content", c.get("text", ""))) for c in window_chunks)
    if not prompt_text:
        prompt_text = str(window.get("text", "") or window.get("source_text", ""))
    # Prepend any supervisor hint injected by rerun_window (stored separately to survive chunk reassembly)
    supervisor_hint = str(window.get("supervisor_hint", "") or "")
    prompt_has_digest = "PROJECT_STRUCTURE_DIGEST:" in prompt_text
    rolling_context = _rolling_window_context(
        state,
        registry,
        include_digest=not prompt_has_digest,
        include_source_marker=not prompt_has_digest,
    )
    prompt_text = rolling_context + prompt_text
    if supervisor_hint:
        prompt_text = supervisor_hint + "\n\n" + prompt_text
    directives_header = build_directives_header((state.get("import_plan") or {}).get("prompt_policy", {}))
    if directives_header:
        prompt_text = directives_header + "\n\n" + prompt_text
    registry_summary = _registry_summary(registry)
    chapter_range = str(window.get("chapter_range") or f"chunk_{chunk_id}")

    failed_prompts: list[str] = []

    _src_lang = state.get("source_language", "en")
    _src_lang_label = "Chinese (Simplified)" if _src_lang == "zh" else "English"
    _lang_policy = (state.get("tool_operating_spec") or {}).get("language_policy", "preserve_source")

    # 5-parallel extraction
    _prompts = _select_extraction_prompts(state)
    _prompt_manifest = _selected_extraction_prompt_manifest(state)
    prompt_specs = [
        ("character", _prompts["character"], {}),
        ("event", _prompts["event"], {}),
        ("world", _prompts["world"], {}),
        ("relationship", _prompts["relationship"], {}),
        ("scene", W1_EXTRACT_SCENE_SUMMARIES, {"chapter_hint": chapter_range}),
    ]

    async def invoke_prompt(kind: str, prompt: str, extra: dict[str, Any]) -> Any:
        return await _invoke_window_prompt_with_activity(
            state, window_id, chapter_range, kind, llm, prompt,
            chunk_content=prompt_text, chunk_id=chunk_id,
            total_chunks=total, entity_registry_summary=registry_summary,
            source_language_label=_src_lang_label, language_policy=_lang_policy,
            **extra,
        )

    # A fail-closed ledger must observe each completed call before starting the
    # next one; concurrent preflights cannot reserve max_calls safely. Creating
    # each coroutine lazily also makes cancellation leave no un-awaited siblings.
    if state.get("context", {}).get("budget_policy"):
        results = []
        for kind, prompt, extra in prompt_specs:
            try:
                results.append(await invoke_prompt(kind, prompt, extra))
            except ProviderCallRequiresHumanConfirmation:
                raise
            except Exception as exc:
                results.append(exc)
                if _is_budget_exhausted_error(exc):
                    break
        results.extend([RuntimeError("budget_exhausted: skipped after ledger exhaustion")] * (len(prompt_specs) - len(results)))
    else:
        results = await asyncio.gather(
            *(invoke_prompt(kind, prompt, extra) for kind, prompt, extra in prompt_specs),
            return_exceptions=True,
        )

    labels = ["character", "event", "world", "relationship", "scene"]
    outputs: list[dict] = []
    _budget_exhausted_in_window = False
    for i, (label, result) in enumerate(zip(labels, results)):
        if isinstance(result, ProviderCallRequiresHumanConfirmation):
            raise result
        if isinstance(result, Exception):
            if _is_budget_exhausted_error(result):
                _budget_exhausted_in_window = True
                print(f"[extract_window] {window_id} BUDGET EXHAUSTED (402) on {label}: {result}", flush=True)
            failed_prompts.append(f"{label}:{type(result).__name__}:{result}")
            print(f"[extract_window] {window_id} {label} extraction FAILED: {result}", flush=True)
            outputs.append({})
        else:
            outputs.append(result if isinstance(result, dict) else {})

    char_data, event_data, world_data, rel_data, scene_data = outputs

    # Cap world mentions to 20 per chapter to bound entity_registry growth across
    # many windows. Sort by confidence descending so the best candidates survive.
    chapter_count = len(chunk_ids) or 1
    world_cap = chapter_count * 20
    world_mentions_raw = world_data.get("world_mentions", [])
    if len(world_mentions_raw) > world_cap:
        world_mentions_raw = sorted(
            world_mentions_raw,
            key=lambda wm: float(wm.get("confidence", 0) or 0),
            reverse=True,
        )[:world_cap]
        world_data = {**world_data, "world_mentions": world_mentions_raw}

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
    new_relationship_count = 0
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
            "evidence": rel.get("evidence", []),
            "aliasEvidence": rel.get("aliasEvidence", []),
            "contradictionHint": str(rel.get("contradictionHint", "")).strip(),
            "confidence": float(rel.get("confidence", 0.7)),
        })
        new_relationship_count += 1

    # ── Write window artifact ────────────────────────────────────────────────
    import_run_id = state.get("import_run_id", "")
    project_path = state.get("project_path", "")
    if import_run_id and project_path:
        artifact = {
            "window_id": window_id, "chunk_ids": chunk_ids,
            "chapter_range": chapter_range, "failed_prompts": failed_prompts,
            "char_count": len(new_char_ids), "event_count": len(new_events),
            "world_count": len(new_world),
            "import_granularity_profile": state.get("import_granularity_profile", {}),
            "selected_prompt_variants": _prompt_manifest,
        }
        _write_import_artifact(project_path, import_run_id, f"windows/{window_id}.json", artifact)

    # ── Build metrics ────────────────────────────────────────────────────────
    _char_extraction_failed = any(
        f.split(":")[0] == "character" for f in failed_prompts
    )
    _gate_passed = (
        len(failed_prompts) < 3
        and not (_char_extraction_failed and len(new_char_ids) == 0)
    )
    metrics: WindowExtractionMetrics = {
        "window_id": window_id,
        "chapter_count": len(chunk_ids),
        "char_count_extracted": len(new_char_ids),
        "event_count_extracted": len(new_events),
        "world_count_extracted": len(new_world),
        "relationship_count_extracted": new_relationship_count,
        "failed_prompts": failed_prompts,
        "confidence_distribution": {},
        "missing_majors_count": 0,
        "duplicate_count": 0,
        "rerun_count": state.get("window_metrics", {}).get(window_id, {}).get("rerun_count", 0),
        "gate_passed": _gate_passed,
    }

    window_metrics = dict(state.get("window_metrics", {}))
    window_metrics[window_id] = metrics

    log = list(state.get("supervisor_log", []))
    log.append(f"extract_window {window_id}: {len(new_char_ids)} chars, {len(new_events)} events, {len(new_world)} world, {len(failed_prompts)} failed")

    result: dict = {
        "entity_registry": registry,
        "raw_relationships": raw_rels,
        "window_metrics": window_metrics,
        "supervisor_log": log,
        "current_stage": "extract_window",
    }
    if _budget_exhausted_in_window:
        result["budget_exhausted"] = True
        result["errors"] = list(state.get("errors", [])) + [
            f"[budget_exhausted] API HTTP 402 during extraction of window {window_id} — insufficient balance"
        ]
        log.append(f"extract_window {window_id}: budget_exhausted=True — halting reruns")
    return result


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
        response = await _ainvoke_with_budget(
            llm,
            [HumanMessage(content=full_prompt)],
            session_id=_session_id(state),
            estimated_input_tokens=_estimate_tokens(full_prompt),
        )
        raw = response.content if isinstance(response.content, str) else str(response.content)
        result = _parse_json_response(raw)
    except ProviderCallRequiresHumanConfirmation:
        raise
    except Exception as exc:
        log = list(state.get("supervisor_log", []))
        log.append(f"cross_validate_window {window_id}: non-fatal error — {exc}")
        if _is_budget_exhausted_error(exc):
            return {
                "supervisor_log": log,
                "budget_exhausted": True,
                "errors": list(state.get("errors", [])) + [f"budget_exhausted during cross-validation: {exc}"],
            }
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
                sw["output_token_budget"] = profile_config.get("output_token_budget", 4000)
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
    new_prompt_text = hint_block + parent.get("prompt_text", parent.get("text", ""))
    new_win = {
        **parent,
        "id": new_id,
        "prompt_text": new_prompt_text,
        # supervisor_hint is applied at extraction time; text/source_text stay
        # span-reconstructable source payloads.
        "supervisor_hint": hint_block,
        "estimated_tokens": _estimate_tokens(new_prompt_text),
        "split_reason": f"supervisor_augment_of_{window_id}",
        "output_token_budget": profile_config.get("output_token_budget", 4000),
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

_CHARACTER_EVIDENCE_FIELDS = (
    "evidence", "evidence_cards", "source_evidence", "source_span",
    "source_spans", "provenance", "evidence_refs", "evidenceRefs",
)
_CHARACTER_IDENTITY_FIELDS = (
    "identityDisambiguator", "identity_disambiguator", "identity_context",
    "birthplace", "faction", "affiliation",
)


def _normalize_character_identity_name(value: Any) -> str:
    """Normalize CJK names deterministically without treating titles as identity."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"[\s\-_·・,，.。:：;；'\"“”‘’()（）\[\]{}<>《》]+", "", text)


def _character_names(entry: dict) -> tuple[str, set[str], set[str]]:
    canonical = _normalize_character_identity_name(entry.get("canonical_name") or entry.get("name"))
    aliases = {
        normalized for normalized in (
            _normalize_character_identity_name(alias) for alias in entry.get("aliases", [])
        ) if normalized
    }
    return canonical, aliases, ({canonical} if canonical else set()) | aliases


def _character_window_keys(entry: dict) -> set[str]:
    windows: set[str] = set()
    for field in ("window_id", "source_window_id"):
        value = str(entry.get(field) or "").strip()
        if value:
            windows.add(value)
    for field in ("window_ids", "source_window_ids"):
        values = entry.get(field, [])
        if isinstance(values, list):
            windows.update(str(value).strip() for value in values if str(value).strip())
    for note in entry.get("notes", []):
        if isinstance(note, str):
            windows.update(match.strip() for match in re.findall(r"\[window\s+([^\]]+)\]", note, re.IGNORECASE))
    return windows


def _character_evidence_keys(entry: dict) -> set[str]:
    """Return only provenance-shaped identity evidence, never prose similarity."""
    keys: set[str] = set()
    for field in _CHARACTER_EVIDENCE_FIELDS:
        value = entry.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not item:
                continue
            if isinstance(item, dict):
                for key in ("source_id", "sourceId", "evidence_id", "evidenceId", "id", "substring_hash", "raw_source_hash"):
                    token = str(item.get(key) or "").strip()
                    if token:
                        keys.add(f"{key}:{token}")
            elif isinstance(item, str) and field in {"source_evidence", "provenance"}:
                keys.add(f"{field}:{_normalize_character_identity_name(item)}")
    return keys


def _character_identity_conflicts(left: dict, right: dict) -> list[dict]:
    conflicts: list[dict] = []
    for field in _CHARACTER_IDENTITY_FIELDS:
        left_value = _normalize_character_identity_name(left.get(field))
        right_value = _normalize_character_identity_name(right.get(field))
        if left_value and right_value and left_value != right_value:
            conflicts.append({
                "field": field,
                "existing": left.get(field),
                "incoming": right.get(field),
                "resolution": "preserve_separate_candidates",
            })
    return conflicts


def _character_pair_match(left: dict, right: dict) -> tuple[list[str], list[dict]]:
    left_canonical, left_aliases, left_names = _character_names(left)
    right_canonical, right_aliases, right_names = _character_names(right)
    if not left_names or not right_names or not (left_names & right_names):
        return [], []

    conflicts = _character_identity_conflicts(left, right)
    if conflicts:
        return [], conflicts

    reasons: list[str] = []
    if left_aliases & right_names or right_aliases & left_names:
        reasons.append("shared_alias")
    left_evidence, right_evidence = _character_evidence_keys(left), _character_evidence_keys(right)
    if left_evidence & right_evidence:
        reasons.append("shared_source_evidence")
    if _character_window_keys(left) & _character_window_keys(right):
        reasons.append("overlapping_window")
    left_key = _normalize_character_identity_name(left.get("dedupeKey") or left.get("dedupe_key") or left.get("identity_key"))
    right_key = _normalize_character_identity_name(right.get("dedupeKey") or right.get("dedupe_key") or right.get("identity_key"))
    if left_key and left_key == right_key:
        reasons.append("shared_declared_identity_key")

    if left_canonical == right_canonical:
        # Same-name candidates are the normal cross-window case. They merge unless
        # explicit identity evidence proves they are separate people; absence of a
        # shared evidence-card ID is not evidence of separate identities.
        reasons.append("same_normalized_canonical_name")
    elif "shared_alias" not in reasons:
        return [], []
    return reasons, []


def _stable_value_union(*values: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in values:
        items = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
        for item in items:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                merged.append(item)
    return merged


def _merge_character_texts(*values: Any) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        for line in value.splitlines():
            cleaned = line.strip()
            key = _normalize_character_identity_name(cleaned)
            if cleaned and key not in seen:
                seen.add(key)
                lines.append(cleaned)
    return "\n".join(lines)


def _character_field_values(entry: dict, *fields: str) -> list[Any]:
    """Collect scalar/list field variants without letting an empty alias mask data."""
    return _stable_value_union(*(entry.get(field) for field in fields))


def _character_has_evidence(entry: dict) -> bool:
    return any(_character_field_values(entry, field) for field in _CHARACTER_EVIDENCE_FIELDS)


def _strip_note_provenance(note: str) -> str:
    return re.sub(r"^\s*\[(?:window|chunk)\s+[^\]]+\]\s*", "", note, flags=re.IGNORECASE).strip()


_BACKGROUND_NOTE_HINTS = (
    "出身", "家中", "家庭", "父", "母", "兄", "姐", "妹", "家族", "农家", "籍贯",
    "born", "raised", "family", "father", "mother", "sibling", "village", "hometown", "origin",
)
_BACKGROUND_SUMMARY_HINTS = _BACKGROUND_NOTE_HINTS + (
    "少年", "弟子", "学徒", "child", "student", "apprentice",
)
_EXPERIENCE_NOTE_HINTS = (
    "参加", "通过", "成为", "拜", "习得", "修炼", "获得", "捡到", "离开", "进入", "加入", "救", "战",
    "attend", "pass", "became", "joined", "learned", "trained", "obtained", "found", "left", "entered", "saved", "fought",
)


def _is_major_character(entry: dict) -> bool:
    importance = str(entry.get("importance", "")).strip().lower()
    role = " ".join(str(entry.get(field, "")) for field in ("role_in_story", "story_function")).lower()
    notes = _character_field_values(entry, "notes")
    return (
        importance in {"protagonist", "main", "core", "major"}
        or any(token in role for token in ("protagonist", "main character", "主角", "主人公"))
        or len(notes) >= 4
    )


def _normalize_character_profile_fields(entry: dict) -> dict:
    """Canonicalize profile variants and backfill only source-supported major fields."""
    normalized = dict(entry)
    experiences = _character_field_values(normalized, "experience", "experiences")
    if experiences:
        normalized["experience"] = experiences
    normalized.pop("experiences", None)

    traits = _character_field_values(normalized, "personality_traits", "traits")
    if traits:
        normalized["personality_traits"] = traits
    normalized.pop("traits", None)

    notes = _character_field_values(normalized, "notes")
    if notes:
        normalized["notes"] = notes

    evidence_refs = _character_field_values(normalized, "evidence_refs", "evidenceRefs")
    if evidence_refs:
        normalized["evidence_refs"] = evidence_refs
    normalized.pop("evidenceRefs", None)

    if not _is_major_character(normalized) or not _character_has_evidence(normalized):
        return normalized

    note_texts = [
        _strip_note_provenance(note) for note in notes
        if isinstance(note, str) and _strip_note_provenance(note)
    ]
    field_evidence = dict(normalized.get("profile_field_evidence", {}))
    evidence_for_backfill = _character_field_values(normalized, "evidence_refs", "evidence", "evidence_cards", "source_evidence", "source_span", "source_spans", "provenance")

    if not str(normalized.get("background", "")).strip():
        candidates = [note for note in note_texts if any(hint in note.lower() for hint in _BACKGROUND_NOTE_HINTS)]
        summary = str(normalized.get("summary", "")).strip()
        if not candidates and summary and any(hint in summary.lower() for hint in _BACKGROUND_SUMMARY_HINTS):
            candidates = [summary]
        if candidates:
            normalized["background"] = _merge_character_texts(*candidates)
            field_evidence["background"] = evidence_for_backfill

    candidates = [note for note in note_texts if any(hint in note.lower() for hint in _EXPERIENCE_NOTE_HINTS)]
    if candidates:
        normalized["experience"] = _stable_value_union(normalized.get("experience", []), candidates)
        field_evidence["experience"] = evidence_for_backfill

    if field_evidence:
        normalized["profile_field_evidence"] = field_evidence
    return normalized


def _character_quality_key(item: tuple[str, dict]) -> tuple[Any, ...]:
    _, entry = item
    canonical, _, _ = _character_names(entry)
    richness = sum(bool(entry.get(field)) for field in (
        "background", "experience", "experiences", "personality_traits", "traits", "notes", "evidence",
    ))
    first_seen = entry.get("first_seen_chunk", entry.get("chunk_id", 10**9))
    try:
        first_seen = int(first_seen)
    except (TypeError, ValueError):
        first_seen = 10**9
    stable_payload = {key: value for key, value in entry.items() if key not in {"canonical_id", "id"}}
    return (
        -float(entry.get("confidence", 0) or 0),
        -len(_character_evidence_keys(entry)),
        -richness,
        canonical,
        first_seen,
        min(_character_window_keys(entry), default=""),
        _sha256_text(json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, default=str)),
    )


def _merge_cross_window_characters(state: ImportSupervisorState) -> tuple[dict, dict]:
    """Merge only evidence-backed intra-import character duplicates before review."""
    registry = dict(state.get("entity_registry", {}))
    characters = {
        cid: dict(entry) for cid, entry in registry.get("characters", {}).items()
        if isinstance(entry, dict)
    }
    ids = list(characters)
    parents = {cid: cid for cid in ids}

    def find(cid: str) -> str:
        while parents[cid] != cid:
            parents[cid] = parents[parents[cid]]
            cid = parents[cid]
        return cid

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    pair_reasons: dict[tuple[str, str], list[str]] = {}
    pair_conflicts: dict[tuple[str, str], list[dict]] = {}
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1:]:
            reasons, conflicts = _character_pair_match(characters[left_id], characters[right_id])
            if reasons:
                pair_reasons[(left_id, right_id)] = reasons
                union(left_id, right_id)
            elif conflicts:
                pair_conflicts[(left_id, right_id)] = conflicts

    groups: dict[str, list[str]] = {}
    for cid in ids:
        groups.setdefault(find(cid), []).append(cid)

    merged_characters: dict[str, dict] = {}
    character_id_map: dict[str, str] = {}
    duplicate_candidates: list[dict] = []
    decisions: list[dict] = []
    for members in groups.values():
        ordered = sorted(((cid, characters[cid]) for cid in members), key=_character_quality_key)
        canonical_id, canonical = ordered[0]
        canonical_name, _, _ = _character_names(canonical)
        stable_key = f"character:{canonical_name}"
        merged = dict(canonical)
        merged["stable_dedupe_key"] = stable_key
        for _, duplicate in ordered[1:]:
            merged["aliases"] = _stable_value_union(
                merged.get("aliases", []), duplicate.get("canonical_name") or duplicate.get("name"), duplicate.get("aliases", []),
            )
            merged["background"] = _merge_character_texts(merged.get("background"), duplicate.get("background"))
            experiences = _stable_value_union(
                _character_field_values(merged, "experience", "experiences"),
                _character_field_values(duplicate, "experience", "experiences"),
            )
            if experiences:
                merged["experience"] = experiences
            traits = _stable_value_union(
                _character_field_values(merged, "personality_traits", "traits"),
                _character_field_values(duplicate, "personality_traits", "traits"),
            )
            if traits:
                merged["personality_traits"] = traits
            merged["notes"] = _stable_value_union(merged.get("notes", []), duplicate.get("notes", []))
            for field in _CHARACTER_EVIDENCE_FIELDS:
                evidence = _stable_value_union(merged.get(field), duplicate.get(field))
                if evidence:
                    merged[field] = evidence
            merged["confidence"] = max(float(merged.get("confidence", 0) or 0), float(duplicate.get("confidence", 0) or 0))
        merged = _normalize_character_profile_fields(merged)
        merged_characters[canonical_id] = merged
        for cid in members:
            character_id_map[cid] = canonical_id
        if len(members) > 1:
            merged_ids = [cid for cid, _ in ordered[1:]]
            reasons = sorted({
                reason for (left_id, right_id), values in pair_reasons.items()
                if left_id in members and right_id in members for reason in values
            })
            decision = {
                "contract": "EntityMergeDecision/v1",
                "scope": "intra_import",
                "canonical_id": canonical_id,
                "duplicate_ids": merged_ids,
                "stable_dedupe_key": stable_key,
                "match_reasons": reasons,
                "fields": {
                    "background": {"action": "evidence_append", "value": merged.get("background", "")},
                    "experience": {"action": "union", "value": merged.get("experience", [])},
                    "aliases": {"action": "union", "value": merged.get("aliases", [])},
                    "traits": {"action": "union", "value": merged.get("personality_traits", [])},
                    "notes": {"action": "union", "value": merged.get("notes", [])},
                    "confidence": {"action": "max", "value": merged.get("confidence", 0)},
                    "evidence": {"action": "union", "value": merged.get("evidence", [])},
                },
                "conflicts": [],
            }
            decisions.append(decision)
            duplicate_candidates.extend({
                "entity_type": "character",
                "canonical_id": canonical_id,
                "duplicate_id": duplicate_id,
                "stable_dedupe_key": stable_key,
                "reason": "+".join(reasons),
                "entity_merge_decision": decision,
            } for duplicate_id in merged_ids)

    semantic_conflicts: list[dict] = []
    for (left_id, right_id), conflicts in pair_conflicts.items():
        if character_id_map[left_id] != character_id_map[right_id]:
            semantic_conflicts.append({
                "entity_type": "character",
                "left_id": left_id,
                "right_id": right_id,
                "name": characters[left_id].get("canonical_name", ""),
                "reason": "conflicting_identity_disambiguator",
                "conflicts": conflicts,
                "resolution": "preserve_separate_candidates",
            })
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1:]:
            if character_id_map[left_id] == character_id_map[right_id]:
                continue
            left_canonical, _, _ = _character_names(characters[left_id])
            right_canonical, _, _ = _character_names(characters[right_id])
            if left_canonical and left_canonical == right_canonical:
                semantic_conflicts.append({
                    "entity_type": "character",
                    "left_id": left_id,
                    "right_id": right_id,
                    "name": characters[left_id].get("canonical_name", ""),
                    "reason": "same_normalized_name_without_identity_evidence",
                    "resolution": "preserve_separate_candidates",
                })

    registry["characters"] = merged_characters
    registry["intra_import_character_id_map"] = character_id_map
    def _remap_character_id(value: Any) -> Any:
        return character_id_map.get(str(value), value)

    def _remap_character_id_list(value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return _stable_value_union(*(_remap_character_id(item) for item in value))

    def _remap_character_references(record: dict) -> dict:
        updated = dict(record)
        for field in ("character_ids", "characterIds", "participantCharacterIds", "participant_character_ids"):
            if field in updated:
                updated[field] = _remap_character_id_list(updated[field])
        for field in (
            "character_id", "characterId", "sourceId", "targetId", "source_id", "target_id",
            "sourceCharacterId", "targetCharacterId", "source_character_id", "target_character_id",
            "source_candidate_id", "target_candidate_id",
        ):
            if field in updated:
                updated[field] = _remap_character_id(updated[field])
        return updated

    events = {
        event_id: _remap_character_references(event)
        for event_id, event in registry.get("events", {}).items() if isinstance(event, dict)
    }
    registry["events"] = events
    relationships = [
        _remap_character_references(relationship) if isinstance(relationship, dict) else relationship
        for relationship in state.get("relationships", [])
    ]
    raw_relationships = [
        _remap_character_references(relationship) if isinstance(relationship, dict) else relationship
        for relationship in state.get("raw_relationships", [])
    ]
    artifact = {
        "duplicate_candidates": duplicate_candidates,
        "character_merge_decisions": decisions,
        "semantic_conflicts": semantic_conflicts,
    }
    return {
        **state,
        "entity_registry": registry,
        "relationships": relationships,
        "raw_relationships": raw_relationships,
    }, artifact


async def reduce_entities(state: ImportSupervisorState) -> dict:
    """Deduplicate intra-import characters, then reconcile against canonical project data."""
    reduced_state, intra_import_artifact = _merge_cross_window_characters(state)
    result1 = await node_reconcile_entities(reduced_state)
    merged1 = {**reduced_state, **result1}
    result2 = await node_resolve_low_confidence(merged1)

    registry = result2.get("entity_registry") or result1.get("entity_registry") or reduced_state.get("entity_registry", {})
    chars = registry.get("characters", {})

    missing_groupkey = sum(1 for c in chars.values() if not c.get("groupKey") and not c.get("skip_create"))
    org_chars = sum(
        1 for c in chars.values()
        if "organization" in str(c.get("role_in_story", "")).lower() or
           str(c.get("importance", "")).lower() == "organization"
    )

    log = list(state.get("supervisor_log", []))
    log.append(
        f"reduce_entities: {len(chars)} chars total, {len(intra_import_artifact['duplicate_candidates'])} "
        f"cross-window merges, {missing_groupkey} missing groupKey, {org_chars} org-chars"
    )

    reducer_artifact = dict(result1.get("reducer_artifact", {}))
    reducer_artifact["duplicate_candidates"] = [
        *reducer_artifact.get("duplicate_candidates", []),
        *intra_import_artifact["duplicate_candidates"],
    ]
    reducer_artifact["character_merge_decisions"] = [
        *reducer_artifact.get("character_merge_decisions", []),
        *intra_import_artifact["character_merge_decisions"],
    ]
    reducer_artifact["semantic_conflicts"] = [
        *reducer_artifact.get("semantic_conflicts", []),
        *intra_import_artifact["semantic_conflicts"],
    ]
    if reduced_state.get("import_run_id"):
        _write_import_artifact(
            reduced_state["project_path"],
            reduced_state["import_run_id"],
            "reducer_artifact.json",
            reducer_artifact,
        )

    updates = {
        **result1,
        **result2,
        "relationships": result1.get("relationships", reduced_state.get("relationships", [])),
        "raw_relationships": result1.get("raw_relationships", reduced_state.get("raw_relationships", [])),
        "reducer_artifact": reducer_artifact,
        "supervisor_log": log,
        "current_stage": "reduce_entities",
    }
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


# ── Reviewer helpers ─────────────────────────────────────────────────────────────

def _collect_repair_proposals(reviewer_reports: dict, import_run_id: str) -> list[dict]:
    """Convert local_repair_actions from reviewer reports to Proposal-format dicts.

    Only actions that carry `proposed_operations` produce inbox proposals.
    Advisory-only actions (no `proposed_operations`) are skipped — they appear
    solely in the reviewer report written to the sidecar log.
    """
    import uuid as _uuid
    from datetime import datetime, timezone
    proposals = []
    for reviewer_kind, report in reviewer_reports.items():
        source = f"{reviewer_kind}_reviewer"
        run_id = f"{import_run_id}_{reviewer_kind}_review" if import_run_id else f"{reviewer_kind}_{_uuid.uuid4().hex[:8]}"
        for action in (report.get("local_repair_actions") or []):
            ops = action.get("proposed_operations") or []
            if not ops:
                continue  # advisory-only; not written to inbox
            primary_id = (action.get("target_entity_ids") or ["unk"])[0]
            entity_type = ops[0].get("entityType", "character")
            title = action.get("action_type", "repair").replace("_", " ").title()
            description = action.get("description", "")
            advisory = not action.get("deterministic", True)
            proposal: dict = {
                "id": f"repair_{primary_id}_{_uuid.uuid4().hex[:8]}",
                "title": title,
                "source": source,
                "originTaskRunId": run_id,
                "description": description,
                "preview": description[:200],
                "targetEntityType": entity_type,
                "targetEntityId": primary_id,
                "status": "pending",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "reviewPolicy": "manual_workbench",
                "proposedOperations": ops,
                "dependsOn": [],
                "data": {"reviewerRunId": run_id, "advisory": advisory},
            }
            proposals.append(proposal)
    return proposals


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

    log = list(state.get("supervisor_log", []))
    log.append(f"qa_review: status={report.get('status', '?')}, gate_failures={len(gate_failures)}, flags={flags}")

    # Run deterministic reviewers (zero-cost, no live API)
    from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer
    from sidecar.supervisor.reviewers.fact_reviewer import FactReviewer
    from sidecar.supervisor.reviewers.consistency_reviewer import ConsistencyReviewer

    quality_report = QualityReviewer().review(merged)
    fact_report = FactReviewer().review(merged)
    consistency_report = ConsistencyReviewer().review(merged)

    reviewer_reports = {
        "quality": quality_report,
        "fact": fact_report,
        "consistency": consistency_report,
    }
    log.append(
        f"reviewers: quality={quality_report.get('verdict')}, "
        f"fact={fact_report.get('verdict')}, consistency={consistency_report.get('verdict')}"
    )

    import_run_id = str(state.get("import_run_id") or "")
    repair_proposals = _collect_repair_proposals(reviewer_reports, import_run_id)

    # Push repair proposals to inbox if project context is available
    project_path = state.get("project_path")
    if project_path and repair_proposals:
        from sidecar.shared import s4_proposal_queue
        for proposal in repair_proposals:
            try:
                await s4_proposal_queue.push_to_inbox(proposal, str(project_path))
            except Exception:
                pass  # Non-blocking: repair proposals are advisory, never hard-fail import

    return {
        **result,
        "gate_failures": gate_failures,
        "supervisor_log": log,
        "reviewer_reports": reviewer_reports,
        "reviewer_repair_proposals": repair_proposals,
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

    # Result classification — softer than binary pass/fail
    profile = state.get("prompt_profile", "balanced")
    if state.get("budget_exhausted"):
        result_status = "budget_exhausted"
    elif passed:
        result_status = "passed"
    elif failed_gates == ["character_undercoverage"] and profile in ("fast", "balanced"):
        # Soft gate: character undercoverage alone is a warning for lower-granularity profiles
        result_status = "acceptable_with_warnings"
    elif len(failed_gates) == 1:
        result_status = "needs_review"
    else:
        result_status = "failed"

    artifact: JudgeArtifact = {
        "score": round(score, 3),
        "passed": passed,
        "result_status": result_status,
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

    # 4. Language field validation: strip Latin traits for zh source.
    # Strip threshold aligns with _symptom_flags detection: any trait with >=4 consecutive
    # Latin chars is flagged, so we must strip those to prevent gate false positives.
    source_lang = state.get("source_language", "en")
    latin_stripped = 0
    if source_lang == "zh":
        for cid, entry in chars.items():
            if entry.get("skip_create"):
                continue
            cleaned_traits = []
            for trait in entry.get("personality_traits", []):
                if isinstance(trait, str) and re.search(r"[A-Za-z]{4,}", trait):
                    latin_stripped += 1
                else:
                    cleaned_traits.append(trait)
            entry["personality_traits"] = cleaned_traits
        if latin_stripped:
            repair_log.append(f"language_validation: stripped {latin_stripped} Latin-dominant traits for zh source")

    # Tag name language validation for zh source
    tag_normalized = 0
    tag_rejections: list[dict] = list(state.get("tag_rejections", []))
    character_tags: list[dict] = []
    if state.get("character_tags"):
        character_tags = [dict(tag) for tag in state.get("character_tags", [])]
        if source_lang == "zh":
            normalized_tags: list[dict] = []
            for tag in character_tags:
                normalized, rejection = _normalize_character_tag(tag, source_lang)
                if rejection:
                    tag_rejections.append(rejection)
                    continue
                assert normalized is not None
                if normalized.get("name") != tag.get("name"):
                    tag_normalized += 1
                normalized_tags.append(normalized)
            character_tags = normalized_tags
        if tag_normalized or tag_rejections:
            repair_log.append(f"language_validation: translated {tag_normalized} tag names and rejected {len(tag_rejections)} unmapped tags for zh source")

    registry["characters"] = chars
    registry["world"] = world_map
    registry["world_detailed"] = world_detailed
    registry["events"] = events

    log = list(state.get("supervisor_log", []))
    log.append(f"minor_repair: groupKey={groupkey_fixed}, orgs_migrated={migrated}, resequenced={resequenced}, latin_stripped={latin_stripped}, tag_normalized={tag_normalized}, tag_rejections={len(tag_rejections)}")

    result = {
        "entity_registry": registry,
        "minor_repair_log": repair_log,
        "supervisor_log": log,
        "current_stage": "minor_repair",
        "tag_rejections": tag_rejections,
    }
    # Always write the normalized list. In zh mode this explicitly replaces a
    # fully rejected English set with [], so stale source tags cannot survive.
    result["character_tags"] = character_tags
    return result


# ── Tool: proposal_write ────────────────────────────────────────────────────────

def _normalize_character_profiles_for_proposal_write(entity_registry: Any) -> dict:
    """Apply evidence-gated character profile normalization at the write boundary."""
    registry = dict(entity_registry) if isinstance(entity_registry, dict) else {}
    characters = registry.get("characters", {})
    if not isinstance(characters, dict):
        return registry
    registry["characters"] = {
        character_id: (
            _normalize_character_profile_fields(character)
            if isinstance(character, dict)
            else character
        )
        for character_id, character in characters.items()
    }
    return registry


async def proposal_write(state: ImportSupervisorState) -> dict:
    """Run synthesis nodes then write proposals to the project."""
    # Write diagnostics BEFORE proposal write so they survive an OOM crash.
    # supervisor_decisions, window_metrics, and judge_artifact are complete by
    # this stage and will not change during the write phase.
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
        if state.get("import_granularity_profile"):
            _write_import_artifact(
                project_path, import_run_id, "import_granularity_profile.json",
                state.get("import_granularity_profile", {}),
            )
        if state.get("import_plan"):
            _write_import_artifact(
                project_path, import_run_id, "import_plan.json",
                state.get("import_plan", {}),
            )
        if state.get("import_plan_validation"):
            _write_import_artifact(
                project_path, import_run_id, "import_plan_validation.json",
                state.get("import_plan_validation", {}),
            )
        if state.get("prompt_policy_decision"):
            # Enrich the artifact with late-stage topology and reviewer signals
            # now that timeline_architecture and gate_failures are available.
            from sidecar.supervisor.prompt_policy import prompt_policy_decision as _ppd
            _ppd_base = state["prompt_policy_decision"]
            _ppd_patch = (_ppd_base.get("prompt_policy_patch") or {})
            _ppd_enriched = _ppd(
                state.get("source_profile"),
                _ppd_patch,
                topology_signals=state.get("timeline_architecture"),
                reviewer_feedback=state.get("gate_failures"),
            )
            _write_import_artifact(
                project_path, import_run_id, "prompt_policy_decision.json",
                _ppd_enriched,
            )
        if state.get("planner_proposal"):
            _write_import_artifact(
                project_path, import_run_id, "planner_proposal.json",
                state.get("planner_proposal", {}),
            )
        if state.get("planner_proposal_validation"):
            _write_import_artifact(
                project_path, import_run_id, "planner_proposal_validation.json",
                state.get("planner_proposal_validation", {}),
            )
        if state.get("source_profile"):
            _write_import_artifact(
                project_path, import_run_id, "source_profile.json",
                state.get("source_profile", {}),
            )
        _write_import_artifact(
            project_path, import_run_id, "extraction_prompt_variants.json",
            _selected_extraction_prompt_manifest(state),
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

    try:
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
    finally:
        from sidecar.workflows.w1_import import persist_w1_usage_ledger
        persist_w1_usage_ledger(state)

    # Synthesis can replace registry entries after reducer/minor-repair. Normalize
    # once at the authoritative proposal boundary so the review registry and write
    # payload retain evidence-backed character background and experience fields.
    merged["entity_registry"] = _normalize_character_profiles_for_proposal_write(
        merged.get("entity_registry", {})
    )

    # The supervisor owns five domain calls per prompt window, rather than the
    # legacy ``chunk_extractions`` list. Preserve a compact, domain-level
    # receipt for the semantic gate before releasing prompt windows/metrics.
    # A receipt is emitted only for calls that actually completed; an absent or
    # failed window remains unknown/failed at the W1 boundary.
    supervisor_semantic_receipts: list[dict[str, Any]] = []
    metrics_by_window = state.get("window_metrics", {})
    for window in state.get("prompt_windows", []):
        if not isinstance(window, dict):
            continue
        window_id = str(window.get("id") or "")
        metrics = metrics_by_window.get(window_id) if isinstance(metrics_by_window, dict) else None
        if not isinstance(metrics, dict):
            continue
        failed_labels = {
            str(item).split(":", 1)[0].strip()
            for item in metrics.get("failed_prompts", [])
            if str(item).strip()
        }
        for chunk_id in window.get("chunk_ids", []) or []:
            supervisor_semantic_receipts.append({
                "chunk_id": chunk_id,
                "window_id": window_id,
                "domain_status": {
                    "characters": "failed" if "character" in failed_labels else "complete",
                    "events": "failed" if "event" in failed_labels else "complete",
                    "world": "failed" if "world" in failed_labels else "complete",
                    "relationships": "failed" if "relationship" in failed_labels else "complete",
                    "scenes": "failed" if "scene" in failed_labels else "complete",
                },
                "completion_evidence": {
                    "contract": "w1-supervisor-window-receipt/v1",
                    "failed_prompts": sorted(failed_labels),
                    "window_gate_passed": bool(metrics.get("gate_passed")),
                },
            })

    # Build a slim write_input — only the keys node_write_to_project actually reads.
    # Evict everything else (timeline_architecture, prompt_windows, supervisor_decisions,
    # window_metrics, chunks, cross_validation) so GC can reclaim their pages
    # before the 400+ sequential propose_write() calls that follow.
    _WRITE_KEYS = frozenset({
        "entity_registry", "manuscript_chapters", "timeline_branches",
        "chunk_extractions", "project_path", "import_run_id", "source_file_path",
        "import_review_report", "import_mode", "source_language", "relationships",
        "character_tags", "world_settings", "world_containers",
        "workflow_id", "context", "errors", "checkpoint_path",
        "supervisor_semantic_receipts",
    })
    merged["supervisor_semantic_receipts"] = supervisor_semantic_receipts
    write_input = {k: merged[k] for k in _WRITE_KEYS if k in merged}
    del merged

    import gc
    gc.collect()

    write_result = await node_write_to_project(write_input)
    del write_input

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
    # Evict large blobs so the router/status-polling state stays compact.
    return_dict.pop("entity_registry", None)
    return_dict.pop("cross_validation", None)
    return return_dict
