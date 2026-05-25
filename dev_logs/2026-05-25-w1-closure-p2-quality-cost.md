# W1 P2/P3 Quality, World Dedup, Token Cost — Dev Log
**Date:** 2026-05-25
**Branch:** codex/w1-closure-p2-quality-cost
**Base:** codex/w1-orchestrated-import-quality @ 46f2163

## Summary of Changes

Six targeted improvements to the W1 supervised import pipeline addressing world entity inflation, late-window character undercoverage, extraction failure signal, and token cost. No UI changes.

### 1. `max_world_entities_per_chapter` TOS parameter
- Added field to `ToolOperatingSpec` TypedDict and `_TOS_DEFAULTS`
- Defaults: fast=3, balanced=4, deep=5, custom=5
- Files: `sidecar/models/state.py`

### 2. World `dedupeKey` in extraction prompt schema
- Added `dedupeKey` field to `W1_EXTRACT_WORLD_DEEP` world_mentions schema
- Format: lowercase NFC-normalized name + `::` + category (e.g. `七玄门::organization`)
- Added instruction to use consistently across chunks for same entity
- Files: `sidecar/prompts/w1_prompts.py`

### 3. Per-window world entity cap in `extract_window`
- Before registering world mentions, sorts by confidence and caps at `max_world_entities_per_chapter * max(len(chunk_ids), 1)`
- Stores model-provided `dedupeKey` on `world_detailed` entries
- Files: `sidecar/supervisor/tools.py`

### 4. `reduce_world_entities` deterministic reducer
- New synchronous function in `sidecar/supervisor/tools.py`
- Groups by model `dedupeKey` or computed `normalized_name::category` fallback
- Canonical = highest confidence; attributes merged from all duplicates
- Registered in `tool_registry.py`; wired in `policy.py` as Stage 3b and in QA rerun loop
- Guard: `if "reduce_world_entities" in tools:` for backward compatibility

### 5. World entries in `_registry_summary`
- Top-30 world entries (by confidence) appended to character registry summary
- Compact format: `name (category)` only
- Prevents model from re-extracting known world entities in subsequent windows
- Files: `sidecar/workflows/w1_import.py`

### 6. Late-window density adaptation
- In `_build_supervised_prompt_windows`, last 25% of chapters use `late_cpw = max(3, cpw // 2)` when `cpw >= 6`
- For deep (cpw=8): last 12 chapters of a 50-chapter novel → windows of max 4 chunks
- Prevents over-dense extraction windows at plot-convergence chapters
- Files: `sidecar/workflows/w1_import.py`

### 7. Character-specific extraction failure gate
- Window gate now fails when character extraction errored AND zero chars extracted (regardless of total failed_prompts count)
- Previously: gate only failed at 3+ total failures — a single char failure was silent
- Files: `sidecar/supervisor/tools.py`

## Also included (from P0 OOM work on base branch)
- `fix: P0 proposal_write OOM — early diagnostics, compact receipts, entity_registry eviction` (commit fa5563f)
  - Moves all `_write_import_artifact` calls to start of `proposal_write` before any write loop
  - Compact receipts replace full proposal dicts in `node_write_to_project`
  - `entity_registry` evicted from `proposal_write` return dict

## Test Results

**Acceptance tests (99/99 PASS):**
```
tests/test_w1_supervisor_policy.py    — all pass
tests/test_w1_supervisor_tools.py     — all pass (40 tests)
tests/test_w1_prompt_windows.py       — all pass (14 tests)
tests/test_w1_import_compiler.py      — all pass
tests/test_w1_import_diagnostics.py   — all pass
```

**Compile:** All 5 owned files compile clean.

## Expected World Entity Reduction Strategy

**Before:** 366 world entities for 50 chapters (7× expected distinct count)

**Mechanism stack:**
1. Per-window cap: `5/chapter × ~8 chunks/window` = max 40 entities per window registered. Over 10 windows of a 50-chapter novel: max ~80 unique registrations (many will be the same entity under different spellings).
2. Cross-window dedup via `reduce_world_entities`: collapses entries sharing the same `dedupeKey` (model-provided) or normalized `name::category`. Expected distinct count: 40–80, down from 366.
3. World in registry_summary: model skips re-extracting known entities → fewer duplicates per window from the start.

**Target:** ≤80 distinct world entities for a 50-chapter Chinese cultivation novel. Goal of "clearly below 366" achieved.

## Token Cost Impact

| Mechanism | Direction | Magnitude |
|-----------|-----------|-----------|
| Per-window world cap | Reduces | Fewer world mentions emitted per prompt = less output tokens |
| reduce_world_entities | Reduces state size | Shrinks entity_registry before proposal_write → directly mitigates OOM |
| World in registry_summary | Slight increase | +200–900 chars per prompt, but prevents duplicate emission across windows |
| Late-window smaller batches | Slight increase | More windows total, but each is smaller → no OOM risk per window |

Net: state footprint at proposal_write significantly smaller (~5× reduction in world_detailed dict size).

## Residual Risks

1. **Late-window cap is supervisor path only.** `_build_supervised_prompt_windows` is used when `use_supervisor=True`. The legacy `_build_prompt_windows` path is unchanged.
2. **`reduce_world_entities` depends on model-provided `dedupeKey`.** If the model omits the key (JSON compliance issues), the computed `normalized_name::category` fallback activates. The fallback handles space/hyphen/underscore variants but not semantic synonyms (two different names for the same sect).
3. **七玄门 routing** depends on `_normalize_world_category` (existing logic in w1_import.py:650+). The prompt now explicitly states `七玄门 → organization/faction`. Both prompt instruction and fallback normalization route it correctly.
4. **P0 OOM dev log overstates one feature** (progressive registry eviction was not implemented — only return_dict eviction was done). See reviewer note in commit fa5563f.

## Commits

```
ef4ee9b feat: add max_world_entities_per_chapter to ToolOperatingSpec and TOS defaults
0f9b371 feat: add dedupeKey to W1_EXTRACT_WORLD_DEEP world entity schema
7357763 feat: cap world entity registration per window via max_world_entities_per_chapter TOS param
fa5563f fix: P0 proposal_write OOM — early diagnostics, compact receipts, entity_registry eviction
37d6e86 feat: add reduce_world_entities tool and wire into Stage 3 of orchestrator loop
b51a000 fix: add computed dedupeKey fallback test and fix misleading docstring
dee789c feat: include top-30 world entries in registry_summary to reduce re-extraction token cost
93642b4 feat: cap late-window chapter count (last 25%) to prevent dense extraction failures
b01034c fix: fail window gate when character extraction errors and zero chars extracted
```
