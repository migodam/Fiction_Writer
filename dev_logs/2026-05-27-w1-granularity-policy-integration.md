# W1 Orchestrator Granularity Policy Integration

**Date:** 2026-05-27
**Branch:** `codex/w1-orchestrated-import-quality`

---

## Problem

`_ensure_orchestrator_plan()` called `plan_orchestrator_targets()`, which wrapped `plan_tool_operating_spec()` + `plan_converge_target()` without a granularity profile. Converge targets were derived purely from TOS defaults:

- Deep profile: `min_characters_per_chapter=1.5`
- 50-chapter zh source: `expected_min_characters = ceil(1.5 × 50) = 75`

For a Chinese webnovel this is too high. The correct target for `coarse_webnovel` (the source-adaptive profile for CJK >30 chapters) is `min_characters_per_chapter=1.0`, yielding `expected_min_characters=50`.

The `select_granularity_profile()` function and the `granularity_profile` argument to `plan_converge_target()` already existed and were tested in isolation. The wiring into the policy loop was missing.

---

## Changes

### `sidecar/supervisor/policy.py`

- **Imports**: added `plan_converge_target`, `plan_tool_operating_spec`, `select_granularity_profile`. Retained `plan_orchestrator_targets` for external callers.

- **`_ensure_orchestrator_plan()`**: replaced the single `plan_orchestrator_targets()` call with a three-step pattern:
  1. `plan_tool_operating_spec()` → `spec`
  2. `select_granularity_profile(chapter_count, source_language, prompt_profile, import_mode)` → `granularity_profile`
  3. `plan_converge_target(spec, source_language, chapter_count, granularity_profile=granularity_profile)` → `target`
  - Stores `granularity_profile` as `state["import_granularity_profile"]`.
  - Early-return guard (`tool_operating_spec` + `converge_target` already set) unchanged.

No changes to cost guard, 402 hard stop, `thematic_rerun_wave_cap`, or any other policy loop path.

### `tests/test_w1_supervisor_policy.py`

New class `TestOrchestratorPlanGranularity` (3 tests):
- `test_stores_import_granularity_profile` — verifies field is present after plan
- `test_50ch_zh_deep_expected_min_characters_equals_50` — verifies coarse_webnovel override
- `test_idempotent_when_spec_and_target_already_set` — verifies early-return does not overwrite

### `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`

Updated TOS/ConvergeTarget section to document the three-step `_ensure_orchestrator_plan()` flow and granularity decision rules.

### `dev_docs/W1_IMPORT_COMPILER.md`

Added one sentence to Timeline Requirements noting that `ConvergeTarget` values are source-adaptive via `select_granularity_profile()` when supervisor mode is active.

---

## Before / After

| Scenario | Before | After |
|----------|--------|-------|
| 50-ch zh deep `expected_min_characters` | 75 (TOS 1.5×50) | 50 (coarse_webnovel 1.0×50) |
| `state["import_granularity_profile"]` | not set | `{"profile_name": "coarse_webnovel", ...}` |

---

## Test Results

```
tests/test_w1_supervisor_policy.py   28 passed  (25 pre-existing + 3 new)
tests/test_w1_granularity.py         22 passed
─────────────────────────────────────────────
50 passed in 0.36s
```

---

## Unchanged

- `budget_exhausted` handling
- `thematic_rerun_wave_cap` enforcement
- 402 hard stop
- All other policy loop paths
- `sidecar/supervisor/tools.py`, `sidecar/prompts/w1_prompts.py`, `sidecar/workflows/w1_import.py`
