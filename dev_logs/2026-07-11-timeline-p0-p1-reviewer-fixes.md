# Timeline P0/P1 Reviewer Fixes

Date: 2026-07-11
Scope: `TimelineWorkspace.tsx`, `components/timeline/**`, Timeline P0/P1 E2E tests, and this log only.

## Changes

- Propagated host endpoint drag deltas through shared event anchors and rendered attached branch endpoints from the same visible event coordinates as their nodes.
- Restored parallel offset rendering for branches that share a host's topology and geometry.
- Made branch context-menu closure ignore clicks inside the menu so Delete reaches the confirmation flow.
- Reworked browser-only E2E assumptions: disk cleanup already lives in `projectService.saveProject`, which the Vite browser runtime cannot access; tests now validate the canonical save payload. Delete-confirmation tests use an empty branch because non-empty branch deletion is intentionally blocked to prevent orphaned events.
- Replaced duplicate text and DOM-order assertions with stable Timeline test selectors. SVG context-menu coverage dispatches `contextmenu` to the hitarea because Playwright treats a horizontal SVG path at the top edge as hidden despite its working event handler.

## Validation

- `npx playwright test --config tests/playwright.config.ts tests/e2e/p0/timeline_canvas.spec.js tests/e2e/p0/timeline_sync.spec.js tests/e2e/p1/timeline_undo_transactions.spec.ts tests/e2e/p1/timeline_sync_roundtrip.spec.ts tests/e2e/p1/timeline_topology_import.spec.ts tests/e2e/p1/timeline_interaction.spec.ts --workers=1 --retries=0 --reporter=list` - passed (53 tests).
- `npm run ui:lint` - passed.
- `npm run ui:build` - passed.

## Notes

- No shared store, service, Electron, or other shared-surface files were modified.
- No commit created.
