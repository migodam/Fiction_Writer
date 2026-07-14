# A2 Workbench Proposal Gate

## Changes
- Removed the reachable Workbench-local import path that directly created canonical chapters and scenes.
- Routed every W1 import, including singleton imports, through a package card and atomic package transaction.
- Consumed the W1 `stagedManuscriptProjection` artifact only inside package acceptance, applying staged scene documents and manuscript nodes atomically with the proposal operations.
- Replaced the global acceptance control with accept/reject actions scoped to the current package.
- Kept package rollback, exact blocking-edge display, and retry behavior on the package card.

## Files Modified
- `src/ui-react/components/WorkbenchWorkspace.tsx`
- `src/ui-react/services/projectService.ts`
- `tests/e2e/p1/workbench_import_package_accept.spec.ts`
- `tests/e2e/p1/import_smoke_acceptance.spec.ts`
- `dev_docs/FRONTEND_BACKEND_CHECKLIST.md`
- `dev_logs/2026-07-11-a2-workbench-proposal-gate.md`

## Tests
- `npm run ui:build` - passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_import_package_accept.spec.ts tests/e2e/p1/workbench_reviewer_repair_package.spec.ts tests/e2e/p1/import_smoke_acceptance.spec.ts` - passed (20/20)
- `npx eslint src/ui-react/components/WorkbenchWorkspace.tsx src/ui-react/services/projectService.ts` - passed
- `npm run ui:lint` - blocked by an existing `no-constant-condition` error in forbidden, untouched `src/ui-react/store.ts:1963`.

## Remaining Risk
- The store still retains a generic `resolveAllProposals` action for non-Workbench callers. The reachable Workbench UI no longer exposes it; removing the shared-store action is outside this task's ownership.

## F2 Projection Safety Follow-up

### Changes
- Added a no-mutation package-operation dry run before staged projection or canonical draft application, so duplicate/conflicting operations and all reference edges block the whole package before acceptance work begins.
- Bound staged projection acceptance to one package `importRunId`, its exact `system/imports/<run>/` path, and the run `manifest.json` source hash.
- Added realpath checks for the run directory, projection, and manifest. Any symlink resolution, unavailable realpath support, or escape outside the expected run blocks acceptance.
- Required exact artifact chapter/scene descriptor agreement with the accepted package and rejected targets that already exist in canonical chapters or scenes.

### Tests
- `npx eslint src/ui-react/services/projectService.ts tests/e2e/p1/workbench_import_package_accept.spec.ts` - passed
- `npm run ui:build` - passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_import_package_accept.spec.ts` - passed (11/11)

### Follow-up Verification
- Added direct manifest/source-span hash mismatch coverage.
- Added preflight checks for scene-document and manuscript-node references.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_import_package_accept.spec.ts` - passed (12/12)
