# W1 Industrial Import Quality Rubric

**Date**: 2026-05-27
**Branch**: `codex/w1-orchestrated-import-quality`
**Base commit**: `7d5c20f`

---

## Summary

Added zero-cost quality rubric, `PromptPolicyPatch` typed layer, windowing metadata fields,
`converge_status` Literal fix, and harness quality rubric integration. No live model calls.
No full50 run. No w1_prompts.py changes.

---

## Files Changed

| File | Change |
|------|--------|
| `sidecar/models/state.py` | Added `PromptPolicyPatch` TypedDict; added `prompt_policy_patch` optional field to `PlannerProposal`; extended `converge_status` Literal to include `"planning_failed"`, `"acceptable_with_warnings"`, `"hard_fail"` |
| `sidecar/supervisor/planner.py` | Added `"prompt_policy_patch"` to `_PROPOSAL_ALLOWED_FIELDS`; added `_PPP_*` constants; added `validate_prompt_policy_patch()` function; wired patch validation into `validate_planner_proposal()` |
| `sidecar/supervisor/quality.py` | New file — `evaluate_import_quality(state)` zero-cost quality rubric |
| `sidecar/workflows/w1_import.py` | Added `late_zone` and `effective_cpw` params to `_make_windows_from_batch()`; propagated through recursive splits; added `late_window_cap_applied`, `effective_chapters_per_window`, `chapters_per_window_config` to window dicts; updated `_prompt_window_manifest_entry()` |
| `benchmark_results/v2_planner_dry_run/run_harness.py` | Integrated `evaluate_import_quality()`; added `quality_rubric_no_hard_fail` assertion; added `quality_rubric` key to case result |
| `tests/test_w1_quality_rubric.py` | New file — 12 tests for `evaluate_import_quality()` |
| `tests/test_w1_planner_proposal.py` | Added `validate_prompt_policy_patch` import; added `TestPromptPolicyPatch` class with 8 tests |
| `tests/test_w1_prompt_windows.py` | Added `TestWindowMetadata` class with 4 tests (cpw=6 synthetic profile) |
| `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md` | Added planning artifact table entries for `planner_proposal.json` and `planner_proposal_validation.json`; added sections for quality rubric, PromptPolicyPatch, and window metadata |

---

## Quality Rubric Behaviour

`evaluate_import_quality(state)` is soft-first:

**Hard failures** (only contract/safety breaks):
- `import_plan_validation["ok"] is False`
- `import_plan.safety` missing or proposal gates not set
- `planner_proposal_validation["ok"] is False` (when present)
- Proposal present but `planner_kind == "deterministic_rules"` (gate bypass indicator)

**Warn** (novelist quality signals — not gates):
- No character proposals when `converge_target.expected_min_characters > 0`
- Events missing `branchId` or `orderIndex`
- Relationships missing `evidence`
- `source_profile` absent
- `import_plan` absent

Dry-run harness cases (no real import proposals) return `verdict == "warn"`, passing
`quality_rubric_no_hard_fail` assertion.

---

## PromptPolicyPatch

Typed and validated. Not applied to prompts this session.
`planner_proposal_to_import_plan()` ignores the patch — application is deferred to a future
prompt-design session after explicit design approval.

---

## Token / Cost Ledger

| Item | Value |
|------|-------|
| **Live model calls** | none |
| **full50 run** | NOT RUN |
| **Model used** | none |
| **Estimated API calls** | 0 |
| **Zero-cost tests run** | 369 |

Confirmation: full50 was NOT run. No live model/API call was made.

---

## Tests Run

Phase B (targeted):
```
tests/test_w1_quality_rubric.py    12 passed
tests/test_w1_planner_proposal.py  (all, including 8 new TestPromptPolicyPatch) passed
tests/test_w1_prompt_windows.py    (all, including 4 new TestWindowMetadata) passed
Total: 57 passed
```

Phase C (combined W1 regression, run once):
```
369 passed in 3.82s
(344 baseline + 25 new)
```

Phase D (harness --no-write):
```
5/5 cases PASS  (includes quality_rubric_no_hard_fail assertion)
Secret scan: CLEAN
```

---

## Deferred

| Item | Reason |
|------|--------|
| Applying `PromptPolicyPatch` knobs to `w1_prompts.py` | Type safety established; application needs dedicated prompt-design session |
| Live smoke run (10-ch deep) | Requires explicit Codex approval |
| `w1_planner_prompts.py` LLM system prompt | Model-call session |
| Per-prompt failure artifact (structured) | Low priority; `failed_prompts` list is sufficient |
| `_write_chunk_prompt_failure()` dead code cleanup | Housekeeping |
