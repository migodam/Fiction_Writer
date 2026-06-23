# W1 Source Profile + ImportPlan Validation Integration

## Summary

Integrated the deterministic source profiler and ImportPlan validator into the W1 orchestrator planning path.

## Changes

- `sidecar/supervisor/policy.py`
  - `_ensure_orchestrator_plan()` now calls `analyze_source_profile()` and stores `state["source_profile"]`.
  - Generated `ImportPlan` values are validated with `validate_import_plan()`.
  - Validation results are stored as `state["import_plan_validation"]`.
  - Pre-existing invalid `import_plan` values are marked as `hard_fail` before execution.
- `sidecar/supervisor/tools.py`
  - `proposal_write()` now writes `source_profile.json` and `import_plan_validation.json` before proposal synthesis, matching the existing OOM-safe artifact strategy.
- `sidecar/models/state.py`
  - Added `import_plan_validation` to `ImportSupervisorState`.
- Tests
  - Added policy coverage for stored source profile, stored validation result, and invalid pre-existing plans.
  - Extended early-artifact coverage for `source_profile.json` and `import_plan_validation.json`.
- Docs
  - Updated `W1_AGENTIC_IMPORT_SUPERVISOR.md` and `W1_IMPORT_COMPILER.md` to document the integrated planning sequence and new artifacts.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/supervisor/policy.py sidecar/supervisor/tools.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_plan_validator.py tests/test_w1_source_profile.py tests/test_w1_supervisor_policy.py::TestOrchestratorPlanGranularity tests/test_w1_supervisor_tools.py::TestProposalWriteEarlyArtifacts -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_plan_validator.py tests/test_w1_source_profile.py tests/test_w1_granularity.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_extraction_variants.py tests/test_w1_import_compiler.py tests/test_w1_prompt_windows.py tests/test_w1_import_diagnostics.py -q`

Result: 54 targeted tests passed; 253 W1 regression tests passed.

## Notes

- This is still schema-first deterministic planning. No LLM planner, dynamic prompt mutation, model call, or benchmark run was introduced.
- Future LLM/RAG planner proposals must pass the same `validate_import_plan()` safety contract before execution.
