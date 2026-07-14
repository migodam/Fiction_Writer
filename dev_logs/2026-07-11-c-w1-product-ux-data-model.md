# W1 Product UX and Data Model - Worker C

## Scope
- Added the W1 import run entry with file, model/profile, stage, token budget, cancel visibility, errors, and retry/reset recovery.
- Added manuscript outline save-state feedback and made chapter/scene outline nodes visibly distinct from full body editing.
- Added typed character experience evidence and ordered flexible custom attributes to the project model and character editor.
- Added stable parent-ID notebook/folder projection in the World workspace while retaining legacy category compatibility.

## Verification
- `npm run ui:build` passed.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/w1_product_projections.spec.ts` passed (4/4); it uses injected local state only and makes no external API calls.
- Existing import preset regression: `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_workflow_presets.spec.ts` passed (9/9).

## Concurrent Work
- Preserved all pre-existing A/B changes, including `WorkbenchWorkspace.tsx`, `projectService.ts`, and sidecar files.
