# W1 Final Semantic Gates

## Scope

- Updated only `tools/w1_import_diagnostics.py`, `tools/w1_live_smoke_10ch.py`, their focused tests, and this log.
- No backend workflow modules were changed.

## Changes

- High-severity `evidence_entity_mismatch` and any `evidence_unusable` reviewer finding are hard failures.
- A protagonist/main character with supporting notes but blank `background` or `experience` is a hard failure. Major status accepts explicit role metadata and repeated canonical-event participation so incomplete extractor role labels do not bypass the gate.
- World items classified as organizations/factions are flagged when they represent a person or event.
- Expected `discarded_duplicate` and scene-beat presence is reported in `informational_flags`; it does not independently fail `--fail-on-threshold` or the live smoke quality probe.
- Proposal-gated staged manuscript behavior remains unchanged: empty canonical manuscript data is accepted while the staged projection and receipts are valid.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_diagnostics.py tests/test_w1_live_smoke_runner.py` -> `28 passed`.
- `sidecar/.venv/bin/python -m py_compile tools/w1_import_diagnostics.py tools/w1_live_smoke_10ch.py` -> passed.
- `tools/w1_import_diagnostics.py` against `/tmp/narrative_ide_w1_live_smoke/20260713_020933/project`, run `live_smoke_20260713_020933_538641e3`, exits `1` under `--fail-on-threshold` for 26 high evidence mismatches, the supported-but-empty `韩立` profile, `马副门主` as an organization, and `七玄门内门测试` as an organization. Its discarded duplicate is informational only.
