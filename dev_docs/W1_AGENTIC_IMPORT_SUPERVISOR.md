# W1 Agentic Import Supervisor

## Why

The static LangGraph pipeline (`run_streaming`, `use_supervisor=False`) packs all chapters into one prompt window. With `ChatOpenAI(max_tokens=4096)` and a 50-chapter novel this produces ~26 000 output tokens needed but only 4 096 available — resulting in 24 characters instead of 50+, 10 events instead of 40+.

The supervisor works around this by splitting the manuscript into small windows, extracting and validating each window independently, and re-running windows that fail quality gates.

---

## Activation

Set `use_supervisor=True` in the W1 start request. The default is `False` — the legacy LangGraph path is untouched.

```json
POST /workflow/w1/start
{ "use_supervisor": true, "prompt_profile": "deep", ... }
```

Or from the Zustand store: `setW1UseSupervisor(true)` before `startImport`.

---

## Tool Registry (11 tools)

All tools are in `sidecar/supervisor/tools.py` and registered in `sidecar/supervisor/tool_registry.py`.

| Tool | Stage | Side-effects |
|------|-------|-------------|
| `segment_manifest` | 1 | Builds `prompt_windows` from chunks using `_build_supervised_prompt_windows`. Idempotent (skips if windows exist). |
| `extract_window` | 2 | 5-parallel LLM calls (characters, events, world, relationships, scene). Merges into `entity_registry`. Records `WindowExtractionMetrics`. Injects `source_language_label` and `language_policy` into all five deep extraction prompts. |
| `cross_validate_window` | 2 | Checks each window's characters against the full registry. Sets `missing_majors`. |
| `rerun_window` | 2 (conditional) | strategy=`split` halves chunk count and re-runs extract; strategy=`augment` injects `SUPERVISOR_HINT` with missing names. |
| `reduce_entities` | 3 | Deduplicates characters/events via `node_reconcile_entities` + `node_resolve_low_confidence`. |
| `reduce_world_entities` | 3b | Deterministic deduplication of world entries cross-window. Groups `world_detailed` entries by model-provided `dedupeKey` or computed `normalized_name::category` key. Picks highest-confidence entry as canonical per group; merges attributes from all duplicates. Synchronous (no LLM call). Logs merge count to `supervisor_log`. |
| `minor_repair` | 4 | Deterministic fixes: groupKey normalization, world/person boundary migration, orderIndex resequencing, Latin trait strip for zh source. Strip threshold aligned with `_symptom_flags` detection (≥4 consecutive Latin chars). |
| `architect_timeline` | 5 | Calls `node_architect_timeline`. |
| `qa_review` | 6 | Calls `node_review_import`. Sets `gate_failures`. |
| `judge_import` | 6b | Deterministic convergence judge. Writes `JudgeArtifact`, emits thematic rerun requests, and never writes canonical proposals. |
| `proposal_write` | 7 | Writes diagnostic artifacts first (crash-safe), then runs synthesis nodes and `node_write_to_project`. Returns compact receipts (no full proposal dicts). Evicts `entity_registry` from return state. |

---

## Language Policy

All five deep extraction prompts (`W1_EXTRACT_CHARACTERS_DEEP`, `W1_EXTRACT_EVENTS_DEEP`, `W1_EXTRACT_WORLD_DEEP`, `W1_EXTRACT_RELATIONSHIPS_CHUNK`, `W1_EXTRACT_SCENE_SUMMARIES`) require two template variables at call time:

| Variable | Source | Example (zh) |
|----------|--------|--------------|
| `source_language_label` | `"Chinese (Simplified)" if source_language == "zh" else "English"` | `"Chinese (Simplified)"` |
| `language_policy` | `tool_operating_spec.get("language_policy", "preserve_source")` | `"normalize_to_source"` |

Valid `language_policy` values: `preserve_source` \| `normalize_to_source` \| `allow_mixed`. Default is `preserve_source`.

These are injected in `extract_window` (supervisor path) and `node_process_chunks` (legacy LangGraph path). Both paths derive `source_language` from `state["source_language"]`.

Fields that intentionally remain in English (enum/internal keys): `eventClass`, `timelineClass`, `eventType`, `arcRole`, `causalRole`, `branchRole`, `forkMergeHint`, `arcId`, `category`, `importance`, `story_function`, `groupKey`, `directionality`, `status`, `topologyRole`, `container_hint`.

---

## Policy Loop (`sidecar/supervisor/policy.py`)

