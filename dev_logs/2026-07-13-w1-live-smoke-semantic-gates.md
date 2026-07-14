# W1 Live Smoke Semantic Gates - 2026-07-13

## Scope

- Owned paths: `tools/w1_live_smoke_10ch.py`, `tests/test_w1_live_smoke_runner.py`, and this log.
- No diagnostics, sidecar, UI, Electron, backend, provider configuration, or canonical project storage code changed.
- No network or provider call was made.

## Changes

- Added smoke-run semantic gates aligned with `tools/w1_import_diagnostics.py` for duplicate canonical characters, unresolved reviewer evidence, branch density over 10, Chinese-project English tags, invalid relationship ontology labels, world-module contamination, and exhausted or over-cap usage ledgers.
- Duplicate names remain permitted only when every implicated character has explicit identity-disambiguation evidence.
- Reviewer `manuscript_empty` is ignored when `staged_manuscript_projection.json` contains chapters, preserving the proposal-acceptance contract. Low `character_thin_card` findings remain advisory.
- The probe derives branch density from both reviewer findings and `timeline_architecture.json`, so missing receipt metadata cannot hide an overfull canonical branch.

## Verification

```text
sidecar/.venv/bin/python -m py_compile tools/w1_live_smoke_10ch.py tests/test_w1_live_smoke_runner.py
sidecar/.venv/bin/python -m pytest -q tests/test_w1_live_smoke_runner.py
# 19 passed in 0.43s

Offline probe: /tmp/narrative_ide_w1_live_smoke/20260713_013817/project
# semantic failures: duplicate_canonical_character_names, unresolved_evidence_missing, branch_density_over_budget
# manuscript_empty correctly absent because the staged projection contains 10 chapters, 20 nodes, and 10 scene documents

git diff --check -- tools/w1_live_smoke_10ch.py tests/test_w1_live_smoke_runner.py
# passed
```
