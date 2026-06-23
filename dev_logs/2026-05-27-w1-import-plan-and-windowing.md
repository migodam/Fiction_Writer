# W1 Import Plan + Windowing Follow-up

## Summary
- Added artifact-level observability for granularity/profile dispatch.
- Switched supervisor `segment_manifest` to use supervised multi-chapter window packing.
- Added a schema-first `ImportPlan` foundation for future agentic/RAG planners without enabling free-form prompt or pipeline mutation.

## Changes
- `sidecar/supervisor/tools.py`
  - Added `_selected_extraction_prompt_manifest()`.
  - Window artifacts now include `import_granularity_profile` and `selected_prompt_variants`.
  - `proposal_write` now writes:
    - `import_granularity_profile.json`
    - `import_plan.json`
    - `extraction_prompt_variants.json`
  - `segment_manifest` now calls `_build_supervised_prompt_windows()` over all chunks instead of packing one chunk at a time.
- `sidecar/models/state.py`
  - Added `ImportPlanToolStep` and `ImportPlan`.
  - Added `plan_import_pipeline()`.
  - Added optional `import_plan` to `ImportSupervisorState`.
- `sidecar/supervisor/policy.py`
  - `_ensure_orchestrator_plan()` now stores `state["import_plan"]`.
- Docs updated:
  - `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
  - `dev_docs/W1_IMPORT_COMPILER.md`

## Validation
- `sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/supervisor/policy.py sidecar/supervisor/tools.py` — pass
- `sidecar/.venv/bin/python -m pytest tests/test_w1_granularity.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_extraction_variants.py -q` — pass

## Notes
- This is not a free-form LLM planner yet. It intentionally creates a schema-first plan that future LLM/RAG planners can propose into.
- Dynamic prompt edits remain disabled; prompt adaptation is still via vetted prompt variant constants.
- No model calls or full benchmark runs were performed for this code change.