```
run_supervisor_streaming(project_path, config)   ← async generator (same interface as run_streaming)
  └── node_validate_file(state)
  └── node_split_chunks(state)                   ← uses _build_supervised_prompt_windows
  └── run_supervisor_policy(state, tools)
        1. segment_manifest(state)
        2. FOR windows in batches of 3:
             extract_window(state, wid)
             IF validation_strictness != "off":
               cross_validate_window(state, wid)
             EVALUATE gate (char_density, event_density, failed_prompts)
             IF gate fails AND rerun_count < max_rerun_iterations:
               strategy = "split" if can_split else "augment"
               rerun_window(state, wid, strategy, missing_names)
        3. reduce_entities(state)
        4. minor_repair(state)
        5. architect_timeline(state)
        6. qa_review(state)
           IF gate_failures AND supervisor_iteration < max_supervisor_iterations:
             rerun failing windows → back to 3
        7. judge_import(state)  → emits result_status, rerun_cap_reached
           IF budget_exhausted: SKIP all reruns
           IF thematic_rerun_requests AND rerun_budget remains AND waves < thematic_rerun_wave_cap:
             rerun targeted windows with soft parameter overrides → reduce/repair/architect/QA/judge
             waves_applied += 1
           IF waves_applied >= thematic_rerun_wave_cap: set rerun_cap_reached=True in JudgeArtifact
        8. proposal_write(state)
```

---

## ToolOperatingSpec, ConvergeTarget, and JudgeArtifact

Before the supervisor policy loop runs, `_ensure_orchestrator_plan()` performs three steps:
1. `plan_tool_operating_spec()` — derives `ToolOperatingSpec` from `prompt_profile`, `source_language`, chapter count, and optional `context.tool_operating_spec_overrides`.
2. `select_granularity_profile()` — selects an `ImportGranularityProfile` based on chapter count, source language, and prompt profile. Stored as `state["import_granularity_profile"]`. Decision rules: fast→coarse; CJK >30ch→coarse_webnovel; non-CJK >30ch→balanced_novel (relaxed floor); 15–30ch→balanced_novel; ≤15ch→fine_short_story.
3. `plan_converge_target(..., granularity_profile=...)` — builds `ConvergeTarget` using the selected granularity profile to override character and event density targets.

This means converge targets for a 50-chapter Chinese webnovel use `coarse_webnovel` (`min_characters_per_chapter=1.0`), not the TOS deep default of 1.5, giving `expected_min_characters=50` instead of 75.

Deep and Custom profiles default to orchestrator/supervisor behavior. Fast and Balanced stay lighter unless `use_supervisor` or `use_orchestrator` is explicitly enabled.

The deterministic judge emits `JudgeArtifact` with:
- `score`, `passed`, `result_status`, `failed_gates`
- `thematic_rerun_requests`
- `iteration`, `metrics_snapshot`, `rationale`
- `rerun_cap_reached` (bool) — True when thematic wave cap is hit
- optional `artifact_paths`

`result_status` four-tier classification:
| Status | Condition |
|--------|-----------|
| `passed` | All gates pass |
| `acceptable_with_warnings` | Only `character_undercoverage` failed, profile is `fast` or `balanced` |
| `needs_review` | Exactly 1 non-trivial gate failed |
| `failed` | 2+ gates failed |
| `budget_exhausted` | API 402 Insufficient Balance detected — no reruns attempted |

Thematic rerun themes are:
- `character_undercoverage`
- `timeline_undercoverage`
- `world_boundary`
- `language_mismatch`

The orchestrator may plan soft parameters and request bounded reruns. It must not write canonical proposals or bypass reducer/repair/timeline/review validators.

---

## Gate Thresholds

| Gate | Metric | Threshold | Action |
|------|--------|-----------|--------|
| `char_density` | `char_count / chapter_count` | `< ToolOperatingSpec.min_characters_per_chapter` | split (if >1 chunk) or augment |
| `event_density` | `event_count / chapter_count` | `< ToolOperatingSpec.event_density_target` | augment |
| `failed_prompts` | `len(failed_prompts)` | ≥ 3 | augment |
| `output_budget` | `chapters × 650 tokens` | > 3 500 | preemptive split in `segment_manifest` |

---

## Extraction Variant Dispatch

`extract_window` selects per-domain extraction prompts based on `state["import_granularity_profile"]` (type `ImportGranularityProfile`, optional). If the profile is absent or a field is unset, the original constant is used.

| Field | Value → Variant constant |
|-------|--------------------------|
| `character_granularity` | `major_only` → `W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL` / `named_only` → `BALANCED` / `all` → `FINE` / absent → `W1_EXTRACT_CHARACTERS_DEEP` |
| `event_density` | `arc_level` → `ARC` / `chapter_level` → `CHAPTER` / `scene_level` → `DENSE` / absent → `W1_EXTRACT_EVENTS_DEEP` |
| `world_density` | `named_only` → `SPARSE` / `structural` → `STRUCTURAL` / `full_lore` → `LORE` / absent → `W1_EXTRACT_WORLD_DEEP` |
| `relationship_depth` | `core` → `CORE` / `recurring` → `RECURRING` / `dense` → `DENSE` / absent → `W1_EXTRACT_RELATIONSHIPS_CHUNK` |

The profile is populated by the Orchestrator before extraction begins. Scene summaries are not dispatched.

---

## Profile Config Dimensions

| Dimension | fast | balanced | deep |
|-----------|------|----------|------|
| `character_granularity` | major_only | named_only | all |
| `event_density` | arc_level | chapter_level | chapter_level |
| `validation_strictness` | off | per_window | per_window |
| `chapters_per_window` | 20 | 12 | 8 |
| `max_rerun_iterations` | 1 | 2 | 2 |
| `max_world_entities_per_chapter` | 3 | 4 | 5 |
| `thematic_rerun_wave_cap` | 0 | 1 | 1 |
| `output_token_budget` | 3 000 | 3 000 | 3 000 |
| `input_window_budget` | 64 000 | 48 000 | 32 000 |

