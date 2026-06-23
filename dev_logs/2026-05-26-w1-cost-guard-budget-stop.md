# W1 Cost Guard: API 402 Hard Stop + Rerun Wave Cap

**Date:** 2026-05-26
**Branch:** `codex/w1-cost-guard-budget-stop`
**Base:** `codex/w1-orchestrated-import-quality` @ `bed8ec6`

---

## Problem

Full-50 benchmark run 4 (`w1_full50_after_streaming_20260526_190513`) failed in 2 minutes because all 70 LLM calls returned HTTP 402 Insufficient Balance. Despite every window returning 402, the supervisor loop still:
1. Completed 29 failed-window metrics records.
2. Tried to rerun each window via `rerun_window` (dispatched from per-window gate evaluation).
3. Burned rerun budget against a known-bad API state.

An earlier run (run 1, `w1_full50_100642`) had the same issue: 148 failed prompts × 5 types = wasted API calls after the balance was exhausted at chapter 25.

Additional risk: prior runs show that the judge can trigger multiple thematic rerun waves (each wave = judge+reruns+reduce+repair+arch+QA), potentially 2–3 cycles even with `rerun_budget=2`. For a 50-chapter deep run, each cycle consumes another ~20–40 API calls.

---

## Changes

### `sidecar/supervisor/tools.py`

- **`_is_budget_exhausted_error(exc)`**: Helper that detects HTTP 402 / "insufficient balance" from any OpenAI-compatible provider. Checks `str(exc).lower()` for `"402"`, `"insufficient balance"`, `"insufficient_balance"`. Also checks `openai.APIStatusError.status_code == 402` if openai is importable.

- **`extract_window`**: After `asyncio.gather`, checks each failed exception via `_is_budget_exhausted_error`. If any prompt returns 402, sets `_budget_exhausted_in_window = True`. Returns `budget_exhausted=True` and appends a clear message to `errors[]`.

- **`judge_import`**: Added `result_status` four-tier classification to `JudgeArtifact`:
  - `passed` — all gates pass
  - `acceptable_with_warnings` — only `character_undercoverage` failed, profile is `fast` or `balanced`
  - `needs_review` — exactly 1 non-trivial gate failed
  - `failed` — 2+ gates failed
  - `budget_exhausted` — `state["budget_exhausted"]` is True

### `sidecar/supervisor/policy.py`

- **`_process_window`**: After `extract_window` returns, propagates `budget_exhausted` to state and returns immediately (no cross-validate, no gate reruns) if True.

- **`run_supervisor_policy`** extraction batch loop: Checks `state.get("budget_exhausted")` before each batch and after each result. Breaks the loop on first detection, appending a log entry.

- **`_apply_thematic_reruns`**: Hard-exits immediately if `state.get("budget_exhausted")`. Added `thematic_rerun_wave_cap` enforcement: the while loop now also checks `waves_applied < wave_cap`. Increments `waves_applied` after each reduce/repair/arch/qa/judge cycle. When cap is hit, sets `JudgeArtifact.rerun_cap_reached=True`. If the only failing gate is `character_undercoverage` at cap time, upgrades `result_status` to `acceptable_with_warnings`.

- **TOS resolution after judge**: Both `run_supervisor_policy` and `_policy_with_progress` now read `state.get("tool_operating_spec")` after `_run_judge_import` (judge may return an updated TOS with wave cap). Previously the pre-judge local variable was used, causing wave_cap=0 to be ignored.

- **Streaming path** (`_policy_with_progress`): Same budget-exhausted break guard added to batch loop.

### `sidecar/models/state.py`

- **`ToolOperatingSpec`**: Added `thematic_rerun_wave_cap: int` field.
- **`_TOS_DEFAULTS`**: `thematic_rerun_wave_cap` defaults: fast=0, balanced=1, deep=1, custom=2.
- **`JudgeArtifact`**: Added `result_status` and `rerun_cap_reached` fields.
- **`ImportSupervisorState`**: Added `budget_exhausted: bool` and `global_rerun_count: int`.

### `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`

- Updated policy loop pseudocode (wave cap, budget stop).
- Added `result_status` table to JudgeArtifact section.
- Added `thematic_rerun_wave_cap` row to Profile Config Dimensions table.
- Added **Cost Protection** section with 402 hard stop, wave cap, and benchmark one-shot guard rules.

---

## Tests

### New tests (19 total)

**`tests/test_w1_supervisor_tools.py`** (14 new):
- `TestBudgetExhausted402Detection` (3): `_is_budget_exhausted_error` detection variants
- `TestExtractWindowBudgetExhausted` (4): extract_window returns budget_exhausted flag; error messages; non-402 doesn't set flag
- `TestJudgeImportResultStatus` (4): result_status values for passed/acceptable_with_warnings/deep-fail/budget_exhausted
- `TestTOSThematicRerunWaveCap` (3): TOS defaults for fast/balanced/deep wave cap

**`tests/test_w1_supervisor_policy.py`** (5 new):
- `TestPolicyBudgetExhaustedStop` (3): stops after first batch, prevents rerun, skips thematic reruns
- `TestPolicyThematicRerunWaveCap` (2): wave_cap=1 sets rerun_cap_reached; wave_cap=0 blocks all thematic reruns

### Full suite result

```
tests/test_w1_supervisor_tools.py    73 passed
tests/test_w1_supervisor_policy.py   25 passed
tests/test_w1_import_compiler.py     15 passed
─────────────────────────────────────────────
113 passed in 0.90s
```

---

## How 402 is Detected

`_is_budget_exhausted_error(exc)` checks:
1. `"402"` substring in `str(exc).lower()`
2. `"insufficient balance"` or `"insufficient_balance"` substring
3. `openai.APIStatusError.status_code == 402` (if openai importable)

Covers DeepSeek V4 Pro's exact error format:
```
APIStatusError: Error code: 402 - {'error': {'message': 'Insufficient Balance', 'type': 'unknown_error', 'code': 'invalid_request_error'}}
```

---

## How Reruns are Capped

`thematic_rerun_wave_cap` defaults:
- `fast`: 0 (no thematic reruns ever)
- `balanced`: 1 (one judge+rerun cycle max)
- `deep`: 1 (one judge+rerun cycle max)
- `custom`: 2

This means for a deep profile run: at most 1 thematic repair wave after the initial judge. If it still fails after that wave, `proposal_write` runs with whatever was extracted and `rerun_cap_reached=True` is recorded in the artifact.

---

## Benchmark Guard (documented in W1_AGENTIC_IMPORT_SUPERVISOR.md)

Explicit rules added to the docs:
1. At most one full-50 attempt per API balance top-up.
2. 402 → stop and report. No retry.
3. Code errors → fix on new branch, smoke run (10ch), then one full-50.
4. Do not modify product code during a validation benchmark run.
5. Do not start a second full-50 run without Codex approval.

---

## Residual Risk

- `_is_budget_exhausted_error` relies on string matching. If the API provider changes the error message format, detection will fail silently (no 402 guard fires). The fallback is still present: 5 failed prompts per window → gate fails → reruns exhaust budget per window (same as before).
- `global_rerun_count` is added to `ImportSupervisorState` schema but not yet incremented by the policy loop (reserved for future cost telemetry). No logic depends on it yet.
- The streaming path (`_policy_with_progress`) budget guard applies to the extraction loop. Thematic reruns in the streaming path are also guarded via `_apply_thematic_reruns`. But `_policy_with_progress` doesn't call `_apply_thematic_reruns` directly — it calls it via `_run_judge_import`... wait, it does call `_apply_thematic_reruns` directly. Both paths are guarded.
