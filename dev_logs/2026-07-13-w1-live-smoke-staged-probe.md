# W1 Live Smoke Staged Probe - 2026-07-13

## Scope

- Owned paths: `tools/w1_live_smoke_10ch.py`, `tests/test_w1_live_smoke_runner.py`, and this log.
- No sidecar, UI, Electron, provider configuration, or canonical project storage behavior was changed.
- No provider call was made.

## Changes

- Split probe counts into canonical manuscript state and staged proposal projection state.
- Treat `acceptance_required: true` as a positive safety gate: canonical chapters and manuscript nodes must remain zero until proposal acceptance, while the staged projection must contain 10 chapters, 20 nodes, and 10 scene documents.
- Require proposal-write receipts for exactly 10 chapter and 10 scene proposals.
- Verify `raw_source.txt` against the manifest SHA-256, then validate manifest and staged source spans against the preserved raw source.
- Keep required import artifacts strict and require a complete provider-reported token/call/cost ledger. Estimated prompt-window tokens and zero-cost reviewer metadata are not substituted for provider usage.

## Offline Regression

- Artifact: `/tmp/narrative_ide_w1_live_smoke/20260713_010237`.
- Confirmed staged projection: `acceptance_required=true`, 10 chapters, 20 nodes, 10 scene documents; canonical manuscript remained unwritten.
- Confirmed proposal receipts: 10 chapter and 10 scene proposals.
- Confirmed raw-source SHA-256 and all manifest/staged source spans.
- The historical artifact is intentionally rejected with exit code 1: it is missing required `evidence_cards.json` and `cross_validation.json`, and has no complete provider token/call/cost ledger. The updated gate reports `missing_required_artifacts` and `usage_ledger_missing` instead of fabricating zero usage.

## Tests

- `sidecar/.venv/bin/python -m py_compile tools/w1_live_smoke_10ch.py` - passed.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_live_smoke_runner.py` - 14 passed.
- Offline probe against `/tmp/narrative_ide_w1_live_smoke/20260713_010237/project` - expected exit 1 only for missing required artifacts and missing provider usage ledger; staged/canonical, receipts, and source-evidence checks passed.
- `git diff --check` - passed.
