# Package Accept Tombstone Recovery

## Changes
- Made project transaction operations explicit: a target either provides a string postimage or an explicit `delete: true` tombstone.
- Upgraded prepared transaction manifests to record each target's `write` or `delete` intent alongside staged, hashed preimages.
- Added non-recursive stale-file tombstones during package acceptance for only `writing/chapters/*.json` and `writing/scenes/*.{md,meta.json}` files absent from the accepted canonical snapshot.
- Kept all other namespaces and filename extensions untouched.

## Verification
- `npx playwright test tests/e2e/p1/project_transaction_recovery.spec.ts tests/e2e/p1/workbench_import_package_accept.spec.ts --config tests/playwright.config.ts` - 33 passed.
- `npm run ui:build` - passed.
- `npm run ui:lint` - passed.

## Coverage
- Tombstone recovery before, during, and after a crash; rollback and repeated recovery; unrelated-file preservation.
- Package acceptance removes stale blank starter chapter/scene files and both scene file pairs while preserving an unrelated file.
