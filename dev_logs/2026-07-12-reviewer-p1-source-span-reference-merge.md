# Reviewer P1 SourceSpan, Required References, and Merge Enforcement

## Scope

- Owned: `src/ui-react/services/projectService.ts` and `tests/e2e/p1/workbench_import_package_accept.spec.ts`.
- No Electron, store, graph, or sidecar/backend files were changed.
- Concurrent modifications already present in the shared worktree were preserved.

## Changes

- Reconstruct staged-manuscript `SourceSpan` ranges with JavaScript Unicode code points so Python character offsets remain correct for emoji and other non-BMP text.
- Removed first-entity defaults for imported timeline event `branchId`, scene `chapterId`, and world item `containerId`; each missing required reference now blocks package acceptance.
- Enforced `EntityMergeDecision/v1` as the executable character-update allowlist. Payload fields must be declared by the decision, match the approved value, target the canonical ID, and remain consistent with the current canonical field for preserve/union/append/max actions.
- Added Playwright coverage for code-point spans, required references, undeclared merge fields, and stale merge decisions.

## Verification

- PASS: `npm run ui:build`
- PASS: new targeted cases in `npx playwright test tests/e2e/p1/workbench_import_package_accept.spec.ts --retries=0`:
  - missing `branchId` / `chapterId` / `containerId`
  - non-BMP Python SourceSpan reconstruction
  - undeclared and stale `EntityMergeDecision/v1` fields
- The full 19-test spec was attempted with `--retries=0`; 10 passed, including all new cases. The remaining 9 failed only at `page.goto('http://localhost:3000')` with intermittent `ERR_CONNECTION_REFUSED` from the shared local dev server.
- A final exact grep rerun was also blocked before test setup by the same `ERR_CONNECTION_REFUSED`; it did not reach an assertion. The only code change after the passing run restored legacy defaults for non-import proposals and does not alter the covered import paths.
