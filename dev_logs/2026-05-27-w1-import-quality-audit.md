# W1 Import Quality Deep Audit

**Date**: 2026-05-27
**Branch**: codex/w1-orchestrated-import-quality
**Files changed**: `sidecar/supervisor/policy.py`, `tests/test_w1_supervisor_policy.py`
**Files added**: this log

---

## Scope

Full read-only audit of:
- `sidecar/workflows/w1_import.py` (5161 lines) — windowing, artifact writes
- `sidecar/supervisor/tools.py` (1376 lines) — extract_window, minor_repair, proposal_write
- `sidecar/supervisor/policy.py` (930 lines) — policy loop, judge verdict, converge_status
- `sidecar/models/state.py` (1320 lines) — state schema, planners, formulas
- `sidecar/prompts/w1_prompts.py` (1413 lines) — all 32 prompt constants
- All 11 `tests/test_w1_*.py` files — existing coverage audit
- Benchmark results: `w1_granularity_smoke_20260527_020021`, `w1_orchestrated_import_quality_20260525_085059`

---

## Findings Table

| Sev | File / Function | Issue | Evidence | Fix |
|-----|-----------------|-------|----------|-----|
| **LOW-MEDIUM** | `policy.py:738,975` (`run_supervisor_policy`, `run_supervisor_streaming`) | `acceptable_with_warnings` verdict not propagated to final `converge_status` — UI shows "failed" for acceptable imports | `_apply_thematic_reruns` sets `result_status="acceptable_with_warnings"` but never sets `passed=True`; final `_with_status()` reads only `passed` | **Fixed**: extract `_ja = state.get("judge_artifact") or {}`; use `_ja.get("result_status", "failed")` when `passed=False` |
| **LOW** | `w1_import.py:990` | `_write_chunk_prompt_failure()` defined but never called anywhere | grep confirms 0 call sites; failures are captured in `failed_prompts` list in window artifact instead | **Deferred** — current behaviour adequate; window artifact captures all failures in `failed_prompts`; cleanup belongs in a separate housekeeping task |
| **LOW** | `tools.py:487` | `extract_window` returns `{}` for failed prompt exceptions — no per-prompt failure artifact | Captured in `failed_prompts` string list in window artifact (tools.py:652–664); not silent data loss | **Report only** — window artifact is sufficient for audit trail |

---

## No Issues Found

| Area | Evidence |
|------|----------|
| Multi-chapter window packing | `_build_supervised_prompt_windows()` w1_import.py:1537–1637; late-chapter 50% cap for final 25% of chapters |
| Language injection in all prompts | `source_language_label` + `language_policy` injected in all 5 parallel prompt calls — tools.py:435–473 |
| Budget exhaustion propagation + halt | Detected tools.py:479–483; flagged in return dict tools.py:701–707; halted in extract batch loop policy.py:574 and thematic reruns policy.py:428 |
| Policy loop sequence and result forwarding | Correct order: orchestrator plan → segment_manifest → extract batches → reduce → repair → architect_timeline → QA loop → judge → thematic reruns → proposal_write; all tool results merged into state via `{**state, **update}` or `_merge_window_result()` |
| `_ensure_orchestrator_plan()` | Calls `analyze_source_profile`, stores `source_profile`, `import_plan_validation`, `converge_target`, `import_plan`, `tool_operating_spec` — policy.py:103–177 |
| `ImportSupervisorState` schema | All required fields present including `source_profile: SourceProfile` — state.py:1108–1148 |
| Convergence target formulas | Correct floor/ceiling with granularity profile override — state.py:619–661 |
| Import plan validation | Comprehensive: planner_kind, source_type, required tools, no duplicates, prompt_policy, cost_policy, safety gates — state.py:930–986 |
| All 12 prompt variant template variables | All variants inherit `{source_language_label}`, `{language_policy}`, `{chunk_content}`, `{entity_registry_summary}`, `{chunk_id}`, `{total_chunks}` via PRE composition — w1_prompts.py:562–1187 |
| `minor_repair` implementation | 4 deterministic repairs: groupKey normalization, world/person boundary migration, orderIndex re-sequencing, Latin trait stripping for zh source (≥4 consecutive Latin chars) — tools.py:1171–1266 |
| `minor_repair` Latin stripping tested | `TestMinorRepairLatinStrip` + `TestMinorRepairShortLatinStrip` in test_w1_supervisor_tools.py:385–703 |
| Window artifact always written | Written regardless of extraction success/failure, includes `failed_prompts` list — tools.py:652–664 |
| Conditional pre-OOM artifact writes | `source_profile.json`, `import_plan.json` etc. written conditionally if state fields exist; safe because `_ensure_orchestrator_plan()` always populates them before reaching proposal_write — tools.py:1291–1310 |

---

## Fix Applied

### `acceptable_with_warnings` verdict propagation — policy.py

**Root cause**: Both `run_supervisor_policy()` (line 738) and `run_supervisor_streaming()` (line 975)
computed the final `converge_status` using only `judge_artifact["passed"]`:

```python
# Before (both locations)
converge_status="passed" if state.get("judge_artifact", {}).get("passed", True) else "failed"
```

When `_apply_thematic_reruns()` hits wave cap with only soft gates (`character_undercoverage`),
it sets `judge_artifact["result_status"] = "acceptable_with_warnings"` but does not set
`passed = True`. The old code then returned `converge_status = "failed"`, which is shown in
the UI via `session["converge_status"]`.

**Fix** (identical at both locations):

```python
# After
_ja = state.get("judge_artifact") or {}
converge_status = "passed" if _ja.get("passed", True) else _ja.get("result_status", "failed")
```

`result_status` can be `"acceptable_with_warnings"`, `"needs_targeted_repair"`, or `"hard_fail"`.
The `True` default on `passed` preserves the no-judge-tool case where all imports proceed.

---

## Tests Added

File: `tests/test_w1_supervisor_policy.py`

**Class `TestAcceptableWithWarningsVerdict`** (3 tests):

1. `test_wave_cap_soft_only_sets_acceptable_with_warnings` — asserts `judge_artifact["rerun_cap_reached"]` is True and `result_status == "acceptable_with_warnings"` after wave cap hit with only `character_undercoverage` failure.
2. `test_acceptable_with_warnings_propagates_to_converge_status` — asserts `converge_status == "acceptable_with_warnings"` after `run_supervisor_policy` (verifies the fix).
3. `test_acceptable_with_warnings_does_not_block_proposal_write` — asserts `proposal_write` is still called when verdict is `acceptable_with_warnings`.

All zero-cost, no API, deterministic mocks only.

---

## Deferred

| Item | Reason |
|------|--------|
| `_write_chunk_prompt_failure()` cleanup | Dead code in w1_import.py — failures are adequately captured in window artifact `failed_prompts` list; removing is housekeeping, not a bug fix |
| Per-prompt failure artifact (structured) | Low priority; window artifact's `failed_prompts` string list is sufficient for current forensics; a richer per-prompt artifact would be a future observability improvement |

---

## Verification

```
sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py  →  OK

sidecar/.venv/bin/python -m pytest \
  tests/test_w1_supervisor_policy.py \
  tests/test_w1_supervisor_tools.py \
  tests/test_w1_import_compiler.py \
  tests/test_w1_prompt_windows.py \
  tests/test_w1_import_diagnostics.py \
  -q

→ 141 passed in 1.71s
  (includes 3 new TestAcceptableWithWarningsVerdict tests)
```
