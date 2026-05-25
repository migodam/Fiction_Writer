# W1 P0 Proposal OOM / Write Stability

**Date:** 2026-05-25  
**Branch:** `codex/w1-closure-p0-proposal-oom`  
**Issue:** 50-chapter run (`sup_2d42990ac3`) killed by macOS OOM during `proposal_write` after 21 minutes. All diagnostic artifacts lost.

## Root Causes

1. `node_write_to_project` accumulated full proposal return dicts in `proposals: list[dict]` while holding entity_registry + timeline_architecture + all window extractions in memory simultaneously — monotonic growth.
2. Diagnostic artifact writes (`supervisor_decisions.json`, `window_metrics.json`, `cross_validation.json`) happened AFTER `node_write_to_project`, so an OOM crash left no diagnostics.
3. World entity inflation: 366 world entities across 50 chapters with no per-chapter cap.
4. `asyncio.gather(return_exceptions=True)` silently returned `{}` for failed coroutines.

## Changes

### `sidecar/supervisor/tools.py`

- **`proposal_write`**: Moved all `_write_import_artifact` calls (supervisor_decisions, window_metrics, tool_operating_spec, judge_artifact, cross_validation) to BEFORE `node_build_manuscript`. Added `return_dict.pop("entity_registry", None)` and `pop("cross_validation", None)` to evict large state from the return dict.
- **`extract_window`**: Added explicit print on exception for each failed coroutine (visible OOM post-mortem). No architecture change — silent swallowing addressed in P0 follow-up.
- **`extract_window` world cap**: The existing TOS-based cap (`max_world_entities_per_chapter`, default 5) already limits per-window world entity inflation. Tests confirm 20/chapter behavior when TOS is set accordingly.

### `sidecar/workflows/w1_import.py`

- **`node_write_to_project`**: Replaced `proposals: list[dict]` accumulator with `receipts: list[dict]` compact receipts (`id`, `entity_type`, `status`, `confidence`, `blocked` — no `operations`). Full proposal dicts are GC-eligible immediately after each `propose_write` call.
- Added `registry.pop("characters")` / `pop("events")` / `pop("world")` / `pop("world_detailed")` after each write group finishes to free memory progressively.
- Rewrote `review_report` computation from receipts instead of full proposals.
- Added progress print statements (`[proposal_write] writing N character proposals...`).

### `tests/test_w1_supervisor_tools.py`

- `TestProposalWriteEarlyArtifacts`: verifies all four diagnostic artifacts are written before `MemoryError` from `node_write_to_project`.
- `TestProposalWriteCompactReturn`: verifies `entity_registry` not in returned dict.
- `TestWorldEntityCapInExtractWindow`: verifies TOS cap at 20/chapter (60 → ≤40; 10 → exactly 10).

### `tests/test_w1_import_compiler.py`

- `TestNodeWriteToProjectCompactReceipts`: verifies receipts have `id` + `entity_type` but no `operations`.
- `TestNodeWriteToProjectManuscriptStillWritten`: verifies `manuscript.json` written with correct chapters.
- Updated `test_character_card_proposals_stay_slim_by_default` to use op-capture closure instead of inspecting result proposals.

## Test Results

```
64 passed in 0.59s
```

All 64 tests pass (57 existing + 7 new).

## Artifact Write Sequence (post-fix)

| Artifact | When written |
|----------|-------------|
| `supervisor_decisions.json` | Start of `proposal_write` (before OOM risk) |
| `window_metrics.json` | Start of `proposal_write` |
| `judge_artifact.json` | Start of `proposal_write` (if present) |
| `cross_validation.json` | Start of `proposal_write` (if present) |
| `tool_operating_spec.json` | Start of `proposal_write` |
| `inbox.json` | Via `propose_write` inside `node_write_to_project` |
| `manuscript.json` | Inside `node_write_to_project` |
| `review_report.json` | Inside `node_write_to_project` |

## Remaining Risk

- If entity_registry exceeds ~500 entities or world entities exceed TOS cap, memory pressure can reappear. The architectural fix (streaming receipts from `extract_window` via `write_proposal` tool) is tracked as P0 follow-up, separate branch, ~2-day scope.
- `asyncio.gather` silent swallowing (P2): failures now print to stdout but still return `{}` — architectural fix deferred.
- Chapter ordering in `manuscript.json`: `chapter_order` field was unknown due to OOM on prior run. Will be verifiable on next full 50-chapter benchmark run.
