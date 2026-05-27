# W1 Smart Import Iteration

**Date**: 2026-05-27
**Branch**: `codex/w1-orchestrated-import-quality`
**Base commit**: `aaa597a`

---

## Summary

Advanced W1 from a validated planning foundation toward a product-grade smart import path:

- `PlannerProposal` execution now drives the final `import_granularity_profile`, `converge_target`, and window `profile_config`.
- `PromptPolicyPatch` is applied as normalized metadata and static directive keys in `ImportPlan.prompt_policy`; raw prompt text is still forbidden and `w1_prompts.py` was not changed.
- Added zero-cost `planner_llm.py` scaffolding for prompt context, JSON parsing, and deterministic stub proposal generation.
- Extended the offline quality rubric with novelist-facing soft checks: role distribution, canonical-event vs scene-beat separation, zh Latin leakage, and source provenance.
- Added window/harness observability for quality summaries and token/cost ledger reporting.

No live model/API calls were made. full50 was not run.

---

## Progress Update

| Area | Status | Notes |
|------|--------|-------|
| PlannerProposal execution consistency | Complete | Converted plans now synchronize granularity, converge target, and chapters-per-window config |
| PromptPolicyPatch safe application | Complete (metadata only) | Static directives stored in `ImportPlan.prompt_policy`; prompt templates unchanged |
| LLM planner producer | Stub complete | `llm_planner_mode="stub"` is zero-cost; `live` is rejected without model calls |
| Quality rubric | Expanded | Additional soft checks for narrative usefulness and provenance |
| Window/token observability | Expanded | Manifest and harness expose more cost/quality signals |
| Live validation | Deferred | Requires explicit approval and cheapest configured flash model |
| Custom pipeline assembly | Deferred | Preset pipeline with safe planner influence remains the current milestone |

---

## Files Changed

| File | Change |
|------|--------|
| `sidecar/supervisor/policy.py` | Sync proposal-derived plan into execution state; support zero-cost planner stub mode; reject live mode without approval |
| `sidecar/supervisor/planner.py` | Apply validated `PromptPolicyPatch` metadata to converted `ImportPlan` before final validation |
| `sidecar/supervisor/prompt_policy.py` | New static directive helper; no raw prompt text accepted |
| `sidecar/supervisor/planner_llm.py` | New zero-cost planner context/parser/stub helper; no model/API calls |
| `sidecar/supervisor/quality.py` | Added role, event-class, zh Latin leakage, and provenance soft checks |
| `sidecar/workflows/w1_import.py` | Expanded prompt-window manifest observability fields |
| `benchmark_results/v2_planner_dry_run/run_harness.py` | Added per-case and aggregate quality summaries |
| `tests/test_w1_*.py` | Added focused coverage for planner consistency, prompt policy, planner stub, quality rubric, harness, and window metadata |
| `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md` | Updated planner/proposal, quality rubric, PromptPolicyPatch, and window metadata contracts |
| `dev_docs/W1_IMPORT_COMPILER.md` | Documented bounded PromptPolicyPatch behavior |

---

## Token / Cost Ledger

| Item | Value |
|------|-------|
| Live model calls | `false` |
| full50 run | `false` |
| Model used | `null` |
| Estimated API calls | `0` |
| 402 encountered | `false` |

No API key was read or written. Harness live smoke remained skipped.

---

## Verification

Compile:
```bash
sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/supervisor/planner.py sidecar/supervisor/planner_llm.py sidecar/supervisor/prompt_policy.py sidecar/supervisor/quality.py sidecar/supervisor/policy.py sidecar/supervisor/tools.py sidecar/workflows/w1_import.py benchmark_results/v2_planner_dry_run/run_harness.py
```

Targeted tests:
```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_quality_rubric.py tests/test_w1_prompt_windows.py tests/test_w1_v2_harness.py tests/test_w1_supervisor_policy.py -q
# 121 passed
```

Combined W1 regression:
```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_orchestrator_artifacts.py tests/test_w1_import_plan_validator.py tests/test_w1_source_profile.py tests/test_w1_v2_harness.py tests/test_w1_quality_rubric.py tests/test_w1_granularity.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_extraction_variants.py tests/test_w1_import_compiler.py tests/test_w1_prompt_windows.py tests/test_w1_import_diagnostics.py -q
# 392 passed
```

Harness:
```bash
sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write
# 5/5 passed, secret scan CLEAN

sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --case case_2_50ch_zh_deep --output-dir /tmp/w1_v2_planner_check
# 1/1 passed, output file scan CLEAN
```

---

## Deferred

- Actual live LLM planner calls.
- Applying static PromptPolicyPatch directives to prompt templates.
- User-facing UI controls for planner mode or prompt policy knobs.
- full50 benchmark.
- Custom pipeline assembly beyond the validated preset pipeline.
