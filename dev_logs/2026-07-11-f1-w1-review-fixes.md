# F1 W1 Review Fixes

## Changes
- Preserved exact raw window `text`/`source_text` and absolute `SourceSpan` for oversized/supervised prompt-window parts; rendered prompt headers are stored separately.
- Converted matched-character `EntityMergeDecision/v1` records into proposal-gated character update operations with conflict diagnostics.
- Executed only legal, registered planner initial actions; out-of-order actions fall back to deterministic segmentation.
- Explicitly overwrite Chinese `character_tags` with an empty normalized list when all candidates are rejected.
- Configured E0 budget policy at W1 entry points and wrapped every W1 provider call with preflight and postflight accounting.

## Verification
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_compiler.py tests/test_w1_supervisor_tools.py tests/test_w1_backend_contract.py tests/test_w1_supervisor_policy.py`
- Result: `198 passed`
- `python -m py_compile sidecar/workflows/w1_import.py sidecar/supervisor/tools.py sidecar/supervisor/policy.py sidecar/supervisor/planner.py`
- `git diff --check`
