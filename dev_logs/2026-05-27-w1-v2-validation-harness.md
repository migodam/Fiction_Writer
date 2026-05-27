# W1 V2 Validation Harness

**Date**: 2026-05-27
**Branch**: codex/w1-orchestrated-import-quality
**Files added**: `tests/test_w1_orchestrator_artifacts.py`, `benchmark_results/v2_planner_dry_run/run_harness.py`
**Files updated**: `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`

---

## What Was Added

### `tests/test_w1_orchestrator_artifacts.py` — 57 tests, 4 groups

All zero-cost, no API key, no mocking required. Calls only deterministic planner functions.

**Group 1 — TestOrchestratorPlannerMatrix** (parametrized over 5 cases):
Asserts `import_granularity_profile.profile_name`, `source_profile.recommended_granularity_profile`,
`converge_target.expected_min_characters`, `import_plan_validation.ok == True`,
`window_strategy.strategy == "supervised_chapter_batching"`, all tools enabled.
Includes one dedicated test for the fast-profile divergence case.

**Group 2 — TestPromptVariantDispatch**:
Identity checks (`is`) on char/event prompts. Manifest `prompt_constant` name assertions for
fine (10ch zh) and coarse (50ch zh) cases.

**Group 3 — TestArtifactIntegrity** (uses `tmp_path`):
`_write_import_artifact` creates correct files; source_profile and import_plan_validation have
expected schema keys; no secret pattern in any artifact JSON; safety gates and cost policy flags
set correctly.

**Group 4 — TestConvergeTargetConsistency**:
Acceptable floor ≤ expected_min for coarse + balanced cases. Fine (10ch zh deep) has higher
`expected_min_characters` than fast (10ch en fast) despite same chapter count.

### `benchmark_results/v2_planner_dry_run/run_harness.py` — Standalone report generator

Zero-cost. Runs the same 5-case matrix and writes `benchmark_metrics.json` + `benchmark_report.md`
to `runs/<YYYYMMDD_HHMMSS>/`.

Key JSON fields: `"dry_run": true, "live_model_calls": false`.

**Gated live smoke** is documented in `run_gated_live_smoke()` as an unimplemented stub.
Requires `LIVE_SMOKE_APPROVED=1` + `DEEPSEEK_API_KEY` in env. Will not run until user approves.

---

## Dry-Run Output (2026-05-27)

```
case_1_10ch_zh_deep:     PASS
case_2_50ch_zh_deep:     PASS
case_3_40ch_en_deep:     PASS
case_4_20ch_en_balanced: PASS
case_5_10ch_en_fast:     PASS

Secret scan: CLEAN (on artifact payloads)
Summary: 5/5 passed
```

Codex review tightened the harness `safety_gates_set` assertion so API 402 protection is checked
from `import_plan.cost_policy.stop_on_api_402` instead of a defaulted safety lookup.

**Note on secret scan**: the grep verification command over the output directory reports
false positives because the report files self-document the pattern string being checked
(e.g., `"DEEPSEEK_API_KEY=<key>"` in the live smoke instruction line). The harness itself
scans only artifact payload dicts and reports CLEAN.

---

## Fast-Profile Divergence (Case 5)

| Field | Value |
|-------|-------|
| `source_profile.recommended_granularity_profile` | `fine_short_story` (10 chapters, descriptive) |
| `import_granularity_profile.profile_name` | `coarse_webnovel` (fast override, execution policy) |
| `converge_target.expected_min_characters` | 5 (0.5 × 10 = 5, coarse_fast rate) |

The divergence is intentional. `analyze_source_profile` is purely descriptive and ignores the
fast override. `select_granularity_profile` applies the execution override and forces coarse.
Both values are separately observable in the artifacts.

---

## Matrix Expected Values

| Case | n | lang | profile | Gran Profile | Source Type | Min Chars | Char Variant | Event Variant |
|------|---|------|---------|--------------|-------------|-----------|--------------|---------------|
| 1 | 10 | zh | deep | fine_short_story | fine_short_story | 15 | FINE | DENSE |
| 2 | 50 | zh | deep | coarse_webnovel | coarse_webnovel | 50 | BALANCED | CHAPTER |
| 3 | 40 | en | deep | balanced_novel | balanced_novel | 40 | BALANCED | CHAPTER |
| 4 | 20 | en | balanced | balanced_novel | balanced_novel | 24 | BALANCED | CHAPTER |
| 5 | 10 | en | fast | coarse_webnovel | fine_short_story | 5 | BALANCED | ARC |

---

## Deferred

- Gated live 10-ch smoke: requires `LIVE_SMOKE_APPROVED=1` + `DEEPSEEK_API_KEY`. Documented
  in harness as a stub; user must approve before implementation and execution.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/supervisor/planner.py benchmark_results/v2_planner_dry_run/run_harness.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_orchestrator_artifacts.py tests/test_w1_import_plan_validator.py tests/test_w1_source_profile.py tests/test_w1_granularity.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_extraction_variants.py tests/test_w1_import_compiler.py tests/test_w1_prompt_windows.py tests/test_w1_import_diagnostics.py -q`

Result: 328 tests passed.
