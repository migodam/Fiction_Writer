# Reviewer P1 #2/#3: Graph Transactions and World Container Integrity

## Scope
- Touched only the assigned UI/store/E2E surfaces and this development log.
- Did not modify `projectService`, Electron, or backend files.

## Changes
- Made `updateGraphNode` transaction-aware so a graph drag does not capture an independent undo snapshot while a drag transaction is pending.
- Kept the existing GraphBoardFlow drag start/stop transaction wiring and added direct-store plus real React Flow drag coverage.
- Made `deleteWorldContainer` recursively remove child folders and their items in one store update.
- Centralized World-item reference cleanup for both item and container deletion: characters, timeline locations/links, scenes, scripts, storyboard shots, graph nodes, marker links, and WorldMap marker IDs are cleaned together.
- Added regression coverage that one undo atomically restores the full deleted folder tree and every cleared reference.

## TDD Evidence
- Initial focused run failed as expected before the fix:
  - pending graph transaction had `undoDepth: 1` instead of `0`.
  - container deletion left a child folder, child item, and dangling references.
- Final focused run passed:
  - `npx playwright test --config tests/playwright.config.ts --retries=0 tests/e2e/p0/graph_crud.spec.ts tests/e2e/p1/context_menu_completeness.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts`
  - Result: 14 passed.

## Verification
- `npm run ui:lint` - passed.
- `npm run ui:build` - passed; Vite emitted the existing chunk-size warning only.
- `git diff --check` - passed.

## Integration Notes
- `src/ui-react/store.ts` is a shared surface. This change is intentionally narrow and reuses one cleanup helper for the existing World-item delete behavior plus the new recursive container delete behavior.
