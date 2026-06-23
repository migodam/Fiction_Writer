# W7 QA Follow-up Addendum — Codex

**Date:** 2026-06-05  
**Scope:** Close W7-reported QA-01 / QA-05 stale fixture gap.

## Summary

Worker W7 correctly identified a stale expectation in the W1 orchestrator artifact tests and dry-run harness. W1 now intentionally routes the `fast` 10-chapter case to `W1_EXTRACT_EVENTS_DEEP_SPARSE`, but two fixtures still expected `W1_EXTRACT_EVENTS_DEEP_ARC`.

Codex updated the stale expectations only. No production/source workflow behavior was changed.

## Fix

| File | Change |
|---|---|
| `tests/test_w1_orchestrator_artifacts.py` | Fast-profile matrix now expects `W1_EXTRACT_EVENTS_DEEP_SPARSE`; manifest assertion renamed to sparse turning-points |
| `benchmark_results/v2_planner_dry_run/run_harness.py` | Dry-run matrix now expects `W1_EXTRACT_EVENTS_DEEP_SPARSE` for `case_5_10ch_en_fast` |

## Verification

| Command | Result |
|---|---|
| `sidecar/.venv/bin/python -m pytest tests/test_w1_orchestrator_artifacts.py tests/test_w1_v2_harness.py -q` | `63 passed` |
| `sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write` | `5/5 passed`, secret scan clean |

## Updated QA Status

| W7 Issue | Status |
|---|---|
| QA-01 stale test fixtures expecting ARC for fast profile | Fixed |
| QA-05 v2 harness failures cascading from QA-01 | Fixed |
| QA-02 / QA-03 live artifact observation gaps | Still require next live 10-chapter smoke |
| QA-04 pre-existing unrelated Playwright failures | Still separate backlog |

## Recommendation

The zero-cost W1/W7 gate is now clean for the stale-fixture issue. Proceed to the controlled 10-chapter live smoke only when API key/cost conditions are ready, and stop immediately on 402.
