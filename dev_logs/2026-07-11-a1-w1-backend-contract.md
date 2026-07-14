# A1 W1 Backend Contract

## Changes
- Added canonical reconstructable `SourceSpan` helpers and propagated spans through W1 segmentation and raw-source manuscript projection.
- Prevented extraction output from becoming chapter prose; pre-acceptance manuscript output is now staged in `staged_manuscript_projection.json` and referenced from chapter/scene proposals.
- Added bounded planner next-action validation and resolution, including registered-tool checks, stop handling, and rerun/budget fallback.

## Tests
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_prompt_windows.py tests/test_w1_backend_contract.py tests/test_w1_import_compiler.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_import_plan_validator.py tests/test_w1_planner_proposal.py`
- Result: `281 passed`.

## Risks
- The acceptance layer must consume `stagedManuscriptProjection` to materialize canonical manuscript files after proposal/package acceptance; this A1 slice intentionally does not modify frontend or acceptance-owner files.
