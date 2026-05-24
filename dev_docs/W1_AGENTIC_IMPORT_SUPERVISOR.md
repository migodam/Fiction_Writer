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

## Tool Registry (9 tools)

All tools are in `sidecar/supervisor/tools.py` and registered in `sidecar/supervisor/tool_registry.py`.

| Tool | Stage | Side-effects |
|------|-------|-------------|
| `segment_manifest` | 1 | Builds `prompt_windows` from chunks using `_build_supervised_prompt_windows`. Idempotent (skips if windows exist). |
| `extract_window` | 2 | 5-parallel LLM calls (characters, events, world, relationships, scene). Merges into `entity_registry`. Records `WindowExtractionMetrics`. |
| `cross_validate_window` | 2 | Checks each window's characters against the full registry. Sets `missing_majors`. |
| `rerun_window` | 2 (conditional) | strategy=`split` halves chunk count and re-runs extract; strategy=`augment` injects `SUPERVISOR_HINT` with missing names. |
| `reduce_entities` | 3 | Deduplicates characters/events via `node_reconcile_entities` + `node_resolve_low_confidence`. |
| `minor_repair` | 4 | Deterministic fixes: groupKey normalization, world/person boundary migration, orderIndex resequencing, Latin trait strip for zh source. |
| `architect_timeline` | 5 | Calls `node_architect_timeline`. |
| `qa_review` | 6 | Calls `node_review_import`. Sets `gate_failures`. |
| `proposal_write` | 7 | Calls `node_write_to_project` + `node_build_manuscript`. |

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
        7. proposal_write(state)
```

---

## Gate Thresholds

| Gate | Metric | Threshold | Action |
|------|--------|-----------|--------|
| `char_density` | `char_count / chapter_count` | < 0.5 | split (if >1 chunk) or augment |
| `event_density` | `event_count / chapter_count` | < 0.5 | augment |
| `failed_prompts` | `len(failed_prompts)` | ≥ 3 | augment |
| `output_budget` | `chapters × 650 tokens` | > 3 500 | preemptive split in `segment_manifest` |

---

## Profile Config Dimensions

| Dimension | fast | balanced | deep |
|-----------|------|----------|------|
| `character_granularity` | major_only | named_only | all |
| `event_density` | arc_level | chapter_level | chapter_level |
| `validation_strictness` | off | per_window | per_window |
| `chapters_per_window` | 20 | 12 | 8 |
| `max_rerun_iterations` | 1 | 2 | 2 |
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

---

## Artifact Paths

All artifacts land under `<project_path>/system/imports/<import_run_id>/`:

| File | Contents |
|------|---------|
| `prompt_windows.json` | Final window manifest (text hash, chunk_ids, chapter_range) |
| `project_structure_digest.json` | Digest used for character card compaction |
| `supervisor_decisions.json` | Written by `proposal_write` from `state["supervisor_decisions"]` |
| `window_metrics.json` | Written by `proposal_write` from `state["window_metrics"]` |

---

## Status Endpoint

```
GET /workflow/w1/supervisor_status?session_id=<id>
→ { supervisor_decisions, gate_failures, window_metrics, supervisor_iteration }
```

---

## Non-goals

- Does not replace the LangGraph graph (`use_supervisor=False` default is unchanged).
- Does not modify `content_only` import mode (supervisor early-returns to legacy path).
- No UI toggle component yet — `w1UseSupervisor` is in Zustand store but no UI element is wired.
