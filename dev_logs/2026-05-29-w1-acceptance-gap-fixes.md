# W1 Acceptance Gap Fixes — 2026-05-29

## Summary

Closed deterministic acceptance gaps found after reviewing the W1 import robustness branch.

## Changes

- Restored `benchmark_results/v2_planner_dry_run/run_harness.py` as tracked source while keeping generated benchmark outputs ignored.
- Raised canonical W1 `output_token_budget` defaults from 3000 to 4000.
- Made supervisor rolling context digest injection idempotent when a prompt window already contains `PROJECT_STRUCTURE_DIGEST`.
- Added relationship extraction counts to per-window metrics.
- Surfaced running `extraction_counts` through W1 status, Electron API types, Zustand state, and the import modal.

## Verification

- Python compile: passed for `state.py`, `tools.py`, `w1_import.py`, and `workflows.py`.
- W1 backend tests: `206 passed`.
- V2 dry-run harness: `5/5 passed`, secret scan clean, live smoke skipped.
- UI build: `npm run ui:build` passed.
- Playwright: `32 passed` using `tests/playwright.config.ts`.

## Cost Ledger

- Live API/model calls: none.
- full50 benchmark: not run.
- Provider credentials used: none.
