# W1 Supervisor S3 — Policy Loop Integration

**Branch:** `codex/w1-windowing-redesign`
**Date:** 2026-05-24

## Summary

Completed S3 (policy loop integration) on top of S1 (supervisor tools) and S2 (chapter-count-aware windowing).

## Steps completed

### Step 0 — Branch hygiene
- Merged `codex/w1-deep-import-quality-integration` (ae5abd1) cleanly into branch
- Removed duplicate `_detect_language` at line ~1428 (kept ae5abd1 version at ~504)
- All 58 tests passed post-merge

### Step 1 — Tool regression fixes
- Added `_event_cap_from_profile(profile_config, chapter_count)` helper to tools.py
- Replaced hardcoded `[:3]` event cap in `extract_window` with profile-aware cap
- Added `_is_world_entity_candidate` + `_normalize_world_category` imports; replaced org_roles keyword check in `minor_repair`
- Removed `_USE_SUPERVISOR_WINDOWING = False` dead flag; replaced `if use_supervisor and _USE_SUPERVISOR_WINDOWING:` with `if use_supervisor:`
- Updated test_w1_prompt_windows.py: removed import of deleted constant, rewrote Test 5 as logic check

### Step 2 — `sidecar/supervisor/policy.py` (created)
- `run_supervisor_streaming(project_path, config)` — async generator, same interface as `run_streaming()`
- `run_supervisor_policy(state, tools)` — pure policy loop returning final state
- Gate thresholds: char_density < 0.5, event_density < 0.5, failed_prompts ≥ 3
- Window batching: asyncio.gather in groups of 3
- QA rerun loop: up to `max_supervisor_iterations` (default 3)
- Supervisor path skips when `import_mode != "import_all"`

### Step 3 — `run_streaming()` dispatch
- Added supervisor dispatch at top of `run_streaming()` in w1_import.py (7 lines)

### Step 4 — Router wiring
- Added `use_supervisor: bool = False` to `W1StartRequest`
- Added `use_supervisor` to config dict and session init dict
- Added `GET /workflow/w1/supervisor_status` endpoint
- Electron IPC bridge passes through via `...rest` spread (no change needed)

### Step 5 — UI store
- Added 4 fields: `w1UseSupervisor`, `w1SupervisorDecisions`, `w1GateFailures`, `w1SupervisorIteration`
- Added `setW1UseSupervisor(v: boolean)` setter
- Added `use_supervisor: w1UseSupervisor` to `startImport` call
- Added `use_supervisor?: boolean` to `W1StartPayload` interface in `electronApi.ts`

### Step 6 — Tests
- Created `tests/test_w1_supervisor_policy.py` (8 tests, all pass)
- Fixed event loop issue: `_run()` uses `asyncio.run()` in both policy and tools test files

### Step 7 — Documentation
- Created `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
- Added pointer line to `dev_docs/W1_IMPORT_COMPILER.md`

## Test results

```
tests/test_w1_supervisor_policy.py  — 8/8 PASS
tests/test_w1_supervisor_tools.py   — 21/21 PASS
tests/test_w1_prompt_windows.py     — 13/13 PASS
tests/test_w1_import_compiler.py    — 24/24 PASS
Total                               — 66/66 PASS
```

TypeScript lint: 0 warnings, 0 errors.
