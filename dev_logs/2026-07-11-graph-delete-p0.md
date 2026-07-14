# Graph Delete P0

## Root Cause
- `GraphBoardFlow` correctly called `deleteGraphNode`, whose store action removes the node, connected edges, and selection state.
- The global context menu intentionally requires a second click for items marked `destructive`; the P0 test only performed the first confirmation click and therefore never executed the delete action.

## Changes
- Kept Graph node deletion destructive and explicitly covered its two-step confirmation contract.
- The test verifies that the first click changes the label to Confirm while preserving the node, then the second click deletes the node and closes the menu.

## Files
- `src/ui-react/components/graph/GraphBoardFlow.tsx`
- `tests/e2e/p0/graph_crud.spec.ts`

## Verification
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p0/graph_crud.spec.ts --retries=0` passed: 3 tests, including Graph node deletion.
- `npm run ui:build` passed. Vite reported the existing large generated chunk warning only.
