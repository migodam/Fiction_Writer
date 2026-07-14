# W1 Supervisor Timeline Density and QA Staging

Date: 2026-07-13

## Changes

- Added deterministic post-architect timeline density enforcement in `sidecar/supervisor/timeline_density.py`.
- Enforced a maximum of 10 canonical events per branch after architecture, preserving chapter coverage where capacity permits and using stable importance, confidence, causal role, source order, and stable-id ranking.
- Preserved merge/demotion provenance through `mergedEventIds`, density reasons, source spans, and chapter ranges; overflow becomes a semantic merge when supported or a `scene_beat` otherwise.
- Prepared explicit `reviewer_staged_projection_metrics` in supervisor policy before QA so preproposal review recognizes deterministic manuscript staging inputs.
- Updated the quality reviewer to avoid `manuscript_empty` only when staged projection metrics show real chapter inputs.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_timeline_density.py tests/test_w1_reviewers_quality.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py`
  - Result: 146 passed.
- `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py sidecar/supervisor/reviewers/quality_reviewer.py sidecar/supervisor/timeline_density.py tests/test_w1_timeline_density.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.
- Read-only probe against `/tmp/narrative_ide_w1_live_smoke/20260713_013817/project/system/imports/sup_51096b2887/timeline_architecture.json`
  - Result: 14 canonical events reduce to 10, with 4 deterministic overflow adjustments.
