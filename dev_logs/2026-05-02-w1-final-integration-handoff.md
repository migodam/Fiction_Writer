# W1 Import + Timeline Final Integration Handoff

Date: 2026-05-02
Branch: `codex/w1-import-timeline-integration`

## Integrated Branches

1. `codex/w1-import-diagnostics`
2. `codex/w1-context-windowing`
3. `codex/w1-prompt-crossvalidate`
4. `codex/w1-timeline-topology-v2`
5. `codex/timeline-layout-engine-v2`
6. `codex/timeline-interaction-v2`
7. `codex/w1-deepseek-v4-pro-validation`

## Final Verification

- W1 sidecar targeted tests: `18 passed`.
- Python compile: `sidecar/workflows/w1_import.py` passed.
- UI lint: passed.
- UI build: passed.
- Timeline dense layout fixture: `121 events, 1 clusters`.
- Chrome fallback Playwright navigation smoke: `1 passed`.
- Chrome fallback Playwright timeline interaction smoke: `3 passed`.

## DeepSeek V4 Pro Validation

- Full 50-chapter Import_Test6 copy completed with `deepseek-v4-pro`.
- Runtime: `7595.6s`.
- Chunks: `50/50`.
- Final errors: `[]`.
- Proposal count: `430`.
- Validation project: `/Volumes/migodam's-external-brain/home/narrative_ide/Import_Test6_W1V2_Validation_20260502_145524`.
- Original Import_Test6 project was not modified.

## Quality Outcome

Timeline improved from the old baseline:

- Canonical events: `132 -> 51`.
- Duplicate event clusters: `14 -> 0`.
- Branch over-budget failures: `branch_main=77`, `branch_import_conflict=32` -> none.
- Mainline density: `77 -> 24`.

Character-card compaction required one validation follow-up:

- Pre-fix generated character proposal outliers: `3`.
- Post-fix compaction simulation on actual proposals: `0`.
- The fix is now integrated into the reducer and proposal write path.

## Known Notes

- Official managed Playwright Chromium was missing and `npx playwright install chromium` repeatedly timed out while downloading the 162MB archive. Smoke validation used installed system Google Chrome through a temporary config, which was deleted afterward.
- Broad `npm run sidecar:test` remains a poor W1 gate because legacy `src.core.persistence.ProjectMemory` tests are already red from unrelated API drift. W1-targeted tests are green.
- The validation project still contains pre-compaction proposals because the full live run completed before the reducer guardrail patch. The code path is covered by tests and by applying the compactor to the actual generated proposal data.

## Main Merge Gate

Do not merge this integration branch to `main` until the user reviews:

- `dev_logs/2026-05-02-w3-deepseek-v4-pro-validation.md`
- `dev_logs/2026-05-02-w1-final-integration-handoff.md`
- The validation project artifacts under `system/imports/import_a574e4dbd71f`.
