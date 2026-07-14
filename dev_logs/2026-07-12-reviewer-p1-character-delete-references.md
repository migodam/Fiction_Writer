# Reviewer P1: Character Hard-Delete Reference Integrity

## Scope
- Touched only `src/ui-react/store.ts`, `tests/e2e/p1/context_menu_completeness.spec.ts`, and this log.
- Did not modify the Character commands/modal, model, service, Electron, or backend surfaces.

## Changes
- Added one store-level character reference cleanup path used by both `deleteCharacter` and confirmed `hardDeleteCharacter`.
- The cleanup atomically removes the deleted character and its relationships, and clears references from timeline participants, scene links and POV, World items, character tags, graph character nodes, scripts, and storyboard shots.
- Graph cleanup recognizes both explicit `linkedEntityType: 'character'` nodes and legacy `character_ref` nodes without an explicit entity type.
- Reused the existing structured snapshot contract so one hard delete produces one Undo entry and Undo restores every entity and reference together.

## TDD Evidence
- Initial focused Playwright run failed as expected: `hardDeleteCharacter` returned early when it found references, leaving the character and every reference unchanged with no Undo entry.
- Added a focused regression that seeds relationships, timeline, scene POV/link, World, tag, graph, script, and storyboard references; it asserts cleanup and complete one-step Undo restoration.

## Verification
- `npx playwright test --config tests/playwright.config.ts --retries=0 tests/e2e/p1/context_menu_completeness.spec.ts` - passed: 7 tests.
- `npm run ui:lint` - passed.
- `npm run ui:build` - passed; Vite emitted the existing chunk-size warning only.
- `git diff --check` - passed.

## Integration Note
- Archive remains the default UI lifecycle behavior. The store hard-delete path is now reference-safe when invoked after the existing confirmation flow; modal impact-list presentation remains outside this assigned write scope.
