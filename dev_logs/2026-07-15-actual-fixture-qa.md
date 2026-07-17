# Actual Fixture QA - 2026-07-15

## Scope
- Updated `tests/electron/w1_actual_fixture_recovery.mjs` for the explicit Repair -> Accept contract and the `repair-blocked-package-*` selector.
- Kept the `electron:w1-actual-fixture` npm script in `package.json`.
- The harness uses disposable copies and fresh user data, strips credential-like environment variables, starts real Vite/Electron/sidecar processes, and never mutates backup/original fixtures.

## Harness Contract
- Wait for Repair or Accept.
- When blocked, click Repair and assert 89 pending, 0 accepted, no canonical count changes, no history, no block reasons, and an explicit Accept action.
- If Repair remains visible, repeat it and assert state, artifact hash, and migration transaction are idempotent.
- Click explicit Accept and assert 89 accepted / 0 pending, exact canonical counts, source spans/hashes, committed migration receipt, screenshot, and restart persistence.
- Independently start the real sidecar and assert Recovery Center discovers 4/10 with the expected legacy attempt identity, compatible source, and zero resume events/API credentials.
- Aggregate independent stage failures and retain `/tmp` screenshots/state/failure artifacts.

## Execution
```text
npm run electron:w1-actual-fixture
```

Result: **PASS** after the production fixes.

### Package Result

- Repair migrated the legacy projection contract while leaving `89` proposals pending and `0` accepted.
- The explicit Accept action then committed exactly `89` proposals with no pending remainder.
- Canonical counts matched the fixture contract: `20` characters, `5` tags, `2` relationships, `10` chapters, `10` scenes, `20` manuscript nodes, `1` timeline branch, `9` timeline events, `7` world containers, and `24` world items.
- Restart persistence reproduced the same counts.

### Recovery Result

- Recovery Center discovered one interrupted Import Text 18 attempt.
- Progress was exactly `4/10`; the source hash remained compatible and the remaining work was `6` chunks.
- No unknown API calls were present and the harness did not resume the paid task.

### Lifecycle Result

All three real Electron sessions closed cleanly after draining streams, sidecars,
and databases. No forced cleanup was required by the successful run.

## Artifacts
- Accepted-state screenshot: `/tmp/narrative-ide-w1-actual-fixture-1784093945827/accepted-package.png`
- Migration receipt: `/tmp/narrative-ide-w1-actual-fixture-1784093945827/migration-receipt.json`
- Recovery result: `/tmp/narrative-ide-w1-actual-fixture-1784093945827/recovery-result.json`
- Aggregate result: `/tmp/narrative-ide-w1-actual-fixture-1784093945827/result.json`
