# Reviewer P1: Package-External Mutation

## Scope
- `src/ui-react/services/projectService.ts`
- `tests/e2e/p1/workbench_import_package_accept.spec.ts`

## Change
- Removed the global dangling-reference pruning pass from proposal finalization and import package acceptance.
- Package acceptance now preserves package-external canonical records exactly as they were, including legacy dangling references.
- Kept `prepareProjectForImportApply` unchanged, so intentional removal of blank starter chapter, branch, and world-container defaults remains in effect for relevant imports.

## Regression Coverage
- Added an import-package acceptance test with a pre-existing dangling external scene `chapterId` and event `branchId` plus dangling linked-reference arrays.
- The test accepts an unrelated valid package, asserts those two external records are byte-for-byte equivalent as objects, and verifies the package was accepted.

## Verification
- `npm run ui:build` passed.
- Targeted Playwright regression passed:
  `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_import_package_accept.spec.ts --grep "does not rewrite package-external dangling"`
- The full spec was attempted. Its first seven tests passed, then the web test server became unavailable and later tests failed at the page-load boundary. The first affected existing source-evidence test passes when run in isolation, so this did not reproduce as a behavioral failure from this change.