---

## Windowing Math

```
estimated_output_tokens(window) = len(chunk_ids) × 650
  where 650 = 1.5 chars × 120 + 3 events × 80 + 2 world × 50

if estimated > 3 500:
    recursively halve chunk_ids (up to 4 iterations)
```

`_build_supervised_prompt_windows` in `w1_import.py` groups chunks by `chapters_per_window` from the profile, then applies the output budget pre-flight split.

**Late-window density cap:** For chunks in the last 25% of total chapters, `effective_chapters_per_window` is capped at `max(3, chapters_per_window // 2)` when `chapters_per_window >= 6`. This prevents over-dense windows at plot-convergence chapters where extraction complexity increases. For `deep` profile (cpw=8): last 25% → windows of max 4 chapters. For `balanced` (cpw=12): last 25% → windows of max 6 chapters.

---

## Artifact Paths

All artifacts land under `<project_path>/system/imports/<import_run_id>/`:

| File | When written | Contents |
|------|-------------|---------|
| `prompt_windows.json` | `segment_manifest` | Final window manifest (text hash, chunk_ids, chapter_range) |
| `project_structure_digest.json` | `segment_manifest` | Digest used for character card compaction |
| `supervisor_decisions.json` | **Start of `proposal_write`** (before OOM risk) | All supervisor routing decisions |
| `window_metrics.json` | **Start of `proposal_write`** (before OOM risk) | Per-window extraction quality metrics |
| `tool_operating_spec.json` | **Start of `proposal_write`** (before OOM risk) | Planned soft parameters for this import run |
| `judge_artifact.json` | **Start of `proposal_write`** (before OOM risk, if present) | Final deterministic convergence judgment |
| `cross_validation.json` | **Start of `proposal_write`** (before OOM risk, if present) | Cross-window entity validation results |
| `inbox.json` | Inside `node_write_to_project` | Per-entity `propose_write` proposals (gated) |
| `manuscript.json` | Inside `node_write_to_project` | Ordered chapter content |
| `review_report.json` | Inside `node_write_to_project` | Proposal counts, blocked IDs, safe-accept IDs |

---

## Status Endpoint

```
GET /workflow/w1/supervisor_status?session_id=<id>
→ { supervisor_decisions, gate_failures, window_metrics, supervisor_iteration, current_tool, current_window, chapter_range, orchestrator_phase, judge_score, rerun_reason, converge_status, judge_artifact }
```

---

## Cost Protection

### API 402 Hard Stop

`_is_budget_exhausted_error(exc)` in `tools.py` detects HTTP 402 / "insufficient balance" from any OpenAI-compatible provider (DeepSeek, OpenAI). When detected:
1. `extract_window` sets `budget_exhausted=True` and writes a clear error to `errors[]`.
2. `_process_window` exits immediately — no cross-validation, no per-window reruns.
3. `run_supervisor_policy`/`_policy_with_progress` breaks out of the extraction batch loop.
4. `_apply_thematic_reruns` returns immediately without firing any rerun.
5. `JudgeArtifact.result_status` is set to `"budget_exhausted"`.

**Effect:** A 402 on window N stops extraction of windows N+1, N+2, … and prevents thematic reruns. 148 wasted API calls (from the May 26 run 4 incident) cannot recur.

### Thematic Rerun Wave Cap

`thematic_rerun_wave_cap` in `ToolOperatingSpec` (defaults: fast=0, balanced=1, deep=1) limits the number of judge+thematic-rerun cycles. Each cycle:
1. Applies up to `rerun_budget` targeted reruns.
2. Runs reduce → repair → architect → qa → judge.
3. Increments `waves_applied`.

When `waves_applied >= wave_cap`, the loop exits even if the judge still fails. `JudgeArtifact.rerun_cap_reached=True` is set. For `deep` profile the default is 1 wave — meaning at most 1 thematic repair pass before proceeding to `proposal_write`.

### Benchmark One-Shot Guard

When running a validation benchmark (full 50-chapter import):
- **Run at most one full-50 attempt per API balance top-up.**
- If the run fails with 402, stop immediately. Do not start another run. Report in dev log.
- If the run fails with code errors (not 402), fix the code on a new branch. One targeted smoke run (10 chapters) to validate the fix, then one full-50 run.
- **Do not modify product code during a benchmark validation run.**
- Do not start a second full-50 run without explicit approval from Codex.

Expected cost per full-50 deep run: ~1–2 hours of DeepSeek V4 Pro. Ensure ≥ 3× balance before starting.

## Non-goals

- Does not replace the LangGraph graph (`use_supervisor=False` default is unchanged).
- Does not modify `content_only` import mode (supervisor early-returns to legacy path).
- No UI toggle component yet — `w1UseSupervisor` is in Zustand store but no UI element is wired.
