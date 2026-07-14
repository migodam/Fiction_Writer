# Context Menu Completeness

## Changes
- Added typed `AppCommand` context-menu definitions for character cards, world items, and world folders.
- Added typed clipboard copy/paste for characters and world items; unsupported operations remain disabled with a visible reason.
- Preserved global context-menu keyboard handling, Escape dismissal, and focus restoration for the updated entry points.
- Replaced user-visible World `Categories` and `Add Category` language with Folder/Folders (and Chinese `文件夹` labels) while retaining the existing category data model.

## Files
- `src/ui-react/components/CharactersWorkspace.tsx`
- `src/ui-react/components/WorldWorkspace.tsx`
- `src/ui-react/commands/characterCommands.ts`
- `src/ui-react/commands/worldContextCommands.ts`
- `tests/e2e/p1/context_menu_completeness.spec.ts`

## Verification
- `npm run ui:lint` passed.
- `npm run ui:build` passed (Vite emitted the existing large-chunk warning only).
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/context_menu_completeness.spec.ts` passed: 3 tests.
