# D1 Interaction Commands

## Changes
- Added typed `AppCommand`, `CommandContext`, and typed command clipboard primitives.
- Hardened the global context menu with keyboard navigation, disabled reasons, destructive confirmation, viewport clamping, and focus restoration.
- Added copy, cut, and paste commands for manuscript nodes and world items.
- Wrapped world item and graph node drags in one undo transaction; Escape rolls back the world transaction.
- Reactivated graph context-menu regression coverage.

## Verification
- `npm run ui:build` passed.
- Focused Playwright (`graph_crud`, `timeline_undo_transactions`): 13 passed.
- Headed Playwright (`graph_crud`): 3 passed.
- `npm run ui:lint` passed after replacing the literal W1 polling loop condition with a named cancellation predicate; polling cadence and terminal exits are unchanged.
