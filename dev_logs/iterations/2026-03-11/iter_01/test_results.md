# Test Results - Iteration 1

## Commands Run
- `cmd /c npm run test:e2e -- tests/e2e/p0/characters_crud.spec.ts tests/e2e/p1/characters_routes.spec.ts tests/e2e/p0/navigation.spec.ts tests/e2e/p0/timeline_crud_drag.spec.ts tests/e2e/p0/writing_editor.spec.ts`
- `cmd /c npm run test:e2e -- tests/e2e/smoke.spec.ts --grep "app layout is visible|can navigate through activities and see sidebar sections|can search for characters and navigate|can manage relationships"`
- `cmd /c npm run test:e2e -- tests/e2e/smoke.spec.ts --grep "can manage world model containers and items"`
- `cmd /c npm run build`

## Passed
- `tests/e2e/p0/characters_crud.spec.ts`
- `tests/e2e/p1/characters_routes.spec.ts`
- `tests/e2e/p0/navigation.spec.ts`
- `tests/e2e/p0/timeline_crud_drag.spec.ts`
- `tests/e2e/p0/writing_editor.spec.ts`
- Smoke subset:
  - `app layout is visible`
  - `can navigate through activities and see sidebar sections`
  - `can search for characters and navigate`
  - `can manage relationships`

## Failed
- `tests/e2e/smoke.spec.ts` - `can manage world model containers and items`

## Failure Notes
- World Model failure remains reproducible on both initial run and retry.
- Symptom: `world-item-name-input` never appears after `add-world-item-btn`.
- Playwright trace/error context saved under:
  - `test-results/smoke-Narrative-IDE-Smoke--b5cfb--model-containers-and-items-chromium/`
  - `test-results/smoke-Narrative-IDE-Smoke--b5cfb--model-containers-and-items-chromium-retry1/`

## Result Summary
- Characters iteration target: passed.
- P0 regression check for navigation, character create, timeline create, and writing autosave: passed.
- Production build: passed.
- Non-Characters blocker deferred with fresh evidence: World item creation path still broken.
