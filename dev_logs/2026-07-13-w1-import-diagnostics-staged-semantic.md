# W1 Import Diagnostics: Staged Projection And Semantic Flags

## Scope

- Owned paths: `tools/w1_import_diagnostics.py`, focused diagnostics tests, and this log.
- No sidecar, UI, Electron, canonical project storage, provider configuration, or network activity was changed.

## Changes

- Diagnostics now treats `staged_manuscript_projection.json` as the effective manuscript projection when `acceptance_required` is true. It reports the staged smoke contract of 10 chapters, 20 nodes, and 10 scene documents while separately flagging any canonical chapter or manuscript-node write before acceptance.
- Proposal-write receipts are read and cross-checked against staged chapter and scene counts.
- Added hard semantic flags from final proposals and reviewer artifacts for unresolved duplicate character names (unless every duplicate has explicit identity disambiguation), `evidence_missing`, Chinese-project English tags, invalid relationship ontology labels, reviewer branch-density failures, world contamination, and usage-ledger missing/exhausted/over-cap states.
- Budget checks only use values declared by the authoritative ledger; no competing diagnostics threshold was introduced.

## Verification

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_diagnostics.py tests/test_w1_import_artifact_quality.py
# 8 passed in 0.05s

sidecar/.venv/bin/python -m py_compile tools/w1_import_diagnostics.py
git diff --check -- tools/w1_import_diagnostics.py tests/test_w1_import_diagnostics.py tests/test_w1_import_artifact_quality.py
# passed
```

Offline inspection of `/tmp/narrative_ide_w1_live_smoke/20260713_013817/project`, run `sup_51096b2887`, exits `1` under `--fail-on-threshold` for real quality findings: duplicate canonical character names, unresolved `evidence_missing`, and reviewer branch density. Its staged projection and receipts pass: 10 chapters, 20 nodes, 10 scene documents; canonical manuscript remains empty before acceptance.
