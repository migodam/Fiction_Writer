# Reviewer P1: Undo and World Reference Integrity

## Scope
- Owned changes: global structured-data undo shortcut ownership, World item context commands, World delete/move store behavior, and focused P1 E2E coverage.
- Explicitly untouched: `src/ui-react/services/projectService.ts`, Electron runtime files, and existing parallel changes outside the assigned paths.

## Changes
- Made `useCommandShortcuts` the sole Cmd/Ctrl+Z owner in the always-mounted Command Palette and removed the legacy duplicate listener.
- Changed World cut/paste to move the original item for cut operations, retaining its stable ID and committing one undo entry.
- Added a single-action World move path and made World delete atomically remove World-item references from characters, timeline events, scenes, World markers, scripts, storyboards, and graph nodes.
- Added regression coverage for one-key/one-undo behavior, cut/paste identity and references, delete cleanup plus one-step restoration, and drag/move transaction depth.

## Verification
- `npm run ui:lint` - passed.
- `npm run ui:build` - passed; existing Vite chunk-size warning only.
- `npx playwright test --config tests/playwright.config.ts --retries=0 tests/e2e/p1/global_undo.spec.ts tests/e2e/p1/context_menu_completeness.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts` - passed: 13 tests.
- `git diff --check` - passed.

## Integration Note
- Lead integration moved shortcut ownership out of `ContextMenu` and removed the legacy Command Palette undo branch, leaving one structural listener rather than relying on propagation order.
