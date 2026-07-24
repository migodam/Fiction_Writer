# World Model/Harness Semantic Review Log

Date: 2026-07-25

## Changes recorded

- Documented stable `folderId` ownership for the Notebook/Folder/Item World tree.
- Documented candidate ledger, semantic review, organizer relocation, and proposal-gate flow.
- Recorded accepted-project reconcile results and the normalized Agent execution surface.
- Verified and committed concrete timeline deep-link focus; deterministic Electron runtime smoke passed.
- Re-reviewed the pending `Import Text 18` package without provider calls: 108 proposals retained,
  20 rerouted/backfilled, 8 held, 0 graph diagnostics, and 0 dropped references.
- Added crash-recoverable two-file staging transactions and blocked direct single-proposal
  acceptance for every package-scoped proposal.
- Fixed blank-template chapter cleanup using the actual generated default values.

## Accepted-project evidence

- Baseline: 1 semantic error and 19 linkage warnings.
- Offline reconcile result: 0 errors and 0 warnings.
- Repairs: 9 event-scene links, 13 event-world links, 7 scene-world inverse links.
- Classification: 10 high-confidence reclassifications; 2 quarantined candidates.
- The reconcile tool is dry-run by default and does not call an external API.

## Documentation evidence

- Open-source Harness research: `communication/2026-07-25-agent-harness-open-source-architecture-research.md`.
- Semantic audit: `tools/w1_semantic_quality_audit.py`.
- Accepted-project reconcile: `tools/w1_reconcile_accepted_semantics.py`.

## Verification boundary

## Test evidence

- Active W1/runtime pytest: `817 passed`.
- Full repository pytest: `842 passed`; `11 failed + 7 errors` belong to reference-only V2/V3
  `src/core` tests and missing `tests/api_key.txt`.
- UI lint/build: passed.
- Full P0/P1 Playwright: `276 passed`; timeline gesture stability repeated 5 times (`15 passed`).
- Focused package/relocation/writing Playwright: `39 passed`.
- Electron actual-fixture: passed in 17.6 seconds, including 89-proposal package repair/accept,
  restart persistence, interrupted-run discovery, durable event inspection, screenshot, and receipt.
- Electron runtime smoke: passed in 7.1 seconds after the sandbox-only `listen EPERM` was rerun with
  local loopback permission.
- Actual browser: 1280px World detail and centered event focus verified.

The 8 held candidates remain pending by design and require a human semantic decision.
