# W1 Supervisor Evidence And Cross-Validation

## Scope

- Owned changes: `sidecar/supervisor/policy.py`, `sidecar/workflows/w1_import.py`, targeted W1 pytest coverage.
- Explicitly untouched: `sidecar/supervisor/tools.py`.
- No live model, paid API, or external network call was run.

## Changes

- `_merge_window_result()` now combines per-window `cross_validation` through the existing bounded, de-duplicating `_merge_cross_validation_artifacts()` helper.
- The supervisor policy annotates new window candidates with prompt-window and chunk provenance, then materializes `evidence_cards.json` before QA review.
- Supervisor evidence cards include the originating prompt-window id and its `source_span`; affected character, event, world, and raw relationship candidates receive matching `evidence_refs`.
- Reviewer proposal views now carry character evidence provenance.
- Review observability is explicitly `pre_proposal`: relationship and manuscript metrics no longer claim final write status before relationship synthesis or manuscript staging.
- Corrected stale W1 docstrings that implied direct canonical manuscript writes.

## Tests

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_evidence.py tests/test_w1_supervisor_policy.py tests/test_w1_import_compiler.py
120 passed in 3.66s

sidecar/.venv/bin/python -m compileall -q sidecar/supervisor/policy.py sidecar/workflows/w1_import.py tests/test_w1_supervisor_evidence.py
passed

git diff --check -- sidecar/supervisor/policy.py sidecar/workflows/w1_import.py tests/test_w1_supervisor_evidence.py tests/test_w1_import_compiler.py
passed

sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_evidence.py tests/test_w1_supervisor_policy.py tests/test_w1_import_compiler.py tests/test_w1_reviewers_fact.py tests/test_w1_quality_rubric.py
146 passed in 2.57s
```

## Integration Notes

- `sidecar/workflows/w1_import.py` and `tests/test_w1_import_compiler.py` had unrelated in-progress edits when this work started; they were preserved.
- `sidecar/supervisor/tools.py` was already modified by another workstream and was not edited here.
